// io_controller.cpp - single unified controller for every component on the
// CureBox IO board (Raspberry Pi CM5), in C++.
//
// Full counterpart of io_controller.py: one file driving every component at
// once over Linux i2c-dev.
//   - PCA9685   (i2c-0, 0x55)  - 16-channel PWM (heater/fans/lights/motor EN/LEDs)
//   - TCA6424A  (i2c-0, 0x23)  - I/O expander (motor direction, valves, fan ON/OFF, NFC)
//   - ADS1115   (analog 0x48)  - analog reads (light sensors / signals)
//   - ADS1115   (temp   0x49)  - NTC thermistors -> temperature (beta equation)
//   - Direct GPIO / Servo      - via the `pinctrl` tool (system()), like the Python version
//
// Build:  g++ -O2 -std=c++17 -o io_controller io_controller.cpp
// Run:    sudo ./io_controller <component> <action> ...      (see ./io_controller help)
//
// Note: the PWM and analog components access /dev/i2c-N directly (root or i2c-group
//       membership required). servo/gpio go through the pinctrl tool, as in Python.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <string>
#include <vector>
#include <map>
#include <set>
#include <memory>
#include <functional>
#include <cctype>
#include <stdexcept>
#include <algorithm>
#include <chrono>
#include <csignal>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>

// ===========================================================================
//  I2C helper - thin wrapper over /dev/i2c-N
// ===========================================================================
class I2CBus {
public:
    explicit I2CBus(int bus) : fd_(-1) {
        std::string path = "/dev/i2c-" + std::to_string(bus);
        fd_ = ::open(path.c_str(), O_RDWR);
        if (fd_ < 0)
            throw std::runtime_error("failed to open " + path + " (is I2C enabled and permitted?)");
    }
    ~I2CBus() { if (fd_ >= 0) ::close(fd_); }
    I2CBus(const I2CBus&) = delete;
    I2CBus& operator=(const I2CBus&) = delete;

    void set_addr(int addr) {
        if (::ioctl(fd_, I2C_SLAVE, addr) < 0)
            throw std::runtime_error("failed to select I2C address");
    }
    void write_byte_data(int addr, uint8_t reg, uint8_t val) {
        set_addr(addr);
        uint8_t buf[2] = {reg, val};
        if (::write(fd_, buf, 2) != 2) throw std::runtime_error("I2C write failed");
    }
    uint8_t read_byte_data(int addr, uint8_t reg) {
        set_addr(addr);
        if (::write(fd_, &reg, 1) != 1) throw std::runtime_error("register select failed");
        uint8_t v = 0;
        if (::read(fd_, &v, 1) != 1) throw std::runtime_error("I2C read failed");
        return v;
    }
    void write_block(int addr, uint8_t reg, const std::vector<uint8_t>& data) {
        set_addr(addr);
        std::vector<uint8_t> buf;
        buf.reserve(data.size() + 1);
        buf.push_back(reg);
        buf.insert(buf.end(), data.begin(), data.end());
        if (::write(fd_, buf.data(), buf.size()) != (ssize_t)buf.size())
            throw std::runtime_error("I2C block write failed");
    }
    std::vector<uint8_t> read_block(int addr, uint8_t reg, int n) {
        set_addr(addr);
        if (::write(fd_, &reg, 1) != 1) throw std::runtime_error("register select failed");
        std::vector<uint8_t> out(n);
        if (::read(fd_, out.data(), n) != n) throw std::runtime_error("I2C block read failed");
        return out;
    }
private:
    int fd_;
};

static void sleep_ms(double ms) { ::usleep((useconds_t)(ms * 1000.0)); }

// ===========================================================================
//  Unified configuration
// ===========================================================================
namespace cfg {
// --- PCA9685 ---
constexpr int PCA_BUS = 0, PCA_ADDR = 0x55;
constexpr uint8_t PCA_MODE1 = 0x00, PCA_MODE2 = 0x01, PCA_PRESCALE = 0xFE, PCA_LED0_ON_L = 0x06;
constexpr uint8_t PCA_SLEEP = 0x10, PCA_AI = 0x20, PCA_RESTART = 0x80;

const std::map<std::string,int> PCA_CHANNELS = {
    {"FAN_HEATER",0},{"FAN_DOOR",1},{"FAN_RIGHT",2},{"FAN_LEFT",3},{"FAN_BACK",4},{"FAN_COOLING",5},
    {"PWM_HEATER",6},{"LIGHT1",7},{"MOT1_EN",8},{"MOT2_EN",9},{"BOFA",10},
    {"LED_BACK",11},{"LED_DOOR",12},{"LED_RIGHT",13},{"LED_LEFT",14},{"LED_ANALOG5",15},
};
inline bool pca_inverted(int ch) {
    static const std::vector<int> inv = {0,1,2,3,4,5,7,8,9};
    return std::find(inv.begin(), inv.end(), ch) != inv.end();
}
inline bool pca_digital(int ch) { return ch == 6; }

// --- TCA6424A ---
constexpr int TCA_BUS = 0, TCA_ADDR = 0x23;
constexpr uint8_t TCA_REG_INPUT = 0x80, TCA_REG_OUTPUT = 0x84, TCA_REG_CONFIG = 0x8C;
struct Pin { int port, bit; };
const std::map<std::string,Pin> TCA_PINS = {
    {"NFC_RESET",{0,1}},{"LED_SWITCH",{0,5}},
    {"FAN1_ONOFF",{1,1}},{"FAN2_ONOFF",{1,2}},{"FAN3_ONOFF",{1,3}},
    {"FAN4_ONOFF",{1,4}},{"FAN5_ONOFF",{1,5}},{"FAN6_ONOFF",{1,6}},
    {"MOT1_IN1",{2,5}},{"MOT1_IN2",{2,4}},{"MOT2_IN1",{2,2}},{"MOT2_IN2",{2,1}},
    {"VALVE_2_ON",{2,6}},{"DOOR_MAGNET",{2,6}},   // P26 = valve 2 = door magnet (OUT2 -> J8_DOOR_MAGNET)
    {"VALVE_1_ON",{2,7}},
};
inline bool tca_inverted(const std::string& n) {
    static const std::vector<std::string> inv = {
        "FAN1_ONOFF","FAN2_ONOFF","FAN3_ONOFF","FAN4_ONOFF","FAN5_ONOFF","FAN6_ONOFF"};
    return std::find(inv.begin(), inv.end(), n) != inv.end();
}
inline bool tca_safe_high(const std::string& n) { return n == "NFC_RESET"; }

// --- ADS1115 ---
constexpr uint8_t ADS_REG_CONVERT = 0x00, ADS_REG_CONFIG = 0x01;
inline double ads_fs(int pga) {
    static const double fs[] = {6.144,4.096,2.048,1.024,0.512,0.256};
    return fs[pga];
}
// analog
constexpr int ANALOG_PGA = 0;
constexpr double ANALOG_SUPPLY = 5.0;
struct AdcCfg { int bus, addr; };
const std::map<std::string,AdcCfg> ANALOG_ADCS = { {"U10",{1,0x48}}, {"U8",{0,0x48}} };
struct Chan { std::string chip; int ch; };
const std::vector<std::pair<std::string,Chan>> ANALOG_SENSORS = {
    {"LIGHT1",{"U10",0}},{"LIGHT2",{"U10",1}},{"AIN2",{"U10",2}},{"AIN3",{"U10",3}},
    {"SENSOR1_A1",{"U8",0}},{"SENSOR1_A2",{"U8",1}},{"SENSOR2_A1",{"U8",2}},{"SENSOR2_A2",{"U8",3}},
};
inline double analog_divider(const std::string& n) { return (n=="AIN2"||n=="AIN3") ? 2.0 : 1.0; }

// temperature (NTC)
constexpr int TEMP_PGA = 1;
const std::map<std::string,AdcCfg> TEMP_ADCS = { {"U6",{0,0x49}}, {"U7",{1,0x49}} };
const std::vector<std::pair<std::string,Chan>> TEMP_SENSORS = {
    {"TEMP_RIGHT_ORIGIN",{"U6",0}},{"TEMP_RIGHT",{"U6",1}},
    {"TEMP_LEFT_ORIGIN",{"U6",2}},{"TEMP_LEFT",{"U6",3}},
    {"TEMP_BACK_ORIGIN",{"U7",0}},{"TEMP_DOOR_ORIGIN",{"U7",1}},
    {"TEMP_CHAMBER",{"U7",2}},   // NTC7 - chamber temperature
};
constexpr double NTC_R0 = 10000.0, NTC_BETA = 3934.0, NTC_T0 = 298.15;
constexpr double NTC_R_SERIES = 10000.0, NTC_VREF = 3.3;
const std::string NTC_DIVIDER = "pullup";

// direct GPIO (pinctrl)
const std::map<std::string,int> GPIO_SIGNALS = {
    {"NITROGEN_VALVE",13},   // nitrogen valve - GPIO13
    {"RGB_LED",12},          // RGB status LEDs (TM3909 driver, RGB_LV line) - GPIO12
    {"GPIO16",16},           // GPIO16 (per schematic blue label)
    {"GPIO20",20},           // GPIO20 (per schematic blue label)
};
// Read-only GPIO inputs (sensors) - read via pinctrl get, never driven.
const std::map<std::string,int> GPIO_INPUTS = { {"DOOR_STATUS",27} };  // door sensor - GPIO27
// Level that means "open" for each input (flip if wired the other way).
const std::map<std::string,int> GPIO_INPUT_OPEN_LEVEL = { {"DOOR_STATUS",0} };  // HIGH = closed, LOW = open (bench-confirmed 2026-07-22)

// Servo (SG90) - driven via pinctrl/note (see cmd_servo)
constexpr int SERVO_PIN = 8;
} // namespace cfg

// ===========================================================================
//  Set-and-verify with retry (shared by every writable component)
// ===========================================================================
constexpr int VERIFY_RETRIES = 3;

// apply(): performs the write.  check(): returns {ok, observed-as-string}.
// Returns the (1-based) attempt that succeeded; throws if all attempts failed.
template <typename Apply, typename Check>
int set_and_verify(const std::string& label, Apply apply, Check check) {
    std::string observed;
    for (int attempt = 1; attempt <= VERIFY_RETRIES; ++attempt) {
        apply();
        auto pr = check();          // std::pair<bool,std::string>
        observed = pr.second;
        if (pr.first) return attempt;
    }
    throw std::runtime_error(label + ": not confirmed after " +
        std::to_string(VERIFY_RETRIES) + " attempts (last read back: " + observed + ")");
}

// Run every (label, action) pair, attempting all of them, then throw one
// aggregated error listing whatever failed. Used by the bulk paths (alloff /
// safe) so the whole system is still driven to its target state even if one
// component cannot be confirmed.
static void verify_each(const std::vector<std::pair<std::string, std::function<void()>>>& actions) {
    std::vector<std::string> failures;
    for (const auto& pr : actions) {
        try { pr.second(); }
        catch (const std::exception& e) { failures.push_back(pr.first + ": " + e.what()); }
    }
    if (!failures.empty()) {
        std::string msg = std::to_string(failures.size()) + " component(s) not confirmed:";
        for (const auto& f : failures) msg += "\n  " + f;
        throw std::runtime_error(msg);
    }
}

// ===========================================================================
//  PCA9685
// ===========================================================================
class PCA9685 {
public:
    PCA9685() : bus_(cfg::PCA_BUS) {
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE1, cfg::PCA_AI);
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE2, 0x04);
        sleep_ms(1);
    }
    void set_freq(double hz) {
        int prescale = (int)std::lround(25000000.0 / (4096.0 * hz)) - 1;
        prescale = std::max(3, std::min(255, prescale));
        uint8_t old = bus_.read_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE1);
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE1, (old & 0x7F) | cfg::PCA_SLEEP);
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_PRESCALE, (uint8_t)prescale);
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE1, old);
        sleep_ms(5);
        bus_.write_byte_data(cfg::PCA_ADDR, cfg::PCA_MODE1, old | cfg::PCA_RESTART | cfg::PCA_AI);
    }
    void set_pwm(int ch, int on, int off) {
        uint8_t base = cfg::PCA_LED0_ON_L + 4 * ch;
        bus_.write_block(cfg::PCA_ADDR, base,
            { (uint8_t)(on & 0xFF), (uint8_t)(on >> 8),
              (uint8_t)(off & 0xFF), (uint8_t)(off >> 8) });
    }
    void set_duty(int ch, double percent) {
        percent = std::max(0.0, std::min(100.0, percent));
        if (cfg::pca_digital(ch)) percent = percent > 0 ? 100.0 : 0.0;
        double eff = cfg::pca_inverted(ch) ? (100.0 - percent) : percent;
        if (eff <= 0)        set_pwm(ch, 0, 0x1000);          // full-OFF
        else if (eff >= 100) set_pwm(ch, 0x1000, 0);          // full-ON
        else                 set_pwm(ch, 0, (int)(eff / 100.0 * 4095));
    }
    void on(int ch)  { set_duty(ch, 100); }
    void off(int ch) { set_duty(ch, 0); }

    std::string read_state(int ch) {
        uint8_t base = cfg::PCA_LED0_ON_L + 4 * ch;
        auto d = bus_.read_block(cfg::PCA_ADDR, base, 4);
        int on = d[0] | (d[1] << 8), off = d[2] | (d[3] << 8);
        bool inv = cfg::pca_inverted(ch);
        if (on & 0x1000)  return inv ? "OFF (full)" : "ON (full)";
        if (off & 0x1000) return inv ? "ON (full)"  : "OFF (full)";
        double pct = off / 4095.0 * 100.0;
        if (inv) pct = 100.0 - pct;
        char buf[16]; std::snprintf(buf, sizeof buf, "%.0f%%", pct);
        return buf;
    }

    // The (on, off) register pair set_duty would write for this command.
    std::pair<int,int> intended_regs(int ch, double percent) {
        percent = std::max(0.0, std::min(100.0, percent));
        if (cfg::pca_digital(ch)) percent = percent > 0 ? 100.0 : 0.0;
        bool inv = cfg::pca_inverted(ch);
        double eff = inv ? (100.0 - percent) : percent;
        if (eff <= 0)   return {0, 0x1000};     // full-OFF
        if (eff >= 100) return {0x1000, 0};     // full-ON
        return {0, (int)(eff / 100.0 * 4095)};
    }
    // Set duty, then read the channel registers back to confirm. Retries.
    int set_duty_verified(int ch, double percent) {
        auto want = intended_regs(ch, percent);
        uint8_t base = cfg::PCA_LED0_ON_L + 4 * ch;
        return set_and_verify("PCA channel " + std::to_string(ch),
            [&]{ set_duty(ch, percent); },
            [&]{ auto d = bus_.read_block(cfg::PCA_ADDR, base, 4);
                 std::pair<int,int> got{ d[0] | (d[1] << 8), d[2] | (d[3] << 8) };
                 return std::make_pair(got == want, read_state(ch)); });
    }
    int on_verified(int ch)  { return set_duty_verified(ch, 100); }
    int off_verified(int ch) { return set_duty_verified(ch, 0); }
private:
    I2CBus bus_;
};

// ===========================================================================
//  TCA6424A
// ===========================================================================
class TCA6424A {
public:
    TCA6424A() : bus_(cfg::TCA_BUS), out_{0,0,0} { safe_init(); }

    void set_pin(const std::string& name, int value) {
        auto p = pin(name);
        int level = cfg::tca_inverted(name) ? (value ? 0 : 1) : (value ? 1 : 0);
        setbit(p, level);
        commit();
    }
    int get_pin(const std::string& name) {
        auto p = pin(name);
        auto d = bus_.read_block(cfg::TCA_ADDR, cfg::TCA_REG_INPUT, 3);
        int level = (d[p.port] >> p.bit) & 1;
        return cfg::tca_inverted(name) ? (1 - level) : level;
    }
    void motor(int n, const std::string& dir) {
        std::string in1 = "MOT" + std::to_string(n) + "_IN1";
        std::string in2 = "MOT" + std::to_string(n) + "_IN2";
        int a, b;
        if      (dir == "fwd")   { a = 1; b = 0; }
        else if (dir == "rev")   { a = 0; b = 1; }
        else if (dir == "brake") { a = 1; b = 1; }
        else if (dir == "stop")  { a = 0; b = 0; }
        else throw std::runtime_error("direction: fwd/rev/stop/brake");
        setbit(pin(in1), a); setbit(pin(in2), b);
        commit();
    }
    void valve(int n, bool on) { set_pin("VALVE_" + std::to_string(n) + "_ON", on ? 1 : 0); }
    void nfc_reset() {
        set_pin("NFC_RESET", 0); sleep_ms(10);
        set_pin_verified("NFC_RESET", 1);   // confirm it returns to idle (high)
    }
    void all_safe() {
        for (int n : {1, 2}) { motor(n, "stop"); valve(n, false); }
    }

    // --- verified variants (set, read back, retry) ------------------------
    int set_pin_verified(const std::string& name, int value) {
        return set_and_verify("TCA pin " + name,
            [&]{ set_pin(name, value); },
            [&]{ int v = get_pin(name); return std::make_pair(v == value, std::to_string(v)); });
    }
    int valve_verified(int n, bool on) {
        return set_pin_verified("VALVE_" + std::to_string(n) + "_ON", on ? 1 : 0);
    }
    int motor_verified(int n, const std::string& dir) {
        std::map<std::string,std::pair<int,int>> table = {
            {"fwd",{1,0}},{"rev",{0,1}},{"brake",{1,1}},{"stop",{0,0}}};
        auto it = table.find(dir);
        if (it == table.end()) throw std::runtime_error("direction: fwd/rev/stop/brake");
        std::pair<int,int> want = it->second;
        std::string in1 = "MOT" + std::to_string(n) + "_IN1";
        std::string in2 = "MOT" + std::to_string(n) + "_IN2";
        return set_and_verify("TCA motor " + std::to_string(n) + " (" + dir + ")",
            [&]{ motor(n, dir); },
            [&]{ std::pair<int,int> got{ get_pin(in1), get_pin(in2) };
                 return std::make_pair(got == want,
                     std::to_string(got.first) + "," + std::to_string(got.second)); });
    }
    void all_safe_verified() {
        std::vector<std::pair<std::string, std::function<void()>>> acts;
        for (int n : {1, 2}) {
            acts.push_back({"motor " + std::to_string(n), [this, n]{ motor_verified(n, "stop"); }});
            acts.push_back({"valve " + std::to_string(n), [this, n]{ valve_verified(n, false); }});
        }
        verify_each(acts);
    }
private:
    cfg::Pin pin(const std::string& name) {
        auto it = cfg::TCA_PINS.find(name);
        if (it == cfg::TCA_PINS.end()) throw std::runtime_error("unknown pin: " + name);
        return it->second;
    }
    void setbit(cfg::Pin p, int val) {
        if (val) out_[p.port] |=  (1 << p.bit);
        else     out_[p.port] &= ~(1 << p.bit);
    }
    void commit() {
        bus_.write_block(cfg::TCA_ADDR, cfg::TCA_REG_OUTPUT,
                         {out_[0], out_[1], out_[2]});
    }
    void safe_init() {
        for (const auto& kv : cfg::TCA_PINS) {
            if (cfg::tca_safe_high(kv.first) || cfg::tca_inverted(kv.first))
                out_[kv.second.port] |= (1 << kv.second.bit);  // logical OFF = physical high
        }
        commit();
        uint8_t c[3] = {0xFF, 0xFF, 0xFF};
        for (const auto& kv : cfg::TCA_PINS)
            c[kv.second.port] &= ~(1 << kv.second.bit);        // mapped pin = output
        bus_.write_block(cfg::TCA_ADDR, cfg::TCA_REG_CONFIG, {c[0], c[1], c[2]});
    }
    I2CBus bus_;
    uint8_t out_[3];
};

// ===========================================================================
//  ADS1115
// ===========================================================================
class ADS1115 {
public:
    ADS1115(I2CBus& bus, int addr, int pga) : bus_(bus), addr_(addr), pga_(pga) {}
    int read_raw(int channel) {
        int mux = 0b100 + channel;
        int config = (1 << 15) | (mux << 12) | (pga_ << 9) |
                     (1 << 8) | (0b100 << 5) | 0b00011;
        bus_.write_block(addr_, cfg::ADS_REG_CONFIG,
                         { (uint8_t)((config >> 8) & 0xFF), (uint8_t)(config & 0xFF) });
        for (int i = 0; i < 50; ++i) {
            sleep_ms(2);
            auto c = bus_.read_block(addr_, cfg::ADS_REG_CONFIG, 2);
            if (c[0] & 0x80) break;
        }
        auto d = bus_.read_block(addr_, cfg::ADS_REG_CONVERT, 2);
        int raw = (d[0] << 8) | d[1];
        if (raw > 0x7FFF) raw -= 0x10000;
        return raw;
    }
    double read_voltage(int channel) {
        return read_raw(channel) * cfg::ads_fs(pga_) / 32768.0;
    }
private:
    I2CBus& bus_;
    int addr_, pga_;
};

// NTC helpers
static double ntc_v_to_r(double v) {
    if (v <= 0 || v >= cfg::NTC_VREF) return NAN;
    if (cfg::NTC_DIVIDER == "pullup")
        return cfg::NTC_R_SERIES * v / (cfg::NTC_VREF - v);
    return cfg::NTC_R_SERIES * (cfg::NTC_VREF - v) / v;
}
static double ntc_r_to_temp(double r) {
    if (std::isnan(r) || r <= 0) return NAN;
    double inv_t = (1.0 / cfg::NTC_T0) + (1.0 / cfg::NTC_BETA) * std::log(r / cfg::NTC_R0);
    return (1.0 / inv_t) - 273.15;
}

// ===========================================================================
//  Direct GPIO / Servo via pinctrl
// ===========================================================================
static int run_pinctrl(const std::string& args) {
    std::string cmd = "pinctrl " + args;
    return std::system(cmd.c_str());
}
static void gpio_set_signal(const std::string& name, bool on) {
    auto it = cfg::GPIO_SIGNALS.find(name);
    if (it == cfg::GPIO_SIGNALS.end()) throw std::runtime_error("unknown signal: " + name);
    std::string lvl = on ? "dh" : "dl";
    run_pinctrl("set " + std::to_string(it->second) + " op " + lvl);
}
// Capture `pinctrl <args>` stdout so we can read a pin back.
static std::string pinctrl_capture(const std::string& args) {
    std::string cmd = "pinctrl " + args + " 2>/dev/null";
    FILE* f = ::popen(cmd.c_str(), "r");
    if (!f) throw std::runtime_error("failed to run pinctrl");
    std::string out; char buf[256];
    while (std::fgets(buf, sizeof buf, f)) out += buf;
    ::pclose(f);
    return out;
}
// Read back a signal's logical level: 1, 0, or -1 if it could not be parsed.
static int gpio_get_signal(const std::string& name) {
    auto it = cfg::GPIO_SIGNALS.find(name);
    if (it == cfg::GPIO_SIGNALS.end()) throw std::runtime_error("unknown signal: " + name);
    std::string out = pinctrl_capture("get " + std::to_string(it->second));
    for (auto& c : out) c = (char)std::tolower((unsigned char)c);
    if (out.find("hi") != std::string::npos) return 1;
    if (out.find("lo") != std::string::npos) return 0;
    return -1;
}
// Generalized `pinctrl set <pin> op dh && pinctrl get <pin>`: drive, read back, retry.
static int gpio_set_signal_verified(const std::string& name, bool on) {
    int desired = on ? 1 : 0;
    return set_and_verify("GPIO " + name,
        [&]{ gpio_set_signal(name, on); },
        [&]{ int v = gpio_get_signal(name); return std::make_pair(v == desired, std::to_string(v)); });
}
// Configure a pin as a plain input with NO internal pull, once per process.
// After boot pinctrl shows unconfigured pins as "no ... | --" (no level), and a
// default pull-down would load the door line (it has its own pull-up, R46).
static void ensure_gpio_input(int pin) {
    static std::set<int> configured;
    if (configured.count(pin)) return;
    run_pinctrl("set " + std::to_string(pin) + " ip pn");
    configured.insert(pin);
}
// Read a read-only GPIO input via pinctrl get: 1, 0, or -1 if unparseable.
static int gpio_read_input(const std::string& name) {
    auto it = cfg::GPIO_INPUTS.find(name);
    if (it == cfg::GPIO_INPUTS.end()) throw std::runtime_error("unknown input: " + name);
    ensure_gpio_input(it->second);
    std::string out = pinctrl_capture("get " + std::to_string(it->second));
    for (auto& c : out) c = (char)std::tolower((unsigned char)c);
    if (out.find("hi") != std::string::npos) return 1;
    if (out.find("lo") != std::string::npos) return 0;
    return -1;
}
static std::string door_label(int level) {
    if (level < 0) return "?";
    return level == cfg::GPIO_INPUT_OPEN_LEVEL.at("DOOR_STATUS") ? "OPEN" : "CLOSED";
}

// ===========================================================================
//  CLI helpers
// ===========================================================================
static std::string upper(std::string s) {
    for (auto& c : s) c = (char)std::toupper((unsigned char)c);
    return s;
}
static int resolve_pca_channel(const std::string& tok) {
    std::string u = upper(tok);
    auto it = cfg::PCA_CHANNELS.find(u);
    if (it != cfg::PCA_CHANNELS.end()) return it->second;
    bool num = !tok.empty() && std::all_of(tok.begin(), tok.end(), ::isdigit);
    if (num) { int v = std::stoi(tok); if (v >= 0 && v <= 15) return v; }
    throw std::runtime_error("unknown PCA channel: " + tok);
}
// Open each unique bus once and build the ADCs on top of it.
struct AdcSet {
    std::vector<std::unique_ptr<I2CBus>> buses;
    std::map<int, I2CBus*> by_num;
    std::map<std::string, std::unique_ptr<ADS1115>> adcs;
};
static AdcSet open_adcs(const std::map<std::string,cfg::AdcCfg>& table, int pga) {
    AdcSet s;
    for (const auto& kv : table) {
        int n = kv.second.bus;
        if (!s.by_num.count(n)) {
            s.buses.push_back(std::make_unique<I2CBus>(n));
            s.by_num[n] = s.buses.back().get();
        }
    }
    for (const auto& kv : table)
        s.adcs[kv.first] = std::make_unique<ADS1115>(
            *s.by_num[kv.second.bus], kv.second.addr, pga);
    return s;
}

// ===========================================================================
//  Commands
// ===========================================================================
static void usage() {
    std::printf(
        "io_controller - unified controller for every component on the CureBox IO board\n\n"
        "Usage: ./io_controller <component> <action> [args]\n\n"
        "  pca set <channel> <%%>   set duty (name or 0-15)\n"
        "  pca on|off <channel>    full on/off\n"
        "  pca freq <hz>           PWM frequency\n"
        "  pca alloff|status|list\n\n"
        "  io  motor <1|2> <fwd|rev|stop|brake>\n"
        "  io  valve <1|2> <on|off>\n"
        "  io  pin <name> <0|1>    drive a pin directly\n"
        "  io  nfc-reset|safe|status|list\n\n"
        "  temp   read [name|all] | raw | list\n"
        "  analog read [name|all] | raw | list\n\n"
        "  servo  angle <deg>      (via pinctrl - see note)\n"
        "  gpio   on|off <name> | status [name|all] | list\n\n"
        "  cooling run <rate> [target]   closed-loop cooling mode: damper open +\n"
        "                          heater fan 100%%, chamber fan PI-controlled so\n"
        "                          dT/dt tracks <rate> C/min (0-5); stops at\n"
        "                          [target] C (default 25). Ctrl+C stops safely.\n\n"
        "  status                  snapshot of *all* components at once\n"
        "  safe                    return the whole system to a safe state\n\n"
        "Examples:\n"
        "  sudo ./io_controller pca set PWM_HEATER 25\n"
        "  sudo ./io_controller io motor 1 fwd\n"
        "  sudo ./io_controller temp read TEMP_RIGHT\n"
        "  sudo ./io_controller status\n");
}

static int cmd_pca(const std::vector<std::string>& a) {
    if (a.empty()) { usage(); return 2; }
    const std::string& cmd = a[0];
    if (cmd == "list") {
        std::vector<std::pair<int,std::string>> v;
        for (auto& kv : cfg::PCA_CHANNELS) v.push_back({kv.second, kv.first});
        std::sort(v.begin(), v.end());
        for (auto& kv : v) std::printf("  %2d  %s\n", kv.first, kv.second.c_str());
        return 0;
    }
    PCA9685 pca;
    if (cmd == "set") {
        int ch = resolve_pca_channel(a.at(1)); double pct = std::stod(a.at(2));
        int att = pca.set_duty_verified(ch, pct);
        std::printf("channel %d (%s) -> %g%% (verified, attempt %d/%d)\n",
                    ch, a[1].c_str(), pct, att, VERIFY_RETRIES);
    } else if (cmd == "on") {
        int ch = resolve_pca_channel(a.at(1)); int att = pca.on_verified(ch);
        std::printf("channel %d -> ON (verified, attempt %d/%d)\n", ch, att, VERIFY_RETRIES);
    } else if (cmd == "off") {
        int ch = resolve_pca_channel(a.at(1)); int att = pca.off_verified(ch);
        std::printf("channel %d -> OFF (verified, attempt %d/%d)\n", ch, att, VERIFY_RETRIES);
    } else if (cmd == "freq") {
        double hz = std::stod(a.at(1)); pca.set_freq(hz); std::printf("PWM frequency -> %g Hz\n", hz);
    } else if (cmd == "alloff") {
        std::vector<std::pair<std::string, std::function<void()>>> acts;
        for (int ch = 0; ch < 16; ++ch)
            acts.push_back({"ch" + std::to_string(ch), [&pca, ch]{ pca.off_verified(ch); }});
        verify_each(acts);
        std::printf("all channels off (each verified up to %d attempts)\n", VERIFY_RETRIES);
    } else if (cmd == "status") {
        std::map<int,std::string> names;
        for (auto& kv : cfg::PCA_CHANNELS) names[kv.second] = kv.first;
        for (int ch = 0; ch < 16; ++ch)
            std::printf("  %2d %-13s %s%s\n", ch, names[ch].c_str(),
                        pca.read_state(ch).c_str(), cfg::pca_inverted(ch) ? " (inv)" : "");
    } else { usage(); return 2; }
    return 0;
}

static int cmd_io(const std::vector<std::string>& a) {
    if (a.empty()) { usage(); return 2; }
    const std::string& cmd = a[0];
    if (cmd == "list") {
        for (auto& kv : cfg::TCA_PINS)
            std::printf("  %-12s P%d%d\n", kv.first.c_str(), kv.second.port, kv.second.bit);
        return 0;
    }
    TCA6424A io;
    if (cmd == "motor") {
        int n = std::stoi(a.at(1)); int att = io.motor_verified(n, a.at(2));
        std::printf("motor %d -> %s (verified, attempt %d/%d)\n", n, a[2].c_str(), att, VERIFY_RETRIES);
    } else if (cmd == "valve") {
        int n = std::stoi(a.at(1)); bool on = a.at(2) == "on";
        int att = io.valve_verified(n, on);
        std::printf("valve %d -> %s (verified, attempt %d/%d)\n", n, a[2].c_str(), att, VERIFY_RETRIES);
    } else if (cmd == "pin") {
        std::string name = upper(a.at(1)); int val = std::stoi(a.at(2));
        int att = io.set_pin_verified(name, val);
        std::printf("%s -> %d (verified, attempt %d/%d)\n", name.c_str(), val, att, VERIFY_RETRIES);
    } else if (cmd == "nfc-reset") {
        io.nfc_reset(); std::printf("NFC reset pulse done\n");
    } else if (cmd == "safe") {
        io.all_safe_verified();
        std::printf("all components returned to a safe state (verified up to %d attempts)\n", VERIFY_RETRIES);
    } else if (cmd == "status") {
        for (auto& kv : cfg::TCA_PINS)
            std::printf("  %-12s %d\n", kv.first.c_str(), io.get_pin(kv.first));
    } else { usage(); return 2; }
    return 0;
}

static int cmd_temp(const std::vector<std::string>& a) {
    if (a.empty()) { usage(); return 2; }
    const std::string& cmd = a[0];
    if (cmd == "list") {
        for (auto& kv : cfg::TEMP_SENSORS) {
            auto c = cfg::TEMP_ADCS.at(kv.second.chip);
            std::printf("  %s  ->  %s (i2c-%d, 0x%02X), AIN%d\n",
                        kv.first.c_str(), kv.second.chip.c_str(), c.bus, c.addr, kv.second.ch);
        }
        return 0;
    }
    auto s = open_adcs(cfg::TEMP_ADCS, cfg::TEMP_PGA);
    auto read = [&](const cfg::Chan& ch) {
        double v = s.adcs[ch.chip]->read_voltage(ch.ch);
        return std::make_pair(v, ntc_r_to_temp(ntc_v_to_r(v)));
    };
    if (cmd == "raw") {
        for (auto& kv : cfg::TEMP_SENSORS)
            std::printf("  %s: %.4f V\n", kv.first.c_str(),
                        s.adcs[kv.second.chip]->read_voltage(kv.second.ch));
    } else if (cmd == "read") {
        std::string sel = a.size() > 1 ? upper(a[1]) : "ALL";
        for (auto& kv : cfg::TEMP_SENSORS) {
            if (sel != "ALL" && sel != kv.first) continue;
            auto pr = read(kv.second);
            if (std::isnan(pr.second))
                std::printf("  %s: -   (%.3f V)\n", kv.first.c_str(), pr.first);
            else
                std::printf("  %s: %.1f C   (%.3f V)\n", kv.first.c_str(), pr.second, pr.first);
        }
    } else { usage(); return 2; }
    return 0;
}

static int cmd_analog(const std::vector<std::string>& a) {
    if (a.empty()) { usage(); return 2; }
    const std::string& cmd = a[0];
    if (cmd == "list") {
        for (auto& kv : cfg::ANALOG_SENSORS) {
            auto c = cfg::ANALOG_ADCS.at(kv.second.chip);
            double sc = cfg::analog_divider(kv.first);
            std::printf("  %-11s ->  %s (i2c-%d, 0x%02X), AIN%d%s\n",
                        kv.first.c_str(), kv.second.chip.c_str(), c.bus, c.addr, kv.second.ch,
                        sc != 1.0 ? "  (divider x2)" : "");
        }
        return 0;
    }
    auto s = open_adcs(cfg::ANALOG_ADCS, cfg::ANALOG_PGA);
    auto read = [&](const std::string& name, const cfg::Chan& ch) {
        double v = s.adcs[ch.chip]->read_voltage(ch.ch) * cfg::analog_divider(name);
        double pct = std::max(0.0, std::min(100.0, v / cfg::ANALOG_SUPPLY * 100.0));
        return std::make_pair(v, pct);
    };
    if (cmd == "raw") {
        for (auto& kv : cfg::ANALOG_SENSORS)
            std::printf("  %s: %.4f V\n", kv.first.c_str(),
                        s.adcs[kv.second.chip]->read_voltage(kv.second.ch));
    } else if (cmd == "read") {
        std::string sel = a.size() > 1 ? upper(a[1]) : "ALL";
        for (auto& kv : cfg::ANALOG_SENSORS) {
            if (sel != "ALL" && sel != kv.first) continue;
            auto pr = read(kv.first, kv.second);
            std::printf("  %-11s %.3f V   (%.0f%%)\n", kv.first.c_str(), pr.first, pr.second);
        }
    } else { usage(); return 2; }
    return 0;
}

static int cmd_servo(const std::vector<std::string>& a) {
    // In Python the servo is driven via gpiozero. C++ has no built-in software PWM,
    // so precise SG90 angle control should run through the Python tool.
    if (a.size() >= 2 && a[0] == "angle") {
        std::printf("note: precise SG90 angle control needs software PWM.\n"
                    "      run: python3 io_controller.py servo angle %s\n", a[1].c_str());
        return 0;
    }
    std::printf("servo: use  python3 io_controller.py servo <angle|min|max|center|sweep>\n");
    return 0;
}

static int cmd_gpio(const std::vector<std::string>& a) {
    if (a.empty()) { usage(); return 2; }
    const std::string& cmd = a[0];
    if (cmd == "list") {
        for (auto& kv : cfg::GPIO_SIGNALS)
            std::printf("  %-16s GPIO%d  [output]\n", kv.first.c_str(), kv.second);
        for (auto& kv : cfg::GPIO_INPUTS)
            std::printf("  %-16s GPIO%d  [input, read-only]\n", kv.first.c_str(), kv.second);
        return 0;
    }
    if (cmd == "on" || cmd == "off") {
        std::string name = upper(a.at(1));
        int att = gpio_set_signal_verified(name, cmd == "on");
        std::printf("%s -> %s (verified, attempt %d/%d)\n",
                    name.c_str(), cmd == "on" ? "ON" : "OFF", att, VERIFY_RETRIES);
    } else if (cmd == "status") {
        std::string sel = a.size() > 1 ? upper(a[1]) : "ALL";
        for (auto& kv : cfg::GPIO_SIGNALS) {
            if (sel != "ALL" && sel != kv.first) continue;
            int v = gpio_get_signal(kv.first);
            std::printf("  %-16s %s\n", kv.first.c_str(), v < 0 ? "?" : std::to_string(v).c_str());
        }
        for (auto& kv : cfg::GPIO_INPUTS) {
            if (sel != "ALL" && sel != kv.first) continue;
            int v = gpio_read_input(kv.first);
            std::string extra = (kv.first == "DOOR_STATUS") ? "  (" + door_label(v) + ")" : "";
            std::printf("  %-16s %s%s\n", kv.first.c_str(),
                        v < 0 ? "?" : std::to_string(v).c_str(), extra.c_str());
        }
    } else { usage(); return 2; }
    return 0;
}

static int cmd_status() {
    std::printf("=== PCA9685 (PWM) ===\n");
    {
        PCA9685 pca;
        std::map<int,std::string> names;
        for (auto& kv : cfg::PCA_CHANNELS) names[kv.second] = kv.first;
        for (int ch = 0; ch < 16; ++ch)
            std::printf("  %-13s %s\n", names[ch].c_str(), pca.read_state(ch).c_str());
    }
    std::printf("\n=== TCA6424A (I/O) ===\n");
    {
        TCA6424A io;
        for (auto& kv : cfg::TCA_PINS)
            std::printf("  %-12s %d\n", kv.first.c_str(), io.get_pin(kv.first));
    }
    std::printf("\n=== temperature (NTC) ===\n");
    {
        auto s = open_adcs(cfg::TEMP_ADCS, cfg::TEMP_PGA);
        for (auto& kv : cfg::TEMP_SENSORS) {
            double v = s.adcs[kv.second.chip]->read_voltage(kv.second.ch);
            double t = ntc_r_to_temp(ntc_v_to_r(v));
            if (std::isnan(t)) std::printf("  %s: -\n", kv.first.c_str());
            else               std::printf("  %s: %.1f C\n", kv.first.c_str(), t);
        }
    }
    std::printf("\n=== analog ===\n");
    {
        auto s = open_adcs(cfg::ANALOG_ADCS, cfg::ANALOG_PGA);
        for (auto& kv : cfg::ANALOG_SENSORS) {
            double v = s.adcs[kv.second.chip]->read_voltage(kv.second.ch)
                       * cfg::analog_divider(kv.first);
            std::printf("  %-11s %.3f V\n", kv.first.c_str(), v);
        }
    }
    return 0;
}

static int cmd_safe() {
    PCA9685 pca;
    TCA6424A io;
    std::vector<std::pair<std::string, std::function<void()>>> acts;
    for (int ch = 0; ch < 16; ++ch)
        acts.push_back({"PCA ch" + std::to_string(ch), [&pca, ch]{ pca.off_verified(ch); }});
    for (int n : {1, 2}) {
        acts.push_back({"motor " + std::to_string(n), [&io, n]{ io.motor_verified(n, "stop"); }});
        acts.push_back({"valve " + std::to_string(n), [&io, n]{ io.valve_verified(n, false); }});
    }
    for (const auto& kv : cfg::GPIO_SIGNALS) {
        std::string nm = kv.first;
        acts.push_back({nm, [nm]{ gpio_set_signal_verified(nm, false); }});
    }
    verify_each(acts);
    std::printf("whole system verified safe (PWM off, motors stopped, valves closed) "
                "- each component read back, up to %d attempts.\n", VERIFY_RETRIES);
    return 0;
}

// ===========================================================================
//  Cooling mode - closed-loop cooling-rate control (counterpart of cooling_mode.py)
//
//  Entry sequence: damper OPEN + heater fan fixed 100% PWM for the whole mode,
//  then the chamber fan runs under PI control so the measured chamber dT/dt
//  (least-squares slope over a sliding window) tracks the requested rate
//  (0-5 C/min). Auto-terminates at the target temperature: fans OFF, damper
//  CLOSED. Every component is driven ONLY through the existing verified
//  activation functions (set_duty_verified; the damper through the documented
//  Python servo path - C++ has no software PWM, see cmd_servo).
//
//  Note: the rate setpoint is fixed for a CLI run (Ctrl+C stops safely);
//  live setpoint updates are available in the Python dashboard.
//  Keep these constants in sync with the "cooling" section of components.json.
// ===========================================================================
namespace cool {
constexpr int    DAMPER_OPEN_ANGLE = 180, DAMPER_CLOSED_ANGLE = 0;
constexpr double HEATER_FAN_PWM = 100.0;
constexpr double RATE_MIN = 0.0, RATE_MAX = 5.0, TARGET_DEFAULT = 25.0;
constexpr double SAMPLE_SEC = 2.0, WINDOW_SEC = 30.0;
constexpr double KP = 25.0, KI = 2.0, PWM_START = 50.0;
constexpr double PWM_MIN = 0.0, PWM_MAX = 100.0;
const std::string HEATER_FAN = "FAN_HEATER", CHAMBER_FAN = "FAN_COOLING";
const std::string THERMISTOR = "TEMP_CHAMBER";
} // namespace cool

static volatile std::sig_atomic_t g_cool_stop = 0;
static void cool_on_sigint(int) { g_cool_stop = 1; }

static double mono_sec() {
    return std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

// Least-squares dT/dt over (time, temp) samples -> COOLING rate in C/min
// (positive while cooling), or NAN while the window is still filling up.
static double cool_slope_c_per_min(const std::vector<std::pair<double,double>>& s) {
    if (s.size() < 3 || s.back().first - s.front().first < 10.0) return NAN;
    double t0 = s.front().first, n = (double)s.size();
    double mx = 0, my = 0;
    for (const auto& p : s) { mx += p.first - t0; my += p.second; }
    mx /= n; my /= n;
    double num = 0, den = 0;
    for (const auto& p : s) {
        double dx = (p.first - t0) - mx;
        num += dx * (p.second - my);
        den += dx * dx;
    }
    if (den <= 0) return NAN;
    return -(num / den) * 60.0;          // C/sec -> C/min, cooling positive
}

// Damper = SG90 servo: like cmd_servo, angle moves go through the Python
// servo driver (the only servo activation path available to the C++ build).
static void cool_set_damper(bool open) {
    int angle = open ? cool::DAMPER_OPEN_ANGLE : cool::DAMPER_CLOSED_ANGLE;
    std::string cmd = "python3 io_controller.py servo angle " + std::to_string(angle);
    std::system(cmd.c_str());
    std::printf("damper -> %s (%d deg)\n", open ? "OPEN" : "CLOSED", angle);
}

static double cool_read_chamber_temp(AdcSet& s) {
    for (const auto& kv : cfg::TEMP_SENSORS)
        if (kv.first == cool::THERMISTOR) {
            double v = s.adcs[kv.second.chip]->read_voltage(kv.second.ch);
            return ntc_r_to_temp(ntc_v_to_r(v));
        }
    return NAN;
}

static int cmd_cooling(const std::vector<std::string>& a) {
    if (a.empty() || a[0] != "run") { usage(); return 2; }
    double rate = std::max(cool::RATE_MIN, std::min(cool::RATE_MAX, std::stod(a.at(1))));
    double target = a.size() > 2 ? std::stod(a[2]) : cool::TARGET_DEFAULT;

    PCA9685 pca;
    auto adcs = open_adcs(cfg::TEMP_ADCS, cfg::TEMP_PGA);
    int hfan = cfg::PCA_CHANNELS.at(cool::HEATER_FAN);
    int cfan = cfg::PCA_CHANNELS.at(cool::CHAMBER_FAN);

    double t = cool_read_chamber_temp(adcs);
    if (std::isnan(t))
        throw std::runtime_error("thermistor " + cool::THERMISTOR +
                                 " disconnected / invalid reading");
    if (t <= target) {
        std::printf("chamber already at %.1f C (target %.1f C) - nothing to do\n", t, target);
        return 0;
    }

    // Entry sequence (precondition): 1. damper OPEN  2. heater fan fixed 100%
    cool_set_damper(true);
    pca.set_duty_verified(hfan, cool::HEATER_FAN_PWM);
    // 3. chamber fan starts under closed-loop control
    double pwm = cool::PWM_START;
    pca.set_duty_verified(cfan, pwm);

    std::signal(SIGINT, cool_on_sigint);
    std::printf("cooling mode ON: rate=%.2f C/min, target=%.1f C, chamber=%.1f C "
                "(Ctrl+C to stop)\n\n", rate, target, t);

    std::vector<std::pair<double,double>> samples;
    double integ = cool::KI > 0 ? cool::PWM_START / cool::KI : 0.0;   // bumpless start
    double last = mono_sec();
    std::string fault;
    bool reached = false;

    while (!g_cool_stop) {
        sleep_ms(cool::SAMPLE_SEC * 1000.0);
        if (g_cool_stop) break;
        t = cool_read_chamber_temp(adcs);
        if (std::isnan(t)) { fault = "thermistor invalid while cooling"; break; }
        double now = mono_sec(), dt = now - last;
        last = now;
        if (t <= target) { reached = true; break; }       // auto-terminate at target
        samples.push_back({now, t});
        while (!samples.empty() && now - samples.front().first > cool::WINDOW_SEC)
            samples.erase(samples.begin());
        double meas = cool_slope_c_per_min(samples);
        if (std::isnan(meas)) {                           // window still filling up
            std::printf("  chamber=%.1fC  rate=--    (set %.2f)  fan=%.0f%%\n",
                        t, rate, pwm);
            continue;
        }
        double err = rate - meas;                         // >0: cooling too slowly -> more fan
        integ += err * dt;
        if (cool::KI > 0)                                 // anti-windup inside PWM range
            integ = std::max(cool::PWM_MIN / cool::KI,
                             std::min(cool::PWM_MAX / cool::KI, integ));
        pwm = std::max(cool::PWM_MIN,
                       std::min(cool::PWM_MAX, cool::KP * err + cool::KI * integ));
        bool limited = pwm >= cool::PWM_MAX - 1e-6 && err > 0.1;
        try { pca.set_duty_verified(cfan, pwm); }
        catch (const std::exception& e) { fault = e.what(); break; }
        std::printf("  chamber=%.1fC  rate=%+.2f C/min  (set %.2f)  fan=%.0f%%%s\n",
                    t, meas, rate, pwm, limited ? "  [rate not achievable]" : "");
    }

    // End of process: ALL fans OFF (verified), damper CLOSED - always.
    for (const auto& kv : cfg::PCA_CHANNELS) {
        if (kv.first.rfind("FAN_", 0) != 0) continue;
        try { pca.set_duty_verified(kv.second, 0); }
        catch (const std::exception&) {}          // keep going, close the rest
    }
    cool_set_damper(false);
    if (!fault.empty()) throw std::runtime_error("cooling fault: " + fault);
    std::printf(reached ? "\ntarget temperature reached - fans off, damper closed.\n"
                        : "\ncooling stopped by user - fans off, damper closed.\n");
    return 0;
}

// ===========================================================================
//  main
// ===========================================================================
int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);
    if (args.empty() || args[0] == "help" || args[0] == "-h" || args[0] == "--help") {
        usage();
        return args.empty() ? 2 : 0;
    }
    std::string comp = args[0];
    std::vector<std::string> rest(args.begin() + 1, args.end());
    try {
        if (comp == "pca")         return cmd_pca(rest);
        else if (comp == "io")     return cmd_io(rest);
        else if (comp == "temp")   return cmd_temp(rest);
        else if (comp == "analog") return cmd_analog(rest);
        else if (comp == "servo")  return cmd_servo(rest);
        else if (comp == "gpio")   return cmd_gpio(rest);
        else if (comp == "cooling") return cmd_cooling(rest);
        else if (comp == "status") return cmd_status();
        else if (comp == "safe")   return cmd_safe();
        else { usage(); return 2; }
    } catch (const std::exception& e) {
        std::fprintf(stderr, "error: %s\n", e.what());
        return 1;
    }
}
