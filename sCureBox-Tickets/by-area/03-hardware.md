# 03 - Hardware area (SCureBox.Hardware)

## Hardware — overview

`src/SCureBox.Hardware` (namespace root `SCureBox.Hardware`) is the hardware abstraction of the sCure appliance: a Raspberry Pi CM5 on the sCure IO board **BRD-74205 rev07**. It exposes ONE facade, `IHardwareSystem`, with two implementations: `IoBoardHardwareSystem` (the real board: PCA9685 + TCA6424A + two ADS1115 over Linux I2C, GPIO via libgpiod, damper servo + RGB strip via RP1-PIO helper processes) and `SimulatedHardwareSystem` (deterministic model driven by a `TimeProvider`). Every write in production goes through `Safety.FreezableHardwareSystem` (DVT hang gate). A separate process mode (`scurebox --watchdog`, `Safety.OutputWatchdog`) cuts heater + UV LEDs when the firmware heartbeat goes stale. The live machine configuration comes from `components.json` (`IHardwareConfig`, hot-reloaded every 1 s).

Build settings (repo `Directory.Build.props`, applies to every project): `net10.0`, `Nullable=enable`, `ImplicitUsings=enable`, `LangVersion=latest`, `TreatWarningsAsErrors=true` (except CS1591, xUnit1004), `InvariantGlobalization=true`, `NoWarn CA1416`.

Csproj `src/SCureBox.Hardware/SCureBox.Hardware.csproj`: packages `System.Device.Gpio 4.2.0`, `Iot.Device.Bindings 4.2.0`, `Microsoft.Extensions.Logging.Abstractions 10.0.13`, `Microsoft.Extensions.DependencyInjection.Abstractions 10.0.13`; ProjectReference `../SCureBox.Domain/SCureBox.Domain.csproj`; `<InternalsVisibleTo Include="SCureBox.Hardware.Tests" />`.

Test project `tests/SCureBox.Hardware.Tests/SCureBox.Hardware.Tests.csproj`: `Microsoft.NET.Test.Sdk 18.11.0`, `xunit 2.9.3`, `xunit.runner.visualstudio 4.0.1`, `coverlet.collector 10.1.0`, `Microsoft.Extensions.TimeProvider.Testing 10.11.0`; references the Hardware project. Tests read the repo's `config/components.json` through `TestPaths.ComponentsJson()` (walk up from `AppContext.BaseDirectory` until `config/components.json` exists, else `FileNotFoundException`).

Types used from the **Domain** area (must exist there; names exact): `SCureBox.Domain.Models`: `enum Fan { FAN_HEATER, FAN_DOOR, FAN_RIGHT, FAN_LEFT, FAN_BACK, FAN_COOLING }`, `enum LedPanel { LED_BACK, LED_DOOR, LED_RIGHT, LED_LEFT }`, `enum TempSensor { TEMP_RIGHT, TEMP_LEFT, TEMP_BACK, TEMP_DOOR, TEMP_CHAMBER }`, `enum UvSensor { UV_LEFT, UV_RIGHT }`, `enum Wavelength { Nm405 = 405, Nm450 = 450 }` with `ModeName()` ("405nm"/"450nm") and `WavelengthExtensions.TryParse(int nm, out Wavelength)`, `enum CoolingMode { Fast, Medium, Slow }` with `Wire()` ("fast"/"medium"/"slow"), `HardwareNames.LedFan` (LED_LEFT->FAN_LEFT, LED_RIGHT->FAN_RIGHT, LED_BACK->FAN_BACK, LED_DOOR->FAN_DOOR), `UvSensor.Panel()` (UV_LEFT->LED_LEFT, UV_RIGHT->LED_RIGHT). `SCureBox.Domain.Sensors`: `NtcMath` (R0 10000, Beta 3934, T0Kelvin 298.15, RSeries 10000, VRef 3.3, `VoltageToTemperature(double) -> double?`, null when v<=0 or v>=VRef), `ChamberTempCalibration(TimeProvider)` with `Correct(double rawC)`, `PressureConversion.Convert(double vAdc, PressureSensorParameters)` -> `PressureResult(VAdc, VSensor, Mpa, Bar, On, Saturated, Mode, SetPointMpa)`, `PressureConversion.MpaToBar = 10.0`, `PressureSensorParameters(Mode, VMin, VMax, IMinMa, IMaxMa, ShuntOhms, PAtLowMpa, PAtHighMpa, Divider, AdcSaturationVolts, OnAboveVolts, SetPointMpa)` with constants `ModeAnalogVoltage="analog_voltage"`, `ModeAnalogCurrent="analog_current"`, `ModeSwitch="switch"`. `SCureBox.Domain.Control`: `TachRateTracker<TKey>(int pulsesPerRev)` with `int? Rpm(TKey, long count, double nowSec)` (MinWindowSec 1.0, SampleSpacingSec 0.1), `SensorGlitchHold<TKey,TValue>` with `TimeSpan? Good(key, value, now)` / `GlitchVerdict Bad(key, now, holdSec, out TValue? held)`, `enum GlitchVerdict { Report, HoldStarted, Holding, HoldExpired }`, `WatchdogMonitor(double timeoutSec = 20, double recutSec = 5)` with `WatchdogEvent Step(long? heartbeatTickMs, long nowTickMs)`, `enum WatchdogEvent { None, Armed, Tripped, Recut, Recovered, Disarmed }`, `FanHealthEvaluator.ExpectedRpm(IReadOnlyList<(double duty, double rpm)>? points, double duty) -> double?` (linear interpolation between points, proportional (rpm*duty/pointDuty) below the lowest / above the highest point, null for no points).

### Hardware channel map (IO board BRD-74205 rev07, as used by the code)

**Buses / chips**

| Chip | Board ref | Linux bus | 7-bit addr | Used for | Driver class |
|---|---|---|---|---|---|
| PCA9685 16-ch 12-bit PWM | U15 | `/dev/i2c-0` (GPIO0/1, `dtparam=i2c_vc=on`) | 0x55 | fans, heater SSR, chamber light, motor enables, BOFA speed ref, UV LED DIM | `Pca9685` |
| TCA6424A 24-bit IO expander | U1 | `/dev/i2c-0` | 0x23 | LED_SWITCH relay K4, door magnet/valves, motor direction, NFC reset | `Tca6424a` |
| ADS1115 16-bit ADC | U6 | `/dev/i2c-0` | 0x49 | UV photoresistors, Left/Right panel NTCs (PGA 1, +/-4.096 V) | `Ads1115` |
| ADS1115 16-bit ADC | U7 | `/dev/i2c-1` (GPIO2/3, `dtparam=i2c_arm=on`) | 0x49 | Back/Door/Chamber NTCs + N2 pressure (PGA 1) | `Ads1115` |
| ADS1115 | U8 | `/dev/i2c-0` | 0x48 | analog sensors - NOT used by the C# code | - |
| ADS1115 | U10 | `/dev/i2c-1` | 0x48 | light sensors - NOT used by the C# code | - |

All I2C transactions of the process share ONE global lock (`SystemDeviceI2cBus.GlobalLock`).

**PCA9685 channels (0x55)** - logical duty 0..100 %; "inverted" = the board has an inverting driver stage, the code writes 100-duty.

| Ch | Name | Function | Inverted | Notes |
|---|---|---|---|---|
| 0 | FAN_HEATER | heater fan PWM | yes | tach GPIO22 |
| 1 | FAN_DOOR | door LED-panel fan | yes | tach GPIO23 |
| 2 | FAN_RIGHT | right LED-panel fan | yes | tach GPIO24 |
| 3 | FAN_LEFT | left LED-panel fan | yes | tach GPIO19 |
| 4 | FAN_BACK | back LED-panel fan | yes | tach GPIO25 |
| 5 | FAN_COOLING | chamber cooling / intake fan | yes | tach GPIO26 |
| 6 | PWM_HEATER | heater SSR K3 | no | DIGITAL: any duty>0 = full on |
| 7 | LIGHT1 | chamber light | yes | `SetLight` writes 100/0 |
| 8 | MOT1_EN | L298N enable 1 | yes | not driven by the facade (safe state 0) |
| 9 | MOT2_EN | L298N enable 2 | yes | not driven by the facade (safe state 0) |
| 10 | BOFA | extraction-fan 0-10 V speed reference (RC-filtered, x3.3 op-amp U18B on 12 V rail) | no | 60 % channel duty = 10 V (`bofa.max_duty`) |
| 11 | LED_BACK | UV LED driver DIM | no | 405 nm only |
| 12 | LED_DOOR | UV LED driver DIM | no | 405 + 450 nm |
| 13 | LED_RIGHT | UV LED driver DIM | no | 405 nm only |
| 14 | LED_LEFT | UV LED driver DIM | no | 405 nm only |
| 15 | LED_ANALOG5 | unused | no | safe state 0 |

Register write per channel: 4-byte block at `0x06 + 4*ch` = `[on & 0xFF, on >> 8, off & 0xFF, off >> 8]`; full-on `(on=0x1000, off=0)`, full-off `(0, 0x1000)`, partial `(0, (int)(eff/100*4095))` (truncation). LED brightness: physical duty = percent * `led_max_duty`(60) / 100. BOFA: channel duty = percent * `bofa.max_duty`(60) / 100.

**TCA6424A pins (0x23)** - registers with auto-increment bit: INPUT 0x80, OUTPUT 0x84, CONFIG 0x8C (3 bytes each, ports 0..2; CONFIG bit 1 = input).

| Pin | Port.bit | Function | Polarity |
|---|---|---|---|
| NFC_RESET | P0.1 | NFC reader reset | active low; safe = HIGH |
| LED_SWITCH | P0.5 | -> Q28 -> relay K4 (selects LED_OUT1/LED_OUT2 at J21) | 1 while 405 nm runs, 0 at rest / 450 nm |
| FAN1_ONOFF..FAN6_ONOFF | P1.1..P1.6 | fan on/off (unused by facade) | inverted (logical 1 = LOW) |
| MOT1_IN1 / MOT1_IN2 | P2.5 / P2.4 | motor 1 direction | - |
| MOT2_IN1 / MOT2_IN2 | P2.2 / P2.1 | motor 2 direction | - |
| VALVE_2_ON = DOOR_MAGNET | P2.6 | valve 2 output = door magnet (J8_DOOR_MAGNET) | active high |
| VALVE_1_ON | P2.7 | valve 1 | active high |

Safe-init bytes: OUTPUT `[0x02, 0x7E, 0x00]` written first, then CONFIG `[0xDD, 0x81, 0x09]`.

**ADS1115 channels** (single-ended, PGA 1 = +/-4.096 V, 128 SPS, single shot)

| Signal | ADC | Bus | AIN | Conversion |
|---|---|---|---|---|
| UV_RIGHT (right panel photoresistor) | U6 | i2c-0 | 0 | volts only (~2.8 V dark, lower when lit) |
| TEMP_RIGHT (right panel NTC) | U6 | i2c-0 | 1 | NTC -> deg C |
| UV_LEFT (left panel photoresistor) | U6 | i2c-0 | 2 | volts only |
| TEMP_LEFT (left panel NTC) | U6 | i2c-0 | 3 | NTC -> deg C |
| TEMP_BACK | U7 | i2c-1 | 0 | NTC -> deg C |
| TEMP_DOOR | U7 | i2c-1 | 1 | NTC -> deg C |
| TEMP_CHAMBER | U7 | i2c-1 | 2 | NTC -> deg C -> `ChamberTempCalibration.Correct` |
| N2 pressure (SMC ISE20A analog, via R86 120 R) | U7 | i2c-1 | 3 | `PressureConversion.Convert` |

Volts = raw(int16) * FS[pga] / 32768, FS = {0: 6.144, 1: 4.096, 2: 2.048, 3: 1.024, 4: 0.512, 5: 0.256}. NTC (Murata NCP21XV103J03RA, 10 k pull-up to 3.3 V): R = 10000*v/(3.3-v); 1/T = 1/298.15 + ln(R/10000)/3934; degC = T-273.15; v<=0 or v>=3.3 -> null (open/short). 1.65 V = 25.0 degC. Pressure (shipped config analog_voltage): MPa linear through (1.0 V, 0.0 MPa) and (5.0 V, 1.0 MPa) i.e. 4 V per MPa; bar = MPa*10; saturated above 3.2 V (Mpa null); On = MPa >= set_point_mpa (0.1).

**CM5 GPIO** (RP1 `/dev/gpiochipN`, chip auto-detected, usually 0)

| GPIO | Dir | Function | Notes |
|---|---|---|---|
| 6 | out | `4DA_BOFA_EN` extraction fan 24 V high-side MOSFET (J24 pin 31) | opened LOW; `bofa.enable_gpio` |
| 8 | out (PIO / soft PWM) | damper servo MG90S via inverting transistor Q16 | `servo.gpio`, signal_inverted=true |
| 12 | out (PIO) | RGB status strip TM1903/WS2811, 21 LEDs, RGB order | `rgb.gpio` |
| 13 | out | nitrogen solenoid valve | active high, opened LOW |
| 16 | out | 450 nm LED supply SSR (K1) | `led_power.ssr_450nm` |
| 17 | out | voltage-routing line; kept LOW in both modes (HIGH kills the door DIM 12 V rail) | `led_power.routing`, read back |
| 18 | in, no pull (ext. R134 4.75k pull-up) | `4DA_BOFA_PRESENT` (J24 pin 12) | `bofa.present_gpio`, active low assumed |
| 19, 22, 23, 24, 25, 26 | in, pull-up, rising-edge counted | fan tachometers (LEFT, HEATER, DOOR, RIGHT, BACK, COOLING) | 2 pulses / revolution |
| 20 | out | 405 nm LED supply SSR (K2) | `led_power.ssr_405nm` |
| 27 | in, no pull (ext. R46) | door sensor; HIGH = closed, LOW = open | `door_sensor.open_level` 0 |

Servo pulse: logical angle a' = 180 - angle; pulse_us = round(500 + a'/180*1900); logical 0 deg = 2400 us, 90 deg = 1450 us, 180 deg = 500 us; period 20000 us. Damper open = 0 deg (2400 us), closed = 90 deg (1450 us) from `cooling.damper_open_angle` / `damper_closed_angle`.

**Notes on docs vs code** (code wins, the rebuild must follow the code): `docs/02-hardware-map.md` still says damper open = 90 / closed = 0 (code + config: open 0 / closed 90 since 2026-10-26); it says `ReadRpm` = delta since last call (code: shared >=1 s window via `TachRateTracker`); it lists old FAN_HEATER nominal RPMs (code: 30:2363, 50:3669, 80:5227, 100:5925); it says door magnet released after 2.0 s (the hardware layer does NOT auto-release; the release timer lives in Application-Process `CureController.OpenDoor`); it mentions `busy` purple comet (shipped config: blue solid). `Pca9685.SetFrequency` exists but is never called in production: the chip runs at its power-on prescale (doc: ~200 Hz). OPEN QUESTION: whether the PWM frequency should be set explicitly.

---

### HW-01 — Hardware facade contract (IHardwareSystem, exceptions, PressureReading)
**Summary**
- **What it is for:** One shared interface that the rest of the software uses to control and read all hardware in the sCure Box: fans, heater, sensors, UV LEDs, valves, door, damper and lights.
- **Problem it solves:** Without one clear contract, each part of the app would talk to the hardware in its own way, and the real board and the simulator could behave differently.
- **How we solve it:** We define one interface plus two error types: one for safety refusals (for example, door not closed) and one for failed writes or bus errors. The real board and the simulator both implement it.

**Project / folder:** `src/SCureBox.Hardware/SCureBox.Hardware.csproj`, project root folder
**Goal:** Define the single interface the application layer uses for every hardware action and reading, plus the two exception types that signal refusals and verification/bus failures. Both the real board (HW-11/HW-12) and the simulation (HW-15) implement it; `FreezableHardwareSystem` (HW-13) decorates it.
**Depends on:** HW-02 (IHardwareConfig); Domain (Fan, TempSensor, UvSensor, LedPanel, Wavelength)
**Files to create:**
- `src/SCureBox.Hardware/SCureBox.Hardware.csproj` (see overview)
- `src/SCureBox.Hardware/IHardwareSystem.cs` - `public interface IHardwareSystem : IDisposable`, `public sealed record PressureReading`, `public sealed class HardwareRefusedException`, `public sealed class HardwareVerifyException`
**Public contract:**
```csharp
namespace SCureBox.Hardware;
public interface IHardwareSystem : IDisposable
{
    string Source { get; }               // "io_controller" (real) / "simulation"
    bool IsSimulated { get; }
    IHardwareConfig Config { get; }
    void StartupSafe();
    void AllSafe();
    void SetFanDuty(Fan fan, int percent, bool verify = true);
    int GetFanDuty(Fan fan);
    int? ReadRpm(Fan fan);
    int MeasureRpm(Fan fan, TimeSpan window);
    void SetHeaterElement(bool on);
    bool GetHeaterElement();
    double? ReadTemperature(TempSensor sensor);
    double ReadTemperatureVolts(TempSensor sensor);
    double ReadUvSensorVolts(UvSensor sensor);
    PressureReading ReadPressure();
    bool? DoorOpen();                    // true open, false closed, null unreadable
    void SetLed(LedPanel led, double percent);
    void AllLedsOff();
    void SelectMode(Wavelength wavelength);
    void LedPowerOff();
    IReadOnlyList<LedPanel> AllowedLeds(Wavelength wavelength);
    IReadOnlyDictionary<LedPanel, double> LedLevels { get; }
    Wavelength? ActiveMode { get; }
    void SetNitrogenValve(bool on);
    bool GetNitrogenValve();
    void SetBofa(bool on);
    bool GetBofa();
    void SetBofaDuty(int percent);
    int GetBofaDuty();
    void SetBofaPower(bool on);
    bool GetBofaPower();
    bool? BofaPresent();
    void SetDoorMagnet(bool on);
    void SetDamper(bool open);
    bool? DamperOpen { get; }
    string? DamperDriver { get; }        // "pio" / "lgpio", null until first driven
    void SetLight(bool on);
    void NfcReset();
    void RgbFill(ReadOnlySpan<int> colors);   // one 0xRRGGBB per LED, length == Config.Rgb.Count
    void RgbOff();
    string? DriverFault { get; }         // last driver fault, null when healthy
}
public sealed record PressureReading(double Volts, double? Mpa, double? Bar, bool On, bool Saturated, string Mode, double SetPointMpa);
public sealed class HardwareRefusedException : Exception { public HardwareRefusedException(string message); }
public sealed class HardwareVerifyException : Exception { public HardwareVerifyException(string message); public HardwareVerifyException(string message, Exception inner); }
```
**Behaviour & rules:**
1. All members must be thread-safe; compound register sequences are serialised on one lock inside the implementation.
2. Refusals (door not confirmed closed, LED not allowed in the wavelength, routing read-back mismatch, LED_SWITCH not confirmed, DVT hang drop) throw `HardwareRefusedException`. Read-back mismatch after retries or I2C/bus errors throw `HardwareVerifyException`.
3. `DoorOpen()` null must never be treated as "open" or as "closed" by callers; LEDs require it to be exactly `false`.
4. `ReadRpm` is non-blocking and returns the same value to every reader (shared window >= 1 s); null until a first window exists. `MeasureRpm` blocks for `window`.
5. `SetLed` takes a *physical* brightness percent; it enforces min intensity, door closed, wavelength gating and the SSR turn-on order, and starts/stops the panel's fan.
6. The hardware layer itself raises no numeric error codes; the Api/Application layers map `HardwareRefusedException` to code 6015 (`ErrorCodes.HardwareRefused`).
**Configuration:** none (exposes `Config`).
**Acceptance criteria:**
- The interface compiles with exactly the members above (names and signatures exact).
- `PressureReading` is a positional record with the 7 fields in the order given.
**Tests:** covered through `IoBoardHardwareSystemTests` and `SimulatedHardwareSystemTests` (HW-11, HW-12, HW-15).
**Reference (source):** `src/SCureBox.Hardware/IHardwareSystem.cs`, `src/SCureBox.Hardware/SCureBox.Hardware.csproj`

---

### HW-02 — Hardware configuration (components.json, IHardwareConfig, hot reload)
**Summary**
- **What it is for:** Reads the machine settings file (components.json) that holds pins, fan speeds, heating values, LED rules, colors and sensor limits.
- **Problem it solves:** Settings must change without rebuilding or restarting the software, and a missing or broken file must not stop the machine.
- **How we solve it:** Every setting has a built-in default. The file is checked at most once a second and re-read when it changes. Bad or missing values fall back to the last good settings or the defaults.

**Project / folder:** `SCureBox.Hardware.csproj`, root + `Config/`
**Goal:** Provide a typed, hot-reloaded view of `components.json` with built-in defaults for every key. The file's mtime is checked at most once per second and re-parsed on change, so edits apply without restart; a missing or broken file keeps the last good snapshot (or defaults).
**Depends on:** Domain (enums, `Wavelength` parse, `CoolingMode.Wire()`, `HardwareNames.LedFan`)
**Files to create:**
- `src/SCureBox.Hardware/IHardwareConfig.cs` - `public interface IHardwareConfig` + all public config records
- `src/SCureBox.Hardware/Config/HardwareConfig.cs` - `public sealed class HardwareConfig : IHardwareConfig`
- `src/SCureBox.Hardware/Config/HardwareConfigSnapshot.cs` - `internal sealed record HardwareConfigSnapshot`
- `src/SCureBox.Hardware/Config/ComponentsJsonParser.cs` - `internal static class ComponentsJsonParser`
- `src/SCureBox.Hardware/Config/JsonSectionExtensions.cs` - `internal static class JsonSectionExtensions`
**Public contract:**
```csharp
public interface IHardwareConfig {
    string Path { get; } TimeSpan ReloadInterval { get; } void Reload();
    LedPowerConfig LedPower { get; } DoorSensorConfig DoorSensor { get; } IReadOnlyDictionary<LedPanel, LedConfig> Leds { get; }
    RgbConfig Rgb { get; } FanHealthConfig FanHealth { get; } LedHeatingConfig LedHeating { get; } FrozenReadingConfig FrozenReading { get; }
    NoHeatConfig NoHeat { get; } HeaterConfig Heater { get; } HeatingConfig Heating { get; } ServoConfig Servo { get; }
    CoolingConfig Cooling { get; } VentilationConfig Ventilation { get; } PressureSensorConfig PressureSensor { get; }
    SensorFilterConfig SensorFilter { get; } UvLightCheckConfig UvLightCheck { get; } BofaConfig Bofa { get; }
}
public sealed record LedModeConfig(bool Ssr450, bool Ssr405, bool Routing, bool LedSwitch, int? LedFanPwm = null);
public sealed record LedPowerConfig(int Ssr450Gpio, int Ssr405Gpio, int RoutingGpio, Wavelength DefaultMode, double SwitchSettleSec,
    double MinIntensity, double LedMaxDuty, IReadOnlyDictionary<Wavelength, LedModeConfig> Modes)
{ public static LedPowerConfig Default { get; } public int LedFanSpeed(LedConfig led, Wavelength? mode); }
public sealed record DoorSensorConfig(int Gpio, int OpenLevel, double AbortAfterSec);
public sealed record LedConfig(Fan Fan, int FanSpeed, double Intensity, IReadOnlyList<Wavelength> Modes);
public sealed record RgbStatusColors(string Normal, string Fault, string DoorOpen, string Busy, string Warning, string ManualHeat,
    int Brightness, double BlinkSec, double ChaseSec, int ChaseTail, string BusyStyle, string BusyDirection, double StatusSec, double InternetCheckSec);
public sealed record RgbConfig(int Gpio, int Count, string Order, RgbStatusColors Status);
public sealed record FanNominalPoint(int Duty, int Rpm);
public sealed record FanHealthConfig(double WarnBelowPct, double CriticalBelowPct, double PersistSec, double SettleSec, int MinEvalDuty,
    double StoppedPersistSec, int LedFanMinRpm, IReadOnlyDictionary<Fan, IReadOnlyList<FanNominalPoint>> NominalRpm,
    IReadOnlyDictionary<Fan, IReadOnlyList<FanNominalPoint>>? NominalRpmDamperOpen = null,
    IReadOnlyDictionary<Fan, double>? CriticalBelowPctByFan = null)
{ public static IReadOnlyDictionary<Fan,double> DefaultCriticalByFan { get; } public static IReadOnlyDictionary<Fan, IReadOnlyList<FanNominalPoint>> DefaultDamperOpen { get; } public static FanHealthConfig Default { get; } }
public sealed record LedHeatingConfig(double MinEvalIntensity, double CheckAfterSec, double MinRiseC, double RestSec, double DropC,
    double DropPersistSec, double DropSettleSec, IReadOnlyDictionary<LedPanel, TempSensor> Panels, bool Enabled);
public sealed record FrozenReadingConfig(bool Enabled, double WindowSec, double MinDeltaC, double MinDutyPct, double RebootAfterSec);
public sealed record BofaConfig(double MaxDuty, int EnableGpio, int PresentGpio, bool PresentActiveLow);
public sealed record UvLightCheckConfig(bool Enabled, double MinIntensity, double ConfirmSec, double LitRatio);
public sealed record NoHeatConfig(bool Enabled, double WindowSec, double MinRiseC, double MinDutyPct);
public sealed record HeaterConfig(int FanPwm, int MinFanRpm, double HealthCheckSec, TempSensor Thermistor, double TempValidMin, double TempValidMax);
public sealed record HeatingConfig(double TargetTemp, double TargetMin, double SampleSec, double Kp, double Ki, double Kd,
    double IntegMax, double IntegMin, double AtTempBand, double CooldownSec, int CooldownFanPwm);
public sealed record ServoConfig(int Gpio, string Driver, bool SignalInverted, double SettleSec, string? PioHelper);
public sealed record CoolingConfig(int DamperOpenAngle, int DamperClosedAngle, int HeaterFanPwm, IReadOnlyDictionary<CoolingMode, int> ModePwms,
    int FastLedFanPwm, double TargetTemp, double SampleSec, double WindowSec);
public sealed record VentilationConfig(int FanPwm);
public sealed record PressureSensorConfig(string Mode, double VMin, double VMax, double IMinMa, double IMaxMa, double ShuntOhms,
    double PAtLowMpa, double PAtHighMpa, double Divider, double AdcSaturationVolts, double OnAboveVolts, double SetPointMpa,
    double MaxBar = DefaultMaxBar, double MinBar = DefaultMinBar, bool FlowCheckEnabled = true,
    double FlowCheckWindowSec = DefaultFlowCheckWindowSec, double FlowCheckMinDropBar = DefaultFlowCheckMinDropBar,
    bool Required = true, double NotReadingAfterSec = DefaultNotReadingAfterSec)
{ public const double DefaultNotReadingAfterSec = 20.0; public const double RangeTolerance = 0.10; public const double DefaultFlowCheckWindowSec = 5.0;
  public const double DefaultFlowCheckMinDropBar = 0.3; public const double DefaultMaxBar = 3.0; public const double DefaultMinBar = 0.5; }
public sealed record SensorFilterConfig(double GlitchHoldSec);
// Every record above (except FanNominalPoint, LedConfig, LedModeConfig) has `public static X Default`.
namespace SCureBox.Hardware.Config;
public sealed class HardwareConfig : IHardwareConfig {
    public HardwareConfig(string path, TimeProvider? timeProvider = null, ILogger<HardwareConfig>? logger = null);
    public static HardwareConfig FromJson(string json, TimeProvider? timeProvider = null);   // fixed snapshot, Path "<inline>", Reload is a no-op
}
internal static class ComponentsJsonParser {
    public static IReadOnlyDictionary<LedPanel, LedConfig> DefaultLeds { get; }
    public static HardwareConfigSnapshot Parse(string json); public static HardwareConfigSnapshot Parse(JsonElement root);
    public static bool TryParseWavelength(string? s, out Wavelength w);
}
internal sealed record HardwareConfigSnapshot(LedPowerConfig LedPower, DoorSensorConfig DoorSensor, IReadOnlyDictionary<LedPanel, LedConfig> Leds,
    RgbConfig Rgb, FanHealthConfig FanHealth, LedHeatingConfig LedHeating, FrozenReadingConfig FrozenReading, NoHeatConfig NoHeat,
    HeaterConfig Heater, HeatingConfig Heating, ServoConfig Servo, CoolingConfig Cooling, VentilationConfig Ventilation,
    PressureSensorConfig PressureSensor, SensorFilterConfig SensorFilter, UvLightCheckConfig UvLightCheck, BofaConfig Bofa)
{ public static HardwareConfigSnapshot Default { get; } }
internal static class JsonSectionExtensions {   // tolerant readers
    JsonElement? Section(this JsonElement parent, string key); JsonElement? Section(this JsonElement? parent, string key);
    double Double(this JsonElement? o, string key, double fallback); int Int(...); bool Bool(...); string String(...);
    string? OptionalString(this JsonElement? o, string key); IEnumerable<string> Strings(this JsonElement? o, string key);
}
```
**Behaviour & rules:**
1. Defaults (exact):
   - `LedPowerConfig.Default` = (16, 20, 17, Nm405, 0.1, 10, 60, { Nm450: (true,false,false,false, LedFanPwm 30), Nm405: (true,true,false,true, null) }).
   - `LedFanSpeed(led, mode)` = mode's `LedFanPwm` when mode non-null, present in `Modes` and `LedFanPwm` non-null, else `led.FanSpeed`.
   - `DoorSensorConfig.Default` = (27, 0, 10).
   - `RgbStatusColors.Default` = ("green","red","ff7800","blue","blue","yellow","ff8c00", 100, 0.5, 0.12, 5, "solid", "rtl", 1.0, 5.0); `RgbConfig.Default` = (12, 21, "RGB", that).
   - `FanHealthConfig.Default` = (10, 20, 60, 5, 30, 5, 100, nominal, DefaultDamperOpen, DefaultCriticalByFan) with nominal FAN_HEATER {30:2363, 50:3669, 80:5227, 100:5925}, FAN_COOLING {30:1235, 60:2690, 100:4790}, FAN_LEFT/RIGHT/BACK/DOOR {100:3560}; `DefaultDamperOpen` = FAN_COOLING {60:2470, 100:4075}; `DefaultCriticalByFan` = {FAN_HEATER: 11.8}.
   - `LedHeatingConfig.Default` = (30, 90, 1.0, 120, 1.0, 30, 120, {LED_LEFT: TEMP_LEFT, LED_RIGHT: TEMP_RIGHT}, Enabled false).
   - `FrozenReadingConfig.Default` = (true, 90, 0.01, 50, 60). `NoHeatConfig.Default` = (true, 600, 0.5, 99). `UvLightCheckConfig.Default` = (true, 10, 5, 0.6). `BofaConfig.Default` = (60, 6, 18, true).
   - `HeaterConfig.Default` = (100, 100, 10, TEMP_CHAMBER, -20, 120). `HeatingConfig.Default` = (60, 30, 0.05, 0.22, 0.00015, 0, 0.85, 0, 1.5, 900, 30).
   - `ServoConfig.Default` = (8, "auto", true, 1.5, null). `CoolingConfig.Default` = (0, 90, 100, {Fast:100, Medium:60, Slow:30}, 100, 25, 1.0, 30). `VentilationConfig.Default` = (60).
   - `PressureSensorConfig.Default` = ("analog_voltage", 1.0, 5.0, 4.0, 20.0, 120.0, 0.0, 1.0, 1.0, 3.2, 2.0, 0.6) + record defaults (MaxBar 3.0, MinBar 0.5, FlowCheckEnabled true, 5.0, 0.3, Required true, 20.0). `SensorFilterConfig.Default` = (15.0).
   - `DefaultLeds`: LED_LEFT (FAN_LEFT,100,100,[Nm405]), LED_RIGHT (FAN_RIGHT,...,[Nm405]), LED_BACK (FAN_BACK,...,[Nm405]), LED_DOOR (FAN_DOOR,100,100,[Nm405, Nm450]).
2. JSON parse: `JsonDocumentOptions { AllowTrailingCommas = true, CommentHandling = Skip }`. Missing sections/keys -> defaults; wrong-typed keys -> default; unknown keys and `_comment*` ignored.
3. Tolerant readers: `Section` returns the child only if it is a JSON object. `Double` accepts a number or a numeric string (invariant culture). `Int` = `(int)Math.Round(Double(...))`. `Bool` accepts true/false or a number (non-zero = true). `String`/`OptionalString` only for JSON strings. `Strings` yields the string items of an array.
4. Key mapping (section -> key -> field):
   - `led_power`: `ssr_450nm`, `ssr_405nm`, `routing` (GPIO numbers), `default_mode` (wavelength string), `switch_settle_sec`, `min_intensity`, `led_max_duty`, `modes` object keyed by wavelength string; each mode: `ssr_450nm`, `ssr_405nm`, `routing`, `led_switch` (bool/0-1), `led_fan_pwm` (int clamped 0..100; absent/negative -> keep old/none). Mode entries merge over the defaults (start from existing mode or all-false).
   - `door_sensor`: `gpio`, `open_level`, `abort_after_sec`.
   - `leds`: object keyed by exact `LedPanel` name (case-sensitive); unknown names skipped; each: `fan` (Fan name), `fan_speed`, `intensity`, `modes` (string array; invalid entries dropped, distinct; empty -> old). If the section yields no valid LED the defaults are kept.
   - `rgb`: `gpio`, `count`, `order` (upper-cased), `status`: `normal`, `fault`, `door_open`, `busy`, `warning`, `manual_heat`, `brightness`, `blink_sec`, `chase_sec`, `chase_tail`, `busy_style`, `busy_direction`, `status_sec`, `internet_check_sec`.
   - `fan_health`: `warn_below_pct`, `critical_below_pct`, `persist_sec`, `settle_sec`, `min_eval_duty`, `stopped_persist_sec`, `led_fan_min_rpm`, `nominal_rpm` and `nominal_rpm_damper_open` (`{ "FAN_X": { "<duty>": rpm } }`; a fan given replaces its default points; points sorted by duty; rpm rounded), `critical_below_pct_by_fan` (`{ "FAN_X": pct }` over the defaults).
   - `led_heating`: `enabled`, `min_eval_intensity`, `check_after_sec`, `min_rise_c`, `rest_sec`, `drop_c`, `drop_persist_sec`, `drop_settle_sec`, `panels` (`{ "LED_X": "TEMP_Y" }` replaces the defaults; if none valid -> defaults).
   - `frozen_reading`: `enabled`, `window_sec`, `min_delta_c`, `min_duty_pct`, `reboot_after_sec`. `no_heat`: `enabled`, `window_sec`, `min_rise_c`, `min_duty_pct`. `uv_light_check`: `enabled`, `min_intensity`, `confirm_sec`, `lit_ratio`.
   - `heater`: `fan_pwm`, `min_fan_rpm`, `health_check_sec`, `thermistor` (TempSensor name), `temp_valid_min`, `temp_valid_max`.
   - `heating`: `target_temp`, `target_min`, `sample_sec`, `kp`, `ki`, `kd`, `integ_max`, `integ_min`, `at_temp_band`, `cooldown_sec`, `cooldown_fan_pwm`.
   - `servo`: `gpio`, `driver` (trimmed, lower-cased), `signal_inverted`, `settle_sec`, `pio_helper` (optional path).
   - `cooling`: `damper_open_angle`, `damper_closed_angle`, `heater_fan_pwm`, `mode_pwms` (`fast`/`medium`/`slow`), `fast_led_fan_pwm`, `target_temp`, `sample_sec`, `window_sec`.
   - `ventilation`: `fan_pwm`.
   - `pressure_sensor`: `mode`, `v_min`, `v_max`, `i_min_ma`, `i_max_ma`, `shunt_ohms`, `p_at_v_min_mpa`, `p_at_v_max_mpa`, `divider`, `adc_saturation_volts`, `on_above_volts`, `set_point_mpa`, `max_bar`, `min_bar`, `flow_check_enabled`, `flow_check_window_sec` (>=0), `flow_check_min_drop_bar` (>=0), `required`, `not_reading_after_sec` (>=0). Legacy keys `p_min_mpa` / `p_max_mpa` are NOT read (an old file gets the defaults 0.0 / 1.0).
   - `sensor_filter`: `glitch_hold_sec` (clamped >= 0).
   - `bofa`: `max_duty` (clamped 1..100), `enable_gpio`, `present_gpio`, `present_active_low`.
5. `TryParseWavelength`: trim, lower-case, remove "nm", parse int, `WavelengthExtensions.TryParse`; "405nm"/"450nm"/"450" ok, "395nm"/null fail with `w = Nm405` (default).
6. `HardwareConfig(path)`: `Path = Path.GetFullPath(path)`; `ReloadInterval` = 1 s; constructor calls `Reload()`. Every getter reads `Current`: under a lock, if never checked or `GetElapsedTime(lastCheck) >= 1 s` -> `Reload()`; returns the snapshot.
7. `Reload()`: no-op for `FromJson`. Else sets lastCheck = now; if file missing -> log warning ("keeping the last good configuration" or "using built-in defaults"), keep snapshot; if `File.GetLastWriteTimeUtc` equals the loaded mtime -> nothing; else parse whole file; on any exception log warning and keep the last good snapshot.
**Configuration:** reads `components.json` (path from `HardwareOptions.ComponentsPath`, default `config/components.json`; shipped file `config/components.json` in repo; on units `/etc/scurebox/components.json`). The shipped file values: see HW overview and the repo file (identical to the defaults except: FAN_LEFT/RIGHT/BACK/DOOR nominal {30:1135, 100:3560}, pressure `set_point_mpa` 0.1, rgb status has no `warning`/`manual_heat` keys).
**Acceptance criteria:**
- Shipped file: Heating Kp 0.22, Ki 0.00015, IntegMax 0.85, CooldownSec 900; Rgb Count 21, Gpio 12, Order "RGB", Busy "blue", BusyStyle "solid", DoorOpen "ff7800", ChaseSec 0.12, Warning "yellow" (default); LedPower Modes[Nm450] == (true,false,false,false,30), Modes[Nm405] == (true,true,false,true); `LedFanSpeed(LED_DOOR, Nm450)` 30, `(LED_DOOR, Nm405)` 100; door (27,0,10); FAN_BACK nominal [(30,1135),(100,3560)]; FAN_COOLING damper-open [(60,2470),(100,4075)]; CriticalBelowPctByFan[FAN_HEATER] 11.8, no FAN_LEFT entry; StoppedPersistSec 5, LedFanMinRpm 100; Servo ("auto", true, 1.5, null); Cooling angles (0,90), Medium 60, target 25; NoHeat (true,600,0.5,99); Ventilation 60; pressure mode analog_voltage, saturation 3.2, set point 0.1; LedHeating.Enabled false; UvLightCheck (true,10,5,0.6); SensorFilter 15.
- Missing file -> `Heating == HeatingConfig.Default`, Rgb.Count 21. Inline `{"rgb":{"count":8,"bogus":1}, "unknown_section":{}, "leds":{"NOT_A_LED":{}}}` -> Count 8, Gpio 12, 4 LEDs.
- `glitch_hold_sec` -5 -> 0.0; 12.5 -> 12.5.
- Hot reload: change within 1 s not seen; after advancing 1 s with a new mtime it is; unparsable file keeps last good; explicit `Reload()` re-reads immediately.
- Old pressure file with `p_min_mpa -0.1` -> PAtLowMpa 0.0, PAtHighMpa 1.0.
**Tests:** `HardwareConfigTests` (Led_checks_switch_is_off_in_the_shipped_config_and_can_be_turned_on, Uv_light_check_is_read_and_defaulted, Sensor_filter_glitch_hold_is_read_defaulted_and_clamped, Loads_the_shipped_components_json, Missing_file_gives_defaults_and_unknown_keys_are_ignored, Hot_reloads_when_the_file_changes_at_most_once_per_second (FakeTimeProvider + `File.SetLastWriteTimeUtc`), Wavelength_keys theory, An_old_machine_config_gets_the_datasheet_pressure_points).
**Reference (source):** `src/SCureBox.Hardware/IHardwareConfig.cs`, `src/SCureBox.Hardware/Config/*.cs`, `config/components.json`, `tests/SCureBox.Hardware.Tests/HardwareConfigTests.cs`

---

### HW-03 — I2C bus abstraction and set-and-verify helper
**Summary**
- **What it is for:** The basic layer that lets the chip drivers talk to the board chips over the I2C bus, plus a helper that writes a value and checks it was really set.
- **Problem it solves:** Two drivers talking on the bus at the same time can corrupt data, and a write can silently fail.
- **How we solve it:** All bus traffic goes through one shared lock. Important writes are read back and retried up to 3 times; if they still fail, a clear error lists every part that failed.

**Project / folder:** `SCureBox.Hardware.csproj`, `Bus/` and `Drivers/`
**Goal:** Give every chip driver an SMBus-style register interface over Linux `/dev/i2c-N`, serialised on one process-wide lock, plus the generic "apply, read back, retry 3x" and "attempt all, aggregate failures" helpers used by every verified write.
**Depends on:** HW-01 (HardwareVerifyException)
**Files to create:**
- `src/SCureBox.Hardware/Bus/II2cBus.cs` - `internal interface II2cBus : IDisposable`
- `src/SCureBox.Hardware/Bus/SystemDeviceI2cBus.cs` - `internal sealed class SystemDeviceI2cBus : II2cBus`
- `src/SCureBox.Hardware/Drivers/Verify.cs` - `internal static class Verify`
- Test fakes: `tests/SCureBox.Hardware.Tests/Fakes/FakeI2cBus.cs`, `Fakes/I2cWrite.cs`
**Public contract:**
```csharp
internal interface II2cBus : IDisposable {
    int BusId { get; }
    void WriteByte(int address, byte register, byte value);
    void WriteBlock(int address, byte register, ReadOnlySpan<byte> data);
    byte ReadByte(int address, byte register);
    void ReadBlock(int address, byte register, Span<byte> buffer);
}
internal sealed class SystemDeviceI2cBus : II2cBus {
    public static readonly object GlobalLock;
    public SystemDeviceI2cBus(int busId);
    public static bool Exists(int busId);          // File.Exists($"/dev/i2c-{busId}")
}
internal static class Verify {
    public const int Retries = 3;
    public static (int Attempt, T Observed) SetAndVerify<T>(string label, Action apply, Func<(bool Ok, T Observed)> check, int retries = Retries);
    public static void Each(IEnumerable<(string Label, Action Act)> actions);
}
```
**Behaviour & rules:**
1. `SystemDeviceI2cBus` keeps one `System.Device.I2c.I2cDevice` per address, created lazily with `I2cDevice.Create(new I2cConnectionSettings(BusId, address))`. Every transaction (and Dispose) runs under the static `GlobalLock` shared by ALL bus instances.
2. `WriteByte`: write `[register, value]`. `WriteBlock`: write `[register, data...]`. `ReadByte`: `WriteRead([register], 1 byte)`. `ReadBlock`: `WriteRead([register], buffer)`. Disposed bus throws `ObjectDisposedException`.
3. `Verify.SetAndVerify`: for attempt 1..retries: `apply()`, `(ok, observed) = check()`; return `(attempt, observed)` on the first ok; after all attempts throw `HardwareVerifyException("{label}: not confirmed after {retries} attempts (last read back: {observed})")`.
4. `Verify.Each`: run every action even if earlier ones throw; collect `"{label}: {message}"`; if any failed throw `HardwareVerifyException("{n} component(s) not confirmed:\n  " + join("\n  "))`.
5. `FakeI2cBus` (test): register memory stored as written blocks keyed by (addr, start reg); a read at a start register returns that block, a read inside a block returns its tail, else zeros. `Mirror(addr, srcReg, dstReg)` copies writes (used for TCA OUTPUT 0x84 -> INPUT 0x80). `FailingAddresses` -> IOException("I2C 0x{addr:X2} NAK"). `DropNextWrites` ignores N writes (still journaled). `Journal` lines: `"i2c{BusId} 0x{addr:X2} reg 0x{reg:X2} <- {HEX}"`. `Writes` list of (Addr, Reg, Data). `Preload`, `Reg`, `Regs` helpers.
**Configuration:** none.
**Acceptance criteria:**
- Two buses never run a transaction concurrently (shared static lock).
- `SetAndVerify` returns attempt 3 when the first two writes are dropped; throws after 3 failed attempts with "3 attempts" in the message.
- `Each` runs all actions and lists every failed label.
**Tests:** exercised by `Pca9685Tests.Verified_write_retries_three_times`, `Tca6424aTests.Verified_set_fails_after_three_attempts`, `IoBoardHardwareSystemTests.All_safe_verifies_and_aggregates_failures`.
**Reference (source):** `src/SCureBox.Hardware/Bus/II2cBus.cs`, `src/SCureBox.Hardware/Bus/SystemDeviceI2cBus.cs`, `src/SCureBox.Hardware/Drivers/Verify.cs`, `tests/SCureBox.Hardware.Tests/Fakes/FakeI2cBus.cs`, `tests/SCureBox.Hardware.Tests/Fakes/I2cWrite.cs`

---

### HW-04 — GPIO pins and libgpiod tachometer edge counter
**Summary**
- **What it is for:** Controls the simple on/off pins of the main computer and counts the pulses from the six fans so their speed can be measured.
- **Problem it solves:** The standard way to set up the fan speed pins fails on this computer (CM5), so fan speeds could not be read.
- **How we solve it:** We use the libgpiod library directly and set up each fan pin in one step as an input that counts rising pulses. Plain pins get simple open, read and write calls.

**Project / folder:** `SCureBox.Hardware.csproj`, `Bus/`
**Goal:** Provide plain GPIO outputs/inputs over libgpiod (never pinctrl, except the watchdog) and free-running rising-edge counters for the six fan tachometers. The tach lines are requested directly through libgpiod v2 in ONE request (input + pull-up + rising edge) because System.Device.Gpio's open-then-reconfigure fails with EINVAL on the CM5.
**Depends on:** none in area (System.Device.Gpio 4.2.0)
**Files to create:**
- `src/SCureBox.Hardware/Bus/IGpioPins.cs` - `internal interface IGpioPins : IDisposable`
- `src/SCureBox.Hardware/Bus/SystemDeviceGpioPins.cs` - `internal sealed class SystemDeviceGpioPins : IGpioPins`
- `src/SCureBox.Hardware/Bus/LibgpiodDrivers.cs` - `internal static class LibgpiodDrivers`
- `src/SCureBox.Hardware/Bus/LibgpiodEdgeCounter.cs` - `internal sealed class LibgpiodEdgeCounter : IDisposable`
- Test fake: `tests/SCureBox.Hardware.Tests/Fakes/FakeGpioPins.cs`
**Public contract:**
```csharp
internal interface IGpioPins : IDisposable {
    void OpenOutput(int pin, bool initialHigh);   // idempotent
    void OpenInput(int pin, bool pullUp);         // idempotent; pullUp false = no pull
    void Write(int pin, bool high);               // throws InvalidOperationException if not an open output
    bool Read(int pin);                           // inputs and outputs (read-back); throws when unreadable
    void OpenCounter(int pin);                    // pull-up input counting rising edges; idempotent
    long ReadCounter(int pin);                    // throws InvalidOperationException if not a counter
}
internal sealed class SystemDeviceGpioPins : IGpioPins { public SystemDeviceGpioPins(int gpioChip); public static int DetectRp1Chip(); }
internal static class LibgpiodDrivers { public static GpioDriver Create(int gpioChip); }
internal sealed class LibgpiodEdgeCounter : IDisposable {
    internal const int DirectionInput = 2; internal const int BiasPullUp = 4; internal const int EdgeRising = 2;
    public LibgpiodEdgeCounter(int gpioChip, int pin, string consumer);
    public int Pin { get; } public long Count { get; } public string? ReaderFault { get; }
}
```
**Behaviour & rules:**
1. `LibgpiodDrivers.Create(chip)`: try `new LibGpiodV2Driver(chip)`; on `PlatformNotSupportedException`/`DllNotFoundException`/`EntryPointNotFoundException`/`TypeInitializationException` try `new LibGpiodDriver(chip)` (v1); if that fails the same way throw `PlatformNotSupportedException("libgpiod not usable: v2 - {m2}; v1 - {m1}")`. (Debian Trixie ships only libgpiod v2.)
2. `SystemDeviceGpioPins(chip)` wraps `new GpioController(LibgpiodDrivers.Create(chip))`; all ops under one private lock; tracks sets of outputs and inputs.
3. `OpenOutput`: return if already an output; open pin if not open; `SetPinMode(Output)`; write initial level; move pin from inputs to outputs. `OpenInput`: return if already an input; open; mode `InputPullUp` or `Input`; move to inputs. `Write` requires an open output. `Read` requires the pin to be open (else `InvalidOperationException("GPIO{pin} is not open")`), returns `== High`.
4. `OpenCounter`: idempotent; throws `InvalidOperationException("GPIO{pin} is already open through the GPIO controller")` if the controller holds the pin; else creates `LibgpiodEdgeCounter(chip, pin, "scurebox-tach")`. `ReadCounter` returns `Count`.
5. `DetectRp1Chip()`: if `/sys/class/gpio` missing -> 0; else for each `gpiochip*` dir whose `label` file trims to `pinctrl-rp1`, resolve the `device` link; if its name is `gpiochipN` return N. Any exception -> 0. Default 0.
6. `LibgpiodEdgeCounter` P/Invokes `libgpiod.so.3`: `gpiod_chip_open("/dev/gpiochip{chip}")`, `gpiod_line_settings_new/set_direction(2)/set_bias(4)/set_edge_detection(2)`, `gpiod_line_config_new/add_line_settings(offsets=[pin], 1)`, `gpiod_request_config_new/set_consumer`, `gpiod_chip_request_lines`, `gpiod_edge_event_buffer_new(64)`; settings/configs freed in finally; on failure release request + close chip and throw `InvalidOperationException("GPIO{pin} tachometer: {what} (errno N)")`. A background thread (`IsBackground`, name `tach-GPIO{pin}`) loops: `wait_edge_events(timeout 100 ms)`; 0 -> continue; <0 -> set `ReaderFault`, sleep 100 ms; then `read_edge_events(buffer, 64)` and `Interlocked.Add(count, read)` (every event is a rising edge). Dispose: stop flag, join 1 s, free buffer, release request, close chip (idempotent).
7. `FakeGpioPins` (test): levels dict, counters dict, `Journal` lines `"gpio{pin} <- 0|1"` on Write, `Outputs`, `Inputs`, `PullUps`, `Unreadable` (Read throws IOException), `SetInput`, `AddPulses`, `Level`. `OpenCounter` = `OpenInput(pin, true)` + counter 0.
**Configuration:** `HardwareOptions.GpioChip` (null = `DetectRp1Chip()`).
**Acceptance criteria:**
- `LibgpiodEdgeCounter.DirectionInput == 2`, `BiasPullUp == 4`, `EdgeRising == 2`.
- Writing a pin that is not an open output throws `InvalidOperationException`.
- A counter pin cannot also be opened through the controller.
**Tests:** `LibgpiodEdgeCounterTests.Line_settings_enums_match_gpiod_h`; GPIO behaviour via `FakeGpioPins` in `IoBoardHardwareSystemTests`. (Real libgpiod is not unit-tested.)
**Reference (source):** `src/SCureBox.Hardware/Bus/IGpioPins.cs`, `Bus/SystemDeviceGpioPins.cs`, `Bus/LibgpiodDrivers.cs`, `Bus/LibgpiodEdgeCounter.cs`, `tests/SCureBox.Hardware.Tests/Fakes/FakeGpioPins.cs`, `tests/SCureBox.Hardware.Tests/LibgpiodEdgeCounterTests.cs`

---

### HW-05 — PCA9685 PWM driver
**Summary**
- **What it is for:** Driver for the 16-channel PWM chip that sets the power level of the fans, heater, chamber light, extraction fan speed and UV LED brightness.
- **Problem it solves:** Some channels are wired inverted and the heater channel is only on or off, so writing raw values would give wrong outputs.
- **How we solve it:** The driver takes simple 0-100% values, flips inverted channels, treats the heater as full on or off, remembers the last value and can check each write.

**Project / folder:** `SCureBox.Hardware.csproj`, `Drivers/`
**Goal:** Drive the 16-channel 12-bit PWM chip (U15, i2c-0, 0x55) with logical duty percentages, applying the board's per-channel inversion and the digital-only heater channel, remembering the last commanded logical duty, and supporting verified writes.
**Depends on:** HW-03
**Files to create:** `src/SCureBox.Hardware/Drivers/Pca9685.cs` - `internal sealed class Pca9685`
**Public contract:**
```csharp
internal sealed class Pca9685 {
    public const int DefaultAddress = 0x55;
    public const byte Mode1 = 0x00, Mode2 = 0x01, Prescale = 0xFE, Led0OnL = 0x06, Sleep = 0x10, AutoIncrement = 0x20, Restart = 0x80;
    public const int ChannelCount = 16;
    public static readonly IReadOnlySet<int> Digital;    // { 6 }
    public static readonly IReadOnlySet<int> Inverted;   // { 0, 1, 2, 3, 4, 5, 7, 8, 9 }
    public Pca9685(II2cBus bus, int address = DefaultAddress, Action<TimeSpan>? sleep = null);
    public IReadOnlyList<double> LastDuty { get; }
    public static byte ProbeMode1(II2cBus bus, int address = DefaultAddress);
    public void SetFrequency(double hz);
    public void SetPwm(int channel, int on, int off);
    public static (int On, int Off) IntendedRegisters(int channel, double percent);
    public void SetDuty(int channel, double percent);
    public (int On, int Off) ReadRegisters(int channel);
    public string ReadState(int channel);
    public int SetDutyVerified(int channel, double percent, int retries = Verify.Retries);
}
```
**Behaviour & rules:**
1. Constructor (opens the chip): `WriteByte(addr, MODE1, 0x20)` (AI, awake), `WriteByte(addr, MODE2, 0x04)` (totem pole, INVRT off), sleep 1 ms (default sleep `Thread.Sleep`).
2. `ProbeMode1`: `bus.ReadByte(address, MODE1)` (presence probe, no side effects).
3. `SetFrequency(hz)`: prescale = clamp(round(25e6/(4096*hz)) - 1, 3, 255); old = read MODE1; write MODE1 = (old & 0x7F) | SLEEP; write PRESCALE; write MODE1 = old; sleep 5 ms; write MODE1 = old | RESTART | AI. (Never called in production.)
4. `SetPwm`: block write at `0x06 + 4*ch` of `[on&0xFF, on>>8, off&0xFF, off>>8]`.
5. `IntendedRegisters(ch, pct)`: clamp 0..100; digital channel -> pct>0 ? 100 : 0; eff = inverted ? 100-pct : pct; eff<=0 -> (0, 0x1000); eff>=100 -> (0x1000, 0); else (0, (int)(eff/100*4095)).
6. `SetDuty`: channel 0..15 else `ArgumentOutOfRangeException`; clamp; store `LastDuty[ch] = pct` (the requested logical value, even for the digital channel, e.g. 37); write `IntendedRegisters`.
7. `ReadRegisters`: read 4 bytes at the channel base -> (on, off). `ReadState`: if on&0x1000 -> inverted ? "OFF (full)" : "ON (full)"; else if off&0x1000 -> inverted ? "ON (full)" : "OFF (full)"; else pct = off/4095*100 -> `$"{(inv ? 100-pct : pct):F0}%"`.
8. `SetDutyVerified`: `Verify.SetAndVerify("PCA channel {ch}", SetDuty, ReadRegisters == IntendedRegisters, observed ReadState)`; returns attempt.
**Configuration:** none.
**Acceptance criteria:**
- Init writes `(0x55, 0x00, [0x20])`, `(0x55, 0x01, [0x04])`, one 1 ms sleep.
- ch11: 100 -> `00 10 00 00`; 0 -> `00 00 00 10`; 50 -> `00 00 FF 07` (2047).
- ch0 (inverted): 100 -> `00 00 00 10`; 0 -> `00 10 00 00`; 30 -> `00 00 32 0B` (2866), `ReadState(0)` "30%", `IntendedRegisters(0,30) == (0, 2866)`.
- ch6: 37 -> `00 10 00 00`, LastDuty 37, "ON (full)"; 0 -> "OFF (full)".
- ch12: 250 -> LastDuty 100, full on; -5 -> 0.
- `SetFrequency(200)`: writes MODE1 0x30, PRESCALE 30, MODE1 0x20, MODE1 0xA0, one 5 ms sleep.
- Verified write: 2 dropped writes -> returns 3; 3 dropped -> throws containing "PCA channel 3" and "3 attempts".
**Tests:** `Pca9685Tests` (Init_writes_mode1_ai_then_mode2_totem_pole_then_sleeps_1ms, Non_inverted_channel_full_on_off_and_partial, Inverted_fan_channel_is_flipped_in_software, Digital_heater_channel_is_a_switch_but_last_duty_keeps_the_request, Duty_is_clamped, Verified_write_retries_three_times, Set_frequency_follows_the_sleep_prescale_restart_sequence).
**Reference (source):** `src/SCureBox.Hardware/Drivers/Pca9685.cs`, `tests/SCureBox.Hardware.Tests/Pca9685Tests.cs`, `reference/io_controller.py` (class PCA9685)

---

### HW-06 — TCA6424A IO-expander driver
**Summary**
- **What it is for:** Driver for the IO expander chip that switches the UV wavelength relay, door magnet, valves, motor direction and NFC reset.
- **Problem it solves:** At power-on the relay line could float high and switch the LED path by mistake, and writes might not take effect.
- **How we solve it:** We write safe output values first, then set pin directions, so nothing switches by accident. Pins are read and written in logical terms and writes are checked.

**Project / folder:** `SCureBox.Hardware.csproj`, `Drivers/`
**Goal:** Drive the 24-bit IO expander (U1, i2c-0, 0x23) that switches the LED_SWITCH relay K4, door magnet / valves, motor direction and NFC reset, with a safe initialisation that prevents LED_SWITCH floating high at power-on, logical (inversion-aware) pin access, and verified writes.
**Depends on:** HW-03
**Files to create:**
- `src/SCureBox.Hardware/Drivers/Tca6424a.cs` - `internal sealed class Tca6424a`
- `src/SCureBox.Hardware/Drivers/TcaPin.cs` - `internal enum TcaPin`
- `src/SCureBox.Hardware/Drivers/MotorDirection.cs` - `internal enum MotorDirection`
**Public contract:**
```csharp
internal enum TcaPin { NFC_RESET, LED_SWITCH, FAN1_ONOFF, FAN2_ONOFF, FAN3_ONOFF, FAN4_ONOFF, FAN5_ONOFF, FAN6_ONOFF,
    MOT1_IN1, MOT1_IN2, MOT2_IN1, MOT2_IN2, VALVE_2_ON, DOOR_MAGNET, VALVE_1_ON }
internal enum MotorDirection { Stop, Forward, Reverse, Brake }   // (IN1,IN2) = (0,0),(1,0),(0,1),(1,1)
internal sealed class Tca6424a {
    public const int DefaultAddress = 0x23;
    public const byte RegInput = 0x80, RegOutput = 0x84, RegConfig = 0x8C;
    public static readonly IReadOnlyDictionary<TcaPin, (int Port, int Bit)> Pins;
    public static readonly IReadOnlySet<TcaPin> SafeHigh;      // { NFC_RESET }
    public static readonly IReadOnlySet<TcaPin> InvertedPins;  // { FAN1_ONOFF..FAN6_ONOFF }
    public Tca6424a(II2cBus bus, int address = DefaultAddress, Action<TimeSpan>? sleep = null);
    public void SetPin(TcaPin name, bool value);
    public bool GetPin(TcaPin name);
    public void Motor(int n, MotorDirection direction);
    public void Valve(int n, bool on);
    public void NfcReset();
    public void AllSafe();
    public int SetPinVerified(TcaPin name, bool value, int retries = Verify.Retries);
    public int ValveVerified(int n, bool on, int retries = Verify.Retries);
    public int MotorVerified(int n, MotorDirection direction, int retries = Verify.Retries);
    public IEnumerable<(string Label, Action Act)> AllSafeActions(int retries = Verify.Retries);
}
```
**Behaviour & rules:**
1. Pin map: NFC_RESET (0,1), LED_SWITCH (0,5), FAN1..FAN6_ONOFF (1,1)..(1,6), MOT1_IN1 (2,5), MOT1_IN2 (2,4), MOT2_IN1 (2,2), MOT2_IN2 (2,1), VALVE_2_ON (2,6), DOOR_MAGNET (2,6) (alias), VALVE_1_ON (2,7).
2. Safe init (constructor): output shadow (3 bytes) = bits of SafeHigh and InvertedPins set -> `[0x02, 0x7E, 0x00]`; block-write OUTPUT (0x84) FIRST while pins are still inputs; then CONFIG = `[0xFF,0xFF,0xFF]` with every mapped pin's bit cleared -> `[0xDD, 0x81, 0x09]`, block-write at 0x8C. Exactly 2 writes.
3. `SetPin(name, value)`: physical = InvertedPins ? !value : value; update the shadow bit; commit all 3 output bytes (block-write 0x84).
4. `GetPin(name)`: block-read 3 bytes at INPUT 0x80; bit of the port; inverted pins return !level.
5. `Motor(n, d)`: n 1 or 2 (else `ArgumentOutOfRangeException`); set both IN bits from the table; one commit. `Valve(n, on)`: n==1 -> VALVE_1_ON else VALVE_2_ON.
6. `NfcReset()`: SetPin(NFC_RESET, false); sleep 10 ms; SetPinVerified(NFC_RESET, true).
7. `AllSafe()`: for n=1,2: Motor(n, Stop), Valve(n, false); then SetPin(LED_SWITCH, false).
8. Verified variants use `Verify.SetAndVerify` with labels `"TCA pin {name}"`, `"TCA motor {n} ({direction})"`. `AllSafeActions` yields `("motor 1", MotorVerified(1,Stop))`, `("valve 1", ...)`, `("motor 2", ...)`, `("valve 2", ...)`, `("LED_SWITCH", SetPinVerified(LED_SWITCH,false))`.
**Configuration:** none.
**Acceptance criteria:**
- Init writes `0x84 <- 02 7E 00` then `0x8C <- DD 81 09`; (output reg & 0x22) == 0x02 (matches the early-boot `scure-io-safe` i2cset 0x04 0x02 / 0x0C 0xDD).
- LED_SWITCH true -> reg 0x84 == 0x22, false -> 0x02; DOOR_MAGNET true -> reg 0x86 == 0x40 and `GetPin(VALVE_2_ON)` true.
- FAN1_ONOFF true -> reg 0x85 == 0x7C, GetPin true; false -> 0x7E.
- After Motor/Valve/LED_SWITCH changes, `AllSafe()` -> reg 0x86 == 0x00, reg 0x84 == 0x02.
- `NfcReset` writes `00 7E 00`, sleeps 10 ms once, writes `02 7E 00`.
- 3 dropped writes -> `SetPinVerified(LED_SWITCH, true)` throws containing "TCA pin LED_SWITCH".
**Tests:** `Tca6424aTests` (Safe_init_writes_output_shadow_before_config_with_P01_high_and_P05_low, Set_pin_updates_the_shadow_and_reads_back, Inverted_fan_pins_drive_low_for_logical_on_and_read_back_logically, Motor_table_and_all_safe, Nfc_reset_pulses_low_for_10ms_then_high_verified, Verified_set_fails_after_three_attempts). FakeI2cBus with `Mirror(0x23, 0x84, 0x80)`.
**Reference (source):** `src/SCureBox.Hardware/Drivers/Tca6424a.cs`, `Drivers/TcaPin.cs`, `Drivers/MotorDirection.cs`, `tests/SCureBox.Hardware.Tests/Tca6424aTests.cs`

---

### HW-07 — ADS1115 ADC driver
**Summary**
- **What it is for:** Driver for the two analog-to-digital converter chips that read the temperature sensors, UV light sensors and nitrogen pressure.
- **Problem it solves:** The software needs real voltages from these sensors to know temperatures, UV light and gas pressure.
- **How we solve it:** The driver takes one measurement at a time from a chosen input and converts the raw number to volts.

**Project / folder:** `SCureBox.Hardware.csproj`, `Drivers/`
**Goal:** Single-shot, single-ended reads of the 16-bit ADCs U6 (i2c-0) and U7 (i2c-1), both at 0x49, that carry the NTC thermistors, UV photoresistors and the N2 pressure input.
**Depends on:** HW-03
**Files to create:** `src/SCureBox.Hardware/Drivers/Ads1115.cs` - `internal sealed class Ads1115`
**Public contract:**
```csharp
internal sealed class Ads1115 {
    public const byte RegConvert = 0x00, RegConfig = 0x01;
    public const int TempPga = 1;      // +/-4.096 V (U6/U7)
    public const int AnalogPga = 0;    // +/-6.144 V (U8/U10, unused)
    public const int PollAttempts = 50;
    public static readonly IReadOnlyDictionary<int, double> FullScale;   // {0:6.144,1:4.096,2:2.048,3:1.024,4:0.512,5:0.256}
    public Ads1115(II2cBus bus, int address, int pga, Action<TimeSpan>? sleep = null);   // pga not in 0..5 -> ArgumentOutOfRangeException
    public static ushort ConfigWord(int channel, int pga);
    public static double RawToVolts(short raw, int pga);
    public short ReadRaw(int channel);
    public double ReadVolts(int channel);
}
```
**Behaviour & rules:**
1. `ConfigWord(ch, pga)`: ch 0..3 else `ArgumentOutOfRangeException`; mux = 0b100 + ch; word = (1<<15) | (mux<<12) | (pga<<9) | (1<<8) | (0b100<<5) | 0b00011 (OS start, single-ended AINch, PGA, single-shot, 128 SPS, comparator disabled).
2. `ReadRaw(ch)`: block-write the word big-endian `[hi, lo]` to reg 0x01; up to 50 times: sleep 2 ms, read 2 bytes of reg 0x01, break when byte0 & 0x80 (conversion done); then read 2 bytes of reg 0x00 -> `(short)((d0<<8)|d1)`. If the OS bit never sets, the conversion register is still read after 50 polls (no exception).
3. `RawToVolts` = raw * FullScale[pga] / 32768.0. `ReadVolts` = RawToVolts(ReadRaw(ch), pga).
4. The constructor performs no I2C traffic.
**Configuration:** none.
**Acceptance criteria:**
- ConfigWord(0,1) = 0xC383, (3,1) = 0xF383, (0,0) = 0xC183, (2,1) = 0xE383.
- RawToVolts(16384,1) = 2.048; (-32768,1) = -4.096; (13200,1) = 1.65; (32767,0) = 6.144*32767/32768.
- Read of AIN1 at PGA1: single write `(0x49, 0x01, [0xD3, 0x83])`, exactly one 2 ms sleep when the OS bit reads set on the first poll, raw 0x3390 -> 1.65 V; raw 0x8000 -> -32768.
- Config write dropped -> exactly 50 sleeps.
**Tests:** `Ads1115Tests` (Config_word_matches_the_formula, Raw_to_volts, Single_shot_read_writes_config_polls_os_bit_and_reads_int16, Polling_gives_up_after_50_attempts).
**Reference (source):** `src/SCureBox.Hardware/Drivers/Ads1115.cs`, `tests/SCureBox.Hardware.Tests/Ads1115Tests.cs`

---

### HW-08 — PIO helper processes (locator, line protocol, native pio_servo / pio_rgb)
**Summary**
- **What it is for:** Small helper programs that make precise timed signals for the damper servo and the RGB status light strip.
- **Problem it solves:** Normal software timing is not exact enough for servo pulses and for the LED strip data signal.
- **How we solve it:** Small C programs use the chip's dedicated timing block (PIO). The main app starts them and sends them simple one-line text commands.

**Project / folder:** `SCureBox.Hardware.csproj`, `Helpers/` and `native/`
**Goal:** Run hardware-timed signals on the RP1 PIO block (damper servo pulses on GPIO8, WS2811 stream on GPIO12) through small C helper programs that the C# side spawns and talks to over stdin/stdout with a one-line-per-command protocol.
**Depends on:** none in area; Deploy-Ops (packaging the built helpers into the app, `SCURE_NATIVE_DIR`)
**Files to create:**
- `src/SCureBox.Hardware/Helpers/HelperLocator.cs` - `internal static class HelperLocator`
- `src/SCureBox.Hardware/Helpers/HelperProcess.cs` - `internal sealed class HelperProcess : IDisposable`
- `src/SCureBox.Hardware/native/pio_servo.c`, `native/pio_rgb.c`, `native/build-pio-helpers.sh`
- `src/SCureBox.Hardware/native/linux-arm64/` (prebuilt `pio_servo`, `pio_rgb`, `PIOLIB-LICENCE`, `README.txt`, `lib/libusbtc08.so` + `lib/PICO-LICENCE` - the TC-08 driver is used by the Dvt-Hdt area, only stored here)
**Public contract:**
```csharp
internal static class HelperLocator {
    public const string PioDevice = "/dev/pio0";
    public static string Resolve(string name, string? configured, string? nativeDir);
    public static bool PioAvailable();     // File.Exists("/dev/pio0")
}
internal sealed class HelperProcess : IDisposable {
    public string ReadyLine { get; }
    public bool IsRunning { get; }
    public static HelperProcess Start(string exe, IEnumerable<string> args, TimeSpan readyTimeout);
    public void Command(string command, TimeSpan? timeout = null);
}
```
**Behaviour & rules:**
1. `Resolve`: candidates = [configured (if not blank)], `<nativeDir ?? AppContext.BaseDirectory/native>/<name>`, `/usr/local/bin/<name>`; return the first existing file, else the first candidate (so the error names it).
2. `Start`: exe missing -> `FileNotFoundException("{exe} not built - run native/build-pio-helpers.sh")`. Start with redirected stdin/stdout/stderr, no shell, args via `ArgumentList`. Read one stdout line with `readyTimeout`; if none or it does not start with "READY": kill the process tree, read stderr for up to 1 s, throw `InvalidOperationException("{fileName}: {line or stderr, trimmed, or 'no READY'}")`. `ReadyLine` = trimmed READY line.
3. `Command`: not running -> `InvalidOperationException("helper process is not running")`; under an IO lock write `command + '\n'`, flush, read one reply line (default timeout 1 s, `TimeoutException("no reply from helper")` on timeout); reply trimmed must be exactly "OK" else `InvalidOperationException("helper '{first token}': {reply or 'no reply'}")`.
4. `Dispose` (idempotent): if alive write "Q\n", wait 2000 ms, else kill tree; on any exception kill; finally dispose the Process.
5. `pio_servo <gpio> [--inverted] [--period-us N (2000..65000, default 20000)] [--pio IDX (default 0)] [--sm N (default 3; -1 any free)] [--test <pulse_us> <hold_ms>]`. Program (clkdiv 200 on the 200 MHz RP1 clock = 1 us per instruction, 1 side-set pin): `pull block side IDLE; out x,16 side IDLE; out y,16 side IDLE; jmp x--,3 side ACTIVE; jmp y--,4 side IDLE`; word = (y<<16)|(x&0xFFFF), x = pulse-1, y = period-pulse-4. Idle level = inverted ? HIGH : LOW. Keeps the 4-deep TX FIFO topped up every 20 ms while driving. Commands: `P <us>` (pulse must be >=100 and pulse+8 <= period, else `ERR pulse out of range`; `ERR bad pulse` for non-positive/garbage; a new width clears the FIFO so it applies within one period), `R` release (clear FIFO, pulse in flight finishes, line idles), `Q` quit; each replied `OK` / `ERR <reason>`; unknown -> `ERR unknown command`. Prints once `READY gpio=<n> sm=<n> inverted=<0|1> period_us=<n>`. stdin HUP -> release and exit. Teardown waits one period + 1 ms before disabling the SM.
6. `pio_rgb <gpio> <count> [--order RGB|GRB (default RGB)] [--pio IDX] [--sm N (default 2)] [--test RRGGBB]`. WS2811 program, 10 PIO cycles per bit at 8 MHz (clkdiv = 200e6/(800e3*10) = 25.0), T1=3, T2=4, T3=3 ('0' = 0.375 us high / 0.875 low; '1' = 0.875 / 0.375); shift left, autopull 24 bits, TX FIFO joined (8 deep); idle LOW. Commands: `F <hex>` exactly 6*count hex chars in RRGGBB per LED (helper reorders to GRB when `--order GRB`; errors `frame length mismatch`, `bad hex`), `O` all off, `Q` quit (strip left as is); over-long line -> `ERR line too long`. After each frame wait for FIFO empty then 300 us latch. Prints `READY gpio=<n> sm=<n> count=<n> order=<RGB|GRB>`.
7. Build: `build-pio-helpers.sh` compiles each helper with `gcc -O2 -Wall -Wextra -Wno-unused-parameter -DLIBRARY_BUILD=1 -I$SRC/include` against piolib sources `piolib.c pio_rp1.c library_piochips.c` from raspberrypi/utils (git clone to `/tmp/rpi-utils` unless `PIOLIB_SRC` set); `install` arg copies to `/usr/local/bin`.
**Configuration:** `HardwareOptions.NativeDir` (host passes `SCURE_NATIVE_DIR`), `servo.pio_helper`.
**Acceptance criteria:**
- `Resolve` prefers the configured path, then native dir, then /usr/local/bin, and returns the first candidate when none exists.
- A helper that does not print READY within the timeout is killed and `Start` throws `InvalidOperationException`.
- A reply other than "OK" makes `Command` throw with the command's first token in the message.
**Tests:** none directly in the existing suite (helpers need /dev/pio0); drivers are tested through `FakeServoDriver` / `FakeRgbDriver`.
**Reference (source):** `src/SCureBox.Hardware/Helpers/HelperLocator.cs`, `Helpers/HelperProcess.cs`, `native/pio_servo.c`, `native/pio_rgb.c`, `native/build-pio-helpers.sh`, `native/linux-arm64/README.txt`

---

### HW-09 — Damper servo (pulse maths, PIO and software-PWM drivers, settle/release)
**Summary**
- **What it is for:** Moves the damper (an air flap used for cooling) open or closed with a small servo motor.
- **Problem it solves:** The servo must reach the right angle through an inverted signal, and if pulses keep running it hums under load.
- **How we solve it:** We convert the angle to the right pulse, send pulses for a short settle time, then stop. We prefer the timed helper and fall back to software pulses.

**Project / folder:** `SCureBox.Hardware.csproj`, `Servo/`
**Goal:** Move the MG90S damper servo on GPIO8 (behind the inverting transistor Q16) to a logical angle, keep pulsing for `settle_sec`, then release so a loaded servo does not hum. Prefer the PIO helper; fall back to software PWM.
**Depends on:** HW-02 (ServoConfig), HW-04 (LibgpiodDrivers), HW-08
**Files to create:**
- `src/SCureBox.Hardware/Servo/IServoDriver.cs` - `internal interface IServoDriver : IDisposable`
- `src/SCureBox.Hardware/Servo/ServoPulse.cs` - `internal static class ServoPulse`
- `src/SCureBox.Hardware/Servo/PioServoDriver.cs` - `internal sealed class PioServoDriver : IServoDriver`
- `src/SCureBox.Hardware/Servo/SoftwarePwmServoDriver.cs` - `internal sealed class SoftwarePwmServoDriver : IServoDriver`
- `src/SCureBox.Hardware/Servo/DamperServo.cs` - `internal sealed class DamperServo : IDisposable`
- Test fake: `tests/SCureBox.Hardware.Tests/Fakes/FakeServoDriver.cs` (Name "pio", records `Pulses`, counts `Releases`)
**Public contract:**
```csharp
internal interface IServoDriver : IDisposable { string Name { get; } void Drive(int pulseUs); void Release(); }
internal static class ServoPulse {
    public const int MinAngle = 0, MaxAngle = 180, MinPulseUs = 500, MaxPulseUs = 2400, PeriodUs = 20000;
    public const bool LogicalInverted = true;
    public static double ClampAngle(double angle);
    public static int PulseUs(double angle);
    public static double DutyPercent(int pulseUs, bool signalInverted);
}
internal sealed class PioServoDriver : IServoDriver {
    public const string HelperName = "pio_servo";
    public string Name => "pio"; public string ReadyLine { get; }
    public static PioServoDriver Start(string exe, int gpio, bool signalInverted);
}
internal sealed class SoftwarePwmServoDriver : IServoDriver {
    public SoftwarePwmServoDriver(GpioController controller, int gpio, bool signalInverted);
    public string Name => "lgpio";
}
internal sealed class DamperServo : IDisposable {
    public DamperServo(IServoDriver driver, double settleSec, TimeProvider? timeProvider = null);
    public string DriverName { get; } public double? LastAngle { get; } public bool Holding { get; }
    public static DamperServo Create(ServoConfig cfg, string? nativeDir, Func<IServoDriver> softwareFactory, TimeProvider time, ILogger log);
    public double Goto(double angle, bool force = false);
    public void Release();
}
```
**Behaviour & rules:**
1. `PulseUs(angle)`: clamp 0..180; a = 180 - angle (logical flip of the linkage); pulse = round(500 + a/180*1900). 0 -> 2400, 90 -> 1450, 180 -> 500, -10 -> 2400, 200 -> 500.
2. `DutyPercent(pulse, inverted)` = pulse/20000*100, inverted -> 100 - that (1450 -> 7.25 / 92.75). The electrical Q16 inversion is separate from the logical flip.
3. `PioServoDriver.Start`: `/dev/pio0` missing -> `FileNotFoundException("/dev/pio0 missing (RP1 PIO: Pi 5 / CM5 kernel only)")`; spawn helper with args `[gpio, "--inverted" if inverted]`, READY timeout 3 s. `Drive(p)` -> `Command("P {p}")`; `Release` -> `Command("R")`; Dispose disposes the helper.
4. `SoftwarePwmServoDriver`: the `SoftwarePwmChannel` exists only while driven (its precision-timer thread busy-waits a core). `Drive`: duty fraction = DutyPercent/100; if no channel: close the pin if open, create `new SoftwarePwmChannel(gpio, 50, duty, usePrecisionTimer: true, controller, shouldDispose: false)` and `Start()`; else set `DutyCycle`. `Release`: stop + dispose the channel; open the pin as output if not open; write idle level (inverted ? High : Low). Dispose = Release.
5. `DamperServo.Create`: driver = `cfg.Driver` trimmed lower; for "auto" or "pio": resolve helper (`HelperLocator.Resolve("pio_servo", cfg.PioHelper, nativeDir)`) and `PioServoDriver.Start`; for "auto" any exception logs a warning and falls back; for "pio" the exception propagates. Otherwise (or fallback) `softwareFactory()`. Log the driver choice. Returns `new DamperServo(driver, cfg.SettleSec, time)`.
6. `Goto(angle, force)`: clamp; under lock: if !force and holding and same angle -> return (skip); else cancel the release timer, `Drive(PulseUs)`, LastAngle = angle, Holding = true; if settle > 0 start a one-shot `TimeProvider.CreateTimer` after settle that calls `Release()`. settle <= 0 = hold forever. Returns the applied angle.
7. `Release()`: Holding = false; driver.Release() with exceptions swallowed. After release a same-angle Goto re-drives (recovers a stalled servo). Dispose cancels the timer and disposes the driver.
**Configuration:** `servo.gpio` (8), `servo.driver` ("auto" | "pio" | "lgpio"), `servo.signal_inverted` (true), `servo.settle_sec` (1.5), `servo.pio_helper` (null).
**Acceptance criteria:**
- Goto(90) with settle 1.5 -> pulses [1450], Holding; repeat Goto(90) skipped; no release at 1.4 s, release at 1.5 s; Goto(90) after release re-drives; Goto(0) -> 2400 and restarts the timer (second release 1.5 s later).
- Settle 0 -> no release after 5 minutes.
**Tests:** `ServoTests` (Pulse_math_flips_the_logical_angle theory, Software_pwm_duty_and_electrical_inversion, Damper_settles_then_releases_and_skips_a_repeat_while_holding, Damper_with_zero_settle_holds_forever) with `FakeTimeProvider`.
**Reference (source):** `src/SCureBox.Hardware/Servo/*.cs`, `tests/SCureBox.Hardware.Tests/ServoTests.cs`, `tests/SCureBox.Hardware.Tests/Fakes/FakeServoDriver.cs`

---

### HW-10 — RGB status strip driver and colours
**Summary**
- **What it is for:** Drives the 21-LED RGB status strip that shows the machine state by color.
- **Problem it solves:** The strip needs a precise data signal, and the status logic needs a simple way to turn color names and brightness into LED values.
- **How we solve it:** We send colors through the RGB helper program and provide parsing of color names and hex codes plus brightness scaling.

**Project / folder:** `SCureBox.Hardware.csproj`, `Rgb/`
**Goal:** Drive the 21-LED TM1903/WS2811 status strip on GPIO12 through the `pio_rgb` helper, and provide the colour-name / hex parsing and brightness scaling used by the status logic (the status ladder itself lives in Application-Platform / Api).
**Depends on:** HW-08
**Files to create:**
- `src/SCureBox.Hardware/Rgb/IRgbDriver.cs` - `internal interface IRgbDriver : IDisposable`
- `src/SCureBox.Hardware/Rgb/PioRgbDriver.cs` - `internal sealed class PioRgbDriver : IRgbDriver`
- `src/SCureBox.Hardware/Rgb/RgbColors.cs` - `public static class RgbColors`
- Test fake: `tests/SCureBox.Hardware.Tests/Fakes/FakeRgbDriver.cs` (`LastFrame`, `Fail` -> throws `InvalidOperationException("helper 'F': ERR strip")`, `Offs` counter)
**Public contract:**
```csharp
internal interface IRgbDriver : IDisposable { int Count { get; } void Fill(ReadOnlySpan<int> colors); void Off(); }
internal sealed class PioRgbDriver : IRgbDriver {
    public const string HelperName = "pio_rgb";
    public string ReadyLine { get; }
    public static PioRgbDriver Start(string exe, int gpio, int count, string order);
    public static string FrameHex(ReadOnlySpan<int> colors);
}
public static class RgbColors {
    public const int Off = 0x000000;
    public static readonly IReadOnlyDictionary<string, int> Named;   // case-insensitive
    public static bool TryParse(string? text, out int color);
    public static int Parse(string text);
    public static int FromRgb(int r, int g, int b);
    public static (int R, int G, int B) ToRgb(int color);
    public static int Scale(int color, double brightnessPct);
    public static string ToHex(int color);
}
```
**Behaviour & rules:**
1. Named colours: red FF0000, green 00FF00, blue 0000FF, white FFFFFF, yellow FFB400, orange FF5A00, purple AA00FF, cyan 00C8FF, pink FF2878, off 000000 (`StringComparer.OrdinalIgnoreCase`).
2. `TryParse`: null -> false; trim, strip leading '#'; named lookup; else exactly 6 hex chars (invariant). On failure `color = 0`. `Parse` throws `ArgumentException("unknown color: {text} (named colors: ..., or hex RRGGBB)")`.
3. `Scale(color, pct)`: f = clamp(pct/100, 0, 1); each channel `(int)(c*f)` (truncation). `ToHex` = `(color & 0xFFFFFF).ToString("X6")`.
4. `PioRgbDriver.Start`: `/dev/pio0` missing -> `FileNotFoundException`; count <= 0 -> `ArgumentOutOfRangeException`; order normalised to "GRB" if it trims/uppercases to GRB else "RGB"; args `[gpio, count, "--order", ord]`; READY timeout 3 s.
5. `Fill`: length != Count -> `ArgumentException("expected {Count} colours, got {n}")`; `Command("F " + FrameHex)` (6 hex chars RRGGBB per LED, upper-case). `Off` -> `Command("O")`.
**Configuration:** `rgb.gpio` (12), `rgb.count` (21), `rgb.order` ("RGB"); `rgb.status.*` consumed by other areas.
**Acceptance criteria:**
- Parses: "red", "GREEN", ..., "off", "ff7800" -> 0xFF7800, "#ff8c00" -> 0xFF8C00, "  #00AAFF " -> 0x00AAFF. Rejects "", "magenta", "fff", "gg0000", null.
- `Scale(0xFF0000, 50)` = 0x7F0000; `Scale(0xFFFFFF, 0)` = 0; `Scale(0xFFFFFF, 150)` = 0xFFFFFF; `ToHex(0xFF7800)` = "FF7800"; `ToRgb(0x123456)` = (0x12,0x34,0x56); `FromRgb(0x12,0x34,0x56)` = 0x123456; `FrameHex([0xFF0000, 0x00FF00])` = "FF000000FF00".
**Tests:** `RgbColorsTests` (Parses_named_and_hex_colours, Rejects_unknown_colours, Scale_and_hex_and_frame).
**Reference (source):** `src/SCureBox.Hardware/Rgb/*.cs`, `tests/SCureBox.Hardware.Tests/RgbColorsTests.cs`, `tests/SCureBox.Hardware.Tests/Fakes/FakeRgbDriver.cs`

---

### HW-11 — IO board map and real-board system: safe states, fans/tach, heater, sensors, actuators
**Summary**
- **What it is for:** The real-board implementation of the hardware interface. It connects all chips, pins, servo and LED strip with the fixed board wiring map.
- **Problem it solves:** The app needs one working object that safely runs fans, heater, sensors, door, nitrogen, extraction fan, damper and lights on the actual board.
- **How we solve it:** We wire all drivers together using the board channel map, add safe start and safe stop states, measure fan speeds, filter short sensor glitches and track bus faults.

**Project / folder:** `SCureBox.Hardware.csproj`, root (`IoBoardMap.cs`, `IoBoardHardwareSystem.cs`)
**Goal:** Implement `IHardwareSystem` for the real BRD-74205 board by wiring the PCA9685, TCA6424A, two ADS1115, GPIO pins, damper servo and RGB strip together with the fixed channel map. This ticket covers construction, I2C fault tracking, safe states, fans + RPM, heater element, temperature / UV / pressure reads with glitch hold, door, nitrogen, BOFA, door magnet, damper, light, NFC reset, RGB and disposal. The UV LED power path is HW-12 (same class).
**Depends on:** HW-01..HW-10, HW-12; Domain (`NtcMath`, `ChamberTempCalibration`, `PressureConversion`, `PressureSensorParameters`, `SensorGlitchHold`, `GlitchVerdict`, `TachRateTracker`)
**Files to create:**
- `src/SCureBox.Hardware/IoBoardMap.cs` - `internal static class IoBoardMap`
- `src/SCureBox.Hardware/IoBoardHardwareSystem.cs` - `internal sealed class IoBoardHardwareSystem : IHardwareSystem`
**Public contract:**
```csharp
internal static class IoBoardMap {
    public const int I2cBusPca = 0, I2cBusU6 = 0, I2cBusU7 = 1, AdsTempAddress = 0x49;
    public const int ChHeater = 6, ChLight1 = 7, ChBofa = 10;
    public const int GpioNitrogenValve = 13, PressureAdcChannel = 3, PulsesPerRev = 2;
    public static readonly IReadOnlyDictionary<Fan, int> FanChannel;      // HEATER 0, DOOR 1, RIGHT 2, LEFT 3, BACK 4, COOLING 5
    public static readonly IReadOnlyDictionary<Fan, int> FanTachGpio;     // HEATER 22, DOOR 23, RIGHT 24, LEFT 19, BACK 25, COOLING 26
    public static readonly IReadOnlyDictionary<LedPanel, int> LedChannel; // BACK 11, DOOR 12, RIGHT 13, LEFT 14
    public static readonly IReadOnlyDictionary<TempSensor, (bool U7, int Channel)> TempChannel;
        // RIGHT (false,1), LEFT (false,3), BACK (true,0), DOOR (true,1), CHAMBER (true,2)
    public static readonly IReadOnlyDictionary<UvSensor, (bool U7, int Channel)> UvChannel;   // UV_RIGHT (false,0), UV_LEFT (false,2)
    public const string DoorOpenMessage = "Door is Open - Operation Disabled";
}
internal sealed class IoBoardHardwareSystem : IHardwareSystem {
    public IoBoardHardwareSystem(II2cBus bus0, II2cBus bus1, IGpioPins gpio, IHardwareConfig config, TimeProvider? timeProvider,
        Action<TimeSpan>? sleep, Func<DamperServo> servoFactory, Func<IRgbDriver> rgbFactory, ILogger logger);
    // + every IHardwareSystem member; Source "io_controller", IsSimulated false
}
```
**Behaviour & rules:**
1. Constructor: time = provider ?? System; sleep = given ?? `Thread.Sleep`; create `ChamberTempCalibration(time)`; tach epoch = `time.GetTimestamp()`; `new Pca9685(bus0, 0x55, sleep)` (MODE1/MODE2 writes), `new Tca6424a(bus0, 0x23, sleep)` (safe init), `new Ads1115(bus0, 0x49, TempPga)` = U6, `new Ads1115(bus1, 0x49, TempPga)` = U7. Open outputs LOW: GPIO13, `led_power.ssr_450nm`, `ssr_405nm`, `routing`, `bofa.enable_gpio`. Open the door pin as input without pull (failure logged as warning, not thrown). `OpenCounter` each tach pin (failure per pin logged "tach {Fan} on GPIO{Pin} unavailable"). Servo and RGB driver are NOT created here (lazy).
2. I2C fault tracking: every chip operation runs inside `Bus(op)`: success clears `_i2cFault`; `HardwareVerifyException` passes through unchanged; any other exception sets `_i2cFault = "I2C: {message}"`, logs, throws `HardwareVerifyException("I2C failure: {message}", e)`. `DriverFault` = `_i2cFault ?? _rgbFault`. One instance lock `_lock` serialises compound sequences.
3. `StartupSafe()` (under lock): Bus{ all 16 PCA channels `SetDuty(ch, 0)` (unverified); `tca.AllSafe()` }; GPIO13 low (failure logged); nitrogen = false; LED power off (HW-12 rule 6); clear LED state; route to `led_power.default_mode` (HW-12 rule 7): `ActiveMode` = default on success, null on failure; then LED_SWITCH -> 0 verified (`HardwareRefusedException` logged, not thrown). Log "startup: all components OFF (safe state)". Bus exceptions from the first block propagate.
4. `AllSafe()` (under lock): builds an action list and runs `Verify.Each`: "PCA ch0".."PCA ch15" (`SetDutyVerified(ch, 0)` inside Bus), each of `tca.AllSafeActions()` (inside Bus), "NITROGEN_VALVE" GPIO13 -> false, "ssr_450nm" -> false, "ssr_405nm" -> false, "routing" -> the default mode's `Routing` level; GPIO steps use `Verify.SetAndVerify("GPIO <name>", write, read == level)`. Before running: nitrogen = false, LED state cleared, `_ledSwitchMovedAt` = now. `ActiveMode` unchanged. Failures aggregate into one `HardwareVerifyException` ("N component(s) not confirmed: ...").
5. Fans: `SetFanDuty(fan, pct, verify=true)` -> under lock Bus{ verify ? `SetDutyVerified(FanChannel[fan], pct)` : `SetDuty` }. `GetFanDuty` = round(`pca.LastDuty[ch]`) (no bus read).
6. `ReadRpm(fan)`: `gpio.ReadCounter(FanTachGpio[fan])`; any exception -> null; nowSec = elapsed since tach epoch; under a tracker lock return `TachRateTracker<Fan>(2).Rpm(fan, count, nowSec)` (null until a first >=1 s window; same value for interleaved readers).
7. `MeasureRpm(fan, window)`: c0 = counter; `sleep(window)`; c1; return round((c1-c0)/2 * (60/window.TotalSeconds)). `InvalidOperationException` -> `HardwareVerifyException("tachometer {fan} unavailable: ...")`.
8. Heater element: `SetHeaterElement(on)` -> under lock Bus{ `SetDuty(6, on ? 100 : 0)` } (unverified). `GetHeaterElement()` = `LastDuty[6] > 0`.
9. `ReadTemperatureVolts(s)` / `ReadUvSensorVolts(s)`: under lock Bus{ (U7 ? u7 : u6).ReadVolts(channel) } from `TempChannel` / `UvChannel`. UV sensors are never converted to temperature and never gated.
10. `ReadTemperature(s)`: raw = `NtcMath.VoltageToTemperature(volts)`; for TEMP_CHAMBER a non-null raw goes through `ChamberTempCalibration.Correct(raw)` (under its own lock). Glitch hold (`SensorGlitchHold<TempSensor,double>`, own lock): a value within [`heater.temp_valid_min`, `heater.temp_valid_max`] (-20..120) is good -> `Good()` (log "reads again after X s" if a glitch ended) and returned. Otherwise (null, out of range, or exception) `Bad(sensor, now, sensor_filter.glitch_hold_sec)`: HoldStarted -> log warning, return held; Holding -> return held; HoldExpired -> log warning, then fall through; Report/HoldExpired: rethrow the captured exception if there was one, else return the raw value (null or the out-of-range value).
11. `ReadPressure()`: under lock Bus{ u7.ReadVolts(3) }. On exception: `SensorGlitchHold<int,PressureReading>.Bad(0, now, glitch_hold_sec)`; HoldStarted logs; HoldStarted/Holding with a held value -> return it; else rethrow. On success: `PressureConversion.Convert(v, new PressureSensorParameters(cfg.Mode, VMin, VMax, IMinMa, IMaxMa, ShuntOhms, PAtLowMpa, PAtHighMpa, Divider, AdcSaturationVolts, OnAboveVolts, SetPointMpa))` -> `PressureReading(p.Volts, p.Mpa, p.Bar, p.On, p.Saturated, p.Mode, p.SetPointMpa)`, recorded as good. (Volts reported = the ADC volts.)
12. `DoorOpen()`: `gpio.OpenInput(door_sensor.gpio, pullUp: false)` (idempotent) then `level == door_sensor.open_level` (level 1 = high); any exception -> null.
13. Nitrogen: `SetNitrogenValve(on)` -> under lock `gpio.Write(13, on)` (no verify, exceptions propagate), remember; `GetNitrogenValve` returns the remembered value.
14. BOFA: `SetBofa(on)` = `SetBofaDuty(on ? 100 : 0)`. `SetBofaDuty(pct)` -> channel duty = clamp(pct,0,100) * `bofa.max_duty` / 100 -> under lock Bus{ `SetDuty(10, duty)` }. `GetBofa` = `LastDuty[10] > 0`. `GetBofaDuty` = round(LastDuty[10]*100 / max(1, max_duty)). `SetBofaPower(on)` -> under lock `gpio.Write(bofa.enable_gpio, on)`, remember; `GetBofaPower` remembered. `BofaPresent()`: `OpenInput(present_gpio, pullUp false)`; return `Read(pin) != present_active_low`; exception -> null.
15. `SetDoorMagnet(on)`: under lock Bus{ `tca.SetPin(DOOR_MAGNET, on)` } (unverified); log "door magnet -> OPEN/CLOSE". No auto release here.
16. `SetDamper(open)`: angle = open ? `cooling.damper_open_angle` (0) : `damper_closed_angle` (90); under lock: create the servo on first use via `servoFactory()`, `Goto(angle)`; any non-`HardwareVerifyException` -> `HardwareVerifyException("damper failed: {msg}")`; then `DamperOpen = open`. `DamperDriver` = servo's driver name (null before first use).
17. `SetLight(on)`: Bus{ `SetDuty(7, on ? 100 : 0)` }. `NfcReset()`: Bus{ `tca.NfcReset()` }.
18. RGB (non-safety; never throws): `RgbFill(colors)` copies the span and `RgbOff()` under lock call `RgbTry`: if no driver and the last creation attempt was < 30 s ago -> return silently; else record attempt time and create via `rgbFactory()`; run the op; success clears `_rgbFault`; any exception sets `_rgbFault = "rgb: {message}"`, logs warning, disposes and drops the driver (retry after 30 s).
19. `Dispose()` (once, under lock): servo, RGB driver, gpio, bus0, and bus1 if a different instance.
**Configuration:** `led_power.*`, `door_sensor.gpio/open_level`, `bofa.*`, `cooling.damper_open_angle/damper_closed_angle`, `heater.temp_valid_min/max`, `sensor_filter.glitch_hold_sec`, `pressure_sensor.*` - all read live on each call.
**Acceptance criteria:**
- After construction + `StartupSafe`: every PCA channel at logical 0 (inverted channels read full-on registers `00 10 00 00`, others `00 00 00 10`); TCA reg 0x84 == 0x02, reg 0x86 == 0x00; GPIO 13/16/17/20 low; ActiveMode Nm405; Source "io_controller"; DriverFault null; GPIO27 is an input without pull-up; GPIO 19,22,23,24,25,26 are pull-up counters.
- `SetFanDuty(FAN_COOLING, 60)` -> GetFanDuty 60, ch5 regs `00 00 66 06` (eff 40 % -> 1638). Heater on -> ch6 full on. `SetBofa(true)` -> ch10 `00 00 99 09` (60 % -> 2457). `SetLight(true)` -> ch7 full-off register (inverted).
- `SetBofaDuty(10)` -> GetBofaDuty 10, ch10 `00 00 F5 00` (6 % -> 245); 100 -> `00 00 99 09`; 0 -> GetBofa false, GetBofaDuty 0.
- RPM: first ReadRpm null; +100 pulses on GPIO26 and +1 s -> 3000; +50 pulses and +2 s -> 750; `MeasureRpm(FAN_HEATER, 1 s)` with no pulses -> 0 and sleeps 1 s. Readers 4 ms apart at 150 pulses/s both read 4400..4600 after the first window.
- 1.65 V (raw 0x3390) on U6 -> TEMP_LEFT 25.0; same on U7 -> TEMP_CHAMBER = 1.0979*25 - 3.9813 (static calibration, few samples), TEMP_BACK 25.0; 0 V on U7 for a never-read sensor -> null.
- Glitch: good 25.0, then open NTC: still 25.0 at +5 s and +14 s, null at +16 s; recovery returns live value and a new glitch is held again.
- UV_RIGHT reads U6 AIN0, UV_LEFT reads U6 AIN2 (one config write on bus0 at 0x49, MUX bits = 0b100 + ain, no bus1 write).
- Pressure (shipped config): raw 14000 (1.75 V) -> Mpa 0.1875, not saturated, On true, SetPointMpa 0.1, Mode "analog_voltage"; raw 10400 (1.30 V) -> On false.
- PCA NAK -> `SetFanDuty` throws `HardwareVerifyException`, DriverFault starts "I2C:"; next success clears it.
- Damper: SetDamper(false) -> servo pulse 1450, DamperDriver "pio", DamperOpen false; SetDamper(true) -> 2400, true. Door magnet on -> TCA reg 0x86 == 0x40, off -> 0x00. Nitrogen on -> GPIO13 high. NfcReset journal: `i2c0 0x23 reg 0x84 <- 007E00` then `... <- 027E00`. RgbFill 21 x 0x00FF00 reaches the driver; failing driver on RgbOff -> no throw, DriverFault starts "rgb:".
- AllSafe after heater fan 100 + nitrogen on -> ch0 full-on register, GPIO13 low, reg 0x84 0x02; with TCA NAK -> throws listing "motor 1" and "LED_SWITCH" but not "PCA ch0".
**Tests:** `IoBoardHardwareSystemTests` with a `Rig` (FakeI2cBus bus0 with TCA mirror 0x84->0x80, bus1, FakeGpioPins with GPIO27 high = closed, FakeTimeProvider, sleep that records and advances time, `DamperServo(FakeServoDriver, settle, time)`, FakeRgbDriver(21), config from shipped components.json; `StartupSafe()` then journal cleared): Startup_safe_parks_everything, Fans_heater_bofa_light_and_rpm, Fan_rpm_is_the_same_for_readers_that_call_a_few_ms_after_each_other, Bofa_duty_is_a_speed_on_the_0_to_10_volt_scale, Temperature_glitch_holds_the_last_good_value_for_the_configured_window, Uv_photoresistors_read_their_own_U6_channel, Temperatures_pressure_and_chamber_calibration, I2c_failure_sets_driver_fault_and_the_next_success_clears_it, Actuators_damper_magnet_nitrogen_nfc_and_rgb, All_safe_verifies_and_aggregates_failures.
**Reference (source):** `src/SCureBox.Hardware/IoBoardMap.cs`, `src/SCureBox.Hardware/IoBoardHardwareSystem.cs`, `tests/SCureBox.Hardware.Tests/IoBoardHardwareSystemTests.cs`, `docs/02-hardware-map.md`

---

### HW-12 — UV LED power path (SSRs, LED_SWITCH relay, routing GPIO17, gating, LED fans)
**Summary**
- **What it is for:** Safely turns the four UV LED panels on and off and selects the 405 nm or 450 nm wavelength.
- **Problem it solves:** UV must never shine with the door open or on the wrong panel, and powering the LEDs in the wrong order can damage the circuit or fail.
- **How we solve it:** Before LEDs turn on we check door closed, wavelength and minimum level, then power up in a tested order with read-back checks. Each panel fan runs with its LEDs, and power drops when the last LED is off.

**Project / folder:** `SCureBox.Hardware.csproj`, `IoBoardHardwareSystem.cs` (LED region)
**Goal:** Switch the four UV LED panels safely: enforce min intensity, door confirmed closed and per-LED wavelength gating, apply the LED supply in the bench-verified order (LED_SWITCH relay -> settle -> SSRs + GPIO17 -> GPIO17 read-back -> DIM PWM), auto-run each panel's cooling fan, and drop the supply when the last LED goes off.
**Depends on:** HW-11 (same class), HW-05, HW-06, HW-02 (`LedPowerConfig`, `LedConfig`)
**Files to create:** part of `src/SCureBox.Hardware/IoBoardHardwareSystem.cs`
**Public contract:** `SetLed(LedPanel, double)`, `AllLedsOff()`, `SelectMode(Wavelength)`, `LedPowerOff()`, `AllowedLeds(Wavelength)`, `LedLevels`, `ActiveMode` (see HW-01).
**Behaviour & rules:**
1. Mode table (`led_power.modes`): 450nm = SSR450 1, SSR405 0, routing 0, LED_SWITCH 0, LED fan 30 %; 405nm = SSR450 1, SSR405 1, routing 0, LED_SWITCH 1, LED fan = LED's `fan_speed` (100). GPIO16 = SSR 450 nm, GPIO20 = SSR 405 nm, GPIO17 = routing (kept LOW in both modes: HIGH cuts the door DIM 12 V rail).
2. `AllowedLeds(w)` = LEDs from `config.Leds` whose `Modes` contain w (shipped: 450 nm -> [LED_DOOR]; 405 nm -> all four).
3. `SetLed(led, pct)`: unknown LED -> `HardwareRefusedException("unknown LED: {led}")`. on = pct > 0 && pct >= `min_intensity` (10); duty = on ? pct * `led_max_duty`(60) / 100 : 0. Under lock:
   a. If `ActiveMode` is null: compute the set of LEDs that will be on; if non-empty set ActiveMode = Nm405 if any of them lacks Nm450 in its modes, else Nm450.
   b. If on: `DoorOpen() != false` -> `HardwareRefusedException("Door is Open - Operation Disabled")`; mode = ActiveMode ?? default; LED not allowed in mode -> `HardwareRefusedException("{led} not allowed in {mode.ModeName()} mode")` (e.g. "450nm"); then ApplyLedPower(mode) (rule 4).
   c. Bus{ `pca.SetDuty(LedChannel[led], duty)`; LED fan `pca.SetDuty(FanChannel[cfg.Fan], on ? LedPower.LedFanSpeed(cfg, ActiveMode ?? default) : 0)` } (unverified writes).
   d. On: add to lit set (log "LED {led} ON ({mode})"), `LedLevels[led] = pct`. Off: remove (log), level 0; if no LED remains lit -> LED power off (rule 6).
   e. A refusal leaves the PWM untouched and the SSRs as they were.
4. ApplyLedPower(mode): mode missing in config -> refused "no led_power config for {mode}". SetLedSwitch(st.LedSwitch) (rule 5); wait for settle (rule 8); `gpio.Write(ssr450, st.Ssr450)`, `Write(ssr405, st.Ssr405)`, `Write(routing, st.Routing)`; read routing back; mismatch -> `HardwareRefusedException("GPIO{pin} routing not {0|1} (read {0|1})")`. (Raw GPIO exceptions here propagate unwrapped.)
5. SetLedSwitch(want, label): Bus{ changed = `tca.GetPin(LED_SWITCH) != want`; `tca.SetPinVerified(LED_SWITCH, want)`; if changed record `_ledSwitchMovedAt = now` and log }. `HardwareVerifyException` -> `HardwareRefusedException("LED_SWITCH relay not {0|1} ({msg})")`.
6. LED power off (`LedPowerOff()` and internal, best effort, never throws): `gpio.Write(false)` on ssr450, ssr405, routing (each failure logged); Bus{ if `tca.GetPin(LED_SWITCH)` then SetPin false, record moved-at, log "LED_SWITCH relay -> 0 (rest)" } (verify failure logged).
7. SetRouting(mode): want = mode's Routing; `Write(routing, want)`; read back; mismatch -> (false, "GPIO{pin} wavelength-select not {w} (read {r})"); exception -> (false, "GPIO{pin} wavelength-select failed ({msg})").
8. Settle wait: if `_ledSwitchMovedAt` set: remaining = max(0, `switch_settle_sec`)(0.1 s) - elapsed; if > 0 `sleep(remaining)`; then clear moved-at. So the relay settle happens once, only after the relay actually moved.
9. `AllLedsOff()`: under lock Bus{ every configured LED's DIM channel 0 and its fan 0 }; clear LED state; LED power off.
10. `SelectMode(w)`: under lock: `AllLedsOff()`; ActiveMode = w; SetRouting(w) - failure logs and throws `HardwareRefusedException(why)` (ActiveMode stays w); then SetLedSwitch(mode.LedSwitch) if the mode exists in config (405 nm moves the relay to 1 here, the settle is waited at the next LED on); log "wavelength mode -> {mode} (ok)".
**Configuration:** `led_power.ssr_450nm` 16, `ssr_405nm` 20, `routing` 17, `default_mode` "405nm", `switch_settle_sec` 0.1, `min_intensity` 10, `led_max_duty` 60, `modes`; `leds.<LED>.fan/fan_speed/modes`.
**Acceptance criteria:**
- After `SelectMode(Nm405)`, `SetLed(LED_LEFT, 50)` writes in this journal order: TCA `0x23 reg 0x84 <- 227E00` (LED_SWITCH 1), `gpio16 <- 1`, `gpio20 <- 1`, `gpio17 <- 0`, PCA `0x55 reg 0x3E <- 0000CC04` (ch14, 30 % -> 1228), PCA `0x55 reg 0x12 <- 00000010` (ch3 FAN_LEFT 100 %, inverted); exactly one 0.1 s sleep; LedLevels[LED_LEFT] 50; FAN_LEFT duty 100; GPIO17 low.
- A second LED (RIGHT 80) -> no sleep. LEFT 0 -> ch14 full-off, FAN_LEFT 0, GPIO16 still high; RIGHT 0 -> GPIO16 and GPIO20 low, TCA reg 0x84 == 0x02.
- 405 nm with LED_DOOR 50: GPIO17 low, 16 high, 20 high, reg 0x84 bit 0x20 set. `SelectMode(Nm450)` turns LED_DOOR off (ch12 full-off, level 0); LED_DOOR 50 in 450 nm -> 17 low, 16 high, 20 low, reg 0x84 == 0x02, ActiveMode Nm450.
- Door open (GPIO27 low) -> `DoorOpen()` true, SetLed throws "Door is Open - Operation Disabled", ch14 off, GPIO16 low. Door unreadable -> `DoorOpen()` null and SetLed still refused.
- SetLed 9.9 -> off (ch14 full-off, level 0, GPIO16 low); SetLed 10 -> ch14 `00 00 F5 00` (6 % -> 245), level 10.
- 450 nm: SetLed(LED_LEFT, 50) throws containing "450nm", nothing switched; LED_DOOR allowed.
- GPIO17 unreadable -> `SelectMode(Nm405)` throws `HardwareRefusedException`.
**Tests:** `IoBoardHardwareSystemTests`: Led_turn_on_order_led_switch_then_settle_then_ssrs_then_routing_readback_then_pwm_and_fan, Routing_gpio17_stays_low_in_both_modes, Led_refused_when_door_open_or_unreadable, Led_below_min_intensity_counts_as_off, Only_the_door_led_is_allowed_at_450nm, Led_refused_when_routing_readback_mismatches.
**Reference (source):** `src/SCureBox.Hardware/IoBoardHardwareSystem.cs` (UV LEDs region), `config/components.json` (`led_power`, `leds`), `tests/SCureBox.Hardware.Tests/IoBoardHardwareSystemTests.cs`

---

### HW-13 — DVT hang gate (OutputFreeze, FreezableHardwareSystem)
**Summary**
- **What it is for:** A test feature that pretends the main software has frozen, used in the DVT safety test.
- **Problem it solves:** We need to prove that the separate watchdog really cuts the heater and UV when the software hangs.
- **How we solve it:** While the hang is active, every hardware write is blocked but reads still work. After it ends, blocked writes are dropped and only the recovery safe state may write.

**Project / folder:** `SCureBox.Hardware.csproj`, `Safety/`
**Goal:** Let a DVT test (DVT-SAF-010, `POST /api/dvt/hang`) simulate a hung firmware: while hung every hardware OUTPUT write blocks (nothing switches on or off) so the output watchdog must cut; reads keep working. When the hang ends, writes issued during it are dropped and only the recovery safe-state may write.
**Depends on:** HW-01; used by Application-Process (DvtHang, CureController, RecipeRunner, SupervisionService) and Api (HeartbeatService)
**Files to create:**
- `src/SCureBox.Hardware/Safety/OutputFreeze.cs` - `public sealed class OutputFreeze`
- `src/SCureBox.Hardware/Safety/FreezableHardwareSystem.cs` - `public sealed class FreezableHardwareSystem : IHardwareSystem`
**Public contract:**
```csharp
public sealed class OutputFreeze {
    public bool Hung { get; }        // outputs frozen
    public bool Active { get; }      // hung or recovering
    public void Hang();
    public void Recover(Action safeState);
    public void Gate(string what);
}
public sealed class FreezableHardwareSystem : IHardwareSystem {
    public FreezableHardwareSystem(IHardwareSystem inner, OutputFreeze freeze);
    public IHardwareSystem Inner { get; }
}
```
**Behaviour & rules:**
1. `Hang()`: under lock epoch++, hung = true, recovering = false.
2. `Gate(what)`: under lock: not hung and not recovering -> return. Recovering: the recovery thread (a `[ThreadStatic]` flag) passes; any other thread -> `HardwareRefusedException("{what} dropped - the firmware is recovering from a hang")`. Hung: remember epoch, `Monitor.Wait` while hung and the epoch is unchanged; then throw `HardwareRefusedException("{what} dropped - issued while the firmware was hung")` (a write computed by a hung loop never lands late).
3. `Recover(safeState)`: under lock hung = false, recovering = true, `PulseAll`; mark this thread as recovery; run `safeState()`; finally clear the flag and recovering = false.
4. `FreezableHardwareSystem` forwards every member to `Inner`; each OUTPUT method first calls `Gate(label)` with these labels: StartupSafe "startup safe", AllSafe "all safe", SetFanDuty "{fan} duty", SetHeaterElement "heater element", SetLed "{led} level", AllLedsOff "LEDs off", SelectMode "LED mode", LedPowerOff "LED power off", SetNitrogenValve "nitrogen valve", SetBofa / SetBofaDuty "BOFA", SetBofaPower "BOFA power", SetDoorMagnet "door magnet", SetDamper "damper", SetLight "light", NfcReset "NFC reset", RgbFill "RGB strip", RgbOff "RGB strip off". Getters, reads (temperatures, UV, pressure, door, RPM, `MeasureRpm`, BOFA present, AllowedLeds, LedLevels, ActiveMode, DamperOpen/Driver, DriverFault, Source, IsSimulated, Config) are never gated. Dispose -> Inner.Dispose().
**Configuration:** none.
**Acceptance criteria:**
- With no hang, `Gate` returns immediately.
- A write issued during a hang blocks until `Recover` and then throws `HardwareRefusedException` (not executed); the `safeState` action passed to `Recover` executes its writes; other threads' writes during recovery are dropped.
- Reads through `FreezableHardwareSystem` never block.
**Tests:** none in `SCureBox.Hardware.Tests` (covered by Application-Process DVT hang tests). Recommended: OutputFreezeTests for rules 1-3.
**Reference (source):** `src/SCureBox.Hardware/Safety/OutputFreeze.cs`, `src/SCureBox.Hardware/Safety/FreezableHardwareSystem.cs`

---

### HW-14 — Output watchdog process (heartbeat, trip record, SafetyCut)
**Summary**
- **What it is for:** A separate safety process that watches whether the main software is still alive.
- **Problem it solves:** If the main software freezes, the heater and UV LEDs could stay on with nothing to stop them.
- **How we solve it:** If no heartbeat arrives for 20 seconds, the watchdog turns off the heater and UV LEDs itself and records it, so the restarted software shows Err 9017. Fans keep running to cool the chamber.

**Project / folder:** `SCureBox.Hardware.csproj`, `Safety/`
**Goal:** A separate process (`scurebox --watchdog`, systemd `scurebox-watchdog.service`) that watches the firmware heartbeat file and, when the firmware has been silent for the timeout (20 s), switches the heater SSR and the UV LEDs off from outside the firmware and records the trip so the restarted firmware raises Err 9017. Fans, damper, valves and BOFA are left alone so the chamber keeps cooling.
**Depends on:** HW-02, HW-03, HW-05, HW-11 (IoBoardMap); Domain (`WatchdogMonitor`, `WatchdogEvent`); Api (`CommandLine` dispatches `--watchdog`, `HeartbeatService` writes the heartbeat every 1 s); Application-Process (reads the trip file, Err 9017)
**Files to create:**
- `src/SCureBox.Hardware/Safety/HeartbeatFile.cs` - `public static class HeartbeatFile`
- `src/SCureBox.Hardware/Safety/WatchdogTripFile.cs` - `public static class WatchdogTripFile`
- `src/SCureBox.Hardware/Safety/SafetyCut.cs` - `public sealed record SafetyCutReport`, `internal sealed class SafetyCut`
- `src/SCureBox.Hardware/Safety/OutputWatchdog.cs` - `public static class OutputWatchdog`
**Public contract:**
```csharp
public static class HeartbeatFile {
    public const string DefaultPath = "/run/scurebox-heartbeat";
    public const string PathVariable = "SCURE_HEARTBEAT_FILE";
    public static string? ConfiguredPath();                       // env "off" -> null; blank -> DefaultPath
    public static void Write(string path, long tickMs, int pid);  // "<tick> <pid>\n" via path.tmp + rename
    public static long? TryReadTick(string path);
    public static void Delete(string path);
}
public static class WatchdogTripFile {
    public const string Suffix = ".trip";
    public static string PathFor(string heartbeatPath);           // heartbeatPath + ".trip"
    public static string? ConfiguredPath();
    public static void Write(string path, DateTimeOffset at, bool cutOk);   // "<unix ms> ok|incomplete\n" atomically
    public static (DateTimeOffset At, bool CutOk)? TryRead(string path);
}
public sealed record SafetyCutReport(IReadOnlyList<string> Done, IReadOnlyList<string> Failed) { public bool Ok => Failed.Count == 0; }
internal sealed class SafetyCut {
    public static readonly IReadOnlyList<int> HeaterChannels;     // { 6 }
    public SafetyCut(II2cBus pcaBus, Action<int> gpioLow, IReadOnlyList<int> ssrGpios);
    public SafetyCutReport Cut();
}
public static class OutputWatchdog {
    public const double DefaultTimeoutSec = 20; public const double RecutSec = 5;
    public static readonly TimeSpan Poll;                         // 500 ms
    public static int Run(string[] args, TextWriter stdout, TextWriter stderr);
    internal static void PinctrlLow(int gpio);
}
```
**Behaviour & rules:**
1. Heartbeat line `"<Environment.TickCount64 ms> <pid>\n"` (monotonic since boot); `TryReadTick` returns the first whitespace token parsed as long, null if missing/unparsable/IO error. `Delete` swallows IO/permission errors (clean stop = watchdog disarms). /run is tmpfs.
2. Trip record: `TryRead` -> null if missing or first token not a long; CutOk = (no second token) or second token == "ok".
3. `SafetyCut.Cut()`: try `new Pca9685(pcaBus)` (writes MODE1 0x20, MODE2 0x04) - failure -> Failed "PCA9685 not answering ({msg})" and skip the channels. For ch 6 (label "heater (PCA ch 6)") then LED channels ordered by channel 11, 12, 13, 14 (label "{LED} DIM (PCA ch {ch})"): write `IntendedRegisters(ch, 0)` via `SetPwm`, read the 4 bytes back at 0x55; match -> Done "{label} off", else Failed "{label} read back on=0x{on:X4} off=0x{off:X4}"; exceptions -> Failed "{label} ({msg})". Then for each SSR GPIO: `gpioLow(gpio)` -> Done "LED supply SSR GPIO{gpio} LOW" / Failed "LED supply SSR GPIO{gpio} ({msg})". Every step is attempted. Fans (ch 0-5) are never written.
4. `PinctrlLow(gpio)`: run `pinctrl set {gpio} op dl`, then `pinctrl lev {gpio}`; output trimmed must be "0" else `IOException("pinctrl reads level '{x}' after set LOW")`. Process helper: 5 s timeout (kill + IOException), non-zero exit -> IOException with stderr.
5. `Run(args)`: defaults timeout 20, heartbeat = `HeartbeatFile.ConfiguredPath() ?? DefaultPath`, components = env `SCURE_COMPONENTS` ?? `/etc/scurebox/components.json`. Args: `--timeout <sec>` (>0, invariant), `--heartbeat <file>`, `--components <json>`, `--cut-now`; anything else -> stderr usage `"usage: scurebox --watchdog [--timeout <sec>] [--heartbeat <file>] [--components <json>] [--cut-now]"`, exit 2. SSR pins from `HardwareConfig(components)` (or `FromJson("{}")` if the file is missing) `LedPower.Ssr450Gpio`, `Ssr405Gpio`; on exception default 16/20 with a stderr note. Opens `SystemDeviceI2cBus(0)`; `SafetyCut(bus, PinctrlLow, distinct SSR pins)`.
6. `--cut-now`: one cut, log "manual cut: heaters + UV LEDs OFF (verified)" or "manual cut: INCOMPLETE" plus the off/FAILED lists; exit 0 if Ok else 1.
7. Loop (until Ctrl+C / process exit; poll 500 ms): `WatchdogMonitor(timeout, 5).Step(TryReadTick(heartbeat), Environment.TickCount64)`: Armed -> "[WATCHDOG] firmware heartbeat present - armed"; Disarmed -> "...firmware stopped cleanly (heartbeat removed) - disarmed"; Tripped -> cut, log "TRIPPED - firmware silent for {age:0.0} s|no heartbeat: heaters + UV LEDs OFF (verified)|cut INCOMPLETE" + lists, then `WatchdogTripFile.Write(PathFor(heartbeat), UtcNow, report.Ok)` (IO errors logged); Recut (every 5 s while silent) -> cut, log only if incomplete; Recovered -> "...firmware heartbeat back - the firmware is in control again". A heartbeat already stale when the watchdog starts trips too. Startup line: "[WATCHDOG] watching {hb}: heaters + UV LEDs off after {t} s without a firmware heartbeat (SSR GPIO 16/20)". All lines prefixed "[WATCHDOG]", stdout flushed. Returns 0.
**Configuration:** env `SCURE_HEARTBEAT_FILE` (path or "off"), `SCURE_COMPONENTS`; components.json `led_power.ssr_450nm` / `ssr_405nm`; CLI args above.
**Acceptance criteria:**
- Cut with heater SSR on, LEDs dimmed and fan 0 running: report Ok, ch 6/11/12/13/14 read `00 00 00 10`, ch0 untouched (no write to it), gpioLow called with [16, 20], 7 Done entries.
- PCA NAK: Failed contains "PCA9685 not answering", SSRs still switched low.
- Heater write dropped: Failed starts "heater (PCA ch 6) read back"; failing GPIO20 -> Failed mentions "GPIO20" and the message; Done contains "LED supply SSR GPIO16 LOW".
- Heartbeat round trip: missing -> null; write 123456789 -> read back; overwrite; delete -> null; "garbage" -> null.
**Tests:** `SafetyCutTests` (Cut_switches_the_heater_and_the_four_LED_DIM_channels_full_off_and_the_SSRs_low_and_leaves_the_fans, A_dead_PCA_is_reported_but_the_SSRs_are_still_switched_low, A_register_that_does_not_read_back_off_and_a_failing_GPIO_are_failures, Heartbeat_file_round_trip_and_delete). WatchdogMonitor state machine is tested in Domain.
**Reference (source):** `src/SCureBox.Hardware/Safety/HeartbeatFile.cs`, `Safety/WatchdogTripFile.cs`, `Safety/SafetyCut.cs`, `Safety/OutputWatchdog.cs`, `src/SCureBox.Domain/Control/WatchdogMonitor.cs`, `tests/SCureBox.Hardware.Tests/SafetyCutTests.cs`, `docs/02-hardware-map.md` (Output watchdog)

---

### HW-15 — Simulated hardware system (thermal / fan / N2 / door model)
**Summary**
- **What it is for:** A simulated sCure Box used for development, QA and unit tests without the real board.
- **Problem it solves:** Developers and tests need hardware that behaves like the real machine, including safety rules, when no machine is available.
- **How we solve it:** A simple time-based model of heat, fans, nitrogen and door, with the same safety rules as the real board, plus hooks to inject faults in tests.

**Project / folder:** `SCureBox.Hardware.csproj`, root (`SimulatedHardwareSystem.cs`)
**Goal:** A deterministic stand-in for the IO board for off-device development, QA and unit tests of the upper layers. It keeps the same gating semantics as the real board (min intensity, door confirmed closed, per-LED wavelength, mode change turns LEDs off) over a simple time-driven model, and offers test hooks for fault injection.
**Depends on:** HW-01, HW-02, HW-11 (`IoBoardMap.DoorOpenMessage`); Domain (`NtcMath`, `PressureConversion`, `PressureSensorParameters`, `FanHealthEvaluator.ExpectedRpm`, `UvSensor.Panel()`)
**Files to create:** `src/SCureBox.Hardware/SimulatedHardwareSystem.cs` - `public sealed class SimulatedHardwareSystem : IHardwareSystem`
**Public contract:**
```csharp
public sealed class SimulatedHardwareSystem : IHardwareSystem {
    public const double Ambient = 24.0, HeaterMaxC = 95.0, HeaterRateCPerSec = 0.5, IdleDriftCPerSec = 0.05, MaxStepSec = 10.0;
    public const int NominalRpm = 2850;
    public const double MagnetOpenSec = 5.0, LedWarmCPerSecPer10Pct = 0.02, UvDarkVolts = 2.8, UvLitVolts = 0.6, UvSaturationPct = 10.0;
    public const double DefaultLineBar = 2.0, OpenValveFactor = 0.3;
    public SimulatedHardwareSystem(IHardwareConfig config, TimeProvider? timeProvider = null);
    public double ChamberTemp { get; }          // ticks the model first
    public bool LedPowerApplied { get; }
    public bool Light { get; }
    public int[]? LastRgbFrame { get; }
    public void Tick();
    public void SimulateDoor(bool? open);
    public void SimulateSensorOpen(TempSensor sensor, bool open);
    public void SimulateFanFailure(Fan fan, int? rpm);
    public void SetChamberTemp(double celsius);
    public void SimulateLinePressure(double? bar);
    public void SimulateN2FlowBlocked(bool blocked);
    public void SimulateN2SensorMissing(bool missing);
    public void SimulateBofaPresent(bool? present);
}
```
**Behaviour & rules:**
1. Identity: Source "simulation", IsSimulated true, DriverFault always null, ActiveMode starts at `led_power.default_mode`; chamber starts at 24.0; `_lineBar` = 2.0; BOFA presence null; damper / driver null until driven.
2. `Tick()` (called lazily by reads and writes, under lock): dt = clamp(now - last, 0, 10 s); last = now. Heater on -> chamber = min(95, chamber + 0.5*dt). Else if FAN_COOLING duty > 0 and damper open -> rate/min = duty>=100 ? 5.0 : duty>=60 ? 2.5 : 1.0; chamber = max(24, chamber - rate/60*dt). Else idle drift 0.05 deg/s toward 24 (clamped at ambient from either side). LED warm-up per panel (LEFT->TEMP_LEFT, RIGHT->TEMP_RIGHT, BACK->TEMP_BACK, DOOR->TEMP_DOOR): lit at pct -> extra += 0.02*(pct/10)*dt; unlit -> extra = max(0, extra - 0.02*dt).
3. `ReadTemperature(s)` = null if forced open, else chamber + offset[s] + ledExtra[s] with offsets LEFT 1.5, RIGHT 2.0, DOOR 0.5, BACK 1.0, CHAMBER 0.0 (no chamber calibration, no glitch hold). `ReadTemperatureVolts`: null -> 3.3; else R = 10000*exp(3934*(1/(t+273.15) - 1/298.15)); V = 3.3*R/(10000+R).
4. `ReadUvSensorVolts(s)` = 2.8 - (2.8-0.6)*clamp(level(panel)/10, 0, 1).
5. Fans: `SetFanDuty` clamps 0..100. RPM model: forced failure value if set; duty 0 -> 0; points = damper open and `fan_health.nominal_rpm_damper_open` has the fan ? those : `nominal_rpm[fan]`; rpm = round(`FanHealthEvaluator.ExpectedRpm(points, duty)` ?? 2850*duty/100). `ReadRpm` returns null on the FIRST call per fan, then the model value; `MeasureRpm` returns the model value immediately (no wait).
6. `ReadPressure()`: sensor missing -> `(0.0, -0.25, -2.5, false, false, "analog_voltage", set_point)`. bar = valve open and not blocked and lineBar set ? round(lineBar*0.3, 3) : lineBar. bar null -> `(0.0, null, null, false, false, "switch", set_point)`. Else mpa = bar/10; volts = round((v_min + (mpa - p_at_v_min)*(v_max-v_min)/(p_at_v_max - p_at_v_min)) / divider, 3); On = mpa >= set_point; Saturated false; Mode "analog_voltage".
7. `DoorOpen()`: forced value if set; else true while within 5 s after `SetDoorMagnet(true)` (then the timer clears); else false. `SetDoorMagnet(false)` does nothing.
8. LEDs: same rules as HW-12 rule 3 a/b (mode inference when null, door refusal with "Door is Open - Operation Disabled", wavelength refusal "{led} not allowed in {mode} mode", unknown LED refusal); on -> LedPowerApplied = true; level = on ? pct : 0; LED fan duty = on ? `LedFanSpeed(cfg, mode)` : 0; last LED off -> LedPowerApplied false. `AllLedsOff` zeroes every LED and its fan, LedPowerApplied false. `SelectMode(w)` = AllLedsOff + mode = w (never refused). `LedPowerOff` -> LedPowerApplied false. `AllowedLeds` as real board.
9. Actuators: nitrogen, light, heater flags stored; `SetBofaDuty` clamps 0..100 and Bofa = duty>0; `SetBofa(on)` = duty 100/0; `GetBofaDuty` returns the requested percent; BOFA power flag; `BofaPresent` returns the simulated value (default null - "cannot tell", so no 9048 in simulation). `SetDamper(open)` ticks, stores open, DamperDriver = "pio". `NfcReset` no-op. `RgbFill` length != `rgb.count` -> `ArgumentException`; stores a copy in `LastRgbFrame`; `RgbOff` stores an all-zero frame of `rgb.count`.
10. `StartupSafe()` / `AllSafe()`: all fan duties 0, heater, nitrogen, BOFA (on, duty, power), light off, LEDs cleared, mode = default. Damper, door magnet, forced faults unchanged. `Dispose` no-op.
**Configuration:** `led_power`, `leds`, `fan_health.nominal_rpm` / `nominal_rpm_damper_open`, `pressure_sensor` (v_min, v_max, p_at_v_min_mpa, p_at_v_max_mpa, divider, set_point_mpa), `rgb.count`.
**Acceptance criteria:**
- Identity: pressure (1.8, 0.2, 2.0, true, false, "analog_voltage", 0.1); door closed; chamber 24.0.
- Heater on +10 s -> 29.0; +60 s in one tick -> 34.0 (dt clamped to 10 s); from 94 +10 s -> 95.0.
- Damper open + FAN_COOLING 100/60/30 from 60 deg over 60 s (6 ticks of 10 s) -> 55.0 / 57.5 / 59.0.
- Damper closed + fan 100 from 30 over 10 s -> 29.5; from 20 -> 20.5; long idle clamps at 24.0.
- 450 nm LED_DOOR 60 -> FAN_DOOR 30; 405 nm -> 100.
- At 24 deg: LEFT 25.5, RIGHT 26.0, DOOR 24.5, BACK 25.0; UV dark 2.8; LEFT 50 -> UV_LEFT 0.6, UV_RIGHT 2.8, FAN_LEFT 100; +10 s -> TEMP_LEFT 25.5 + 0.02*5*10.
- RPM: first ReadRpm(FAN_HEATER) null, then 0; duty 100 -> 5925; duty 50 -> 3669; forced 0 -> 0; cleared -> 3669.
- Magnet: door open until 4.9 s, closed at 5.1 s; LED refused while open. Below-min LED -> level 0; 450 nm LEFT refused; DOOR lit -> LedPowerApplied; AllLedsOff -> false.
- Open sensor -> null and 3.3 V; at 25 deg -> 1.65 V.
- Line 3.5 bar -> Mpa 0.35, Volts 2.4; null -> Bar null; valve open -> 0.6 bar; blocked -> 2.0; sensor missing -> 0.0 V.
- Damper false -> DamperOpen false, driver "pio"; RgbFill 21 ok, 2 colours -> ArgumentException; StartupSafe resets nitrogen, BOFA, heater.
**Tests:** `SimulatedHardwareSystemTests` (Identity_and_fixed_values, Heater_raises_half_a_degree_per_second_up_to_95_with_dt_clamped, Cooling_fan_with_open_damper_cools_per_minute_by_mode_duty theory, Cooling_needs_the_damper_open_and_idle_drifts_back_to_ambient, Led_fan_runs_at_30_percent_in_450nm_and_at_full_speed_in_405nm, Led_panels_warm_their_thermistors_while_lit, Fan_rpm_follows_duty_and_failures_can_be_injected, Door_magnet_opens_the_door_for_five_seconds_and_gating_matches_the_real_board, Open_sensor_reads_null_and_rail_volts, Line_pressure_can_be_set_for_the_n2_interlock_tests, The_n2_sensor_always_reads_unless_a_test_unplugs_it, Line_pressure_drops_while_the_valve_is_open_unless_the_flow_is_blocked, Actuators_and_rgb), using FakeTimeProvider and the shipped components.json.
**Reference (source):** `src/SCureBox.Hardware/SimulatedHardwareSystem.cs`, `tests/SCureBox.Hardware.Tests/SimulatedHardwareSystemTests.cs`

---

### HW-16 — Hardware selection factory, options and DI registration
**Summary**
- **What it is for:** Startup code that picks the real board or the simulator and registers the hardware parts for the rest of the app.
- **Problem it solves:** The app must know which hardware to use, explain why, and start the real board in a safe state.
- **How we solve it:** At startup it decides real or simulated and logs the reason, builds the real board with its servo and LED strip, sets it safe, and registers settings, hang gate and hardware as shared services.

**Project / folder:** `SCureBox.Hardware.csproj`, root (`HardwareOptions.cs`, `HardwareSystemFactory.cs`, `HardwareServiceCollectionExtensions.cs`)
**Goal:** Decide at start-up whether to drive the real IO board or the simulation (logging the reason), build the real board with its servo and RGB factories and drive it to the safe state, and register config, hang gate and the (freezable) hardware system as DI singletons.
**Depends on:** HW-02, HW-04, HW-05, HW-08, HW-09, HW-10, HW-11, HW-13, HW-15; Api (`ScureApiHost` calls `AddSCureBoxHardware` with `ComponentsPath`, `ForceSimulation = settings.Simulate`, `NativeDir` = env `SCURE_NATIVE_DIR`)
**Files to create:**
- `src/SCureBox.Hardware/HardwareOptions.cs` - `public sealed class HardwareOptions`
- `src/SCureBox.Hardware/HardwareSystemFactory.cs` - `public static class HardwareSystemFactory`
- `src/SCureBox.Hardware/HardwareServiceCollectionExtensions.cs` - `public static class HardwareServiceCollectionExtensions`
**Public contract:**
```csharp
public sealed class HardwareOptions {
    public string ComponentsPath { get; set; } = Path.Combine("config", "components.json");
    public bool ForceSimulation { get; set; }
    public string? NativeDir { get; set; }
    public int? GpioChip { get; set; }
    public const string SimulateEnvVar = "SCURE_SIMULATE";
    public static bool SimulateRequestedByEnvironment();     // trimmed lower-case value is "1", "true" or "yes"
}
public static class HardwareSystemFactory {
    public static IHardwareSystem Create(HardwareOptions options, IHardwareConfig config, ILoggerFactory loggerFactory, TimeProvider? timeProvider = null);
    public static string? SimulationReason(HardwareOptions options);
}
public static class HardwareServiceCollectionExtensions {
    public static IServiceCollection AddSCureBoxHardware(this IServiceCollection services, HardwareOptions options);
}
```
**Behaviour & rules:**
1. `SimulationReason`: "ForceSimulation" if forced; "SCURE_SIMULATE=1" if the env asks; "not Linux"; "/dev/i2c-0 missing"; then probe `Pca9685.ProbeMode1(new SystemDeviceI2cBus(0))` (disposed) - exception -> "PCA9685 not answering at 0x55 ({msg})"; else null (use the real board).
2. `Create`: reason null -> try OpenBoard, log info "hardware: real IO board (io_controller) on /dev/i2c-0 + /dev/i2c-1"; any exception -> reason "IO board open failed: {msg}", log error. Otherwise log warning "hardware: SIMULATION ({reason})" and return `new SimulatedHardwareSystem(config, timeProvider)`.
3. OpenBoard: chip = `options.GpioChip ?? SystemDeviceGpioPins.DetectRp1Chip()`; bus0 = `SystemDeviceI2cBus(0)`, bus1 = `SystemDeviceI2cBus(1)`, gpio = `SystemDeviceGpioPins(chip)`. Servo factory: `DamperServo.Create(config.Servo, options.NativeDir, () => new SoftwarePwmServoDriver(new GpioController(LibgpiodDrivers.Create(chip)), cfg.Gpio, cfg.SignalInverted), time, log)`. RGB factory: `PioRgbDriver.Start(HelperLocator.Resolve("pio_rgb", null, options.NativeDir), rgb.Gpio, rgb.Count, rgb.Order)` and log its READY line. Construct `IoBoardHardwareSystem(bus0, bus1, gpio, config, time, null, ServoFactory, RgbFactory, log)` then `StartupSafe()` - an exception there is logged ("startup safe state incomplete") and the board is still returned.
4. `AddSCureBoxHardware`: null args -> `ArgumentNullException`; if not forced but the env asks, set `ForceSimulation = true`. Register singletons: the `HardwareOptions` instance; `IHardwareConfig` = `new HardwareConfig(options.ComponentsPath, sp.GetService<TimeProvider>(), logger)`; `Safety.OutputFreeze`; `IHardwareSystem` = `new FreezableHardwareSystem(HardwareSystemFactory.Create(options, config, loggerFactory, sp.GetService<TimeProvider>()), freeze)`. Logger factory falls back to `NullLoggerFactory.Instance`.
**Configuration:** env `SCURE_SIMULATE` (1/true/yes), `HardwareOptions` (ComponentsPath, ForceSimulation, NativeDir, GpioChip); host env `SCURE_NATIVE_DIR` -> NativeDir (Origin package: `/opt/data/scurebox/native`).
**Acceptance criteria:**
- On Windows / without `/dev/i2c-0` / with `SCURE_SIMULATE=1` the resolved `IHardwareSystem` is a `FreezableHardwareSystem` whose `Inner` is `SimulatedHardwareSystem` and `Source` is "simulation".
- `SimulationReason` returns the exact strings above in that precedence.
- An exception while opening the board falls back to the simulation instead of failing start-up.
- `IHardwareConfig`, `OutputFreeze` and `IHardwareSystem` resolve as singletons (same instance each time).
**Tests:** none in `SCureBox.Hardware.Tests`; recommended: HardwareOptions env parsing and DI resolution tests (simulation path on a dev machine).
**Reference (source):** `src/SCureBox.Hardware/HardwareOptions.cs`, `src/SCureBox.Hardware/HardwareSystemFactory.cs`, `src/SCureBox.Hardware/HardwareServiceCollectionExtensions.cs`, `src/SCureBox.Api/ScureApiHost.cs` (registration call)
