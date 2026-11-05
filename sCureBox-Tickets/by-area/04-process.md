## Application: process engine — overview

The process engine lives in `src/SCureBox.Application` (project `SCureBox.Application.csproj`, .NET 10) and turns the
hardware facade (`SCureBox.Hardware.IHardwareSystem`, `IHardwareConfig` — area **Hardware**) into the machine-level
operations the API and UI use. Layers, bottom-up:

1. **Device loops** (`Devices/`): `HeatingLoop` (PI + delta-sigma on the heater SSR, own thread, heater-fan run-on) and
   `CoolingLoop` (fixed-duty chamber fan + damper open until target, own thread). Both are driven by a `TimeProvider`
   so tests run on `FakeTimeProvider`. `PeriodicWorker` = dedicated thread ticking every N s.
2. **CureController** (`Process/`, namespace `SCureBox.Application.ProcessControl`): the `ICureController`
   command surface. Composes heating, cooling, UV (LED panels), damper, fans, nitrogen valve, BOFA fume extractor, door
   magnet, RGB override; runs the start pre-flights (sensors, frozen reading, critical fans, LED fans, chamber cooling
   fan); builds the `/api/state` snapshot (`MachineState`).
3. **Supervision** (`Supervision/`): `SupervisionService` (1 Hz tick) feeds `SupervisionState` (thread-safe holder of the
   Domain evaluators: sensors, frozen reading, no-heat, fan health, LED heating, UV light) and applies consequences
   (stop all, heater off, restart after 9006), runs the N2 interlock, and the door watchdog.
4. **RecipeRunner** (`Recipe/`): server-side program execution on a 1 s tick, driving the Domain `RecipeStateMachine`
   and translating its commands into `ICureController` calls; records telemetry, phase timings, run alerts.
5. **Status strip** (`Status/`): `StatusLedService` (RGB strip ladder + animation), `InternetWatcher`, `StripStatus`.
6. **DI** (`ProcessServiceCollectionExtensions.AddSCureBoxProcess`).

Shared conventions:
- Every command returns `SCureBox.Domain.Errors.OpResult(bool Ok, string Message, int? Code)` — never throws.
  `OpResult.FromRefusal(reason)`: a reason starting `"[NNNN] "` yields `Code = NNNN` and the message without the prefix,
  else `Code = 6015` (`ErrorCodes.HardwareRefused`). `OpResult.SplitCode(reason)` returns `(int? code, string message)`.
- Error codes used in this area (all from `ErrorCodes`, area **Domain**): 6015 HardwareRefused, 6016 DoorAbort,
  7001 InvalidTemperature, 7002 InvalidIntensity, 9006 TempReadingFrozen, 9007 HeaterNotHeating, 9008 N2PressureTooHigh,
  9009 N2NoSupply, 9010-9014 per-sensor disconnected (Chamber, Left, Right, Back, Door), 9015 N2FlowBlocked,
  9016 N2SensorNotReading, 9017 WatchdogTripped, 9020-9025 fan failure (Heater, Cooling, Left, Right, Back, Door),
  9030-9034 fan not spinning at pre-flight (Left, Right, Back, Door LED fans, Cooling), 9040-9043 LED not heating /
  temp drop (Left, Right), 9046/9047 UV light not detected (Left/Right), 9048 BofaNotDetected, 9060-9065 fan wear.
  Families: `ErrorCodes.Family(code)` maps 9010-9012→9001, 9013-9014→9050, 9020-9025→9002, 9030-9034→9003,
  9040/41/44/45→9004, 9042/43→9005, 9060-9065→9051; `ErrorCodes.IsA(code, family)`.
- Domain enums used (exact): `Fan { FAN_HEATER, FAN_DOOR, FAN_RIGHT, FAN_LEFT, FAN_BACK, FAN_COOLING }`,
  `LedPanel { LED_BACK, LED_DOOR, LED_RIGHT, LED_LEFT }`, `UvSensor { UV_LEFT, UV_RIGHT }`,
  `FanGroup { led_cooling, chamber_intake, chamber_heating }` (led_cooling = FAN_LEFT, FAN_RIGHT, FAN_BACK, FAN_DOOR;
  chamber_intake = FAN_COOLING; chamber_heating = FAN_HEATER), `CoolingMode { Fast, Medium, Slow }` (wire "fast",
  "medium", "slow" via `.Wire()`), `Wavelength` (`Nm405`, `Nm450`; `.Nm()` → 405/450), `TempSensor` (supervised:
  TEMP_CHAMBER "chamber" critical, TEMP_LEFT "left" critical, TEMP_RIGHT "right" critical, TEMP_BACK "back" not critical,
  TEMP_DOOR "door" not critical — `HardwareNames.SupervisedSensors`). `HardwareNames.LedFan[panel]` maps
  LED_LEFT→FAN_LEFT, LED_RIGHT→FAN_RIGHT, LED_BACK→FAN_BACK, LED_DOOR→FAN_DOOR. LED zones (strings): "back", "door",
  "left", "right" (`led.Zone()`).
- Thread model: CureController's `_op` lock serialises compound operations; `_fields` lock guards small fields.
  Rule: never query `_cooling.Active` from a path that holds `_op` and is called back by the cooling timer (deadlock seen
  on a unit) — the intake-fan state is passed in explicitly (`IntakeAir(bool)`).
- DVT hang: when `SCureBox.Hardware.Safety.OutputFreeze.Active` is true, `SupervisionService.Tick` and
  `RecipeRunner.Tick` return immediately (everything frozen).

---

### PROC-01 — Contracts and state DTOs
**Summary**
- **What it is for:** Defines the main commands of the process layer and the exact shape of the machine status data that the screen and API read.
- **Problem it solves:** Without one fixed list of commands and one fixed status shape, the screen could break whenever the data changes, or differ between a real and a simulated machine.
- **How we solve it:** We write shared interfaces and data records. The status always has the same full set of fields (empty when unknown), and commands return a result with an error code instead of crashing.


**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Contracts/`, `Process/UvState.cs`

**Goal:** Define the public interfaces of the process layer (`ICureController`, `IRecipeRunner`, persistence store
interfaces) and the exact JSON shape of `/api/state` (`MachineState` + nested DTOs) and `/api/recipe/status`
(`RecipeStatus`). The state is always the full superset (nulls when unknown) so the UI sees one stable shape for a real or
simulated board.

**Depends on:** Domain (`OpResult`, `ErrorCodes`, `Material`, `Wavelength`, `CoolingMode`, `FanGroup`, `CureLog`,
`CureRunStart`, `CureRunFinish`, `TelemetrySample`, `SensorIssue`, `FanIssue`, `CureReport`, `PrintLog`, `PhaseTiming`).

**Files to create:**
- `Contracts/ICureController.cs` — `ICureController`, `FanTestResult`, `FanTestEntry`, `LedTestResult`, `LedTestEntry`
- `Contracts/IRecipeRunner.cs` — `IRecipeRunner`, `RecipeStatus`
- `Contracts/IStores.cs` — `IMaterialStore`, `IPrintHistoryStore`, `ICureRunStore`, `CureHistoryRetention`, `IPhaseTimingStore`
- `Contracts/MachineState.cs` — `MachineState`, `DvtHangDto`, `N2SensorDto`, `N2PressureDto`, `FaultsDto`, `UvSensorDto`,
  `SensorStatusDto`, `FanHealthDto`, `LedHealthDto`, `CloudSyncDto`, `NfcReaderDto`
- `Process/UvState.cs` — `UvState` (namespace `SCureBox.Application.ProcessControl`)

**Public contract:**
```csharp
namespace SCureBox.Application.Contracts;
public interface ICureController {
  MachineState GetState();
  OpResult HeatToTarget(double targetC);
  OpResult DryToTarget(double targetC);
  OpResult CureUv(Wavelength wavelength, double targetC, double intensityPct);
  OpResult UvOnly(Wavelength wavelength, double intensityPct, bool vent);
  OpResult CoolToTarget(double targetC, CoolingMode mode);
  OpResult SetNitrogen(bool on);
  OpResult StopAll(bool immediate);
  OpResult SetTargetTemperature(double targetC);
  OpResult StopHeating();
  OpResult OpenDoor();
  OpResult AckDoorAbort();
  OpResult AckFanAlarms() => OpResult.Success("Fan alarm acknowledged");          // default interface impl
  OpResult AckWatchdogTrip() => OpResult.Success("Watchdog alert acknowledged");  // default interface impl
  void HoldHeaterFan(bool on) { }                                                  // default no-op
  bool? DoorOpenNow() => GetState().DoorClosed is bool closed ? !closed : null;    // default
  OpResult SetFanSpeed(FanGroup group, int percent);
  OpResult SetFanOverride(string fanOrGroupOrAll, bool on);
  OpResult SetDamper(bool open);
  OpResult SetUv(bool on, double intensityPct, Wavelength wavelength);
  OpResult SetBofa(bool on);
  OpResult SetBofaConnected(bool connected);
  OpResult SetRgb(bool on, string? color);
  void ReportUiAlerts(int critical, int warning);
  FanTestResult RunFanTest(string fanOrGroupOrAll);
  LedTestResult RunLedTest(int seconds, double minRiseC, Wavelength wavelength, int intensity = 100);
  IReadOnlyDictionary<string, double> LedFactors { get; }
  void SetLedFactors(IReadOnlyDictionary<string, double> factors);
  OpResult SetHeaterFan(int percent);
  OpResult CancelHeaterFanCooldown();
  bool AnyProcessActive { get; }
  void Shutdown();
}
public sealed record FanTestResult(bool Ok, int Rpm, string Status, Dictionary<string, FanTestEntry> Fans, string? Message);
public sealed record FanTestEntry(int Rpm, string Status, int Duty = 100, int? Expected = null, double? DeficitPct = null);
public sealed record LedTestResult(bool Ok, string Status, string Stage, int Seconds, int Wavelength, bool Precooled,
    int Intensity, double MinRiseC, IReadOnlyList<LedTestEntry> Results, string? Message);
public sealed record LedTestEntry(string Name, double? Start, double? Temp, double? Rise, string Status);

public interface IRecipeRunner {
  RecipeStatus GetStatus();
  OpResult Start(Material material, string? runId = null, string? serialNumber = null);
  OpResult Pause(); OpResult Resume(); OpResult Abort(); OpResult SkipStep();
}
public sealed record RecipeStatus {   // all init-only properties, JSON names in camelCase as listed
  string State = "idle" ["state"]; string? RunId ["runId"]; string? MaterialId ["materialId"];
  string? MaterialName ["materialName"]; int StepIndex ["stepIndex"]; int TotalSteps ["totalSteps"];
  string? Process ["process"]; string? Phase ["phase"] /* ramping|holding|cooling|nitrogen|paused|null */;
  double? TargetTemp ["targetTemp"]; double StepElapsedSec ["stepElapsedSec"]; double? StepRemainingSec ["stepRemainingSec"];
  double TotalElapsedSec ["totalElapsedSec"]; double EstimatedTotalSec ["estimatedTotalSec"];
  string? StartedAt ["startedAt"]; string? EndedAt ["endedAt"]; string? Message ["message"]; int? ErrorCode ["errorCode"];
}

public interface IMaterialStore { IReadOnlyList<Material> GetPresets(); IReadOnlyList<Material> GetUserMaterials();
  void ReplaceUserMaterials(IReadOnlyList<Material> materials); Material? Find(string id); }
public interface IPrintHistoryStore { IReadOnlyList<PrintLog> GetAll(); void ReplaceAll(IReadOnlyList<PrintLog> prints); }
public interface ICureRunStore {
  IReadOnlyList<CureLog> GetHistory();
  void Start(string extId, CureRunStart start);                          // idempotent per ext id
  bool AddTelemetry(string extId, TelemetrySample sample);               // false when run id unknown
  bool Finish(string extId, CureRunFinish finish, IReadOnlyList<SensorIssue> sensorIssues, IReadOnlyList<FanIssue> fanIssues);
  string SaveReport(string extId, CureReport report);
  CureReport? GetReport(string extId);
  bool Delete(string extId);                                             // false when unknown or still running
  IReadOnlyList<string> DeleteAll();                                     // removes finished runs only
  void Flush();
}
public static class CureHistoryRetention { public const int KeepRuns = 25; }
public interface IPhaseTimingStore { IReadOnlyList<PhaseTiming> GetAll(); int Append(PhaseTiming timing); }

namespace SCureBox.Application.ProcessControl;
public sealed record UvState(bool On, int Intensity, Wavelength? Wavelength, IReadOnlyDictionary<string, double>? Outputs)
{ public static UvState Off { get; } = new(false, 0, null, null); }
```

`MachineState` (sealed record, init-only, `System.Text.Json` names in brackets; defaults shown):
| Property | Type | JSON | Default / note |
|---|---|---|---|
| ChamberTemp | double? | chamberTemp | |
| TargetTemp | double? | targetTemp | |
| InternetOk | bool? | internetOk | |
| OfflineMode | bool | offlineMode | host-decorated |
| DoorClosed | bool? | doorClosed | |
| DoorAborted | bool | doorAborted | |
| IsHeating / IsCooling | bool | isHeating / isCooling | |
| CoolingMode | string? | coolingMode | "fast"/"medium"/"slow" |
| UvOn | bool | uvOn | |
| UvIntensity | int | uvIntensity | |
| UvWavelength | int? | uvWavelength | 405/450 |
| UvOutputs | Dictionary<string,double>? | uvOutputs | per zone |
| VentOn | bool | ventOn | |
| DamperOpen | bool? | damperOpen | |
| DamperDriver | string? | damperDriver | |
| Fans | Dictionary<string,int> | fans | new() |
| FanRpm | Dictionary<string,int?> | fanRpm | new() |
| FanRpmEach | Dictionary<string,int?> | fanRpmEach | new() |
| FanDutyEach | Dictionary<string,int> | fanDutyEach | new() |
| FanOverride | IReadOnlyList<string> | fanOverride | empty |
| StripMode | string? | stripMode | |
| UiAlerts | Dictionary<string,object> | uiAlerts | new() |
| LedTemps | Dictionary<string,double?> | ledTemps | new() |
| UvSensors | Dictionary<string,UvSensorDto> | uvSensors | new() |
| NitrogenActive | bool | nitrogenActive | |
| N2Pressure | N2PressureDto? | n2Pressure | |
| N2LinePressure | double? | n2LinePressure | |
| N2Sensor | N2SensorDto? | n2Sensor | |
| BofaOn, BofaConnected | bool | bofaOn, bofaConnected | |
| BofaDutyPercent | int | bofaDutyPercent | |
| BofaPowered | bool | bofaPowered | |
| BofaDetected | bool? | bofaDetected | |
| AtTemp | bool | atTemp | |
| HeaterPwm | double? | heaterPwm | |
| HeaterOut | bool? | heaterOut | |
| CoolingRate | double? | coolingRate | |
| CoolingFanPwm | int? | coolingFanPwm | |
| Faults | FaultsDto | faults | new() |
| Sensors | Dictionary<string,SensorStatusDto> | sensors | new() |
| FanHealth | Dictionary<string,FanHealthDto> | fanHealth | new() |
| LedHealth | Dictionary<string,LedHealthDto> | ledHealth | new() |
| LedChecksEnabled | bool | ledChecksEnabled | true |
| Alerts | IReadOnlyList<int> | alerts | empty |
| AlertDetails | Dictionary<string,string> | alertDetails | new() |
| HwSource | string | hwSource | "simulation" |
| Counters | Dictionary<string,double> | counters | new(), host-decorated |
| CloudSync | CloudSyncDto | cloudSync | new(), host-decorated |
| NfcEnabled | bool | nfcEnabled | host-decorated |
| NfcReader | NfcReaderDto? | nfcReader | host-decorated |
| Recipe | object? | recipe | runner status, null when idle; host-decorated |
| DvtHang | DvtHangDto? | dvtHang | `[JsonIgnore(Condition = WhenWritingNull)]` |

Nested records (positional, `[property: JsonPropertyName]`):
- `DvtHangDto(bool Active "active", double Until "until")` (unix seconds).
- `N2SensorDto(bool Required "required", bool Ok "ok", string? Problem "problem")`.
- `N2PressureDto(double Volts "volts", double? Mpa "mpa", double? Bar "bar", bool On "on", bool Saturated "saturated",
  string Mode "mode", double SetPointMPa "setPointMPa", double MinBar "minBar" = 0.5, double MaxBar "maxBar" = 3.0,
  bool FlowCheckEnabled "flowCheckEnabled" = true, double FlowCheckWindowSec "flowCheckWindowSec" = 5.0,
  double FlowCheckMinDropBar "flowCheckMinDropBar" = 0.3)`.
- `FaultsDto { string? Heater "heater", Cooling "cooling", Led "led", N2 "n2", Bofa "bofa" }` (init props).
- `UvSensorDto(double? Volts "volts", double? KOhm "kOhm", bool? Lit "lit")`.
- `SensorStatusDto(string Sensor "sensor", bool Ok "ok", int? OpenSec "openSec", bool Critical "critical")`.
- `FanHealthDto(int Duty "duty", int? Rpm "rpm", int? Expected "expected", double? DeficitPct "deficitPct", string Status "status", double? Since "since")`.
- `LedHealthDto { bool Lit "lit"; double Intensity "intensity"; double? Baseline "baseline"; double? Rise "rise"; double LitSec "litSec"; string Status "status" = "off"; double? Peak "peak"; double? Drop "drop" }`.
- `CloudSyncDto { bool Enabled "enabled"; double? LastSyncOk "lastSyncOk"; string? Error "error" }`.
- `NfcReaderDto { bool Detected "detected"; string? Port "port"; string? Model "model"; string? Serial "serial"; string? UsbId "usbId"; bool SeenSinceBoot "seenSinceBoot" }`.

**Behaviour & rules:**
1. Refusals are always `OpResult` with a code; no exceptions cross `ICureController`.
2. `OfflineMode`, `Counters`, `CloudSync`, `NfcEnabled`, `NfcReader`, `Recipe`, `DvtHang` are not filled by the
   controller; the host/Api decorates them (area Api / Application-Platform).
3. `DvtHang` is omitted from JSON when null; every other key is always serialised (also when null).
4. `CureHistoryRetention.KeepRuns = 25`: the store keeps the newest 25 runs, older ones removed when a new run starts
   (implemented by the persistence store — area Application-Platform).

**Configuration:** none.

**Acceptance criteria:**
- Serialising a `MachineState` produces exactly these 52 keys (sorted ordinal): alertDetails, alerts, atTemp, bofaConnected,
  bofaDetected, bofaDutyPercent, bofaOn, bofaPowered, chamberTemp, cloudSync, coolingFanPwm, coolingMode, coolingRate,
  counters, damperDriver, damperOpen, doorAborted, doorClosed, fanDutyEach, fanHealth, fanOverride, fanRpm, fanRpmEach,
  fans, faults, heaterOut, heaterPwm, hwSource, internetOk, isCooling, isHeating, ledChecksEnabled, ledHealth, ledTemps,
  n2LinePressure, n2Pressure, n2Sensor, nfcEnabled, nfcReader, nitrogenActive, offlineMode, recipe, sensors, stripMode,
  targetTemp, uiAlerts, uvIntensity, uvOn, uvOutputs, uvSensors, uvWavelength, ventOn (no dvtHang when null).
- `new RecipeStatus().State == "idle"`.

**Tests:** covered by `CureControllerTests.Get_state_has_every_contract_field` (PROC-05).

**Reference (source):** `src/SCureBox.Application/Contracts/ICureController.cs`, `Contracts/IRecipeRunner.cs`,
`Contracts/IStores.cs`, `Contracts/MachineState.cs`, `Process/UvState.cs`

---

### PROC-02 — Timing primitives (PeriodicWorker, TimeProvider waits)
**Summary**
- **What it is for:** Small timing helpers: a safe wait and a background worker that runs a task every few seconds. All machine loops use them.
- **Problem it solves:** Loops that use the real clock are slow and hard to test, and one error inside a loop could stop it forever.
- **How we solve it:** All waits use a replaceable clock, so tests can move time forward instantly. The worker catches errors, logs only the first one, and keeps running.


**Project / folder:** `SCureBox.Application.csproj` — `Devices/`

**Goal:** Provide testable blocking waits and a dedicated periodic thread, both driven by an injected `TimeProvider`, so
every loop (heating, cooling, supervision, runner, damper watch) can be advanced with `FakeTimeProvider` in tests.

**Depends on:** none (BCL `TimeProvider`, `Microsoft.Extensions.Logging`).

**Files to create:**
- `Devices/TimeProviderWaits.cs` — `internal static class TimeProviderWaits`
- `Devices/PeriodicWorker.cs` — `internal sealed class PeriodicWorker : IDisposable`

**Public contract:**
```csharp
internal static class TimeProviderWaits {
  public static bool Wait(this TimeProvider tp, TimeSpan delay, CancellationToken ct); // true = cancelled first
  public static void Sleep(this TimeProvider tp, TimeSpan delay);                     // not cancellable
}
internal sealed class PeriodicWorker : IDisposable {
  public PeriodicWorker(string name, TimeProvider tp, TimeSpan period, Action tick, ILogger log);
  public void Start(); public void Dispose();
}
```
The csproj declares `<InternalsVisibleTo Include="SCureBox.Application.Tests" />` (needed for `RecipeRunner.FaultCode` /
`TelemetryTemps` tests); existing tests use these two types only indirectly.

**Behaviour & rules:**
1. `Wait`: if `ct` already cancelled → return true immediately; else `Task.Delay(delay, tp, ct).GetAwaiter().GetResult()`,
   return false; `OperationCanceledException` → true.
2. `Sleep`: `Task.Delay(delay, tp).GetAwaiter().GetResult()`.
3. `PeriodicWorker.Start`: idempotent; creates a background thread named `name`. Loop: `while (!tp.Wait(period, ct)) tick();`
   (first tick after one period). Exceptions from `tick` are caught; only the first one is logged (warning
   `"{Worker}: tick failed"`); the thread never ends on an exception.
4. `Dispose`: idempotent; cancels, joins the thread up to 10 s (unless called from the worker thread itself), disposes the CTS.

**Configuration:** none.

**Acceptance criteria:**
- With `FakeTimeProvider`, advancing time by one period runs the tick once; a throwing tick keeps the thread alive.
- Dispose from inside the tick does not deadlock.

**Tests:** none dedicated; exercised by every loop test (`TimePump` in tests/Fakes advances fake time in small steps and
spins until `FakeHardwareSystem.Activity` changes).

**Reference (source):** `src/SCureBox.Application/Devices/TimeProviderWaits.cs`, `Devices/PeriodicWorker.cs`,
`tests/SCureBox.Application.Tests/Fakes/TimePump.cs`

---

### PROC-03 — Heating loop (PI + delta-sigma, heater pre-flight, fan run-on)
**Summary**
- **What it is for:** Controls the heater to bring the chamber to the target temperature and keep it there.
- **Problem it solves:** Heating without checks is unsafe: door open, fan stopped or a broken temperature sensor could overheat the machine. The heater also needs the fan to keep running for a while after it stops.
- **How we solve it:** Before heating we check the door, the fan and the sensor. A control loop switches the heater on and off to hold the target and keeps checking fan and sensor. When heating stops, the fan keeps cooling for 15 minutes.


**Project / folder:** `SCureBox.Application.csproj` — `Devices/`

**Goal:** Closed-loop chamber heating on the heater SSR with the heater fan fixed on. Entry runs the heater pre-flight
(cooling not active, door closed, fan spinning, thermistor valid); exit turns the element off at once and runs the heater
fan on for a cooldown (run-on) unless a program holds the fan. Port of Python `temperature_control.TemperatureController`
+ `io_controller.SystemController` heater safety.

**Depends on:** PROC-02, PROC-04 (`ICoolingLoop.Active`), Domain (`PiDeltaSigmaController`, `PiDeltaSigmaGains`,
`OpResult`, `ErrorCodes`), Hardware (`IHardwareSystem`: `SetFanDuty(Fan,int,bool verify=true)`, `GetFanDuty`, `ReadRpm`,
`MeasureRpm(Fan, TimeSpan)`, `ReadTemperature(TempSensor)`, `SetHeaterElement(bool)`, `GetHeaterElement()`, `DoorOpen()`,
`Config.Heating`, `Config.Heater`).

**Files to create:**
- `Devices/IHeatingLoop.cs` — `IHeatingLoop`
- `Devices/HeatingStatus.cs` — `HeatingStatus`
- `Devices/HeatingLoop.cs` — `HeatingLoop`

**Public contract:**
```csharp
public interface IHeatingLoop : IDisposable {
  bool Active { get; } string? Fault { get; } bool CooldownActive { get; }
  Action? EndOfProcess { get; set; }
  OpResult Start(double targetC);
  double SetTarget(double targetC);
  void Stop(string reason = "user");
  void Shutdown(string reason = "user");
  OpResult CancelCooldown();
  bool HoldFan { get; set; }
  void StartRunOn(double? seconds = null);
  double? CooldownRemainingSec { get; }
  double? PendingRunOnSec();
  HeatingStatus Status();
}
public sealed record HeatingStatus(bool Active, double? Target, double? Temp, double Pwm, bool HeaterOut, bool AtTemp,
    bool Cooldown, string? Fault, int FanPwm);
public sealed class HeatingLoop : IHeatingLoop {
  public const string DoorOpenMessage = "Door is Open - Operation Disabled";
  public HeatingLoop(IHardwareSystem hw, ICoolingLoop cooling, TimeProvider timeProvider, ILogger<HeatingLoop> log);
}
```

**Behaviour & rules:**
1. Locks: `_op` serialises Start/Stop/Shutdown/StartRunOn/CancelCooldown; `_state` guards fields. `HoldFan` is volatile.
2. `Start(targetC)`:
   - If the loop thread is alive and Active → `SetTarget(targetC)`, return `Success("target updated")` (retarget only).
   - Clear `Fault`. If `targetC < heating.target_min` (default 30) → Fault = `"target {t:0.0} C is below the minimum {min:0} C"`,
     return `Fail(..., 6015)`.
   - Cancel any running cooldown (join up to 10 s).
   - `EnableHeater` pre-flight, in order: (a) `cooling.Active` → `"cooling mode active - stop cooling first"`;
     (b) `DoorOpen() != false` (open OR unreadable) → `DoorOpenMessage`; (c) `SetFanDuty(FAN_HEATER, heater.fan_pwm, verify:false)`,
     exception → `"heater fan write failed: {msg}"`; (d) thermistor check (below) failing → DisableHeater + reason;
     (e) `Sleep(2.0 s)` spin-up then `MeasureRpm(FAN_HEATER, 1 s)` (exception → null); null or `< heater.min_fan_rpm`
     → `"heater fan not spinning (RPM={rpm|?})"`, DisableHeater; (f) `SetHeaterElement(false)` (PI owns element; starts OFF),
     exception → DisableHeater + message. Any refusal: Fault = reason, return `OpResult.FromRefusal(reason)` (so 6015 unless
     reason has a [code]).
   - On success: target set, temp null, pwm 0, heaterOut false, atTemp false, FanPwm = heater.fan_pwm, Active = true;
     start background thread "heating-loop"; return `Success("heating started")`.
3. Thermistor check (`heater.thermistor`, default TEMP_CHAMBER): read exception → `"thermistor {S} communication error"`;
   null → `"thermistor {S} disconnected / invalid reading"`; outside `[heater.temp_valid_min, temp_valid_max]` (default
   -20..120) → `"thermistor {S} out of range ({t:0.0} C)"`.
4. Loop: PI = `new PiDeltaSigmaController(new PiDeltaSigmaGains(kp, ki, kd, integ_min, integ_max))`; sample period
   `max(0.02, heating.sample_sec)` (default 0.05 s); health period `max(1.0, heater.health_check_sec)` (default 10 s).
   Each sample: (a) if an element state was written and `GetHeaterElement() != written` → Finish("heater disabled externally");
   (b) health check when due: `ReadRpm(FAN_HEATER)` null or < min → confirm with `MeasureRpm(1 s)`; still bad →
   Finish(`"heater fan failure (RPM={rpm|?})"`); thermistor bad → Finish(`"[9010] {why}"`); (c) thermistor bad →
   Finish(`"[9010] {reason}"`); (d) `err = target - t`; `(power, on) = pi.Step(err)`; Temp = t, Pwm = round(power*100, 1),
   HeaterOut = on, AtTemp = `|err| <= heating.at_temp_band` (default 1.5); (e) write `SetHeaterElement(on)` only when it
   changed; write exception → Finish(`"heater write failed: {msg}"`).
5. `Finish(fault)` (from loop or Stop): cancel; Active=false; Fault=fault if non-null; if it was not active → return;
   DisableHeater (element off + FAN_HEATER 0, logs error unless reason null/"user"); then `StartCooldown()`.
6. `StartCooldown(seconds?)`: if `HoldFan` → set FAN_HEATER to heater.fan_pwm (verify:false), no run-on, return.
   Else secs = seconds>0 ? seconds : heating.cooldown_sec (default 900). secs <= 0 → invoke `EndOfProcess`, return.
   Otherwise thread "heater-cooldown": `SetFanDuty(FAN_HEATER, heating.cooldown_fan_pwm)` (default 30 %), wait secs
   (cancellable), finally `_cooldownUntil = null` and, only if not Active, invoke `EndOfProcess` (all fans off + damper closed).
7. `Stop(reason)`: cancel loop, join (10 s), if Active → Finish(reason == "user" ? null : reason) → element off, run-on.
8. `Shutdown(reason)`: cancel + join; Active=false; Fault=reason unless "user"; if it was on → DisableHeater; cancel a
   running cooldown (its exit invokes EndOfProcess); if there was no cooldown → invoke EndOfProcess directly. No run-on.
9. `SetTarget(t)`: clamps below `target_min` up to it (warning), stores, returns applied target.
10. `CancelCooldown()`: Active → `Fail("heating is active", 6015)` (checked before and inside the lock); else cancel the
    cooldown thread → `Success("cooldown cancelled")`.
11. `StartRunOn(seconds?)`: no-op if Active or CooldownActive; else StartCooldown(seconds).
12. `CooldownRemainingSec`: while cooldown thread alive → `max(0, until - now)` seconds, else null.
13. `PendingRunOnSec()`: cooldown_sec <= 0 → null; Active or HoldFan → full cooldown_sec; else CooldownRemainingSec.
14. `Status()` → `HeatingStatus(Active, Active ? target : null, temp, pwm, heaterOut, atTemp, CooldownActive, fault, fanPwm)`.
15. `Dispose()` cancels both CTSs.

**Configuration:** components.json via `IHardwareConfig`: `heating` {target_temp 60, target_min 30, sample_sec 0.05,
kp 0.22, ki 0.00015, kd 0, integ_max 0.85, integ_min 0, at_temp_band 1.5, cooldown_sec 900, cooldown_fan_pwm 30};
`heater` {fan_pwm 100, min_fan_rpm 100, health_check_sec 10, thermistor TEMP_CHAMBER, temp_valid_min -20, temp_valid_max 120}.

**Acceptance criteria:**
- Door open or unreadable → refused with "Door is Open - Operation Disabled" (6015), element never on.
- Heater fan at 0 RPM → refused "heater fan not spinning (RPM=0)", fan and element off.
- Target 25 → Fail 6015, message names the 30 C minimum.
- Enable: FAN_HEATER is written 2 s (fake time) before the element is touched.
- Heats to target and reports AtTemp within the 1.5 C band.
- Stop → FAN_HEATER at 30 % for 900 s, then all fans off + damper closed (EndOfProcess); PendingRunOnSec returns the
  remainder; StartRunOn(seconds) resumes for that time.
- Shutdown → no run-on, EndOfProcess invoked once.
- CancelCooldown refused while heating; after a stop it ends the run-on with all fans off.
- Thermistor loss while heating → loop stops with Fault starting "[9010]".
- Heater-fan failure is confirmed by MeasureRpm at the health check before shutting down.
- Start while running only retargets.

**Tests:** `Process/HeatingLoopTests` — Refuses_when_the_door_is_open, Refuses_when_the_door_is_unreadable,
Refuses_when_the_heater_fan_does_not_spin, Refuses_a_target_below_the_minimum,
Enable_sequence_spins_the_fan_for_two_seconds_before_the_element, Heats_to_the_target_and_reports_at_temp,
Stop_runs_the_fan_on_at_thirty_percent_then_closes_everything_after_the_cooldown,
The_run_on_a_stop_would_cut_is_known_and_can_be_resumed_for_the_time_left, Shutdown_has_no_run_on,
Cancel_cooldown_is_refused_while_heating_and_ends_with_all_fans_off, Thermistor_loss_shuts_the_heater_down_with_9010,
Fan_failure_is_confirmed_at_the_health_check_before_shutting_down, Restart_while_running_only_retargets.
Use `FakeHardwareSystem` (ambient 24 C, heat 0.5 C/s when element on, idle drift 0.05 C/s) + `FakeTimeProvider` + `TimePump`.

**Reference (source):** `src/SCureBox.Application/Devices/IHeatingLoop.cs`, `Devices/HeatingLoop.cs`,
`Devices/HeatingStatus.cs`, `tests/SCureBox.Application.Tests/Process/HeatingLoopTests.cs`

---

### PROC-04 — Cooling loop (fixed-fan chamber cooling)
**Summary**
- **What it is for:** Cools the chamber down to a target temperature after a heating step.
- **Problem it solves:** Without a cooling process the parts would cool slowly and unevenly, and the fans and air vent (damper) would not be handled in a safe order.
- **How we solve it:** We open the damper, run the heater fan and the cooling fan at a fixed speed, and stop everything when the target is reached. We also measure how fast the chamber cools.


**Project / folder:** `SCureBox.Application.csproj` — `Devices/`

**Goal:** Fixed-duty chamber cooling: damper open, heater fan at a fixed duty, chamber cooling fan (FAN_COOLING) at a
constant duty until the chamber reaches the target, then auto-terminate (fans off, damper closed via `EndOfProcess`).
Reports the measured cooling rate for telemetry. Port of Python `cooling_mode.CoolingController`.

**Depends on:** PROC-02, Domain (`SlopeEstimator`, `OpResult`), Hardware (`SetDamper(bool)`, `SetFanDuty`,
`ReadTemperature`, `Config.Cooling`, `Config.Heater`).

**Files to create:**
- `Devices/ICoolingLoop.cs` — `ICoolingLoop`
- `Devices/CoolingStatus.cs` — `CoolingStatus`
- `Devices/CoolingLoop.cs` — `CoolingLoop`

**Public contract:**
```csharp
public interface ICoolingLoop : IDisposable {
  bool Active { get; } string? Fault { get; }
  Action? EndOfProcess { get; set; }
  OpResult Start(double pwm, double targetC);
  void Stop(string reason = "user");
  CoolingStatus Status();
}
public sealed record CoolingStatus(bool Active, double Pwm, double? Rate, double? Temp, double? Target, string? Fault);
public sealed class CoolingLoop : ICoolingLoop { public CoolingLoop(IHardwareSystem hw, TimeProvider tp, ILogger<CoolingLoop> log); }
```

**Behaviour & rules:**
1. `Start(pwm, targetC)`: pwm clamped to 0..100. If the thread is alive and Active → `SetPwm(pwm)` (FAN_COOLING duty =
   round(pwm); exception → `Fail("chamber fan not confirmed: {msg}", 6015)`) and on success update the target; return.
2. Fresh start: clear Fault; thermistor check on TEMP_CHAMBER (same three texts as heating with sensor name TEMP_CHAMBER,
   range `heater.temp_valid_min..max`) → on failure Fault = why, return `FromRefusal(why)`.
3. Entry sequence (exact order): (1) `SetDamper(true)` — exception → Fault `"damper open failed: {msg}"`, FromRefusal;
   (2) `SetFanDuty(FAN_HEATER, cooling.heater_fan_pwm)` (default 100); (3) `SetFanDuty(FAN_COOLING, round(pwm))` —
   exception in 2/3 → Fault = msg, invoke EndOfProcess, FromRefusal(msg).
4. Then pwm/target/temp stored, rate null, Active = true; thread "cooling-loop" started; return `Success("cooling started")`.
5. Loop every `max(0.1, cooling.sample_sec)` (default 1.0 s): thermistor bad → Finish(why); `t <= target` → Finish(null)
   (auto-terminate); else add (seconds since start, t) to `new SlopeEstimator(cooling.window_sec)` (default 30 s);
   Rate = `-(slope.RatePerMinute())` (positive while cooling) or null.
6. `Finish(fault)`: cancel; invoke `EndOfProcess`; Active = false; Fault = fault if non-null; log.
7. `Stop(reason)`: cancel; join loop (10 s, not from own thread); if still Active → Finish(reason == "user" ? null : reason).
8. `Status()` → `CoolingStatus(Active, Pwm, Rate, Temp, Active ? Target : null, Fault)`.

**Configuration:** `cooling` {damper_open_angle 0, damper_closed_angle 90, heater_fan_pwm 100, mode_pwms {fast 100,
medium 60, slow 30}, fast_led_fan_pwm 100, target_temp 25, sample_sec 1.0, window_sec 30}; `heater.temp_valid_min/max`.

**Acceptance criteria:**
- Entry order is damper open → heater fan → chamber fan.
- At chamber <= target the loop ends: fans off, damper closed, Active false.
- Rate is positive while the chamber cools.
- No valid thermistor → refused, nothing driven.
- Start while running updates FAN_COOLING duty and the target.

**Tests:** `Process/CoolingLoopTests` — Entry_sequence_opens_the_damper_then_fixes_both_fans,
Auto_terminates_at_the_target_with_fans_off_and_damper_closed, Reports_the_measured_cooling_rate,
Refuses_without_a_valid_thermistor, Retarget_while_running_updates_duty_and_target.

**Reference (source):** `src/SCureBox.Application/Devices/ICoolingLoop.cs`, `Devices/CoolingLoop.cs`,
`Devices/CoolingStatus.cs`, `tests/SCureBox.Application.Tests/Process/CoolingLoopTests.cs`

---

### PROC-05 — CureController: process commands, pre-flights, UV, airflow, door, state snapshot
**Summary**
- **What it is for:** The central controller of the machine. It turns requests like heat, dry, cure with UV, cool or open door into actions on the hardware, and builds the live status.
- **Problem it solves:** Many parts (heater, UV lights, fans, damper, door, fume extractor) must work together in the right order. Starting a process with a broken sensor or fan would be unsafe.
- **How we solve it:** One class combines all parts. Before each process it checks sensors and fans and refuses with a clear error code if something is wrong. It applies each step in a safe order and reports the full machine status.


**Project / folder:** `SCureBox.Application.csproj` — `Process/CureController.cs` (namespace `SCureBox.Application.ProcessControl`)

**Goal:** The machine-level command surface (`ICureController`, port of Python `io_bridge.IOBridge`). It composes heating,
cooling, UV panels, damper, fans, BOFA extractor, door magnet and RGB override into the operations the API exposes, runs
the start pre-flights, and builds the `/api/state` snapshot. Nitrogen is PROC-06, diagnostics PROC-07 (same class).

**Depends on:** PROC-01, PROC-02, PROC-03, PROC-04, PROC-08 (`SupervisionState`, `LedCheckOverride`), PROC-10
(`StripStatus`, `RgbColors`), Application-Platform (`BofaPolicy`: `Connected`, `DutyPercent` default 10, `Choose(bool)`),
Domain (`StripInputs`, `StripModeLadder`, `SensorSupervisionEvaluator`, `UvLightEvaluator.IsLit`, `NtcMath.VoltageToResistance`,
`HardwareNames`, `ErrorCodes`), Hardware (`IHardwareSystem`).

**Files to create:** `Process/CureController.cs` — `public sealed class CureController : ICureController, IDisposable`

**Public contract (beyond ICureController):**
```csharp
public CureController(IHardwareSystem hw, IHeatingLoop heating, ICoolingLoop cooling, SupervisionState supervision,
    StripStatus strip, TimeProvider timeProvider, ILogger<CureController> log, LedCheckOverride? ledOverride = null,
    BofaPolicy? bofa = null);
public const int DryIntakeFanPwm = 30;
public const double DoorReleaseSec = 2.0;
public const double LedTestMaxTempC = 80.0;
public const double UiAlertFreshSec = 90.0;
public const double LedFanPreflightGraceSec = 30.0;
public const string BofaNotDetectedText = "Settings says a BOFA unit is connected, but nothing is plugged into the connector";
public UvState UvState { get; }
public double CurrentUvPower { get; }            // UV on ? Intensity : 0
public bool DoorAbortLatched { get; }
public bool AnyProcessActive { get; }            // heating.Active || cooling.Active || uv.On
public bool OutputsLive { get; }                 // heating/cooling/uv/n2/bofa on, or any _fanDuty group > 0
public StripInputs StripInputs();
public void SyncCoolingEnd();
public void DoorAbort();
public void SuperviseN2Pressure();               // PROC-06
public static string? N2SensorProblem(PressureReading r, PressureSensorConfig c);   // PROC-06
```

**Behaviour & rules:**
1. **Construction**: sets `heating.EndOfProcess = cooling.EndOfProcess = CloseFansAndDamper`; calls `SetDamper(false)`
   (start from a known-closed damper; logs "damper servo ready (closed)" or "unavailable"); starts a 1 s `PeriodicWorker`
   "damper-watch" running `DamperWatchTick`. LED factors default 1.0 for zones back/door/left/right.
   `_fanDuty` = {led_cooling 0, chamber_intake 0, chamber_heating 0}.
2. **SensorPreflight** (run by Heat/Dry/CureUv/UvOnly/CoolToTarget BEFORE taking `_op`): (a) `sup.BlockingCriticalFans`
   non-empty → `FromRefusal("[{FanFailureOf(first)}] Fan below minimum speed: {fans joined ', '} - the system cannot run until the fan is replaced")`
   (9020-9025); (b) `sup.HeaterReadingFrozen` set → `FromRefusal("[9006] {detail}")`; (c) up to 3 attempts 0.5 s apart
   reading all supervised sensors; `SensorSupervisionEvaluator.OpenRequired(readings)` (chamber/left/right open or out of
   -20..120) empty → pass; after 3rd failure: `sup.NoteSensorPreflightRefusal(bad, now)` (raises 9010-9012 now) and
   refuse with `SensorSupervisionEvaluator.PreflightRefusal(bad)` = `"[{code of first bad}] Temperature sensor disconnected: {Location (SENSOR), ...} - reconnect the sensor before starting a process"`.
3. **CoolingFanPreflight** (Dry and Cool only, after SensorPreflight): skipped if cooling Active, FAN_COOLING overridden,
   or a pass < 30 s ago (`LedFanPreflightGraceSec`). Drive FAN_COOLING 100 % (verify:false), sleep 1.5 s, `MeasureRpm(0.5 s)`,
   set 0. rpm null or < `fan_health.led_fan_min_rpm` (default 100) → `sup.SetFanStopped([FAN_COOLING], {fan: detail})` and
   refuse `"[9034] Chamber cooling fan not spinning: {Label(fan)}: {rpm|?} RPM - job start refused"` (label e.g.
   "Chamber cooling fan (FAN_COOLING)"). Pass → `SetFanStopped([FAN_COOLING], {})` (clears 9034), remember pass time.
4. **LedFanPreflight(wavelength)** (inside SetUv on): skipped if UV already on or a pass < 30 s ago. Fans = distinct
   `LedFan[l]` for `hw.AllowedLeds(wavelength)`; none → pass. All to 100 %, sleep 1.5 s, measure each 0.5 s; overridden
   fans are ignored; failures → all those fans set 0, `SetFanStopped(fans, {fan: "LED cooling fan not spinning: {Label}: {rpm} RPM - job start refused"})`,
   refuse `"[{FanStoppedOf(first)}] LED cooling fan not spinning: {list} - job start refused"` (9030-9033). Pass → clear,
   record pass time (fans stay at 100 %).
5. **SetUv(on, intensityPct, wavelength)** under `_op`: off → `AllLedsOff()` (exception → `Fail("LED off failed: …", 6015)`),
   `_uv = Off`, `Success("UV off")`. On → `hw.SelectMode(wavelength)` (all LEDs off, relay, SSRs + GPIO17 verified in
   Hardware; exception → `_ledFault = msg`, FromRefusal(msg)); LedFanPreflight; then for each allowed LED: physical =
   clamp(intensity × factor[zone], 0, 100), `SetLed(led, physical)`, outputs[zone] = round(physical, 2); per-LED exception
   recorded as fault. No LED lit → `_ledFault = fault ?? "no LED could be enabled"`, FromRefusal. Success: `_ledFault = null`,
   `_uv = new UvState(true, (int)intensity, wavelength, outputs)`, message `"UV {nm}nm @ {int}%"`. 405 nm lights all four
   panels; 450 nm only LED_DOOR (decided by `hw.AllowedLeds`).
6. **SetLedFactors**: for each zone, value clamped 0..1.5, missing → 1.0.
7. **ReportUiAlerts(c, w)**: stores (max(0,c), max(0,w), now). Fresh for 90 s in `StripInputs`.
8. **StripInputs(internetOk)** → `new StripInputs(DriverFault: hw.DriverFault!=null || heating.Fault!=null || _ledFault!=null || cooling.Fault!=null,
   UiCritical: fresh && critical>0, DoorAbortLatched, DoorOpen: hw.DoorOpen()==true, UiWarning: fresh && warning>0,
   ManualHeat: heating.Active && _manualHeat && !cooling.Active && !uv.On, AnyProcess: heating.Active||cooling.Active||uv.On, InternetOk)`.
9. **Ventilation** (private `SetVentilation(want)`): unchanged → Success; want && cooling.Active → Fail("cooling owns the airflow while it is active", 6015);
   pwm = clamp(ventilation.fan_pwm, 0..100) (default 60); want: pwm<=0 → Fail("ventilation disabled (ventilation.fan_pwm = 0)", 6015);
   SetDamper(true) then SetFanSpeed(chamber_intake, pwm) (failure → close damper, return); off: intake 0, damper closed.
10. **Drying**: `DryToTarget` arms `_drying`; `DamperWatchTick` (1 s) fires once when drying && heating.Active &&
    heating AtTemp: `_drying=false`, SetDamper(true), on success `StartDryFan()` = SetFanSpeed(chamber_intake, 30).
    `StopDryFan()` sets intake 0 if the dry fan was on.
11. **SetDamper(open)**: no-op Success if already in that state; `hw.SetDamper(open)` exception → `Fail("damper failed: …", 6015)`;
    messages "Damper opened"/"Damper closed".
12. **SetFanSpeed(group, percent)**: refusals (6015): chamber_heating while heating Active ("heater fan is controlled by the
    heating loop while it is active"); chamber_intake while cooling Active ("intake fan is controlled by the cooling loop while it is active");
    led_cooling while the FAST-cool LED boost is on ("LED fans are boosting the fast cooling while it is active"). Writes every
    member fan (verify:false; exception → Fail("fan write failed: …", 6015)), stores `_fanDuty[group]`; chamber_intake →
    `IntakeAir(percent > 0)`. Message `"{group} set to {percent}%"`. `SetHeaterFan(p)` = SetFanSpeed(chamber_heating, p).
13. **SetFanOverride(name, on)**: "all" → every fan; a group name; a fan name; else `Fail("unknown fan: {name}")` (no code).
    Calls `sup.SetFanOverride(fans, on)`.
14. **SetCoolLedFans(on)** (FAST-cool boost): no-op if unchanged or any LED level > 0; pwm = clamp(cooling.fast_led_fan_pwm);
    on && pwm<=0 → no-op; writes the 4 LED fans; `_fanDuty[led_cooling] = on ? pwm : 0`.
15. **BOFA**: `IntakeAir(running)` stores `_intakeAir` then `ApplyBofa()`. ApplyBofa: want = intakeAir && bofa.Connected;
    duty = want ? bofa.DutyPercent : 0; `CheckBofaPresent()`; nothing changed → return. Up: `SetBofaPower(true)` then
    `SetBofaDuty(duty)`; down: `SetBofaDuty(0)` then `SetBofaPower(false)`; exception → warning, no state change.
    CheckBofaPresent: fault = Connected && `hw.BofaPresent()==false` (exception → null = never raises) →
    `"[9048] " + BofaNotDetectedText`; on change → `_bofaFault`, `sup.SetBofaNotDetected(text|null)`.
    `SetBofaConnected(c)`: `bofa.Choose(c)`, ApplyBofa, messages "BOFA unit connected"/"BOFA unit not connected".
    `SetBofa(on)` (service, direct): power on first / off last, duty = on ? DutyPercent : 0; exception → Fail("BOFA control failed: …", 6015).
16. **CloseFansAndDamper** (EndOfProcess of both loops): IntakeAir(false); keep = LED fans of lit panels (+ FAN_HEATER if
    `heating.HoldFan`); every other fan duty 0; `hw.SetDamper(false)` and `_damperOpen=false`.
17. **HoldHeaterFan(on)** under `_op`: sets `heating.HoldFan`; on: cancel a running cooldown, ensure FAN_HEATER = heater.fan_pwm;
    off: if !heating.Active && !cooling.Active && FAN_HEATER duty > 0 → `heating.StartRunOn()`.
18. **BeginProgramStep(stopDryFan)**: `_drying=false`; optional StopDryFan; `_manualHeat=false`; clear door-abort latch.
19. **HeatToTarget(t)**: SensorPreflight; under `_op`: BeginProgramStep(true), SetUv(false), cooling.Stop("user"),
    SetVentilation(false), SetDamper(false), heating.Start(t) → `"Heating to {t:0.0###}°C"` or heating's refusal.
20. **DryToTarget(t)**: SensorPreflight, CoolingFanPreflight; BeginProgramStep(false) …same… heating.Start; `_drying = ok`;
    `"Drying to {t}°C"`.
21. **CureUv(wl, t, i)**: SensorPreflight; BeginProgramStep(true), cooling.Stop, SetVentilation(false), SetDamper(false),
    h = heating.Start(t), u = SetUv(true, i, wl). Both ok → `"{Cure|Bleaching} UV {nm}nm @ {int i}%, {t}°C"` ("Bleaching" for 450).
    Else FromRefusal(join "; " of failed messages, each prefixed "[code] " when code != 6015; fallback "cure blocked").
22. **UvOnly(wl, i, vent)**: SensorPreflight; BeginProgramStep(true), cooling.Stop, heating.Stop("user") (fan run-on continues),
    SetUv(true) (failure returned), SetVentilation(vent) (failure only logged); `"UV {nm}nm @ {i}% — no heating[, fresh-air vent]"`.
23. **CoolToTarget(t, mode)**: SensorPreflight, CoolingFanPreflight; under `_op`: `_drying=_dryFanOn=_manualHeat=false`,
    clear door latch, SetVentilation(false); pwm = cooling.mode_pwms[mode] ?? mode_pwms[Medium] ?? 60; if cooling not
    already Active: SetUv(false), `heating.Shutdown("user")` (no run-on: cooling owns the heater fan); `cooling.Start(pwm, t)`;
    ok → `_coolingMode = mode`, `_damperOpen = true`, `SetCoolLedFans(mode == Fast)`, IntakeAir(true),
    `"Cooling ({wire}) to {t}°C"`.
24. **SyncCoolingEnd()** (from GetState and every supervision tick): if cooling not Active and `_coolingMode` set → clear
    mode, `_damperOpen=false`, SetCoolLedFans(false).
25. **StopAll(immediate)** under `_op` (always Success): drying off, StopDryFan, manualHeat off, SetUv(false), SetNitrogen(false),
    cooling.Stop, SetCoolLedFans(false), SetVentilation(false), `heating.Stop("user")` (run-on continues), SetDamper(false),
    clear coolingMode/damperOpen, IntakeAir(false). Message `"All cure outputs stopped[ immediately]"`.
26. **Manual heating**: `SetTargetTemperature(t)`: heating Active → SetTarget, `_manualHeat=true`, "Target set to {t}°C";
    else heating.Start, `_manualHeat = ok`. `StopHeating()`: manualHeat false, heating.Stop("user"), "Heating stopped".
27. **OpenDoor()** under `_op`: SetUv(false), heating.Stop("user"), `SetDoorMagnet(true)`, one-shot timer after 2.0 s →
    `SetDoorMagnet(false)`; exception → Fail("door release failed: …", 6015); "Door opened".
28. **DoorAbort()** (called by the door watchdog, PROC-08): under `_op`: `heating.Shutdown("door open")` (no run-on),
    StopAll(true), every FanGroup SetFanSpeed 0, SetBofa(false), latch `_doorAbortAt = now`. Error log "[SAFETY] Door opened
    mid-process - ALL outputs forced OFF". The latch (state.doorAborted, 6016 to the runner) clears by `AckDoorAbort()`
    ("Door abort acknowledged") or any new process start (BeginProgramStep, CoolToTarget, SetNitrogen(true)).
29. **AckFanAlarms()**: `sup.AcknowledgeFanAlarms()` → released list; message "Fan alarm acknowledged (nothing to release)"
    or "Fan alarm acknowledged: {list}". **AckWatchdogTrip()** → "Watchdog alert acknowledged" / "No watchdog alert to acknowledge".
30. **SetRgb(on, color)**: off → `strip.SetOverride(false, null)`, "RGB off". On → `RgbColors.Parse(color ?? "white")`
    (ArgumentException → Fail(msg)); `strip.SetOverride(true, color)`; fill `rgb.count` pixels with
    `StripModeLadder.Scale(rgb, brightness/100)`; write exception → clear override, Fail("strip write failed: …").
31. **GetState()**: calls SyncCoolingEnd; `ChamberTemp = read(TEMP_CHAMBER) ?? heat.Temp`; `TargetTemp = heat.Active ? heat.Target : cool.Active ? cool.Target : null`;
    `InternetOk = strip.InternetOk`; `DoorClosed = DoorOpen() null → null else !open`; `CoolingMode = mode?.Wire()`;
    `UvWavelength = nm`; `FanDutyEach[fan] = hw.GetFanDuty` (exception → key omitted); `FanRpmEach[fan] = ReadRpm ?? 0`;
    `FanRpm[group] = min of readable member RPMs, else 0`; `LedTemps` keys left/right/back/door = round1(TEMP_LEFT/RIGHT/BACK/DOOR);
    `UvSensors["left"/"right"]` = (volts round 3, kOhm = round1(NtcMath.VoltageToResistance(v)/1000), lit = UvLightEvaluator.IsLit(v, sup.UvBaseline, uv_light_check.lit_ratio)),
    read exception → all null; N2 fields per PROC-06; `HeaterPwm = heat.Active ? heat.Pwm : 0`; `HeaterOut = heat.Active && heat.HeaterOut`;
    `CoolingRate = cool.Rate`; `CoolingFanPwm = cool.Active ? round(cool.Pwm) : null`; `Faults = {Heater: heat.Fault, Cooling: cool.Fault, Led: _ledFault, N2: _n2Fault, Bofa: _bofaFault}`;
    `Sensors/FanHealth/LedHealth/Alerts/AlertDetails` from `sup.Snapshot` (FanHealth keyed by Fan name, Duty rounded;
    LedHealth keyed by LedPanel name); `FanOverride = sup.OverriddenFans`; `StripMode = strip.Mode`;
    `UiAlerts = {critical, warning, at (unix s)}` or empty; `LedChecksEnabled = LedCheckOverride.Effective(led_heating, override).Enabled`;
    `HwSource = hw.Source`; `DamperDriver = hw.DamperDriver`.
32. **Shutdown()**: dispose damper watch; then each step best-effort: RgbOff, heating.Shutdown("user"), cooling.Stop("user"),
    AllLedsOff, SetNitrogen(false), LedPowerOff; `_uv = Off`. `Dispose()` disposes the damper watch.

**Configuration:** `ventilation.fan_pwm` (60), `cooling.mode_pwms` / `fast_led_fan_pwm`, `heater.fan_pwm`,
`fan_health.led_fan_min_rpm` (100), `uv_light_check.lit_ratio` (0.6), `led_heating.enabled` (false), `rgb.count` (21),
`rgb.status.brightness` (100), BOFA settings via `BofaPolicy` (bofa.json `dutyPercent`, default 10).

**Acceptance criteria:**
- TEMP_LEFT open → HeatToTarget refused with code 9011, message "Temperature sensor disconnected: Left LED panel (TEMP_LEFT) - reconnect the sensor before starting a process",
  at least 1.0 s of fake time consumed (3 reads 0.5 s apart), 9011 in state.alerts, heating not active; a latched
  critical FAN_COOLING → 9021.
- CureUv 405 @ 80 % with factors left 0.5/right 1.5/back 1.0/door 0.8 → levels 40/100/80/64; message
  "Cure UV 405nm @ 80%, 60.0°C"; all LED fans at 100 %. CureUv 450 @ 30 % → only door = 30; "Bleaching UV 450nm @ 30%, 50.0°C".
- FAN_COOLING at 0 RPM → CoolToTarget and DryToTarget refused with 9034 and message
  "Chamber cooling fan not spinning: Chamber cooling fan (FAN_COOLING): 0 RPM - job start refused"; Heat and UvOnly still start.
- FAN_BACK at 0 RPM → CureUv refused with 9032.
- UvOnly with vent → damper open, intake fan at ventilation.fan_pwm.
- Cool Fast boosts LED fans; changing mode releases them; fresh cooling entry shuts the heater down without run-on;
  cooling auto-end clears the mode and the boost.
- Drying opens damper + intake 30 % once at temperature.
- StopAll clears everything but leaves the heater-fan run-on.
- OpenDoor stops UV and heater and pulses the magnet for 2 s.
- Manual heating sets StripInputs.ManualHeat; a program step clears it.
- Fan-speed refusals as in rule 12; override parsing ("all", group, fan, unknown).
- Shutdown turns everything off.

**Tests:** `Process/CureControllerTests` (via `Fakes/ProcessRig`): Heat_refuses_with_the_sensor_code_9011_when_a_required_sensor_is_open,
Heat_refuses_with_the_fan_code_9021_while_a_fan_is_latched_critical, Heat_succeeds_and_state_reflects_it,
Cure_405_lights_every_allowed_led_with_the_zone_factors, Cure_450_lights_only_the_door_led,
Chamber_cooling_fan_preflight_refuses_drying_and_cooling_starts_with_9034_and_nothing_else,
Led_fan_preflight_refuses_with_the_fan_code_9032, Uv_only_with_vent_opens_the_damper_and_runs_the_intake_fan,
Cool_fast_boosts_the_led_fans_and_a_mode_change_releases_them, Cool_fresh_entry_shuts_the_heater_down_without_run_on,
Cooling_auto_end_clears_the_mode_and_the_boost, Drying_opens_the_damper_and_intake_fan_once_at_temperature,
Stop_clears_everything_and_keeps_the_heater_fan_run_on, Open_door_stops_uv_and_heater_and_pulses_the_magnet,
Manual_heating_flags_the_strip_and_a_program_step_clears_it, Fan_speed_refusals_and_override_parsing,
Rgb_override_and_ui_alerts, Fan_critical_mid_process_stops_every_output, Get_state_has_every_contract_field (also checks
Fans keys = led_cooling/chamber_intake/chamber_heating, 6 FanRpmEach, 6 FanDutyEach, LedTemps keys back/door/left/right,
Sensors keys back/chamber/door/left/right, 6 FanHealth, LedHealth keys LED_LEFT/LED_RIGHT, LedChecksEnabled false,
N2LinePressure 2.0, MinBar 0.5, MaxBar 3.0, DamperDriver "pio" with the fake), State_reports_the_uv_photoresistors_as_light_not_temperature,
Shutdown_turns_everything_off. Door tests are in PROC-08. Plus `Platform/BofaPolicyTests` (Application-Platform) for BOFA.

**Reference (source):** `src/SCureBox.Application/Process/CureController.cs`,
`tests/SCureBox.Application.Tests/Process/CureControllerTests.cs`, `tests/SCureBox.Application.Tests/Fakes/*`

---

### PROC-06 — Nitrogen control and N2 interlocks (9008 / 9009 / 9015 / 9016)
**Summary**
- **What it is for:** Opens and closes the nitrogen valve that fills the chamber with nitrogen, and watches the gas line pressure.
- **Problem it solves:** Pressure that is too high, no gas supply, a blocked tube or a broken pressure sensor could damage the machine or give a bad cure without anyone knowing.
- **How we solve it:** We check the pressure before opening and every second after. Too high pressure closes the valve. Too low pressure or a missing sensor stops opening. If pressure does not drop after opening, the gas is not flowing, so we close the valve and raise an alert.


**Project / folder:** `SCureBox.Application.csproj` — `Process/CureController.cs` (nitrogen section)

**Goal:** Open/close the nitrogen purge valve with line-pressure protections: never open above `max_bar` (9008), refuse
when the settled closed-valve pressure is below `min_bar` (9009), close the valve if the line pressure does not drop
after opening (flow check, 9015), raise 9016 when the pressure sensor gives no valid reading for 20 s and refuse opening
while it is active. The supervision tick calls `SuperviseN2Pressure()` every second.

**Depends on:** PROC-05 (same class), PROC-08 (`SupervisionState` setters), Hardware (`ReadPressure()` → `PressureReading`
{Volts, Mpa?, Bar?, On, Saturated, Mode, SetPointMpa}, `SetNitrogenValve(bool)`, `Config.PressureSensor`), Domain
(`PressureSensorParameters.ModeSwitch / ModeAnalogVoltage / ModeAnalogCurrent`).

**Files to create:** part of `Process/CureController.cs`.

**Public contract:**
```csharp
public static readonly TimeSpan N2LowSettle = TimeSpan.FromSeconds(3);
public const string N2SensorNotReadingText = "N2 pressure sensor not reading - check that the nitrogen pressure sensor is connected.";
public static string N2TooHighText(double bar, double maxBar, string action);
public static string N2NoSupplyText(double bar, double minBar);
public static string N2FlowBlockedText(double bar);
public static string? N2SensorProblem(PressureReading r, PressureSensorConfig c);
public OpResult SetNitrogen(bool on);
public void SuperviseN2Pressure();
private sealed record N2FlowCheck(double P0, DateTimeOffset OpenedAt);
```
Texts (InvariantCulture; Bar1 = "0.0", BarLimit = "0.0##"):
- `N2TooHighText` = `"N2 supply pressure too high ({Bar1(bar)} bar > {BarLimit(max)} bar) - nitrogen {action}. Lower the regulator below {max:0.###} bar."`
- `N2NoSupplyText` = `"No nitrogen supply - line pressure {Bar1(bar)} bar is below {BarLimit(min)} bar. Check the nitrogen line and regulator."`
- `N2FlowBlockedText` = `"Nitrogen is not flowing into the chamber - the line pressure stayed at {Bar1(bar)} bar after the valve opened. Check the nitrogen valve and the tube to the chamber."`

**Behaviour & rules:**
1. `ReadN2()` → `(reading, problem)`: `ReadPressure()` exception → `(null, "read error: {msg}")`; else `(r, N2SensorProblem(r, cfg))`.
2. `N2SensorProblem`: switch mode → null (never flagged); Saturated → `"input saturated ({volts:0.00} V)"`; Bar null →
   `"no pressure value"`; vSensor = volts × divider; analog_voltage and vSensor outside `[v_min×0.9, v_max×1.1]` →
   `"sensor output {v:0.00} V is outside its {vmin:0.#}-{vmax:0.#} V range"`; analog_current: mA = vSensor/shunt_ohms×1000 outside
   `[i_min×0.9, i_max×1.1]` → `"sensor output {ma:0.0} mA is outside its {imin:0.#}-{imax:0.#} mA range"` (tolerance
   `PressureSensorConfig.RangeTolerance = 0.10`).
3. `LineBar()` = bar only when problem is null.
4. `SetNitrogen(on)`:
   - on && valve closed && `pressure_sensor.required` && 9016 active → `Fail(N2SensorNotReadingText, 9016)`.
   - p0 = (on && was closed) ? LineBar() : null. settled = never closed before OR now − closedAt >= 3 s.
   - If on and bar (p0 when closing→opening, fresh LineBar when already open) is known: bar > max_bar → force valve closed
     (best effort), `_n2On=false`, `sup.SetN2PressureTooHigh(N2TooHighText(bar,max,"closed"))`, return
     `Fail(N2TooHighText(bar,max,"not opened"), 9008)`. Exactly max is allowed. If was closed && settled && bar < min_bar →
     `Fail(N2NoSupplyText(bar,min), 9009)` (low limit judged only with the valve closed and settled).
   - `SetNitrogenValve(on)` exception → `Fail("nitrogen valve failed: …", 6015)`. Closing an open valve records closedAt.
   - Flow-check bookkeeping (under `_n2Lock`): off → pending check dropped (no verdict); new opening → clear `_n2Fault` and
     `sup.SetN2FlowBlocked(null)`, pending check = `flow_check_enabled && settled && p0 known ? new N2FlowCheck(p0, now) : null`.
   - on → clear door-abort latch. Messages "Nitrogen valve opened"/"Nitrogen valve closed".
5. `SuperviseN2Pressure()` (1 Hz from supervision): read; `SuperviseN2Sensor`; bar = valid bar or null.
   - bar > max_bar: if valve open → close it, `_n2On=false`, closedAt=now, drop flow check, error log; always
     `sup.SetN2PressureTooHigh(N2TooHighText(bar,max,"closed"))`.
   - else if 9008 active → clear it (also when there is no reading: no evidence of over-pressure).
   - then `SuperviseN2Flow(bar)`.
6. `SuperviseN2Sensor(cfg, problem)`: required && problem → missingSince ??= now; once `now − missingSince >= not_reading_after_sec`
   (20 s) and 9016 not active → `sup.SetN2SensorNotReading(N2SensorNotReadingText)`; never touches the valve. Valid reading
   (or not required) → missingSince = null and clear 9016. A single valid reading restarts the debounce.
7. `SuperviseN2Flow(cfg, bar)`: no pending check → return. Valve closed or check disabled → drop. `P0 − bar >= min_drop − 1e-9`
   → pass (drop). Within window (`flow_check_window_sec`, 5 s) → wait. Window over: drop the check; no bar → not judged
   (warning only); else close the valve, `_n2On=false`, closedAt=now, `_n2Fault = "[9015] " + N2FlowBlockedText(bar)`,
   `sup.SetN2FlowBlocked(detail)`. 9015 clears only at the next opening.
8. State fields: `NitrogenActive = _n2On`; `N2Pressure = dto` (volts round 3, mpa round 3, bar round 2, plus config
   min/max/flow fields) or null on read error; `N2LinePressure = dto.Bar`; `N2Sensor = (required, problem == null, problem)`;
   `Faults.N2 = _n2Fault`.

**Configuration:** `pressure_sensor` {mode "analog_voltage", v_min 1.0, v_max 5.0, i_min_ma 4, i_max_ma 20, shunt_ohms 120,
p_at_low_mpa 0, p_at_high_mpa 1.0, divider 1.0, adc_saturation_volts 3.2, on_above_volts 2.0, set_point_mpa 0.6,
max_bar 3.0, min_bar 0.5, flow_check_enabled true, flow_check_window_sec 5, flow_check_min_drop_bar 0.3, required true,
not_reading_after_sec 20}.

**Acceptance criteria:**
- Open at 3.5 bar → Fail 9008, valve stays closed, 9008 in alerts; exactly 3.0 bar opens.
- Pressure rising above the limit while open → valve closes, 9008 raised; clears when ≤ limit; limit from config.
- No bar value (switch mode / read error) never blocks or closes; a lost reading after 9008 clears 9008.
- Settled closed-valve reading 0.3 bar → Fail 9009; reading near 0 while open keeps it open with no alert; a low reading
  < 3 s after closing is not judged.
- Flow check: drop ≥ 0.3 bar within 5 s passes (exactly 0.3 passes); no drop → 9015, valve closed, Faults.N2 = "[9015] …";
  closing before the window ends → no alert; no baseline → no check; no bar at window end → no verdict; config can disable/tune.
- A purge step hitting 9015 fails the program with 9015 (PROC-09).
- 9016: raised after 20 s of invalid readings, cleared by the first valid one; a glitch restarts the debounce; saturated
  and out-of-range are "not reading"; switch mode never flagged; opening refused with 9016 while active; losing the
  reading mid-purge raises the alert but leaves the valve open; required=false disables; unplugged sensor (~0 V) never
  reads as no supply or over-pressure.

**Tests:** `Process/N2PressureInterlockTests` (10 facts), `Process/N2FlowCheckTests` (11 facts),
`Process/N2SensorSupervisionTests` (9 facts) — names as listed in the source test files (e.g.
Open_is_refused_above_3_bar_with_9008_and_the_valve_stays_closed, No_drop_within_the_window_raises_9015_and_closes_the_valve,
Not_reading_is_debounced_20_s_then_raises_9016_and_clears_when_readings_return). Fake: `FakeHardwareSystem.Pressure`,
`OpenPressure`, `N2FlowBlocked`, `PressureFault`, `LinePressure(bar)`.

**Reference (source):** `src/SCureBox.Application/Process/CureController.cs` (ReadN2 … SetNitrogen),
`tests/SCureBox.Application.Tests/Process/N2*Tests.cs`

---

### PROC-07 — Diagnostics: fan test and LED heating test
**Summary**
- **What it is for:** Service tests: a fan test that measures fan speeds, and an LED test that turns the UV panels on and checks they warm up.
- **Problem it solves:** Technicians need a quick way to find a weak fan or a dead LED panel before it causes a failed cure.
- **How we solve it:** The fan test runs fans and compares the measured speed to the expected speed, giving OK, WARN or FAIL. The LED test cools warm panels first, lights them, and checks that each panel temperature rises enough.


**Project / folder:** `SCureBox.Application.csproj` — `Process/CureController.cs` (diagnostics section)

**Goal:** Operator/service diagnostics: measure fan RPMs and judge them against the same nominal-RPM policy as the wear
supervision; and an LED test that lights the panels and checks that each panel thermistor rises.

**Depends on:** PROC-05, PROC-08 (`SupervisionService.ToRules(FanHealthConfig, bool damperOpen)`), Domain
(`FanHealthEvaluator.ExpectedRpm`, `FanHealthRules.CriticalFor(fan)`, `WarnBelowPct`, `HardwareNames.Label`).

**Files to create:** part of `Process/CureController.cs`.

**Public contract:** `FanTestResult RunFanTest(string fanOrGroupOrAll)`; `LedTestResult RunLedTest(int seconds, double minRiseC, Wavelength wavelength, int intensity = 100)`.

**Behaviour & rules:**
1. Fan test target: "all" → every fan; empty → "chamber_heating"; else a FanGroup name; unknown →
   `FanTestResult(true, 0, "FAIL", {}, "unknown fan: {x}")` (individual fan names are NOT accepted here).
2. rules = `ToRules(fan_health, damperOpenNow)` (open-damper nominal table for FAN_COOLING when the damper is open);
   minRpm = `heater.min_fan_rpm` (100).
3. Under `_op`: per fan, busy = current duty > 0; judged duty = busy ? current duty : 100. Non-busy fans set 100 %
   (verify:false); sleep 2.0 s; measure all fans in parallel threads (`MeasureRpm(fan, 1 s)`, exception → 0, join ≤ 5 s);
   judge; non-busy fans set back to 0 (a fan a loop owns keeps running).
4. Judge: expected = ExpectedRpm(nominal points, duty) (int when > 0); rpm < minRpm → FAIL (with Expected); no expected
   → OK (duty only); deficit = round((1 − rpm/expected)×100, 1); FAIL if deficit ≥ CriticalFor(fan) (default 20 %, heater
   11.8 %), WARN if ≥ warn_below_pct (10 %), else OK.
5. Result: Ok = true; Rpm = min rpm; Status FAIL > WARN > OK; Message = comma-joined lines for FAIL then WARN fans:
   `"{label}: {rpm} RPM — not spinning"` (rpm < min or no expected) or
   `"{label}: {rpm} RPM, {exp} RPM expected at {duty} % duty ({deficit:0} % below nominal)"`; null if all OK.
6. LED test constants: precool when any start temp ≥ 30.0 C, precool 20 s; panel sensors ("Left LED", TEMP_LEFT),
   ("Right LED", TEMP_RIGHT), ("Back LED", TEMP_BACK), ("Door LED", TEMP_DOOR).
7. Busy (UV on, heating or cooling active) → `(false, "FAIL", "busy", …, [], "a process is running - run the LED test when the machine is idle")`.
8. Under `_op`: read start temps; precool: LED fans 100 % for 20 s then restore previous duties; re-read; Precooled = true.
   Sensor stage: each entry Status OK if temp < 80.0 C (`LedTestMaxTempC`) else FAIL (null = FAIL) → stage "sensors",
   message "no valid temperature reading: {names}".
9. `SetUv(true, intensity, wavelength)` (LED-fan pre-flight applies); failure → stage "uv", message "LEDs could not be switched on: {msg}".
10. Sleep `seconds`, read end temps, always `SetUv(false)`. At 450 nm "Door LED" is INFO (not judged). Rise = round(end − start, 1);
    OK if rise ≥ minRiseC else FAIL. Message: "did not heat up: {Name} ({+0.0} C in {s} s), …" plus "; {Name} not judged at {nm} nm ({rise} C)"
    notes; Status FAIL/OK; stage "heating".

**Configuration:** `fan_health` (warn_below_pct 10, critical_below_pct 20, critical_below_pct_by_fan {FAN_HEATER 11.8},
nominal_rpm tables, nominal_rpm_damper_open {FAN_COOLING 60→2470, 100→4075}), `heater.min_fan_rpm`.

**Acceptance criteria:** result shape per fan (Rpm, Status, Duty, Expected, DeficitPct); reading judged against nominal;
a busy fan judged at its own duty (e.g. 30 % run-on against the 30 % nominal); a fan a loop owns stays running after
the test; LED test stages busy/sensors/uv/heating; warm panel ≥ 30 C precools.

**Tests:** in `Process/CureControllerTests`: Fan_test_result_shape, Fan_test_judges_the_reading_against_the_nominal_rpm,
Fan_test_judges_a_busy_fan_at_its_own_duty, Fan_test_leaves_a_fan_a_loop_owns_running, Led_test_stages,
Led_test_precools_a_warm_panel.

**Reference (source):** `src/SCureBox.Application/Process/CureController.cs` (RunFanTest, Judge, FanTestMessage, RunLedTest)

---

### PROC-08 — Safety supervision (1 Hz tick, verdict store, door watchdog, 9006 restart)
**Summary**
- **What it is for:** A safety watcher that checks the machine every second while it runs: sensors, fans, heater, LEDs, nitrogen and the door.
- **Problem it solves:** Faults can happen in the middle of a process: a fan stops, a sensor freezes, the heater does not heat, or the door is opened. Without a watcher the machine would keep running in an unsafe state.
- **How we solve it:** Every second we check all readings and publish active alerts. Each problem has a fixed reaction: stop all outputs, turn the heater off, restart the machine, or abort everything if the door stays open for 10 seconds.


**Project / folder:** `SCureBox.Application.csproj` — `Supervision/`

**Goal:** A 1 Hz safety tick that runs the Domain evaluators against live readings, publishes their verdicts as the
supervision snapshot (alerts + details for `/api/state`), and applies the consequences: critical fan → stop every output,
chamber NTC open while heating → heater shutdown, frozen reading (9006) → heater off + machine restart, heater not heating
(9007) → heater off; runs the N2 interlock; and the door watchdog (door open with outputs live for `abort_after_sec` →
door abort).

**Depends on:** PROC-05/06 (`CureController`), PROC-03, PROC-02, Application-Platform (`ISystemService.Reboot()`,
`FrozenReadingStore` / `FrozenReadingRecord(double FrozenAtC, string Detail, DateTimeOffset At)`), Domain evaluators
(`SensorSupervisionEvaluator`, `FrozenReadingEvaluator`, `NoHeatEvaluator`, `FanHealthEvaluator`, `LedHeatingEvaluator`,
`UvLightEvaluator`, rules records `FanHealthRules`, `LedHeatingRules`, `FrozenReadingRules`, `NoHeatRules`, `UvLightRules`,
entries `SensorState`, `FanHealthEntry`, `LedHealthEntry`), Hardware (`OutputFreeze`, config records).

**Files to create:**
- `Supervision/SupervisionInputs.cs` — `SupervisionInputs`
- `Supervision/SupervisionConsequences.cs` — `SupervisionConsequences`
- `Supervision/SupervisionSnapshot.cs` — `SupervisionSnapshot`
- `Supervision/SupervisionState.cs` — `SupervisionState`
- `Supervision/SupervisionService.cs` — `SupervisionService : IHostedService, IDisposable`
- `Supervision/LedCheckOverride.cs` — `LedCheckOverride`

**Public contract:**
```csharp
public sealed record SupervisionInputs(Func<TempSensor, double?> ReadTemp, bool HeatingWanted,
  IReadOnlyList<(Fan fan, double duty, int? rpm)> Fans, IReadOnlySet<LedPanel> LitPanels, double UvIntensity,
  FanHealthRules FanRules, LedHeatingRules LedRules, DateTimeOffset Now, bool LedChecksEnabled = true,
  double HeaterDutyPct = 0, FrozenReadingRules? FrozenRules = null, NoHeatRules? NoHeatRules = null,
  Func<UvSensor, double?>? ReadUvVolts = null, UvLightRules? UvRules = null, double? HeatTargetC = null);
public sealed record SupervisionConsequences(IReadOnlyList<Fan> NewlyCriticalFans, bool ChamberSensorOpenWhileHeating,
  string? ChamberReadingFrozen = null, string? HeaterNotHeating = null);
public sealed record SupervisionSnapshot(IReadOnlyDictionary<string, SensorState> Sensors,
  IReadOnlyDictionary<Fan, FanHealthEntry> FanHealth, IReadOnlyDictionary<LedPanel, LedHealthEntry> LedHealth,
  IReadOnlyList<int> Alerts, IReadOnlyDictionary<string, string> AlertDetails) { public static SupervisionSnapshot Empty { get; } }

public sealed class SupervisionState {
  public SupervisionState(); public SupervisionState(FrozenReadingStore? store);
  public SupervisionSnapshot Snapshot { get; }
  public IReadOnlyList<Fan> BlockingCriticalFans { get; }
  public IReadOnlyList<string> OverriddenFans { get; }          // sorted ordinal
  public bool IsFanOverridden(Fan fan);
  public double? UvBaseline(UvSensor sensor);
  public string? HeaterReadingFrozen { get; }                    // 9006 detail
  public string? N2PressureTooHigh { get; } public void SetN2PressureTooHigh(string? detail);      // 9008
  public string? WatchdogTripped { get; } public void SetWatchdogTripped(string detail); public bool AcknowledgeWatchdogTrip(); // 9017
  public string? N2SensorNotReading { get; } public void SetN2SensorNotReading(string? detail);    // 9016
  public string? N2FlowBlocked { get; } public void SetN2FlowBlocked(string? detail);              // 9015
  public string? BofaNotDetected { get; } public void SetBofaNotDetected(string? detail);          // 9048
  public SupervisionConsequences Evaluate(SupervisionInputs inputs);
  public void NoteSensorPreflightRefusal(IReadOnlyList<TempSensor> bad, DateTimeOffset now);
  public void SetFanStopped(IEnumerable<Fan> tested, IReadOnlyDictionary<Fan, string> stopped);
  public IReadOnlyList<string> AcknowledgeFanAlarms();
  public void SetFanOverride(IEnumerable<Fan> fans, bool on);
}
public sealed class SupervisionService : IHostedService, IDisposable {
  public SupervisionService(IHardwareSystem hw, CureController controller, IHeatingLoop heating, SupervisionState state,
    TimeProvider timeProvider, ILogger<SupervisionService> log, ISystemService? system = null,
    OutputFreeze? freeze = null, LedCheckOverride? ledOverride = null);
  public double? RebootInSec { get; } public double? DoorOpenForSec { get; }
  public void Tick();
  public static FanHealthRules ToRules(FanHealthConfig c, bool damperOpen = false);
  public static NoHeatRules ToRules(NoHeatConfig c, double atTargetBandC = 1.5);
  public static UvLightRules ToRules(UvLightCheckConfig c);
  public static FrozenReadingRules ToRules(FrozenReadingConfig c);
  public static LedHeatingRules ToRules(LedHeatingConfig c);
}
public sealed class LedCheckOverride { public bool On { get; set; }  // volatile, in memory only
  public static LedHeatingConfig Effective(LedHeatingConfig configured, LedCheckOverride? o); }
```

**Behaviour & rules:**
1. `SupervisionState` holds one instance each of the Domain evaluators under a single lock; every setter that changes
   something re-publishes the snapshot. Setters for 9008/9015/9016/9048 are no-ops when the detail is unchanged; 9017 is
   latched (only `AcknowledgeWatchdogTrip()` clears; returns true if there was one).
2. Constructor with a store: if `store.Read()` returns a record → `_frozen.Restore(FrozenAtC, Detail)` and publish (the
   9006 latch survives a restart; heating stays refused until the reading moves).
3. `Evaluate(inputs)`: readings of all supervised sensors; sensor evaluator (60 s open-alert default in Domain) with
   HeatingWanted; `chamberOpenWhileHeating = HeatingWanted && TEMP_CHAMBER open now && 9010 was not already alerted`;
   frozen evaluator (if rules); no-heat evaluator only if rules and nothing frozen (now or latched), with HeatTargetC;
   store write when frozen just raised, store clear when the latch just cleared; fan evaluator per fan then `Finish`;
   LED heating: when enabled, chamber temp passed only if panels lit; when disabled the LED evaluator is replaced by a
   fresh one (baselines and latched 9040-9043 forgotten) and evaluated with no lit panels; UV light evaluator (warning
   only, 9046/9047) if rules and reader present. Publish and return consequences (NewlyCritical fans, chamberOpen, frozen
   detail, no-heat detail).
4. Publish: AlertDetails = union of every evaluator's alerts + 9008/9015/9016/9017/9048 details, keyed by code string;
   Alerts = codes sorted ascending.
5. `SupervisionService.Tick()` (PeriodicWorker 1 s, thread "supervision"; tests call it directly): return if
   OutputFreeze active; under tick lock: `controller.SyncCoolingEnd()`; `Supervise(now)` (exceptions logged);
   `controller.SuperviseN2Pressure()` (exceptions logged); `DoorWatchdog(now)`.
6. `Supervise`: fans = (fan, GetFanDuty or 0, ReadRpm or null) for all 6; lit panels = LEDs with level > 0 while UV on;
   led rules = `LedCheckOverride.Effective(...)`; inputs: HeatingWanted = heating.Active || heating.Fault != null;
   UvIntensity = uv.On ? Intensity : 0; FanRules = `ToRules(fan_health, hw.DamperOpen == true)`; HeaterDutyPct =
   heat.Active ? heat.Pwm : 0; NoHeat band = `heating.at_temp_band`; HeatTargetC = heat.Target. Consequences:
   - frozen (9006): error log, `heating.Stop(detail)` (element off, fan runs on); if `frozen_reading.reboot_after_sec > 0`
     and a system service exists and no restart pending → schedule restart at now + reboot_after_sec (60 s).
   - no heat (9007): `heating.Stop("[9007] {detail}")` (Stop, not Shutdown — the fan must keep running).
   - pending restart due: if the heater-fan run-on is active → wait (log once); else clear, `controller.StopAll(true)`,
     `system.Reboot()` (failure logged).
   - newly critical fans (9020-9025) → `controller.StopAll(true)`.
   - chamber open while heating and heating Active → `heating.Shutdown(SensorSupervisionEvaluator.HeaterSensorDetail)`
     ("Heater temperature sensor (chamber NTC TEMP_CHAMBER) is not reading - the heater is off") — Err 9010 at once.
7. Door watchdog: outputsOn = `DoorOpen() == true && controller.OutputsLive`. On first detection record doorOpenSince and
   warn; when `now − since >= door_sensor.abort_after_sec` (default 10 s) → reset and `controller.DoorAbort()`. Door closed
   (or outputs off) → reset (info "Door closed in time"). `DoorOpenForSec` exposes the elapsed time.
8. `ToRules(FanHealthConfig, damperOpen)`: copy nominal tables; when damperOpen, replace fans present in
   `nominal_rpm_damper_open`; `new FanHealthRules(warn_below_pct, critical_below_pct, persist_sec, settle_sec, min_eval_duty,
   stopped_persist_sec, nominal as (duty,rpm) lists, critical_below_pct_by_fan)`. Others map field-for-field:
   `NoHeatRules(enabled, window_sec, min_rise_c, min_duty_pct, atTargetBand)`, `UvLightRules(enabled, min_intensity,
   confirm_sec, lit_ratio)`, `FrozenReadingRules(enabled, window_sec, min_delta_c, min_duty_pct, reboot_after_sec)`,
   `LedHeatingRules(min_eval_intensity, check_after_sec, min_rise_c, rest_sec, drop_c, drop_persist_sec, drop_settle_sec, panels)`.
9. `LedCheckOverride.Effective`: override On and configured disabled → `configured with { Enabled = true }`; else configured.
   The configured panels stay (Left/Right with TEMP_LEFT/TEMP_RIGHT); Back/Door (ORIGIN thermistors) are never judged.
10. `StartAsync` starts the worker; `StopAsync`/`Dispose` dispose it.

**Configuration:** `door_sensor.abort_after_sec` (10); `fan_health` {warn_below_pct 10, critical_below_pct 20, persist_sec 60,
settle_sec 5, min_eval_duty 30, stopped_persist_sec 5, led_fan_min_rpm 100, nominal_rpm {FAN_HEATER 30→2363, 50→3669,
80→5227, 100→5925; FAN_COOLING 30→1235, 60→2690, 100→4790; LED fans 100→3560}, nominal_rpm_damper_open, critical_below_pct_by_fan};
`led_heating` {min_eval_intensity 30, check_after_sec 90, min_rise_c 1.0, rest_sec 120, drop_c 1.0, drop_persist_sec 30,
drop_settle_sec 120, panels {LED_LEFT: TEMP_LEFT, LED_RIGHT: TEMP_RIGHT}, enabled false}; `frozen_reading` {enabled true,
window_sec 90, min_delta_c 0.01, min_duty_pct 50, reboot_after_sec 60}; `no_heat` {enabled true, window_sec 600,
min_rise_c 0.5, min_duty_pct 99}; `uv_light_check` {enabled true, min_intensity 10, confirm_sec 5, lit_ratio 0.6};
`heating.at_temp_band` (1.5).

**Acceptance criteria:**
- Door open during CureUv: no abort after 9 ticks; abort after 11 → doorAborted true, heating/UV off, no heater run-on,
  all fans 0, BOFA off, damper closed, StripInputs.DoorAbortLatched; stays latched after the door closes until
  `AckDoorAbort`; a new process (e.g. SetNitrogen(true)) clears the latch. Door closed within 6 s keeps the process.
- A fan going critical mid-process stops every output.
- Frozen chamber reading while heating at ≥ 50 % → heater off, 9006, heating refused until it reads again; restart
  ~60 s later (after the run-on), and the refusal survives the restart via the store; normal heating never trips 9006.
- No heater supply (full output, no rise in 600 s) → 9007 and heater off within 10 min; slow climb near target and UV
  fans pulling below target never raise 9007.
- LED checks on + a cold lit Left/Right panel → its 9040/9041 code; switching off clears; checks off by default.
- Override on, dark panel → own not-heating code after 90 s; ORIGIN thermistors (TEMP_BACK/DOOR) never read; override off
  = no check; override in memory only, configured panels kept.
- Lit panel whose photoresistor stays dark → 9046/9047 warning, process keeps running; disabled check raises nothing.
- Damper open → FAN_COOLING judged against the open table; no open table keeps the normal one.

**Tests:** `Supervision/FanDamperNominalTests`, `Supervision/FrozenReadingTests`, `Supervision/LedCheckOverrideTests`,
`Supervision/NoHeatTests`, `Supervision/SupervisionLedChecksTests`, `Supervision/UvLightCheckTests`; door/fan tests in
`Process/CureControllerTests` (Door_watchdog_aborts_after_ten_seconds_and_latches_until_ack, Door_closed_in_time_keeps_the_process,
A_new_process_clears_the_door_abort_latch, Fan_critical_mid_process_stops_every_output). Use `ProcessRig.TickSeconds(n)`
(advance 1 s + `SupervisionService.Tick()`), `FakeSystemService` for reboot.

**Reference (source):** `src/SCureBox.Application/Supervision/*.cs`, `tests/SCureBox.Application.Tests/Supervision/*.cs`

---

### PROC-09 — Recipe runner and program validator
**Summary**
- **What it is for:** Runs a full curing program (a list of steps like heat, cure, cool, nitrogen) on the machine by itself, step by step.
- **Problem it solves:** If the screen drove each step, a screen problem could break a run. Bad programs must be blocked, and each run needs a record of what happened.
- **How we solve it:** The machine checks the program first, then runs it with a loop every second. It sends each step to the controller, saves temperatures and alerts, and ends the run as completed, aborted or error with a code.


**Project / folder:** `SCureBox.Application.csproj` — `Recipe/`

**Goal:** Server-side execution of a whole program (`Material` with steps) without the UI driving each phase: a 1 s
loop drives the Domain `RecipeStateMachine`, translates its commands into `ICureController` calls, records telemetry
into the cure-run store, posts phase timings, tracks alerts raised during the run, and ends the run as completed,
aborted or error (with code). Exposed at `/api/recipe/*` (area Api).

**Depends on:** PROC-01, PROC-02, PROC-05 (via `ICureController` only), Domain (`RecipeStateMachine`, `RecipeState
{ Idle, Preflight, Running, Paused, Completed, Aborted, Error }`, `RecipeCommand`, `RecipeCommandKind { Heat, Dry,
CureUv, UvOnly, Cool, Nitrogen, Stop, PhaseEnded }`, `Material`, `CureStep`, `ProcessType`, `RunAlert(double T, int? Code,
string Message)`, `CureRunStart`, `CureRunFinish`, `TelemetrySample`, `PhaseTiming`), Hardware (`OutputFreeze`).

**Files to create:**
- `Recipe/RecipeRunner.cs` — `RecipeRunner : IRecipeRunner, IHostedService, IDisposable`
- `Recipe/RecipeValidator.cs` — `RecipeValidator`

**Public contract:**
```csharp
public sealed class RecipeRunner : IRecipeRunner, IHostedService, IDisposable {
  public const double TelemetryPeriodSec = 2.0;
  public RecipeRunner(ICureController controller, TimeProvider timeProvider, ILogger<RecipeRunner> log,
    RecipeValidator? validator = null, ICureRunStore? runs = null, IPhaseTimingStore? timings = null, OutputFreeze? freeze = null);
  public bool FailFromOutside(string message, int code);
  public void Tick();
  internal static int? FaultCode(string fault);                               // "[9007] ..." -> 9007
  internal static Dictionary<string, double?> TelemetryTemps(MachineState state);
}
public sealed record RecipeValidator(Func<Material, (bool ok, string? message, int? code)> Validate) {
  public const double HeatTargetMin = 30; public const double TempMax = 80; public const double DryTempMax = 50;
  public const double CoolTargetMin = 20; public const double UvIntensityMin = 10;
  public static RecipeValidator Default { get; }                              // = new(BasicChecks)
  public static (bool ok, string? message, int? code) BasicChecks(Material material);
}
```

**Behaviour & rules:**
1. `RecipeValidator.BasicChecks`: no steps → (false, "Program has no steps", 7001). Per step: Nitrogen → no check;
   Cooling: t = Temperature ?? 25, outside 20..80 → "Invalid target {t} (20-80°C)" 7001; others: max = Drying ? 50 : 80;
   Temperature outside 30..max → "Invalid target {t} (30-{max}°C)" 7001; Temperature null and not UV → "Step {n}: {Process}
   needs a target temperature" 7001; UV step: `EffectiveUvIntensity` outside 10..100 → "Invalid intensity {i} (10-100%)" 7002;
   Time < 0 → "Step {n}: negative time" 7001. The host may register the full Domain `ProgramValidator` instead.
2. `Start(material, runId?, serial?)` under lock: a machine in Preflight/Running/Paused → Fail("A program is already
   running - abort it first", 6015); `controller.AnyProcessActive` → Fail("A process is active - stop it before starting a
   program", 6015); validator failure → Fail(message ?? "Invalid program", code ?? 7001). runId = given or new GUID;
   new `RecipeStateMachine(material, runId)`; reset finished flag and telemetry time; snapshot state: alert list cleared,
   active alerts = current `state.Alerts` (only alerts raised during the run are recorded), remembered heater fault and N2
   fault = current ones. `runs.Start(runId, CureRunStart{MaterialName, Steps=count, Phases=step process names,
   TargetTemp=first non-null step temperature, SerialNumber})` (exceptions logged). `controller.HoldHeaterFan(true)`;
   `Execute(machine.Start(now, chamberTemp))`; Success("Program '{name}' started").
3. `Pause()`: only when Running else Fail("No program is running", 6015); HoldHeaterFan(false); Execute(machine.Pause) (emits
   Stop → `StopAll(false)`); "Program paused". `Resume()`: only when Paused else Fail("No paused program", 6015);
   HoldHeaterFan(true); Execute(machine.Resume) (re-issues the current phase command); "Program resumed".
4. `Abort()`: Preflight/Running/Paused else Fail("No program is running", 6015); machine.Abort; `StopAll(true)`;
   FinishRun("aborted"); "Program aborted".
5. `SkipStep()`: Running only else Fail("No program is running", 6015); Execute(machine.SkipStep(now, chamberTemp)); "Step skipped".
6. `FailFromOutside(message, code)`: if a program is on → error log, Fail(message, code), true; else false (used by DVT hang).
7. `Tick()` (PeriodicWorker 1 s "recipe-runner"; StartAsync starts it): return if OutputFreeze active or not Running.
   state = GetState(); TrackAlerts; then in order:
   - `state.DoorAborted` → Fail("Door opened - program aborted", 6016).
   - heater fault changed to a new non-null value: code = FaultCode(text) ?? first active alert in {9007, 9006, 9010, 9001};
     if code is NOT (family 9001 i.e. 9001/9010/9011/9012) and NOT 9006 → Fail("Heater stopped: {fault}", code ?? 6015).
     Sensor faults / 9006 are left to the cure screen (it pauses and asks Retry/Stop). Remember the fault.
   - N2 fault changed to new non-null → Fail("Nitrogen stopped: {message without [code]}", FaultCode ?? 9015).
   - telemetry when first or ≥ 2.0 s since last (`TelemetryPeriodSec`; the class comment says 5 s, the constant is 2 s).
   - Execute(machine.Advance(now, chamberTemp)); if still Running → HoldHeaterFan(true) (re-assert every pass).
8. `Execute(commands)`: Heat→HeatToTarget, Dry→DryToTarget, CureUv→CureUv(wl, target, intensity), UvOnly→UvOnly(wl,
   intensity, vent), Cool→CoolToTarget(target, mode), Nitrogen→SetNitrogen(on), Stop→StopAll(false), PhaseEnded→
   `timings.Append` (exceptions logged). First non-ok result → Fail(r.Message, r.Code ?? 6015) and stop. After the list:
   machine Completed → FinishRun("completed"); Aborted → FinishRun("aborted").
9. `TrackAlerts`: t = round(total elapsed s); each code in state.Alerts not in the active set → add `RunAlert(t, code,
   detail or "Err {code}")`; active set = intersection with current alerts (a code that clears and returns is recorded again).
10. `Fail(message, code)`: add `RunAlert(t, code, message)` unless an alert with that code was recorded ≤ 5 s earlier;
    machine.Fail; `StopAll(true)`; FinishRun("error").
11. `RecordTelemetry` (only with a store and run id): `TelemetrySample{ T = round(total elapsed), ChamberTemp, UvOn,
    UvType = "{nm}nm" or null, LedTemps {right,left,door,back}, FanRpm = FanRpmEach copy, TargetTemp, HeaterPwm, HeaterOn =
    HeaterOut, FanDuty = FanDutyEach copy, Temps = TelemetryTemps(state) (chamber rounded 1 + every LedTemps entry),
    UvOutputs = uvOn ? copy : null, UvIntensity = uvOn ? intensity : null, DamperOpen, Nitrogen = NitrogenActive, DoorClosed }`.
12. `FinishRun(status)`: always `HoldHeaterFan(false)` (normal run-on); once per run: `runs.Finish(runId,
    CureRunFinish{Status, StepsCompleted, Alerts}, sensorIssues = sensors not ok → SensorIssue(sensor, critical),
    fanIssues = fanHealth status "warn"/"critical" → FanIssue(name, deficitPct, status=="critical"))`.
13. `GetStatus()`: no machine → `new RecipeStatus()` ("idle"); else State = lower-case enum name, Process/Phase/target
    from `machine.Progress(now)`, elapsed/remaining/estimated rounded to 0.1 s, StartedAt/EndedAt ISO "O", Message, ErrorCode.
14. State machine summary (Domain, for reference): Nitrogen step = 120 s (`NitrogenSec`); cooling done at chamber ≤ target
    + 0.5 C; heat/dry/cure ramp reached at chamber ≥ target − 0.5 C then hold `Time` minutes (OnRamp timer counts through the
    ramp); a cure step with UV start "at target" heats first and emits CureUv when reached; UV-only holds immediately; pause
    shifts all anchors on resume; last step end emits Stop + Completed.

**Configuration:** none directly (validator limits are constants).

**Acceptance criteria:**
- Short program (Heat 40 C 0.5 min, Cure 40 C 0.5 min @30 %, Cool Fast to 30 C) runs to "completed": 3 phase timings
  (third coolingMode "fast"), one Finish with StepsCompleted 3, ≥ 3 telemetry samples, UV telemetry type "405nm",
  UvOutputs only while UV on, RunId propagated, SerialNumber stored.
- Invalid programs and double starts refused; refused while a manual process runs.
- Abort → StopAll, status "aborted". Pause/Resume work.
- Door abort → "error", ErrorCode 6016, store status "error".
- A refusal mid-run (cure pre-flight with TEMP_RIGHT open after an N2 step) → "error" with 9012 and the valve closed.
- Skip step moves on.
- Heater fan at 100 % for the whole program including no-heat steps; no run-on inside the run; run-on after the end.
- A 9007 mid-program ends the run with 9007, "Heater stopped" message, and the alert recorded once at ~600 s.
- A frozen reading (9006) is left to the cure screen and still recorded.
- FaultCode reads "[NNNN]"; outside a program UV-only does not hold the heater fan; a program without heating still runs
  the heater fan and pause releases it. A purge step hitting 9015 fails with 9015.

**Tests:** `Process/RecipeRunnerTests` — Runs_a_short_program_to_completion, Refuses_invalid_programs_and_double_starts,
Refuses_while_a_manual_process_runs, Abort_stops_everything_and_marks_the_run_aborted, Pause_and_resume,
Door_abort_ends_the_run_with_6016, A_refusal_mid_run_ends_the_run_with_the_code, Skip_step_moves_on,
The_heater_fan_runs_at_full_duty_for_the_whole_program_also_with_heating_off,
A_heater_fault_mid_program_ends_the_run_with_its_code_and_records_the_alert,
A_frozen_reading_is_left_to_the_cure_screen_and_still_recorded, FaultCode_reads_the_bracketed_code,
Outside_a_program_a_uv_only_process_does_not_hold_the_heater_fan,
A_program_with_no_heating_at_all_still_runs_the_heater_fan_and_pause_releases_it; plus
`N2FlowCheckTests.A_purge_step_that_hits_9015_fails_the_program_with_the_code`. Use in-memory `ICureRunStore` /
`IPhaseTimingStore` fakes and pump `runner.Tick()` once per simulated second on a pumped thread.

**Reference (source):** `src/SCureBox.Application/Recipe/RecipeRunner.cs`, `Recipe/RecipeValidator.cs`,
`src/SCureBox.Domain/Control/RecipeStateMachine.cs` (Domain), `tests/SCureBox.Application.Tests/Process/RecipeRunnerTests.cs`

---

### PROC-10 — Status strip (RGB ladder, animation, internet watch)
**Summary**
- **What it is for:** Shows the machine status on the colored LED strip: green for ready, busy color while running, blinking for faults, door or warnings.
- **Problem it solves:** Users need to see the machine state from across the room. A strip error must never stop a running process.
- **How we solve it:** Every second we pick one status from a fixed priority list and paint the matching color or blink. A manual color can override it. Strip errors are ignored. Internet state is checked in the background but not shown on the strip.


**Project / folder:** `SCureBox.Application.csproj` — `Status/`

**Goal:** Show the machine status on the addressable RGB strip: classify the machine every `status_sec` with the
Domain `StripModeLadder`, animate the busy comet, blink faults/door/warnings, honour the manual `/api/rgb` override, and
watch internet reachability on a background thread. Strip failures are swallowed — the strip must never take a process down.

**Depends on:** PROC-02, PROC-05 (`CureController.StripInputs`), Application-Platform (`NetworkPolicy.ExpectsNetwork`),
Domain (`StripModeLadder` modes "fault", "door", "warn", "manual_heat", "busy", "normal";
`Mode(StripInputs)`, `Scale(rgb, level)`, `CometFrame(count, offset, tail, colour, rtl, level)`, `BlinkOn(unixSec, blinkSec)`),
Hardware (`RgbFill(int[])`, `RgbOff()`, `Config.Rgb`).

**Files to create:**
- `Status/StripStatus.cs` — `StripStatus`
- `Status/RgbColors.cs` — `RgbColors`
- `Status/InternetWatcher.cs` — `InternetWatcher`
- `Status/InternetStatusProvider.cs` — `InternetStatusProvider`
- `Status/StatusLedService.cs` — `StatusLedService : IHostedService, IDisposable`

**Public contract:**
```csharp
public sealed class StripStatus { string? Mode {get;set;} bool? InternetOk {get;set;} bool OverrideOn {get;}
  string? OverrideColor {get;} void SetOverride(bool on, string? color); }      // all under one lock
public static class RgbColors { public static int Parse(string text); public static int ParseOr(string? text, int fallback); }
public sealed class InternetWatcher : IDisposable {
  public InternetWatcher(StripStatus status, TimeProvider tp, ILogger log, Func<double> periodSec,
    Func<bool>? probe = null, Func<bool>? expectsNetwork = null);
  public void Start(); public static bool TcpProbe(); public void Dispose(); }
public sealed record InternetStatusProvider(Func<bool?> Get);
public sealed class StatusLedService : IHostedService, IDisposable {
  public StatusLedService(IHardwareSystem hw, CureController controller, StripStatus status, TimeProvider tp,
    ILogger<StatusLedService> log, Func<bool>? internetProbe = null, NetworkPolicy? policy = null);
  public bool? InternetOk { get; } public string Evaluate(); }
```

**Behaviour & rules:**
1. Ladder (Domain): DriverFault || UiCritical || DoorAbortLatched → fault; DoorOpen → door; UiWarning → warn; ManualHeat →
   manual_heat; AnyProcess → busy; else normal. OWNER DECISION 2026-11-05 (v1.0.153): NO internet marking on the strip - idle stays green whatever the internet state.
2. `RgbColors.Parse`: trim, lower, strip '#'; named: red FF0000, green 00FF00, blue 0000FF, white FFFFFF, yellow FFB400,
   orange FF5A00, purple AA00FF, cyan 00C8FF, pink FF2878, off 000000; or 6 hex digits; else ArgumentException
   "unknown color: {text} (named colors: …, or hex RRGGBB)". `ParseOr` returns fallback for blank/invalid.
3. `InternetWatcher`: thread "rgb-net-watch"; loop: probe (exception → false); if previous non-null and changed and network
   expected → info log "Internet back online / UNREACHABLE"; `status.InternetOk = ok`; wait
   `max(2.0, periodSec())`. `TcpProbe`: TCP connect to www.google.com:443 then 1.1.1.1:443, 2 s timeout each; true on the first success.
4. `StatusLedService`: period supplier = ExpectsNetwork ? `rgb.status.internet_check_sec` (5) : max(60, that).
   `Evaluate()`: mode = Ladder(controller.StripInputs()); publishes `status.Mode`. The watcher result (`StripStatus.InternetOk`) is NOT used by the strip;
   it only feeds `internetOk` in /api/state, the TopBar network icon and the cloud agent.
5. Run loop (thread "rgb-status") every `max(0.03, chase_sec)` (0.12 s): re-evaluate every `max(0.5, status_sec)` (1 s);
   override on → skip painting (forget last frame); level = clamp(brightness/100, 0, 1); busy with busy_style "solid" (default) → solid busy colour (fallback 0xAA00FF); busy otherwise
   → comet frame, offset advances 1 per frame mod count, direction rtl unless busy_direction "ltr", tail chase_tail (5);
   fault/door/warn blink (blink_sec 0.5) between colour and 0: fault (fallback FF0000), door_open (FF7800), warning (FFB400);
   manual_heat solid (FF8C00); normal solid (00FF00). Paint fills `rgb.count` pixels with
   Scale(colour, level), skipped when the colour equals the last painted one. Exceptions: first one logged, loop continues.
6. `StartAsync` starts the watcher and thread once; `StopAsync`/`Dispose`: cancel, dispose watcher, join 5 s, `RgbOff()` best effort.
7. `CureController.SetRgb` uses `StripStatus.SetOverride` (PROC-05).

**Configuration:** `rgb` {gpio 12, count 21, order "RGB", status {normal "green", fault "red", door_open "ff7800",
busy "blue", warning "yellow", manual_heat "ff8c00", brightness 100, blink_sec 0.5, chase_sec 0.12,
chase_tail 5, busy_style "solid", busy_direction "rtl", status_sec 1.0, internet_check_sec 5.0}} — hot-reloaded (read on
every evaluation).

**Acceptance criteria:**
- `SetRgb(true,"purple")` sets the override and fills the strip; the status loop does not paint while the override is on;
  invalid colour → Fail. UI alerts older than 90 s are ignored by the ladder.
- With the internet unreachable an idle machine shows normal (green) and a running one busy - no internet mode exists (QA test strip_no_net, NetworkPolicyTests.The_strip_has_no_internet_marking_and_stays_green_when_idle).

**Tests:** `CureControllerTests.Rgb_override_and_ui_alerts`, `Manual_heating_flags_the_strip_and_a_program_step_clears_it`;
`Platform/NetworkPolicyTests` (Application-Platform) for the offline behaviour. OPEN QUESTION: no dedicated test of the
StatusLedService animation loop exists in this test project.

**Reference (source):** `src/SCureBox.Application/Status/*.cs`, `src/SCureBox.Domain/Control/StripModeLadder.cs` (Domain)

---

### PROC-11 — Process layer DI registration
**Summary**
- **What it is for:** One setup method that registers all parts of the process layer so the application can start them together.
- **Problem it solves:** Without one central setup, parts could be created twice or missing, and real and simulated test devices could get mixed up.
- **How we solve it:** One method registers every part as a single shared copy, starts the three background services, and picks real or simulated test instruments from settings.


**Project / folder:** `SCureBox.Application.csproj` — `ProcessServiceCollectionExtensions.cs`

**Goal:** One extension method that registers the whole process execution layer (device loops, cure controller,
supervision, status strip, recipe runner) plus the DVT/HDT services that hang off it, as singletons, and the three hosted
services.

**Depends on:** PROC-03..PROC-10; Hardware (`IHardwareSystem`, `IHardwareConfig`, `OutputFreeze`, `WatchdogTripFile`);
Application-Platform (`FrozenReadingStore`, `PlannedRestart`, `BofaPolicy`, `NetworkPolicy`, `ICloudSync`, `DataOptions`);
Dvt-Hdt (`ITemperatureProbe`, `SimulatedTc08Probe`, `PicoLogTc08Probe`, `IHdtCalibration`/`HdtCalibration`,
`IUvMeterSource`, `StarBrightUsbSource`, `SimulatedUvMeterSource`, `DvtBench`, `UvSweep`, `UvOffTiming`, `RemoteConfirm`,
`IWatchdogTripSource`/`WatchdogTripFileSource`, `DvtHang`).

**Files to create:** `ProcessServiceCollectionExtensions.cs` — `public static class ProcessServiceCollectionExtensions`

**Public contract:** `public static IServiceCollection AddSCureBoxProcess(this IServiceCollection services)` (namespace `SCureBox.Application`).

**Behaviour & rules:** registrations, all `TryAddSingleton` unless noted, in this order:
1. `TimeProvider.System`; `FrozenReadingStore`; `PlannedRestart`; `SupervisionState` (factory: `new SupervisionState(sp.GetService<FrozenReadingStore>())`);
   `StripStatus`; `LedCheckOverride`; `BofaPolicy` (factory `new BofaPolicy(sp.GetService<DataOptions>())`).
2. `ICoolingLoop → CoolingLoop`; `IHeatingLoop → HeatingLoop`; `CureController`; `ICureController` → the same CureController
   instance; `SupervisionService`.
3. `NetworkPolicy` (factory `new NetworkPolicy(() => sp.GetService<ICloudSync>()?.Status().Enabled == true, sp.GetService<DataOptions>())`).
4. `StatusLedService` (factory with hw, CureController, StripStatus, TimeProvider, logger, probe null, NetworkPolicy);
   `InternetStatusProvider(() => StripStatus.InternetOk)`.
5. `RecipeValidator.Default`; `RecipeRunner` (factory with ICureController, TimeProvider, logger, optional RecipeValidator,
   optional ICureRunStore, optional IPhaseTimingStore, optional OutputFreeze); `IRecipeRunner` → same instance.
6. `ITemperatureProbe`: env `SCURE_SIM_TC08` set and not ""/"0"/"false" → `SimulatedTc08Probe(tp, () => CureController.CurrentUvPower)`,
   else `PicoLogTc08Probe(tp, logger)`. `IHdtCalibration → HdtCalibration`.
7. `IUvMeterSource`: env `SCURE_SIM_METER` truthy → `SimulatedUvMeterSource(() => (st.UvOn, st.UvIntensity, st.UvWavelength))`
   from `CureController.GetState()`, else `StarBrightUsbSource()`.
8. `DvtBench`, `UvSweep`, `UvOffTiming`, `RemoteConfirm`; `IWatchdogTripSource → new WatchdogTripFileSource(WatchdogTripFile.ConfiguredPath())`;
   `DvtHang(CureController, OutputFreeze ?? new OutputFreeze(), SupervisionState, TimeProvider, logger, RecipeRunner?, IWatchdogTripSource?)`.
9. `AddSingleton<IHostedService>` (not Try) for SupervisionService, StatusLedService, RecipeRunner (same singleton instances).
10. Optional services resolved with `GetService` (null allowed): ICureRunStore, IPhaseTimingStore, RecipeValidator,
    OutputFreeze, DataOptions, ICloudSync.

**Configuration:** env vars `SCURE_SIM_TC08`, `SCURE_SIM_METER` (truthy = anything except empty, "0", "false").

**Acceptance criteria:**
- Resolving `ICureController` and `CureController` returns the same instance; same for `IRecipeRunner`/`RecipeRunner`.
- Three hosted services are registered; calling `AddSCureBoxProcess` after a host already registered e.g. a custom
  `TimeProvider` or `RecipeValidator` keeps the host's one (TryAdd).

**Tests:** none dedicated in this test project (OPEN QUESTION: the composition is presumably exercised by Api/host
integration tests — area Api).

**Reference (source):** `src/SCureBox.Application/ProcessServiceCollectionExtensions.cs`
