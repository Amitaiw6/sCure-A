#!/usr/bin/env python3
# gpio_manager.py

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False

try:
    from smbus2 import SMBus
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False

I2C_KNOWN_DEVICES = {
    0x20: 'MCP23017 / PCF8574',
    0x27: 'PCF8574 / LCD expander',
    0x3C: 'SSD1306 OLED',
    0x68: 'RTC DS1307/DS3231 / MPU-6050',
    0x76: 'BMP280 / BME280',
    0x77: 'BMP280 / BME280',
    0x40: 'SHT31 / Si7021',
    0x50: 'EEPROM',
    0x53: 'ADXL345 / TSL2561',
    0x22: 'TCA6424A I/O expander',
    0x23: 'TCA6424A I/O expander',
}


# BCM numbers of the I2C bus pins: I2C0 = GPIO0/GPIO1, I2C1 = GPIO2/GPIO3.
# ALT3 ("a3") is the I2C alternate function for these pins.
I2C_ALT3_PINS = [0, 1, 2, 3]


def set_i2c_pins_alt3(pins=None):
    """Force the I2C pins into ALT3 via `pinctrl set <pin> a3`.

    Returns a list of (pin, ok, message). A no-op off-Pi (pinctrl missing).
    """
    import subprocess
    if pins is None:
        pins = I2C_ALT3_PINS
    results = []
    for pin in pins:
        try:
            proc = subprocess.run(
                ['pinctrl', 'set', str(pin), 'a3'],
                capture_output=True, text=True, timeout=5,
            )
            ok = proc.returncode == 0
            msg = (proc.stderr or proc.stdout).strip() or 'a3'
        except FileNotFoundError:
            ok, msg = False, 'pinctrl not found'
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        results.append((pin, ok, msg))
    return results


def get_pin_function(pin):
    """Return the `pinctrl get <pin>` line, or None if pinctrl is unavailable."""
    import subprocess
    try:
        proc = subprocess.run(['pinctrl', 'get', str(pin)],
                              capture_output=True, text=True, timeout=5)
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception:
        return None


def available_i2c_buses():
    """List the I2C bus numbers exposed by the kernel (/dev/i2c-*)."""
    import glob
    buses = []
    for path in sorted(glob.glob('/dev/i2c-*')):
        tail = path.rsplit('-', 1)[-1]
        if tail.isdigit():
            buses.append(int(tail))
    return buses


def probe_i2c_address(address, bus_number=1):
    """Try a single read from `address`. Returns (ok: bool, message: str)."""
    if not SMBUS_AVAILABLE:
        return False, 'smbus2 not installed'
    try:
        with SMBus(bus_number) as bus:
            bus.read_byte(address)
        return True, 'OK'
    except FileNotFoundError:
        return False, f'/dev/i2c-{bus_number} not found (bus not enabled)'
    except Exception as e:
        return False, str(e)


def scan_i2c_bus(bus_number=1):
    # Opening the bus is allowed to raise (e.g. "/dev/i2c-N missing" when I2C is
    # not enabled) so the caller can show the real reason. Per-address probe
    # errors are expected (no device there) and are ignored.
    devices = []
    if not SMBUS_AVAILABLE:
        return devices
    with SMBus(bus_number) as bus:
        for address in range(0x03, 0x78):
            try:
                bus.read_byte(address)
                devices.append(address)
            except Exception:
                continue
    return devices


# --- TCA6424A I/O expander register access ---------------------------------
# Per the datasheet: input ports 0x00-0x02, output ports 0x04-0x06,
# configuration (direction) ports 0x0C-0x0E (1 = input, 0 = output).
# Setting bit 7 of the command byte auto-increments the register pointer.
_TCA_OUTPUT_REGS = (0x04, 0x05, 0x06)
_TCA_CONFIG_REGS = (0x0C, 0x0D, 0x0E)


def tca6424a_read_inputs(address, bus_number=1):
    """Return [port0, port1, port2] input byte values, or None if unavailable."""
    if not SMBUS_AVAILABLE:
        return None
    try:
        with SMBus(bus_number) as bus:
            return bus.read_i2c_block_data(address, 0x80 | 0x00, 3)
    except Exception:
        return None


def tca6424a_set_output(address, port, bit, value, bus_number=1):
    """Configure one TCA6424A pin as an output and drive it high/low.

    Returns True on success, False if smbus2 is unavailable. Raises on I2C error.
    """
    if not SMBUS_AVAILABLE:
        return False
    with SMBus(bus_number) as bus:
        # Direction register: clear the bit to make the pin an output.
        cfg = bus.read_byte_data(address, _TCA_CONFIG_REGS[port])
        cfg &= ~(1 << bit)
        bus.write_byte_data(address, _TCA_CONFIG_REGS[port], cfg)
        # Output register: set/clear the bit to drive high/low.
        out = bus.read_byte_data(address, _TCA_OUTPUT_REGS[port])
        if value:
            out |= (1 << bit)
        else:
            out &= ~(1 << bit)
        bus.write_byte_data(address, _TCA_OUTPUT_REGS[port], out)
    return True


class GpioManager:
    def __init__(self):
        self.available = GPIO_AVAILABLE
        self.pwm_channels = {}
        self.pin_modes = {}
        self.pin_pulls = {}
        import threading
        self._lock = threading.Lock()

        if self.available:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

    def _setup_input(self, bcm_pin, pull):
        if not self.available or bcm_pin is None:
            return
        if self.pin_modes.get(bcm_pin) != 'IN' or self.pin_pulls.get(bcm_pin) != pull:
            pull_map = {
                'up': GPIO.PUD_UP,
                'down': GPIO.PUD_DOWN,
                'off': GPIO.PUD_OFF,
            }
            pud = pull_map.get(pull, GPIO.PUD_DOWN)
            GPIO.setup(bcm_pin, GPIO.IN, pull_up_down=pud)
            self.pin_modes[bcm_pin] = 'IN'
            self.pin_pulls[bcm_pin] = pull

    def _setup_output(self, bcm_pin):
        if not self.available or bcm_pin is None:
            return
        if self.pin_modes.get(bcm_pin) != 'OUT':
            GPIO.setup(bcm_pin, GPIO.OUT)
            self.pin_modes[bcm_pin] = 'OUT'
            self.pin_pulls.pop(bcm_pin, None)

    def set_mode(self, bcm_pin, mode, pull='down'):
        if bcm_pin is None:
            raise ValueError('Cannot set mode on a non-GPIO pin')
        normalized = mode.upper()
        with self._lock:
            if not self.available:
                self.pin_modes[bcm_pin] = normalized
                self.pin_pulls[bcm_pin] = pull
                return

            if normalized == 'IN':
                self._setup_input(bcm_pin, pull.lower())
            elif normalized == 'OUT':
                self._setup_output(bcm_pin)
            else:
                raise ValueError('Mode must be IN or OUT')

    def get_mode(self, bcm_pin):
        if bcm_pin is None:
            return None
        with self._lock:
            return self.pin_modes.get(bcm_pin, 'IN')

    def get_pull(self, bcm_pin):
        if bcm_pin is None:
            return None
        with self._lock:
            return self.pin_pulls.get(bcm_pin, 'down')

    def read_pin(self, bcm_pin):
        if bcm_pin is None:
            raise ValueError('Cannot read a non-GPIO pin')
        with self._lock:
            if not self.available:
                return 0
            if self.pin_modes.get(bcm_pin) != 'OUT':
                self._setup_input(bcm_pin, self.pin_pulls.get(bcm_pin, 'down'))
            return GPIO.input(bcm_pin)

    def write_pin(self, bcm_pin, value):
        if bcm_pin is None:
            raise ValueError('Cannot write a non-GPIO pin')
        with self._lock:
            if not self.available:
                return
            self._setup_output(bcm_pin)
            GPIO.output(bcm_pin, GPIO.HIGH if value else GPIO.LOW)

    def set_pwm(self, bcm_pin, duty_cycle, frequency=1000):
        if bcm_pin is None:
            raise ValueError('Cannot set PWM on a non-GPIO pin')
        with self._lock:
            if not self.available:
                return
            self._setup_output(bcm_pin)
            pwm = self.pwm_channels.get(bcm_pin)
            if pwm is None:
                pwm = GPIO.PWM(bcm_pin, frequency)
                pwm.start(duty_cycle)
                self.pwm_channels[bcm_pin] = pwm
            else:
                pwm.ChangeFrequency(frequency)
                pwm.ChangeDutyCycle(duty_cycle)

    def stop_pwm(self, bcm_pin):
        if bcm_pin is None:
            return
        with self._lock:
            if not self.available:
                return
            pwm = self.pwm_channels.pop(bcm_pin, None)
        if pwm:
            pwm.stop()

    def cleanup(self):
        with self._lock:
            if not self.available:
                return
            for pwm in self.pwm_channels.values():
                pwm.stop()
            self.pwm_channels.clear()
            GPIO.cleanup()
