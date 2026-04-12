/**
 * sCure Temperature Controller (C++)
 * PI controller with Delta-Sigma DAC for heater PWM
 *
 * Direct port from temperature_control.py
 * Runs at 20Hz (50ms loop) for precise heater control
 *
 * Compile into hw_driver.so via pybind11 or use standalone.
 */

#pragma once

#include <cstdio>
#include <cmath>
#include <atomic>
#include <thread>
#include <mutex>
#include <functional>
#include <chrono>

namespace scure {

class TemperatureController {
public:
    // PI gains
    static constexpr float CTL_P = 0.08f;
    static constexpr float CTL_I = 0.00015f;
    static constexpr float CTL_D = 0.0f;

    static constexpr float INTEGRATOR_MAX = 0.85f;
    static constexpr float INTEGRATOR_MIN = 0.0f;

    // Callback: (current_temp, target_temp, at_temp, is_heating)
    using UpdateCallback = std::function<void(float, float, bool, bool)>;

    // Hardware IO interface
    struct IO {
        std::function<float()> read_temp_c;     // Read thermocouple
        std::function<void()> heater_on;        // Relay ON
        std::function<void()> heater_off;       // Relay OFF
        std::function<void(int)> set_fan;       // Fan speed 0-100
    };

private:
    IO io_;
    UpdateCallback on_update_;

    float target_temp_ = 25.0f;
    float integrate_ = 0.0f;
    float prev_error_ = 0.0f;
    bool at_temp_ = false;

    // Delta-Sigma DAC state
    float dac_accum_ = 0.0f;
    bool dac_last_ = false;

    std::atomic<bool> running_{false};
    std::thread loop_thread_;
    std::thread fan_off_thread_;
    mutable std::mutex mutex_;

    // ----------------------------
    // Delta-Sigma DAC for heater
    // ----------------------------
    void run_heater_dac(float set_val) {
        float v = std::max(0.0f, std::min(1.0f, set_val));

        float delta = dac_last_ ? (v - 1.0f) : v;
        float sig = dac_accum_ + delta;
        bool out = sig > 0.5f;

        dac_last_ = out;
        dac_accum_ = sig;

        if (out) {
            io_.heater_on();
        } else {
            io_.heater_off();
        }
    }

    // ----------------------------
    // Main PI loop (runs at 20Hz)
    // ----------------------------
    void loop() {
        printf("[TempCtrl] Starting loop, target=%.2f°C\n", target_temp_);

        while (running_) {
            try {
                float temp = io_.read_temp_c();

                if (std::isnan(temp)) {
                    printf("[TempCtrl] No temperature reading, skipping\n");
                    std::this_thread::sleep_for(std::chrono::seconds(1));
                    continue;
                }

                float error = target_temp_ - temp;

                // Integrator with clamping
                integrate_ += CTL_I * error;
                integrate_ = std::max(INTEGRATOR_MIN, std::min(integrate_, INTEGRATOR_MAX));

                // PID
                float prop = CTL_P * error;
                float deriv = CTL_D * (error - prev_error_);
                prev_error_ = error;

                float control = prop + integrate_ + deriv;

                // Heater power
                float power = std::max(0.0f, std::min(1.0f, control));
                run_heater_dac(power);

                at_temp_ = std::abs(error) < 1.5f;

                // Notify UI
                if (on_update_) {
                    on_update_(temp, target_temp_, at_temp_, power > 0);
                }

                printf("[TempCtrl] T=%.2f target=%.2f err=%.2f ctl=%.3f atTemp=%d\n",
                       temp, target_temp_, error, control, at_temp_);

            } catch (...) {
                printf("[TempCtrl] Error in control loop\n");
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    }

public:
    TemperatureController(IO io) : io_(std::move(io)) {}

    ~TemperatureController() {
        stop();
    }

    // ----------------------------
    // Set update callback for UI
    // ----------------------------
    void set_update_callback(UpdateCallback cb) {
        on_update_ = std::move(cb);
    }

    // ----------------------------
    // Set target temperature
    // ----------------------------
    void set_target(float temp_c) {
        std::lock_guard<std::mutex> lock(mutex_);
        target_temp_ = temp_c;
    }

    float get_target() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return target_temp_;
    }

    bool is_at_temp() const { return at_temp_; }
    bool is_running() const { return running_; }

    // ----------------------------
    // Start heating
    // ----------------------------
    void start(float target_c = -1) {
        if (target_c >= 0) {
            set_target(target_c);
        }

        if (running_) return;

        // Fan ON when heating starts
        printf("[TempCtrl] Heating started — FAN ON\n");
        io_.set_fan(100);

        running_ = true;
        loop_thread_ = std::thread(&TemperatureController::loop, this);
    }

    // ----------------------------
    // Stop heating + 10 min fan cooldown
    // ----------------------------
    void stop() {
        running_ = false;

        if (loop_thread_.joinable()) {
            loop_thread_.join();
        }

        // Heater OFF immediately
        io_.heater_off();
        printf("[TempCtrl] Heating stopped — Heater OFF\n");

        // Notify UI
        if (on_update_) {
            float temp = io_.read_temp_c();
            on_update_(temp, target_temp_, false, false);
        }

        // Fan cooldown at 60% for 10 minutes
        printf("[TempCtrl] FAN cooldown at 60%% for 10 min\n");
        io_.set_fan(60);

        // Detach previous fan-off thread if any
        if (fan_off_thread_.joinable()) {
            fan_off_thread_.detach();
        }

        fan_off_thread_ = std::thread([this]() {
            std::this_thread::sleep_for(std::chrono::minutes(10));
            printf("[TempCtrl] 10 min passed — FAN OFF\n");
            io_.set_fan(0);
        });
        fan_off_thread_.detach();
    }

    // ----------------------------
    // Reset integrator (call on target change)
    // ----------------------------
    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        integrate_ = 0.0f;
        prev_error_ = 0.0f;
        dac_accum_ = 0.0f;
        dac_last_ = false;
    }
};

} // namespace scure
