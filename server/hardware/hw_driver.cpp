/**
 * sCure Hardware Driver (C++)
 * Low-level hardware control for Raspberry Pi CM5
 *
 * Compile as Python extension:
 *   g++ -O2 -shared -fPIC -o hw_driver.so hw_driver.cpp \
 *       $(python3 -m pybind11 --includes) \
 *       -lgpiod -lpthread
 *
 * Or compile as standalone:
 *   g++ -O2 -o hw_driver hw_driver.cpp -lgpiod -lpthread
 *
 * Dependencies:
 *   sudo apt install libgpiod-dev python3-pybind11
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <unistd.h>
#include <fcntl.h>
#include <thread>
#include <atomic>
#include <mutex>

// GPIO chip for CM5
#define GPIO_CHIP "/dev/gpiochip0"

// Pin assignments (BCM numbering - adjust to your PCB)
#define PIN_HEATER      17   // Heater relay
#define PIN_COOLER      27   // Cooling fan relay
#define PIN_UV_LED      22   // UV LED enable
#define PIN_UV_PWM      18   // UV LED PWM (hardware PWM)
#define PIN_DOOR_LOCK   23   // Door lock solenoid
#define PIN_DOOR_SENSOR 24   // Door closed sensor (input)
#define PIN_DAMPER      25   // Damper actuator
#define PIN_FAN_LED     12   // LED cooling fan PWM
#define PIN_FAN_INTAKE  13   // Chamber intake fan PWM
#define PIN_FAN_HEAT    19   // Chamber heating fan PWM
#define PIN_FAN_TACH    26   // Fan tachometer (input)
#define PIN_TEMP_CS     8    // Temperature sensor SPI CS

// I2C address for temperature sensor (e.g., MAX31855 or similar)
#define TEMP_SENSOR_ADDR 0x48

namespace scure {

// ============================================================
// Hardware State
// ============================================================

struct HardwareState {
    float chamber_temp = 24.0f;
    float target_temp = 0.0f;
    bool door_closed = true;
    bool heating = false;
    bool cooling = false;
    bool uv_on = false;
    int uv_intensity = 0;      // 0-100%
    bool damper_open = false;
    int fan_led = 0;           // 0-100%
    int fan_intake = 0;        // 0-100%
    int fan_heating = 0;       // 0-100%
};

static HardwareState g_state;
static std::mutex g_mutex;
static std::atomic<bool> g_running{false};

// ============================================================
// Low-level GPIO (using sysfs for simplicity, use libgpiod in production)
// ============================================================

static int gpio_export(int pin) {
    char buf[64];
    int fd = open("/sys/class/gpio/export", O_WRONLY);
    if (fd < 0) return -1;
    int len = snprintf(buf, sizeof(buf), "%d", pin);
    write(fd, buf, len);
    close(fd);
    usleep(100000); // wait for sysfs
    return 0;
}

static int gpio_direction(int pin, const char* dir) {
    char path[128];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/direction", pin);
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    write(fd, dir, strlen(dir));
    close(fd);
    return 0;
}

static int gpio_write(int pin, int value) {
    char path[128];
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", pin);
    int fd = open(path, O_WRONLY);
    if (fd < 0) return -1;
    write(fd, value ? "1" : "0", 1);
    close(fd);
    return 0;
}

static int gpio_read(int pin) {
    char path[128], val;
    snprintf(path, sizeof(path), "/sys/class/gpio/gpio%d/value", pin);
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    read(fd, &val, 1);
    close(fd);
    return val == '1' ? 1 : 0;
}

// ============================================================
// PWM control (using hardware PWM on CM5)
// ============================================================

static void pwm_set(int channel, int duty_percent) {
    // CM5 has 2 PWM channels via /sys/class/pwm/pwmchip0
    char path[128];
    int period = 25000; // 40kHz for fans
    int duty = (duty_percent * period) / 100;

    snprintf(path, sizeof(path), "/sys/class/pwm/pwmchip0/pwm%d/duty_cycle", channel);
    int fd = open(path, O_WRONLY);
    if (fd >= 0) {
        char buf[32];
        int len = snprintf(buf, sizeof(buf), "%d", duty);
        write(fd, buf, len);
        close(fd);
    }
}

// ============================================================
// Temperature reading (SPI thermocouple)
// ============================================================

static float read_temperature() {
    // TODO: Implement SPI read from MAX31855 or similar
    // For now, return simulated value
    std::lock_guard<std::mutex> lock(g_mutex);
    return g_state.chamber_temp;
}

// ============================================================
// Public API (called from Python via pybind11)
// ============================================================

void init() {
    printf("[HW] Initializing GPIO pins for CM5...\n");

    // Export and configure output pins
    int outputs[] = {PIN_HEATER, PIN_COOLER, PIN_UV_LED, PIN_DOOR_LOCK, PIN_DAMPER};
    for (int pin : outputs) {
        gpio_export(pin);
        gpio_direction(pin, "out");
        gpio_write(pin, 0);
    }

    // Export and configure input pins
    int inputs[] = {PIN_DOOR_SENSOR, PIN_FAN_TACH};
    for (int pin : inputs) {
        gpio_export(pin);
        gpio_direction(pin, "in");
    }

    printf("[HW] GPIO initialized\n");
}

void set_heater(bool on) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.heating = on;
    gpio_write(PIN_HEATER, on ? 1 : 0);
}

void set_cooler(bool on) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.cooling = on;
    gpio_write(PIN_COOLER, on ? 1 : 0);
}

void set_uv(bool on, int intensity) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.uv_on = on;
    g_state.uv_intensity = intensity;
    gpio_write(PIN_UV_LED, on ? 1 : 0);
    pwm_set(0, on ? intensity : 0);
}

void open_door() {
    gpio_write(PIN_DOOR_LOCK, 1); // energize solenoid
    usleep(500000);               // hold 500ms
    gpio_write(PIN_DOOR_LOCK, 0);
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.door_closed = false;
}

bool is_door_closed() {
    int val = gpio_read(PIN_DOOR_SENSOR);
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.door_closed = (val == 1);
    return g_state.door_closed;
}

void set_damper(bool open) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.damper_open = open;
    gpio_write(PIN_DAMPER, open ? 1 : 0);
}

void set_fan_speed(const char* fan, int percent) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (strcmp(fan, "led_cooling") == 0) {
        g_state.fan_led = percent;
        pwm_set(0, percent);
    } else if (strcmp(fan, "chamber_intake") == 0) {
        g_state.fan_intake = percent;
        pwm_set(1, percent);
    } else if (strcmp(fan, "chamber_heating") == 0) {
        g_state.fan_heating = percent;
        // Uses software PWM or separate PWM channel
    }
}

void set_target_temperature(float temp) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state.target_temp = temp;
}

// Fan test - measure RPM from tachometer
int run_fan_test() {
    // Count pulses on tachometer pin for 1 second
    int count = 0;
    auto start = std::chrono::steady_clock::now();

    while (std::chrono::steady_clock::now() - start < std::chrono::seconds(1)) {
        int prev = gpio_read(PIN_FAN_TACH);
        usleep(1000);
        int curr = gpio_read(PIN_FAN_TACH);
        if (prev == 0 && curr == 1) count++;
    }

    // Most fans output 2 pulses per revolution
    return count * 30; // RPM
}

} // namespace scure

// ============================================================
// Python bindings (pybind11)
// Uncomment when building as Python extension
// ============================================================

/*
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;

PYBIND11_MODULE(hw_driver, m) {
    m.doc() = "sCure Hardware Driver for RPi CM5";

    m.def("init", &scure::init);
    m.def("set_heater", &scure::set_heater);
    m.def("set_cooler", &scure::set_cooler);
    m.def("set_uv", &scure::set_uv);
    m.def("open_door", &scure::open_door);
    m.def("is_door_closed", &scure::is_door_closed);
    m.def("set_damper", &scure::set_damper);
    m.def("set_fan_speed", &scure::set_fan_speed);
    m.def("set_target_temperature", &scure::set_target_temperature);
    m.def("run_fan_test", &scure::run_fan_test);

    m.def("get_state", []() {
        std::lock_guard<std::mutex> lock(scure::g_mutex);
        auto& s = scure::g_state;
        return py::dict(
            "chamberTemp"_a = s.chamber_temp,
            "targetTemp"_a = s.target_temp,
            "doorClosed"_a = s.door_closed,
            "isHeating"_a = s.heating,
            "isCooling"_a = s.cooling,
            "uvOn"_a = s.uv_on,
            "uvIntensity"_a = s.uv_intensity,
            "damperOpen"_a = s.damper_open
        );
    });
}
*/
