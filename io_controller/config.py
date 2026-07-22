#!/usr/bin/env python3
# config.py

PINS = [
    {'phys': 1, 'bcm': None, 'name': '3.3V', 'type': 'power'},
    {'phys': 2, 'bcm': None, 'name': '5V', 'type': 'power'},
    {'phys': 3, 'bcm': 2, 'name': 'GPIO2 / I2C SDA', 'type': 'gpio', 'notes': 'I2C SDA'},
    {'phys': 4, 'bcm': None, 'name': '5V', 'type': 'power'},
    {'phys': 5, 'bcm': 3, 'name': 'GPIO3 / I2C SCL', 'type': 'gpio', 'notes': 'I2C SCL'},
    {'phys': 6, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 7, 'bcm': 4, 'name': 'GPIO4', 'type': 'gpio'},
    {'phys': 8, 'bcm': 14, 'name': 'GPIO14 / UART TX', 'type': 'gpio', 'notes': 'UART TX'},
    {'phys': 9, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 10, 'bcm': 15, 'name': 'GPIO15 / UART RX', 'type': 'gpio', 'notes': 'UART RX'},
    {'phys': 11, 'bcm': 17, 'name': 'GPIO17', 'type': 'gpio'},
    {'phys': 12, 'bcm': 18, 'name': 'GPIO18 / PCM CLK / PWM0', 'type': 'gpio', 'supports_pwm': True},
    {'phys': 13, 'bcm': 27, 'name': 'GPIO27', 'type': 'gpio'},
    {'phys': 14, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 15, 'bcm': 22, 'name': 'GPIO22', 'type': 'gpio'},
    {'phys': 16, 'bcm': 23, 'name': 'GPIO23', 'type': 'gpio'},
    {'phys': 17, 'bcm': None, 'name': '3.3V', 'type': 'power'},
    {'phys': 18, 'bcm': 24, 'name': 'GPIO24', 'type': 'gpio'},
    {'phys': 19, 'bcm': 10, 'name': 'GPIO10 / SPI MOSI', 'type': 'gpio', 'notes': 'SPI MOSI'},
    {'phys': 20, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 21, 'bcm': 9, 'name': 'GPIO9 / SPI MISO', 'type': 'gpio', 'notes': 'SPI MISO'},
    {'phys': 22, 'bcm': 25, 'name': 'GPIO25', 'type': 'gpio'},
    {'phys': 23, 'bcm': 11, 'name': 'GPIO11 / SPI SCLK', 'type': 'gpio', 'notes': 'SPI SCLK'},
    {'phys': 24, 'bcm': 8, 'name': 'GPIO8 / SPI CE0', 'type': 'gpio', 'notes': 'SPI CE0'},
    {'phys': 25, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 26, 'bcm': 7, 'name': 'GPIO7 / SPI CE1', 'type': 'gpio', 'notes': 'SPI CE1'},
    {'phys': 27, 'bcm': 0, 'name': 'EEPROM SDA', 'type': 'gpio', 'notes': 'EEPROM SDA'},
    {'phys': 28, 'bcm': 1, 'name': 'EEPROM SCL', 'type': 'gpio', 'notes': 'EEPROM SCL'},
    {'phys': 29, 'bcm': 5, 'name': 'GPIO5', 'type': 'gpio'},
    {'phys': 30, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 31, 'bcm': 6, 'name': 'GPIO6', 'type': 'gpio'},
    {'phys': 32, 'bcm': 12, 'name': 'GPIO12 / PWM0', 'type': 'gpio', 'supports_pwm': True},
    {'phys': 33, 'bcm': 13, 'name': 'GPIO13 / PWM1', 'type': 'gpio', 'supports_pwm': True},
    {'phys': 34, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 35, 'bcm': 19, 'name': 'GPIO19 / PCM FS / PWM1', 'type': 'gpio', 'supports_pwm': True},
    {'phys': 36, 'bcm': 16, 'name': 'GPIO16', 'type': 'gpio'},
    {'phys': 37, 'bcm': 26, 'name': 'GPIO26', 'type': 'gpio'},
    {'phys': 38, 'bcm': 20, 'name': 'GPIO20 / PCM DIN', 'type': 'gpio', 'notes': 'PCM DIN'},
    {'phys': 39, 'bcm': None, 'name': 'GND', 'type': 'ground'},
    {'phys': 40, 'bcm': 21, 'name': 'GPIO21 / PCM DOUT', 'type': 'gpio', 'notes': 'PCM DOUT'},
]

PWM_PINS = [pin['bcm'] for pin in PINS if pin.get('supports_pwm')]


# --- TCA6424A I/O expander (on I2C1) ---------------------------------------
# 24-bit I/O expander. ADDR pin is tied to EXT_3V3 in the schematic, so the
# I2C address is 0x23 (it would be 0x22 if ADDR were tied to GND).
TCA6424A_ADDR = 0x23
TCA6424A_ALT_ADDR = 0x22

# Connection map transcribed from the "IO EXPANDER CIRCUIT" schematic.
# port/bit give the TCA6424A register location (port 0 = P0x, 1 = P1x, 2 = P2x).
# NOTE: read from the schematic image - verify the net names against your board
# and edit here if any are wrong or missing.
TCA6424A_MAP = [
    # Port 0
    {'pin': 'P00', 'port': 0, 'bit': 0, 'net': ''},
    {'pin': 'P01', 'port': 0, 'bit': 1, 'net': 'NFC_RESET'},
    {'pin': 'P02', 'port': 0, 'bit': 2, 'net': ''},
    {'pin': 'P03', 'port': 0, 'bit': 3, 'net': ''},
    {'pin': 'P04', 'port': 0, 'bit': 4, 'net': ''},
    {'pin': 'P05', 'port': 0, 'bit': 5, 'net': 'LED_SWITCH'},
    {'pin': 'P06', 'port': 0, 'bit': 6, 'net': ''},
    {'pin': 'P07', 'port': 0, 'bit': 7, 'net': ''},
    # Port 1
    {'pin': 'P10', 'port': 1, 'bit': 0, 'net': ''},
    {'pin': 'P11', 'port': 1, 'bit': 1, 'net': 'FAN1_ONOFF'},
    {'pin': 'P12', 'port': 1, 'bit': 2, 'net': 'FAN2_ONOFF'},
    {'pin': 'P13', 'port': 1, 'bit': 3, 'net': 'FAN3_ONOFF'},
    {'pin': 'P14', 'port': 1, 'bit': 4, 'net': 'FAN4_ONOFF'},
    {'pin': 'P15', 'port': 1, 'bit': 5, 'net': 'FAN5_ONOFF'},
    {'pin': 'P16', 'port': 1, 'bit': 6, 'net': 'FAN6_ONOFF'},
    {'pin': 'P17', 'port': 1, 'bit': 7, 'net': ''},
    # Port 2
    {'pin': 'P20', 'port': 2, 'bit': 0, 'net': ''},
    {'pin': 'P21', 'port': 2, 'bit': 1, 'net': 'MOT2_IN2'},
    {'pin': 'P22', 'port': 2, 'bit': 2, 'net': 'MOT2_IN1'},
    {'pin': 'P23', 'port': 2, 'bit': 3, 'net': ''},
    {'pin': 'P24', 'port': 2, 'bit': 4, 'net': 'MOT1_IN2'},
    {'pin': 'P25', 'port': 2, 'bit': 5, 'net': 'MOT1_IN1'},
    {'pin': 'P26', 'port': 2, 'bit': 6, 'net': 'VALVE_2_ON'},
    {'pin': 'P27', 'port': 2, 'bit': 7, 'net': 'VALVE_1_ON'},
]
