## Domain — overview

`SCureBox.Domain` is the pure business-rule layer of the sCureBox firmware (reference version 1.0.152): a .NET 10 class library with **no I/O apart from `ErrorRegistry.Load` reading one file, no framework dependencies and no package references**. It holds the hardware naming model (fans, LED panels, thermistors, UV photoresistors), the central error-code registry (`ErrorCodes` + `config/errors.json`), the curing-program model (materials and steps with their exact wire/CSV spelling), program validation, the CSV import/export format, the program duration estimator, the recipe sequencer state machine, sensor conversion maths (NTC, chamber calibration, N2 pressure), signal helpers (slope, tachometer RPM, glitch hold), the heater PI + delta-sigma controller, HDT calibration maths, every supervision evaluator that raises a 9xxx alert (open thermistor, frozen reading, heater not heating, fan wear/failure, LED panel not heating / temperature drop, UV light not detected, output watchdog) and the RGB status-strip priority ladder. Every evaluator is a deterministic, single-threaded object: the caller passes `now` (a `DateTimeOffset` or monotonic seconds) and readings in, and gets verdicts, alert dictionaries (`code -> detail text`) or commands out. Config values (components.json) are mapped into the domain `*Rules` records by the Hardware / Application layers; the domain itself only reads `config/errors.json`. Unit tests live in `tests/SCureBox.Domain.Tests` (xUnit) and some of them read `config/errors.json`, `config/presets.json` and the whole `src/` tree.

---

### DOM-01 — Project scaffold and hardware naming model
**Project / folder:** `src/SCureBox.Domain/SCureBox.Domain.csproj`, `src/SCureBox.Domain/Models/HardwareNames.cs`; test project `tests/SCureBox.Domain.Tests/SCureBox.Domain.Tests.csproj`
**Goal:** Create the domain class library and its test project, and define the physical names of every fan, LED panel, thermistor and UV photoresistor plus the lookups (groups, owning fan, UI zone, operator wording) that all other layers use. These names are the wire IDs used by the API, the UI and the alert texts, so their spelling is part of the contract.
**Depends on:** none (first ticket of the Domain area). Every other DOM ticket depends on it.
**Files to create:**
- `Directory.Build.props` (repo root, shared by all projects — create if no other area did): `TargetFramework net10.0`, `Nullable enable`, `ImplicitUsings enable`, `LangVersion latest`, `TreatWarningsAsErrors true`, `WarningsNotAsErrors CS1591;xUnit1004`, `InvariantGlobalization true`, `SatelliteResourceLanguages en`, `Version 1.0.0`, `Company sCure`, `Product sCureBox firmware`, `NoWarn $(NoWarn);CA1416`.
- `src/SCureBox.Domain/SCureBox.Domain.csproj` — `Microsoft.NET.Sdk`, `RootNamespace SCureBox.Domain`, `Description "Pure business rules, device behaviour models and validation. No I/O, no framework dependencies."`. No package references.
- `src/SCureBox.Domain/Models/HardwareNames.cs` — enums `Fan`, `LedPanel`, `TempSensor`, `UvSensor`, `FanGroup`; static class `HardwareNames`.
- `tests/SCureBox.Domain.Tests/SCureBox.Domain.Tests.csproj` — `IsPackable false`, `IsTestProject true`, `RootNamespace SCureBox.Domain.Tests`; packages `Microsoft.NET.Test.Sdk 18.11.0`, `xunit 2.9.3`, `xunit.runner.visualstudio 4.0.1`, `coverlet.collector 10.1.0`, `Microsoft.Extensions.TimeProvider.Testing 10.11.0`; ProjectReference to the domain csproj.
- `tests/SCureBox.Domain.Tests/Programs/RepoFiles.cs` — `internal static class RepoFiles`.
**Public contract:**
```csharp
namespace SCureBox.Domain.Models;
public enum Fan { FAN_HEATER, FAN_DOOR, FAN_RIGHT, FAN_LEFT, FAN_BACK, FAN_COOLING }      // PCA9685 channels with a tachometer
public enum LedPanel { LED_BACK, LED_DOOR, LED_RIGHT, LED_LEFT }                         // UV LED panels (PCA9685 DIM channels)
public enum TempSensor { TEMP_RIGHT, TEMP_LEFT, TEMP_BACK, TEMP_DOOR, TEMP_CHAMBER }       // NTCs on the ADS1115s
public enum UvSensor { UV_LEFT, UV_RIGHT }                                                // photoresistors on Left/Right panels
public enum FanGroup { led_cooling, chamber_intake, chamber_heating }                     // lower-case on purpose (UI wire names)

public static class HardwareNames
{
    public static readonly IReadOnlyDictionary<FanGroup, Fan[]> FanGroups;
    public static readonly IReadOnlyDictionary<LedPanel, Fan> LedFan;
    public static string Zone(this LedPanel p);
    public static readonly IReadOnlyDictionary<TempSensor, (string name, bool critical)> SupervisedSensors;
    public static string Location(TempSensor sensor);
    public static LedPanel Panel(this UvSensor sensor);
    public static UvSensor? UvSensorOf(LedPanel panel);
    public static string Location(UvSensor sensor);
    public static string Location(Fan fan);
    public static string Label(Fan fan);
    public static bool TryParseFanGroup(string? s, out FanGroup g);
    public static bool TryParseFan(string? s, out Fan f);
}
// tests
internal static class RepoFiles { public static string Config(string name, [CallerFilePath] string sourceFile = ""); public static string Source([CallerFilePath] string sourceFile = ""); }
```
**Behaviour & rules:**
1. Enum member order is exactly as listed above (the ordinal values are not used on the wire, but keep them identical).
2. `FanGroups`: `led_cooling -> [FAN_LEFT, FAN_RIGHT, FAN_BACK, FAN_DOOR]`, `chamber_intake -> [FAN_COOLING]`, `chamber_heating -> [FAN_HEATER]`.
3. `LedFan`: `LED_LEFT -> FAN_LEFT`, `LED_RIGHT -> FAN_RIGHT`, `LED_BACK -> FAN_BACK`, `LED_DOOR -> FAN_DOOR`.
4. `Zone`: `LED_BACK -> "back"`, `LED_DOOR -> "door"`, `LED_RIGHT -> "right"`, anything else -> `"left"`.
5. `SupervisedSensors` is a `Dictionary` built in this insertion order, and that iteration order is relied upon everywhere (alert text ordering, first-code choice): `TEMP_CHAMBER -> ("chamber", true)`, `TEMP_LEFT -> ("left", true)`, `TEMP_RIGHT -> ("right", true)`, `TEMP_BACK -> ("back", false)`, `TEMP_DOOR -> ("door", false)`. `critical=true` = required sensor.
6. `Location(TempSensor)`: CHAMBER `"Chamber"`, LEFT `"Left LED panel"`, RIGHT `"Right LED panel"`, BACK `"Back LED panel"`, DOOR `"Door LED panel"`, default `sensor.ToString()`.
7. `Panel(UvSensor)`: `UV_LEFT -> LED_LEFT`, otherwise `LED_RIGHT`. `UvSensorOf`: LEFT -> `UV_LEFT`, RIGHT -> `UV_RIGHT`, BACK/DOOR -> `null` (no photoresistor). `Location(UvSensor)`: `"Left UV sensor"` / `"Right UV sensor"`.
8. `Location(Fan)`: HEATER `"Heater fan"`, COOLING `"Chamber cooling fan"`, LEFT `"Left LED fan"`, RIGHT `"Right LED fan"`, BACK `"Back LED fan"`, DOOR `"Door LED fan"`, default `ToString()`.
9. `Label(Fan)` = `$"{Location(fan)} ({fan})"`, e.g. `"Left LED fan (FAN_LEFT)"` — the ID must stay in the text (the Cure screen finds failed fans by it).
10. `TryParseFanGroup` / `TryParseFan` = `Enum.TryParse(s, ignoreCase: false, out ...)` (case-sensitive; note `Enum.TryParse` also accepts numeric strings).
11. Background (documentation only): UV photoresistors sit on a 10 kOhm pull-up to 3.3 V (U6 AIN2 = UV_LEFT, U6 AIN0 = UV_RIGHT), read about 2.8 V dark and fall when lit; they are judged as light, never as temperature.
12. `RepoFiles.Config(name)`: walk up from the directory of the calling source file, then from `AppContext.BaseDirectory`, returning the first `<dir>/config/<name>` that exists; else throw `FileNotFoundException("config/{name} not found above {BaseDirectory}")`. `RepoFiles.Source()`: same walk, returns the first `<dir>/src` directory; else `DirectoryNotFoundException`.
**Configuration:** none.
**Acceptance criteria:**
- Solution builds with warnings as errors.
- `HardwareNames.SupervisedSensors[TempSensor.TEMP_LEFT] == ("left", true)` and `[TEMP_RIGHT] == ("right", true)`; `Location(TempSensor.TEMP_LEFT) == "Left LED panel"`.
- `HardwareNames.UvSensorOf(LedPanel.LED_BACK) == null`; `UvSensor.UV_RIGHT.Panel() == LedPanel.LED_RIGHT`.
- `Label(Fan.FAN_HEATER) == "Heater fan (FAN_HEATER)"`.
**Tests:** Covered inside `UvLightEvaluatorTests.Codes_and_panel_mapping` and `UvLightEvaluatorTests.Left_and_right_panel_thermistors_are_the_supervised_left_right_sensors` (see DOM-10); `FanHealthEvaluatorTests` asserts `Label` text in alert details.
**Reference (source):** `Directory.Build.props`, `src/SCureBox.Domain/SCureBox.Domain.csproj`, `src/SCureBox.Domain/Models/HardwareNames.cs`, `tests/SCureBox.Domain.Tests/SCureBox.Domain.Tests.csproj`, `tests/SCureBox.Domain.Tests/Programs/RepoFiles.cs`

---

### DOM-02 — Error registry, error codes and OpResult
**Project / folder:** `src/SCureBox.Domain/Errors/` (+ `config/errors.json`)
**Goal:** One central registry of every error/warning code the machine emits, with severity, message, troubleshooting and support links. The numeric code travels unchanged from the hardware layer to every UI; its first digit is the SRS section. Provides per-component code mappers (one code per thermistor / fan / LED panel since 2026-10-21) and the family mapping back to the older grouped codes, plus `OpResult`, the command-result shape the API returns.
**Depends on:** DOM-01.
**Files to create:**
- `Errors/ErrorCodes.cs` — `public static class ErrorCodes` and `public sealed record OpResult` (same file).
- `Errors/ErrorDef.cs` — `public sealed record ErrorDef`.
- `Errors/ErrorRange.cs` — `public sealed record ErrorRange`.
- `Errors/ErrorSupport.cs` — `public sealed record ErrorSupport`.
- `Errors/ErrorRegistry.cs` — `public sealed class ErrorRegistry` (+ private `RegistryFile`, `RegistryMeta` records).
- `config/errors.json` — the registry data file (shipped next to the app as `<app>/config/errors.json`).
**Public contract:**
```csharp
namespace SCureBox.Domain.Errors;
public static class ErrorCodes
{
    // 3xxx Setup / 4xxx Storage
    public const int SerialRestoreFailed = 3001;   public const int SdBackupWriteFailed = 4003;
    // 6xxx Home / pre-cure
    public const int HardwareRefused = 6015;       public const int DoorAbort = 6016;
    // 7xxx Cure process
    public const int InvalidTemperature = 7001;    public const int InvalidIntensity = 7002;   public const int InvalidCoolingMode = 7003;
    public const int TemperatureStall = 7004;      public const int CureAborted = 7005;
    // 9xxx Device - grouped (no longer raised, kept for old reports) and single
    public const int TempSensorDisconnected = 9001; public const int FanFailure = 9002; public const int LedFanStopped = 9003;
    public const int LedNotHeating = 9004;  public const int LedTempDrop = 9005;  public const int TempReadingFrozen = 9006;
    public const int HeaterNotHeating = 9007; public const int N2PressureTooHigh = 9008; public const int N2NoSupply = 9009;
    public const int N2FlowBlocked = 9015;  public const int N2SensorNotReading = 9016; public const int WatchdogTripped = 9017;
    public const int LedTempSensorDisconnected = 9050; public const int FanWearWarning = 9051; public const int NfcReaderNotDetected = 9052;
    // per component
    public const int ChamberSensorDisconnected = 9010; public const int LeftLedSensorDisconnected = 9011; public const int RightLedSensorDisconnected = 9012;
    public const int BackLedSensorDisconnected = 9013; public const int DoorLedSensorDisconnected = 9014;
    public const int HeaterFanFailure = 9020; public const int CoolingFanFailure = 9021; public const int LeftLedFanFailure = 9022;
    public const int RightLedFanFailure = 9023; public const int BackLedFanFailure = 9024; public const int DoorLedFanFailure = 9025;
    public const int LeftLedFanStopped = 9030; public const int RightLedFanStopped = 9031; public const int BackLedFanStopped = 9032;
    public const int DoorLedFanStopped = 9033; public const int CoolingFanStopped = 9034;
    public const int LeftLedNotHeating = 9040; public const int RightLedNotHeating = 9041; public const int LeftLedTempDrop = 9042;
    public const int RightLedTempDrop = 9043; public const int BackLedNotHeating = 9044; public const int DoorLedNotHeating = 9045;
    public const int LeftUvLightNotDetected = 9046; public const int RightUvLightNotDetected = 9047; public const int BofaNotDetected = 9048;
    public const int HeaterFanWear = 9060; public const int CoolingFanWear = 9061; public const int LeftLedFanWear = 9062;
    public const int RightLedFanWear = 9063; public const int BackLedFanWear = 9064; public const int DoorLedFanWear = 9065;
    // 908x System / backend
    public const int UnknownDiagnosticTool = 9080; public const int NoUsbDrive = 9081; public const int UsbWriteFailed = 9082;
    public const int LogExportFailed = 9083; public const int NetworkError = 9084; public const int DiagnosticFailed = 9085;
    public const int UpdateFailed = 9086; public const int NoUpdatePackage = 9087; public const int ApiUnreachable = 9089;

    public static int SensorDisconnectedOf(Models.TempSensor sensor);
    public static int FanFailureOf(Models.Fan fan);
    public static int FanWearOf(Models.Fan fan);
    public static int FanStoppedOf(Models.Fan fan);
    public static int LedNotHeatingOf(Models.LedPanel panel);
    public static int UvLightNotDetectedOf(Models.LedPanel panel);
    public static Models.LedPanel? PanelOf(string name);
    public static int LedTempDropOf(Models.LedPanel panel);
    public static int Family(int code);
    public static bool IsA(int code, int family);
    public static IReadOnlyList<int> MembersOf(int family);
}
public sealed record OpResult(bool Ok, string Message, int? Code = null)
{
    public static OpResult Success(string message);
    public static OpResult Fail(string message, int? code = null);
    public static OpResult FromRefusal(string reason);
    public static (int? code, string message) SplitCode(string reason);
}
public sealed record ErrorDef   // init-only props, System.Text.Json names in brackets
{ int Code ["code"]; string Key ["key"] = ""; string Message ["message"] = ""; string Severity ["severity"] = "warning";
  string Category ["category"] = ""; string Layer ["layer"] = ""; string Description ["description"] = "";
  IReadOnlyList<string> Troubleshooting ["troubleshooting"] = empty; string? SupportUrl ["supportUrl"]; string? VideoUrl ["videoUrl"]; }
public sealed record ErrorRange(int From ["from"], int To ["to"], string Section ["section"], string Label ["label"]);
public sealed record ErrorSupport { string? Email ["email"]; string? Phone ["phone"]; string? Chat ["chat"]; string? DocsBase ["docsBase"]; }
public sealed class ErrorRegistry
{
    public string? Version { get; }                      // _meta.version, null for Bundled
    public IReadOnlyList<ErrorRange> Ranges { get; }
    public ErrorSupport Support { get; }                 // never null (new ErrorSupport() when absent)
    public IReadOnlyCollection<ErrorDef> All { get; }
    public int Count { get; }
    public ErrorDef? Get(int code);
    public string Severity(int code);
    public string Message(int code);
    public ErrorRange? RangeOf(int code);
    public static ErrorRegistry Parse(string json);
    public static ErrorRegistry Load(string path);
    public static ErrorRegistry Bundled { get; }          // a single static instance
}
```
**Behaviour & rules:**
1. Mappers (each throws `ArgumentOutOfRangeException` for an unsupported value):
   - `SensorDisconnectedOf`: CHAMBER 9010, LEFT 9011, RIGHT 9012, BACK 9013, DOOR 9014 (message "not a supervised sensor").
   - `FanFailureOf`: HEATER 9020, COOLING 9021, LEFT 9022, RIGHT 9023, BACK 9024, DOOR 9025. `FanWearOf`: HEATER 9060, COOLING 9061, LEFT 9062, RIGHT 9063, BACK 9064, DOOR 9065.
   - `FanStoppedOf`: LEFT 9030, RIGHT 9031, BACK 9032, DOOR 9033, COOLING 9034; FAN_HEATER throws ("no pre-flight spin test for this fan").
   - `LedNotHeatingOf`: LEFT 9040, RIGHT 9041, BACK 9044, DOOR 9045. `LedTempDropOf`: LEFT 9042, RIGHT 9043, BACK/DOOR throw. `UvLightNotDetectedOf`: LEFT 9046, RIGHT 9047, BACK/DOOR throw.
   - `PanelOf(name)`: `name.Trim().ToLowerInvariant().Replace("led_", "")` then `"left"/"right"/"back"/"door"` -> panel, else `null` (so `"LED_RIGHT"`, `"Right"`, `" back "` work; `"chamber"` -> null).
2. `Family(code)`: 9010-9012 -> 9001; 9013-9014 -> 9050; 9020-9025 -> 9002; 9030-9034 -> 9003; 9040-9041 and 9044-9045 -> 9004; 9042-9043 -> 9005; 9060-9065 -> 9051; any other code -> itself (a family is its own family). `IsA(code, family) = Family(code) == family`.
3. `MembersOf(family)` (order matters): 9001 -> [9010, 9011, 9012]; 9050 -> [9013, 9014]; 9002 -> [9020..9025]; 9003 -> [9030, 9031, 9032, 9033, 9034]; 9004 -> [9040, 9041, 9044, 9045]; 9005 -> [9042, 9043]; 9051 -> [9060..9065]; anything else -> empty. Total over the 7 families = 28 distinct codes.
4. The grouped codes 9001-9005, 9050, 9051 are never raised any more; they stay in the registry so old logs show a title.
5. `OpResult.SplitCode(reason)`: `reason ??= ""`; if `reason.Length > 7 && reason[0] == '['`, find the first `']'`; if its index > 1 and the text between is an `int`, return `(code, rest.TrimStart())`; otherwise `(null, reason)`. Example `"[9011] Temperature sensor disconnected: ..." -> (9011, "Temperature sensor disconnected: ...")`.
6. `OpResult.FromRefusal(reason)` = `new OpResult(false, message, code ?? 6015)` (generic pre-cure code when the reason carries none). `Success(m)` = `(true, m, null)`, `Fail(m, c)` = `(false, m, c)`.
7. `ErrorRegistry` keeps a `Dictionary<int, ErrorDef>`; duplicate codes: last one wins. `Severity(code)` = record severity or `"warning"`; `Message(code)` = record message or `$"Error {code}"`; `RangeOf(code)` = first range with `From <= code <= To` or null.
8. `Parse(json)`: `JsonSerializer.Deserialize<RegistryFile>(json)` with default options (property names via `[JsonPropertyName]`: `_meta` {`version`, `ranges`}, `support`, `errors`); a `null` result throws `JsonException("empty error registry")`; malformed JSON throws. Missing `errors` -> empty, missing `ranges` -> empty list, missing `support` -> `new ErrorSupport()`.
9. `Load(path)`: `File.Exists(path) ? Parse(File.ReadAllText(path)) : Bundled`; catches `IOException`, `JsonException`, `UnauthorizedAccessException` and returns `Bundled` (the same instance).
10. `Bundled` (fallback): every record has `Layer = "backend"`, `Description = message`, `SupportUrl = $"https://docs.scure.com/errors/{code}"`, `Troubleshooting` empty, `VideoUrl` null, `Version` null, `Support` = empty `ErrorSupport`, ranges `(6000,6999,"6","Home Screen")`, `(7000,7999,"7","Cure Process Screen")`, `(9000,9999,"9","Error Management")`. Records (code KEY "Message" severity category):
    - 6015 PRECURE_CHECK_FAILED "Pre-Cure Check Failed" critical safety; 6016 DOOR_OPENED_DURING_CURE "Door Opened During Cure" critical safety
    - 7001 INVALID_TARGET_TEMP "Invalid Target Temperature" warning validation; 7002 INVALID_UV_INTENSITY "Invalid UV Intensity" warning validation; 7003 INVALID_COOLING_MODE "Invalid Cooling Mode" warning validation; 7004 TEMPERATURE_STALL "Chamber Temperature Not Rising" critical process; 7005 CURE_ABORTED "Cure Aborted" warning process
    - 9001 TEMP_SENSOR_DISCONNECTED "Temperature Sensor Disconnected" critical safety; 9002 FAN_FAILURE "Fan Failure" critical hardware; 9003 LED_FAN_NOT_SPINNING "LED Cooling Fan Not Spinning" critical hardware; 9004 LED_PANEL_NOT_HEATING "LED Panel Not Heating" warning hardware; 9005 LED_PANEL_TEMP_DROP "LED Panel Temperature Drop" warning hardware
    - 9007 HEATER_NOT_HEATING "Heater Not Heating - Check Voltage Selector / Fuse" critical safety; 9008 N2_PRESSURE_TOO_HIGH "Nitrogen Supply Pressure Too High - Nitrogen Closed" critical safety; 9009 N2_NO_SUPPLY "No Nitrogen Supply - Line Pressure Too Low" warning process; 9017 WATCHDOG_TRIPPED "Firmware Stopped Responding - Watchdog Switched Heater and UV Off" critical safety; 9016 N2_SENSOR_NOT_READING "Nitrogen Pressure Sensor Not Reading" warning hardware; 9015 N2_FLOW_BLOCKED "Nitrogen Not Flowing Into the Chamber - Nitrogen Closed" critical process
    - 9050 LED_TEMP_SENSOR_DISCONNECTED "LED Temperature Sensor Disconnected" warning hardware; 9051 FAN_WEAR_WARNING "Fan Below Nominal Speed" warning hardware; 9052 NFC_READER_NOT_DETECTED "NFC Reader Not Detected" warning hardware
    - 9010 CHAMBER_SENSOR_DISCONNECTED "Chamber Temperature Sensor Disconnected" critical safety; 9011 LEFT_LED_SENSOR_DISCONNECTED "Left LED Temperature Sensor Disconnected" critical safety; 9012 RIGHT_LED_SENSOR_DISCONNECTED "Right LED Temperature Sensor Disconnected" critical safety; 9013 BACK_LED_SENSOR_DISCONNECTED "Back LED Temperature Sensor Disconnected" warning hardware; 9014 DOOR_LED_SENSOR_DISCONNECTED "Door LED Temperature Sensor Disconnected" warning hardware
    - 9020 HEATER_FAN_FAILURE "Heater Fan Below Minimum Speed - System Stopped", 9021 COOLING_FAN_FAILURE "Cooling Fan ...", 9022 LEFT_LED_FAN_FAILURE "Left LED Fan ...", 9023 RIGHT_LED_FAN_FAILURE "Right LED Fan ...", 9024 BACK_LED_FAN_FAILURE "Back LED Fan ...", 9025 DOOR_LED_FAN_FAILURE "Door LED Fan ..." (all "<X> Below Minimum Speed - System Stopped", critical hardware)
    - 9030 LEFT_LED_FAN_NOT_SPINNING "Left LED Fan Not Spinning - Job Not Started", 9031 RIGHT_..., 9032 BACK_..., 9033 DOOR_... (same pattern), 9034 COOLING_FAN_NOT_SPINNING "Chamber Cooling Fan Not Spinning - Step Not Started" (all critical hardware)
    - 9040 LEFT_LED_PANEL_NOT_HEATING "Left LED Panel Not Heating - Check LED Connection", 9041 RIGHT_..., 9044 BACK_..., 9045 DOOR_... (critical hardware); 9042 LEFT_LED_PANEL_TEMP_DROP "Left LED Panel Temperature Dropped During Cure", 9043 RIGHT_LED_PANEL_TEMP_DROP "Right LED Panel Temperature Dropped During Cure" (critical hardware)
    - 9060 HEATER_FAN_WEAR "Heater Fan Speed Low - Replace Fan", 9061 COOLING_FAN_WEAR "Cooling Fan ...", 9062 LEFT_LED_FAN_WEAR "Left LED Fan ...", 9063 RIGHT_LED_FAN_WEAR, 9064 BACK_LED_FAN_WEAR, 9065 DOOR_LED_FAN_WEAR (all "<X> Speed Low - Replace Fan", warning hardware)
    - 9080 UNKNOWN_DIAG_TOOL "Unknown Diagnostic Tool", 9081 NO_USB_DRIVE "No USB Drive Found", 9082 USB_WRITE_FAILED "USB Write Failed", 9083 LOG_EXPORT_FAILED "Log Export Failed", 9084 NETWORK_ERROR "Network Error", 9085 DIAGNOSTIC_FAILED "Diagnostic Failed", 9087 NO_UPDATE_PACKAGE "No Update Package Found" (warning system); 9086 UPDATE_FAILED "Software Update Failed" and 9089 API_UNREACHABLE "Machine API Unreachable" (critical system).
    - Note: Bundled deliberately does NOT contain 3001, 4003, 9006, 9046, 9047, 9048 (it is as in the source; their `Message` falls back to "Error N"). Bundled keys differ from errors.json for 6016, 7004 and 908x — reproduce both exactly as written.
11. `config/errors.json` structure: `{"_meta": {version "4.0.0", lastUpdated "2026-10-25", description, editableFields ["message","description","troubleshooting","supportUrl"], systemFields ["code","key","severity","category","layer"], ranges [...]}, "support": {email "support@scure.com", phone "+1-800-123-4567", chat "https://scure.com/support/chat", docsBase "https://docs.scure.com/errors"}, "errors": [ ... 84 records ... ]}`. Ranges: 3000-3999 "3" "Setup Screen"; 4000-4999 "4" "Setup Name Screen"; 5000-5999 "5" "Connect Organization Screen"; 6000-6999 "6" "Home Screen (material list, recipe builder, CSV import, view-all, start cure)"; 7000-7999 "7" "Cure Process Screen"; 8000-8999 "8" "Cure History Screen"; 9000-9999 "9" "Error Management — device/hardware alerts (9001-9079) + cross-cutting system/backend faults (9080-9099)". Every record has all 10 fields: `code, key, message, severity, category, layer, description, troubleshooting[], supportUrl ("https://docs.scure.com/errors/<code>"), videoUrl ("")`.
12. errors.json records (code KEY severity category layer | message):
```
3001 SERIAL_RESTORE_FAILED critical provisioning daemon | Serial Number Restore Failed
3002 CLOUD_COMM_FAILED critical provisioning backend | Cloud Communication Failed
3003 SETUP_NO_INTERNET warning network backend | No Internet Connection
4001 INVALID_DEVICE_NAME warning validation ui | Invalid Device Name
4002 DATA_FILE_WRITE_FAILED critical storage backend | Data File Write Failed
4003 SD_BACKUP_WRITE_FAILED warning storage backend | SD Backup Write Failed
5001 ORG_ID_NOT_FOUND warning validation ui | No Organization ID in File
6001 PROGRAM_NAME_REQUIRED warning validation ui | Program Name Required
6002 NO_STEPS_DEFINED warning validation ui | No Steps Defined
6003 N2_SEQUENCE_INVALID warning validation ui | Invalid N₂ Purge Sequence
6004 STEP_TEMP_TOO_LOW warning validation ui | Step Temperature Too Low
6005 COOLING_TEMP_INVALID warning validation ui | Invalid Cooling Temperature
6006 CSV_STRUCTURE_INVALID warning validation ui | Invalid CSV Structure
6007 CSV_INVALID_PROCESS warning validation ui | Invalid CSV Process
6008 CSV_INVALID_TEMP warning validation ui | Invalid CSV Temperature
6009 CSV_INVALID_TIME warning validation ui | Invalid CSV Time
6010 CSV_TOO_MANY_N2 warning validation ui | Too Many Nitrogen Steps
6011 CSV_SAVE_FAILED warning io ui | CSV Save Failed
6012 MIXED_MATERIALS_SELECTED warning selection ui | Mixed Materials Selected
6013 NO_MATERIAL_SELECTED warning selection ui | No Material Selected
6014 PROGRAM_NOT_RUNNABLE warning selection ui | Cannot Start Program
6015 PRECURE_CHECK_FAILED critical safety daemon | Pre-Cure Check Failed
6016 DOOR_OPENED_MID_PROCESS critical safety daemon | Door Opened — Process Aborted
7001 INVALID_TARGET_TEMP warning validation backend | Invalid Target Temperature
7002 INVALID_UV_INTENSITY warning validation backend | Invalid UV Intensity
7003 INVALID_COOLING_MODE warning validation backend | Invalid Cooling Mode
7004 CURE_TEMP_STALL warning process ui | Cure Temperature Stall
7005 CURE_ABORTED warning process ui | Cure Aborted
9001 TEMP_SENSOR_DISCONNECTED critical safety daemon | Temperature Sensor Disconnected
9002 FAN_FAILURE critical safety daemon | Fan Below Minimum Speed - System Stopped
9003 LED_FAN_NOT_SPINNING critical safety daemon | Cooling Fan Not Spinning - Job Not Started
9004 LED_NOT_HEATING critical safety daemon | LED Panel Not Heating - Check LED Connection
9005 LED_PANEL_TEMP_DROP critical safety daemon | LED Panel Fault - Temperature Dropped During Cure
9006 TEMP_READING_FROZEN critical safety daemon | Temperature Reading Frozen - Heater Switched Off
9007 HEATER_NOT_HEATING critical safety daemon | Heater Not Heating - Check Voltage Selector / Fuse
9008 N2_PRESSURE_TOO_HIGH critical safety daemon | Nitrogen Supply Pressure Too High - Nitrogen Closed
9009 N2_NO_SUPPLY warning process backend | No Nitrogen Supply - Line Pressure Too Low
9010 CHAMBER_SENSOR_DISCONNECTED critical safety daemon | Chamber Temperature Sensor Disconnected
9011 LEFT_LED_SENSOR_DISCONNECTED critical safety daemon | Left LED Temperature Sensor Disconnected
9012 RIGHT_LED_SENSOR_DISCONNECTED critical safety daemon | Right LED Temperature Sensor Disconnected
9013 BACK_LED_SENSOR_DISCONNECTED warning maintenance daemon | Back LED Temperature Sensor Disconnected
9014 DOOR_LED_SENSOR_DISCONNECTED warning maintenance daemon | Door LED Temperature Sensor Disconnected
9015 N2_FLOW_BLOCKED critical process daemon | Nitrogen Not Flowing Into the Chamber - Nitrogen Closed
9016 N2_SENSOR_NOT_READING warning hardware daemon | Nitrogen Pressure Sensor Not Reading
9017 WATCHDOG_TRIPPED critical safety daemon | Firmware Stopped Responding - Watchdog Switched Heater and UV Off
9020..9025 HEATER/COOLING/LEFT_LED/RIGHT_LED/BACK_LED/DOOR_LED _FAN_FAILURE critical safety daemon | <Heater|Cooling|Left LED|Right LED|Back LED|Door LED> Fan Below Minimum Speed - System Stopped
9030..9033 LEFT/RIGHT/BACK/DOOR _LED_FAN_NOT_SPINNING critical safety daemon | <Left|Right|Back|Door> LED Fan Not Spinning - Job Not Started
9034 COOLING_FAN_NOT_SPINNING critical safety daemon | Chamber Cooling Fan Not Spinning - Step Not Started
9040 LEFT_LED_PANEL_NOT_HEATING / 9041 RIGHT_ / 9044 BACK_ / 9045 DOOR_ critical safety daemon | <Side> LED Panel Not Heating - Check LED Connection
9042 LEFT_LED_PANEL_TEMP_DROP / 9043 RIGHT_LED_PANEL_TEMP_DROP critical safety daemon | <Side> LED Panel Temperature Dropped During Cure
9046 LEFT_UV_LIGHT_NOT_DETECTED warning safety daemon | Left UV Light Not Detected
9047 RIGHT_UV_LIGHT_NOT_DETECTED warning safety daemon | Right UV Light Not Detected
9048 BOFA_NOT_DETECTED warning hardware daemon | BOFA Unit Not Detected
9050 LED_TEMP_SENSOR_DISCONNECTED warning maintenance daemon | LED Temperature Sensor Disconnected
9051 FAN_WEAR_WARNING warning maintenance daemon | Fan Speed Low - Replace Fan
9052 NFC_READER_NOT_DETECTED warning io backend | NFC Reader Not Detected
9060..9065 HEATER/COOLING/LEFT_LED/RIGHT_LED/BACK_LED/DOOR_LED _FAN_WEAR warning maintenance daemon | <X> Fan Speed Low - Replace Fan
9080 UNKNOWN_DIAGNOSTIC_TOOL warning validation backend | Unknown Network Tool
9081 USB_NOT_FOUND warning storage backend | No Disk-on-Key Connected
9082 USB_WRITE_FAILED warning storage backend | Disk-on-Key Write Failed
9083 LOG_EXPORT_FAILED warning storage backend | Log Export Failed
9084 NETWORK_STATUS_UNAVAILABLE warning network backend | Network Status Unavailable
9085 NETWORK_DIAGNOSTIC_FAILED warning network backend | Network Diagnostic Failed
9086 UPDATE_FAILED critical update backend | Software Update Failed
9087 UPDATE_PACKAGE_NOT_FOUND warning update backend | Update Package Not Found
9088 UPDATE_INTEGRITY_FAILED critical security ui | Update Integrity Check Failed
9089 HW_API_UNREACHABLE critical system ui | Hardware Service Unreachable
```
13. errors.json content rules that tests enforce: the `description` of each grouped code (9001, 9002, 9003, 9004, 9005, 9050, 9051) starts with `"Grouped code"` (e.g. 9001: "Grouped code - no longer raised since firmware 1.0.106: replaced by 9010 (chamber), 9011 (left), 9012 (right), one code per component. Kept so older reports and logs still show a title. ..."); every per-component member has the same severity as its family, a non-empty `troubleshooting` list and a `videoUrl` field present (empty string until service fills it). 9052 has non-empty troubleshooting. Descriptions/troubleshooting are operator prose (the source file is ~80 KB); OPEN QUESTION: the full prose is not reproduced here — if the original `config/errors.json` is available copy it verbatim, otherwise write a description and 2-4 troubleshooting lines per record that state the trigger, thresholds and effect documented in the relevant DOM ticket (e.g. 9010: open for >= 60 s, immediate while heating, no process can start, clears when the sensor reads; 9017: heartbeat silent 20 s, re-cut every 5 s, latched until acknowledged).
14. Known gaps (codes in errors.json that `ErrorCodes` does not declare, with the reason; used by the coverage test): 3002, 3003 (no cloud serial allocation), 4001, 4002, 5001, 6001-6014 (browser-kiosk editor/CSV/selection validation, other stack), 9088 (updater verifies but reports without the code). Every other errors.json code must be declared in `ErrorCodes`, and every `ErrorCodes` constant must exist in errors.json.
**Configuration:** reads `config/errors.json` (path given by the caller; the app uses `<app>/config/errors.json`).
**Acceptance criteria:**
- `ErrorRegistry.Load(errors.json)`: `Count >= 40`, `Version != null`, `Ranges` non-empty, `Support.Email == "support@scure.com"`, `Get(6015).Key == "PRECURE_CHECK_FAILED"`, `Severity(6015) == "critical"`, `Get(7001).Key == "INVALID_TARGET_TEMP"`, `Severity(7001) == "warning"`, `Severity(9001) == "critical"`, `RangeOf(7003).Section == "7"`.
- Unknown code 1234: `Get == null`, `Severity == "warning"`, `Message == "Error 1234"`.
- Missing file and corrupt file (`"{ not json"`) both return the same `ErrorRegistry.Bundled` instance; Bundled knows 6015, 7001, 7002, 7003, 9001, 9052, 9081, 9086, 9089 and `Severity(9001) == "critical"`.
- `Parse("{\"errors\":[{\"code\":9011,\"message\":\"Left\",\"severity\":\"critical\",\"videoUrl\":\"https://youtu.be/x\"}]}").Get(9011).VideoUrl == "https://youtu.be/x"`.
- 28 distinct member codes; for each: present in errors.json and Bundled, `Family(code) == family`, `IsA` true. `FanStoppedOf(FAN_HEATER)` throws `ArgumentOutOfRangeException`; `PanelOf("chamber") == null`.
- `OpResult.FromRefusal("[9011] text")` -> `(false, "text", 9011)`; `FromRefusal("plain")` -> code 6015.
**Tests:** `ErrorRegistryTests` (Loads_the_central_registry, Every_per_component_code_is_in_the_registry_and_the_bundled_fallback_with_a_video_field, Video_url_is_read_from_the_registry, Unknown_codes_have_a_default_severity_and_message, Missing_file_falls_back_to_the_bundled_registry, Corrupt_file_falls_back_to_the_bundled_registry). `ErrorCoverageTests` with a private `NotImplemented` dictionary (rule 14) and `Declared()` = every public `const int` of `ErrorCodes` via reflection: (a) every declared code exists in errors.json, (b) every errors.json code is declared or in `NotImplemented`, (c) `NotImplemented` has no stale entry (neither declared nor missing from errors.json), (d) every declared constant name is used somewhere in `src/**/*.cs` (excluding bin/obj; whole-word match, excluding its own declaration within 40 chars in ErrorCodes.cs) — test (d) only passes once the other areas (Hardware/Application/Api) use the codes, e.g. 3001/4003 by the serial backup, 9048 by BOFA, 9052 by NFC. Add an `OpResult.SplitCode` test (not in source; recommended).
**Reference (source):** `src/SCureBox.Domain/Errors/ErrorCodes.cs`, `ErrorDef.cs`, `ErrorRange.cs`, `ErrorRegistry.cs`, `ErrorSupport.cs`, `config/errors.json`, `tests/SCureBox.Domain.Tests/Programs/ErrorRegistryTests.cs`, `tests/SCureBox.Domain.Tests/Programs/ErrorCoverageTests.cs`

---

### DOM-03 — Curing program, run-history and job models (wire contracts)
**Project / folder:** `src/SCureBox.Domain/Models/CureProgram.cs`, `src/SCureBox.Domain/Models/History.cs` (+ `config/presets.json`)
**Goal:** The serialisable records that describe a curing program (material + steps), a cure run with its telemetry, alerts and issues, print jobs (with NFC tag) and measured phase timings. JSON property names and enum spellings are the API/UI/CSV contract and must match exactly. Also the bundled read-only preset programs.
**Depends on:** DOM-01.
**Files to create:**
- `Models/CureProgram.cs` — enums `ProcessType`, `CoolingMode`, `TimerMode`, `UvStartMode`, `Wavelength`; static `WavelengthExtensions`, `CoolingModes`; records `CureStep`, `Material`; converters `CoolingModeJsonConverter`, `TimerModeJsonConverter`, `UvStartModeJsonConverter`.
- `Models/History.cs` — records `TelemetrySample`, `SensorIssue`, `FanIssue`, `RunAlert`, `CureLog`, `CureRunStart`, `CureRunFinish`, `CureReport`, `PrintLog`, `PhaseTiming`; static class `NfcUid`.
- `config/presets.json`.
**Public contract:**
```csharp
namespace SCureBox.Domain.Models;
[JsonConverter(typeof(JsonStringEnumConverter<ProcessType>))] public enum ProcessType { Heating, Drying, Cure, Cooling, Bleacher, Nitrogen }
[JsonConverter(typeof(CoolingModeJsonConverter))] public enum CoolingMode { Fast, Medium, Slow }
[JsonConverter(typeof(TimerModeJsonConverter))]   public enum TimerMode { OnRamp, OnTarget }
[JsonConverter(typeof(UvStartModeJsonConverter))] public enum UvStartMode { AtStart, AtTarget }
public enum Wavelength { Nm405 = 405, Nm450 = 450 }        // no converter: serialises as the number
public static class WavelengthExtensions { int Nm(this Wavelength w); string ModeName(this Wavelength w); bool TryParse(int nm, out Wavelength w); }
public static class CoolingModes { string Wire(this CoolingMode m); CoolingMode? Parse(string? s); }
public sealed class CoolingModeJsonConverter : JsonConverter<CoolingMode>; // also TimerModeJsonConverter, UvStartModeJsonConverter

public sealed record CureStep {          // init-only; JSON names
  int Step ["step"]; ProcessType Process ["process"]; double? Temperature ["temperature"]; double? Intensity ["intensity"];
  double Time ["time"]; double? UvIntensity ["uvIntensity"]; TimerMode? TimerMode ["timerMode"]; UvStartMode? UvStartMode ["uvStartMode"];
  double? UvRampPercent ["uvRampPercent"]; CoolingMode? CoolingMode ["coolingMode"]; bool? Ventilation ["ventilation"];
  [JsonIgnore] bool IsUv; [JsonIgnore] bool IsUvOnly; [JsonIgnore] Wavelength UvWavelength; [JsonIgnore] double EffectiveUvIntensity; }
public sealed record Material { string Id ["id"] = Guid.NewGuid().ToString(); string Name ["name"] = ""; IReadOnlyList<CureStep> Steps ["steps"] = empty;
  int TotalDuration ["totalDuration"]; string CreatedAt ["createdAt"] = DateTimeOffset.UtcNow.ToString("O"); bool IsPreset ["isPreset"]; }

public sealed record TelemetrySample { double T ["t"]; double? ChamberTemp ["chamberTemp"]; bool UvOn ["uvOn"]; string? UvType ["uvType"];
  Dictionary<string,double?>? LedTemps ["ledTemps"]; Dictionary<string,int?>? FanRpm ["fanRpm"];
  // the following are [JsonIgnore(Condition = WhenWritingNull)]:
  double? TargetTemp ["targetTemp"]; double? HeaterPwm ["heaterPwm"]; bool? HeaterOn ["heaterOn"]; Dictionary<string,int>? FanDuty ["fanDuty"];
  Dictionary<string,double?>? Temps ["temps"]; Dictionary<string,double>? UvOutputs ["uvOutputs"]; int? UvIntensity ["uvIntensity"];
  bool? DamperOpen ["damperOpen"]; bool? Nitrogen ["n2"]; bool? DoorClosed ["doorClosed"]; }
public sealed record SensorIssue(string Sensor ["sensor"], bool Critical ["critical"]);
public sealed record FanIssue(string Fan ["fan"], double? DeficitPct ["deficitPct"], bool Critical ["critical"]);
public sealed record RunAlert(double T ["t"], int? Code ["code"], string Message ["message"]);
public sealed record CureLog { string Id ["id"]=""; string MaterialName ["materialName"]=""; int Steps ["steps"]; int StepsCompleted ["stepsCompleted"];
  string StartedAt ["startedAt"]=""; string? EndedAt ["endedAt"]; double? Duration ["duration"]; string Status ["status"]="running";
  IReadOnlyList<string> Phases ["phases"]; double? TargetTemp ["targetTemp"]; string? SerialNumber ["serialNumber"];
  IReadOnlyList<TelemetrySample> Telemetry ["telemetry"]; IReadOnlyList<SensorIssue> SensorIssues ["sensorIssues"];
  IReadOnlyList<FanIssue> FanIssues ["fanIssues"]; IReadOnlyList<RunAlert> Alerts ["alerts"]; }       // lists default empty
public sealed record CureRunStart { string MaterialName ["materialName"]=""; int Steps ["steps"]; IReadOnlyList<string> Phases ["phases"]; double? TargetTemp ["targetTemp"]; string? SerialNumber ["serialNumber"]; }
public sealed record CureRunFinish { string Status ["status"]="completed"; int? StepsCompleted ["stepsCompleted"]; IReadOnlyList<RunAlert>? Alerts ["alerts", WhenWritingNull]; }
public sealed record CureReport { string Content ["content"]=""; JsonElement? Summary ["summary"]; string Format ["format"]="html"; }
public sealed record PrintLog { string Id ["id"]=""; string PrintName ["printName"]=""; string MaterialName ["materialName"]=""; string PrinterName ["printerName"]="";
  string Date ["date"]=""; double Duration ["duration"]; string Status ["status"]="completed"; int Steps ["steps"]; string CsvFile ["csvFile"]="";
  string? NfcTag ["nfcTag", WhenWritingNull]; }
public static class NfcUid { string? Normalize(string? text); string? Display(string? text); bool SameTag(string? a, string? b); }
public sealed record PhaseTiming { string? Program ["program"]; int? Step ["step"]; string? Process ["process"]; double? TargetTemp ["targetTemp"];
  double? PlannedMin ["plannedMin"]; string? StartedAt ["startedAt"]; string? EndedAt ["endedAt"]; double? Seconds ["seconds"];
  double? RampSeconds ["rampSeconds"]; double? TempStart ["tempStart"]; double? TempEnd ["tempEnd"]; string? CoolingMode ["coolingMode"];
  double? Intensity ["intensity"]; string? TimerMode ["timerMode"]; string? RunId ["runId"]; }
```
**Behaviour & rules:**
1. `ProcessType` serialises as its PascalCase name (`"Heating"`, `"Drying"`, `"Cure"`, `"Cooling"`, `"Bleacher"`, `"Nitrogen"`) — the same spelling the UI and CSV use. "Bleacher" is the bleaching (450 nm) process.
2. `CoolingModes.Wire`: Fast `"fast"`, Medium `"medium"`, anything else `"slow"`. `CoolingModes.Parse`: `s?.Trim().ToLowerInvariant()` -> fast/medium/slow, else null. `CoolingModeJsonConverter.Read` throws `JsonException("invalid coolingMode")` for an unknown string; Write writes the wire form.
3. `TimerModeJsonConverter`: Read `"on-ramp"` -> OnRamp, ANY other string -> OnTarget; Write `"on-ramp"` / `"on-target"`. `UvStartModeJsonConverter`: Read `"at-start"` -> AtStart, any other -> AtTarget; Write `"at-start"` / `"at-target"`.
4. `WavelengthExtensions`: `Nm` = `(int)w`; `ModeName` = `"405nm"` for Nm405 else `"450nm"`; `TryParse(nm)`: sets `w = nm == 450 ? Nm450 : Nm405` and returns `nm is 405 or 450`.
5. `CureStep` derived (not serialised): `IsUv = Process is Cure or Bleacher`; `IsUvOnly = IsUv && Temperature is null` (UV without heating); `UvWavelength = Process == Bleacher ? Nm450 : Nm405`; `EffectiveUvIntensity = UvIntensity ?? Intensity ?? 30`. `Time` is the hold time in minutes (0 for Cooling and Nitrogen). `Intensity` is legacy (wire compatibility), `UvIntensity` authoritative.
6. `Material.TotalDuration` = estimated total program minutes; `CreatedAt` default = UTC now ISO-8601 round-trip ("O").
7. `TelemetrySample`: posted every 5 s by the UI or the recipe runner; `HeaterPwm` 0-100 % (null = heating loop inactive); `UvOutputs` = physical % per lit zone (back/door/left/right) after calibration factors; `Temps` = every thermistor.
8. `CureLog.Status` is one of `running | completed | aborted | error`; `Duration` seconds; `Alerts` = alerts raised during the run in order (RunAlert.T = seconds since run start).
9. `PrintLog.Duration` is in SECONDS. `PrintLog.NfcTag` is stored in `NfcUid.Display` form.
10. `NfcUid.Normalize`: null/whitespace -> null; skip `':'`, `'-'`, `' '`, `'\t'`; any other non-hex char -> null; collect upper-case hex; accept only if length is even and 4..32 hex digits (2..16 bytes), else null. `Display`: normalized hex split in byte pairs joined by `':'` (e.g. `"E0:07:C0:E1:93:93:18:6D"`), null if not a UID. `SameTag(a,b)`: `Normalize(a)` non-null and equal to `Normalize(b)`. "e0:07:c0:e1:93:93:18:6d", "E007C0E19393186D", "E0 07 C0 E1 93 93 18 6D" are the same tag.
11. `config/presets.json`: JSON array of 19 `Material` objects, all `"isPreset": true`, `"createdAt": "2026-10-31T00:00:00Z"`, ids start with `"preset-"`; every non-cooling step has `"intensity": null`; Cure/Bleacher steps carry `uvIntensity`, `"timerMode": "on-target"`, `"uvStartMode": "at-target"`; Cooling steps carry `temperature` and `coolingMode` and no `time`. Content (id | name | totalDuration | steps "n Process temp time [uv%] [cooling mode]"):
```
preset-stretch-80-v2 | P3 Stretch 80 V2 | 45 | 1 Drying 35 8; 2 Cure 45 22 uv15; 3 Cooling 30 medium
preset-ind403 | LOCTITE 3D IND403 High Modulus | 55 | 1 Drying 45 8; 2 Cure 65 12 uv50; 3 Cooling 30 fast
preset-ST45 | Ultracur3D ST45 | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-3843 | LOCTITE 3D 3843 High Toughness | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-3172 | LOCTITE 3D 3172 High Impact | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-ind405 | LOCTITE 3D IND405 Clear | 39 | 1 Drying 40 6; 2 Cure 40 15 uv60; 3 Bleacher 40 10 uv50; 4 Cooling 30 fast
preset-ind402 | LOCTITE 3D IND402 High Rebound | 45 | 1 Drying 35 8; 2 Cure 45 22 uv15; 3 Cooling 30 medium
preset-silicone-25a | P3 Silicone 25A | 45 | 1 Drying 35 8; 2 Cure 45 22 uv15; 3 Cooling 30 medium
preset-med-silicone-25a | P3 MED Silicone 25A | 45 | 1 Drying 35 8; 2 Cure 45 22 uv15; 3 Cooling 30 medium
preset-ind3380-esd | LOCTITE 3D IND3380 ESD | 55 | 1 Drying 45 8; 2 Cure 65 12 uv50; 3 Cooling 30 fast
preset-3955-fst | LOCTITE 3D 3955 FST | 55 | 1 Drying 45 8; 2 Cure 65 12 uv50; 3 Cooling 30 fast
preset-stretch-ind475 | P3 Stretch IND475 | 45 | 1 Drying 35 8; 2 Cure 45 22 uv15; 3 Cooling 30 medium
preset-dura56 | Stratasys Dura56 | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-med-412 | LOCTITE 3D MED 412 | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-med-413 | LOCTITE 3D MED 413 | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-weatherx-100 | Somos WeatherX 100 | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-rg-3280 | Ultracur3D RG 3280 | 55 | 1 Drying 45 8; 2 Cure 65 12 uv50; 3 Cooling 30 fast
preset-ind3785 | LOCTITE 3D IND3785 Low Migration | 46 | 1 Drying 45 8; 2 Cure 55 15 uv30; 3 Cooling 30 fast
preset-deflect-110 | P3 Deflect 110 | 55 | 1 Drying 45 8; 2 Cure 65 12 uv50; 3 Cooling 30 fast
```
   Presets are read-only programs (the Application persistence layer forces `IsPreset = true` on load); the validator is not applied to them.
**Configuration:** `config/presets.json` (read by the Application persistence layer, not by the domain).
**Acceptance criteria:**
- `JsonSerializer.Deserialize<List<Material>>(presets.json)` yields 19 non-empty materials, all `IsPreset`, ids starting `"preset-"`, `TotalDuration > 0`.
- A `CureStep { Process = Cooling, CoolingMode = Fast }` serialises `"process":"Cooling"`, `"coolingMode":"fast"`; `TimerMode.OnRamp` -> `"on-ramp"`, `UvStartMode.AtStart` -> `"at-start"`; `{"coolingMode":"bogus"}` throws `JsonException`.
- `new CureStep { Process = Bleacher }.UvWavelength == Nm450`; `EffectiveUvIntensity` falls back `UvIntensity -> Intensity -> 30`.
- `NfcUid.SameTag("e0:07:c0:e1:93:93:18:6d", "E0 07 C0 E1 93 93 18 6D")` true; `Normalize("ABC")` null (odd); `Normalize("12")` null (too short); `Display("e007c0e1") == "E0:07:C0:E1"`.
- A `TelemetrySample` with null `HeaterPwm` omits `heaterPwm` from JSON.
**Tests:** `ProgramValidatorTests.Bundled_presets_load_as_read_only_programs` and `ProgramEstimatorTests.Preset_programs_have_a_positive_estimate` read presets.json. No dedicated tests exist for converters/NfcUid in the domain test project (recommended: add `CureProgramJsonTests` and `NfcUidTests`).
**Reference (source):** `src/SCureBox.Domain/Models/CureProgram.cs`, `src/SCureBox.Domain/Models/History.cs`, `config/presets.json`

---

### DOM-04 — Program validation and the program CSV format
**Project / folder:** `src/SCureBox.Domain/Programs/` (`ProgramValidator.cs`, `ValidationError.cs`, `ValidationResult.cs`, `ProgramCsv.cs`, `CsvParseResult.cs`)
**Goal:** Pure validation of an operator-authored curing program (temperature/time/intensity ranges, cooling-drop rule, non-decreasing temperature chain, nitrogen block rules), collecting every failure with an error code; plus the 10-column CSV export/import (with legacy 5-column import) used by the editor and USB import.
**Depends on:** DOM-02 (codes), DOM-03 (CureStep / enums).
**Files to create:** `Programs/ProgramValidator.cs` (`public static class ProgramValidator`), `Programs/ValidationError.cs`, `Programs/ValidationResult.cs`, `Programs/ProgramCsv.cs` (`public static class ProgramCsv`), `Programs/CsvParseResult.cs`.
**Public contract:**
```csharp
namespace SCureBox.Domain.Programs;
public static class ProgramValidator
{
    public const double HeatMinC = 30;  public const double HeatMaxC = 80;  public const double DryMaxC = 50;
    public const double CoolMinC = 30;  public const double CoolMaxC = 75;  public const double CoolingDropMinC = 5;
    public const double UvMinPct = 10;  public const double UvMaxPct = 100;
    public const double HoldMinMin = 1; public const double HoldMaxMin = 120; public const double BleacherHoldMaxMin = 720;
    public const int MaxNitrogenSteps = 2;
    public static double HeatMaxFor(ProcessType process);           // Drying 50, else 80
    public static ValidationResult Validate(IReadOnlyList<CureStep> steps);
}
public sealed record ValidationError(int? Step ["step"], string Field ["field"], string Message ["message"], int Code ["code"]);
public sealed record ValidationResult
{ [JsonPropertyName("ok")] bool Ok => Errors.Count == 0; [JsonPropertyName("errors")] List<ValidationError> Errors { get; init; } = new();
  [JsonIgnore] int? FirstCode; [JsonIgnore] string Summary; }                 // Summary = messages joined with "; "
public static class ProgramCsv
{
    public const string Header = "Step,Process,Temperature,Time,TimerMode,UVIntensity,UVStart,UVRampPercent,CoolingMode,Ventilation";
    public static string ToCsv(IReadOnlyList<CureStep> steps);
    public static CsvParseResult Parse(string text);
}
public sealed record CsvParseResult(IReadOnlyList<CureStep> Steps, IReadOnlyList<string> Errors) { public bool Ok => Steps.Count > 0 && Errors.Count == 0; }
```
**Behaviour & rules (validator):**
1. Empty list -> one error `(null, "steps", "Add at least one step", 6015)` and return.
2. For each step at index i: `n = s.Step > 0 ? s.Step : i + 1`. Order of checks per step (determines `FirstCode`): (a) field checks, (b) nitrogen rules, (c) temperature chain. All failures are collected.
3. Field checks (`fmt` = `v.ToString("0.##", Invariant)`):
   - Nitrogen: none.
   - Cooling: temperature null -> `(n,"temperature","Step {n}: Cooling needs a target temperature (30-75°C)",7001)`; else outside [30,75] or NaN -> `"Step {n}: Invalid temperature {fmt} (must be 30-75 for Cooling)"`, 7001. No time check.
   - Heating/Drying/Cure/Bleacher: temperature present and (`< 30` or `> HeatMaxFor(process)` or NaN) -> `"Step {n}: Invalid temperature {fmt} (must be 30-{max} for {Process})"`, 7001; temperature null and not UV -> `"Step {n}: {Process} needs a target temperature (30-{max}°C)"`, 7001 (Cure/Bleacher with null temperature = UV-only, valid). Time: `maxTime = Bleacher ? 720 : 120`; NaN or `< 1` or `> maxTime` -> `(n,"time","Step {n}: Invalid time {fmt} (must be 1-{maxTime})",6015)`. UV (Cure/Bleacher): `uv = EffectiveUvIntensity`; NaN or outside [10,100] -> `(n,"uvIntensity","Step {n}: Invalid UV intensity {fmt} (must be 10-100)",7002)`.
4. Nitrogen rules: when `s` is Nitrogen: count++; count > 2 -> `(n,"process","Step {n}: A maximum of 2 nitrogen purge steps is allowed",6015)`; if no next step -> `"Step {n}: After an N2 purge, add a Cure or Bleaching step"` 6015; else if next is UV and there is no step after it -> `"Step {n}: Add a Cooling step after the Cure/Bleaching step that follows the N2 purge"` 7003. Independently: previous step Nitrogen and `s` not UV -> `"Step {n}: After nitrogen, only Cure or Bleaching is allowed"` 6015; step i-2 Nitrogen and step i-1 UV and `s` not Cooling -> `"Step {n}: Only Cooling is allowed after the Cure/Bleaching step that follows the N2 purge"` 7003. (All with field "process".)
5. Temperature chain (`lastTemp` = last heated target since the last Cooling, initially null): Cooling: if `lastTemp` and target both set and `target > lastTemp - 5` -> `(n,"temperature","Step {n}: Cooling target ({fmt(target)}°C) must be at least 5°C below the previous step ({fmt(lastTemp)}°C)",7001)`; then `lastTemp = null` (a first-step Cooling has nothing to check). Nitrogen: no change. Others: if temperature `t` set: `t < lastTemp` -> `"Step {n}: Temperature ({fmt(t)}°C) cannot be lower than the previous step ({fmt(lt)}°C) without a Cooling step"` 7001; then `lastTemp = t`. UV-only steps (null temperature) keep the chain unchanged.
6. `FirstCode` = code of `Errors[0]` (null when valid); `Summary` = `string.Join("; ", messages)`.
**Behaviour & rules (CSV):**
7. `ToCsv`: lines = Header + one line per step, joined with `"\n"`, no trailing newline. Columns: `Step` (invariant int); `Process` (enum name); `Temperature` = `""` for Nitrogen, `"off"` when `IsUvOnly`, else `Num(Temperature)`; `Time` = `""` for Cooling/Nitrogen else `Num(Time)`; `TimerMode` (UV only) `"on-ramp"` if OnRamp else `"on-target"`; `UVIntensity` (UV only) `Num(UvIntensity ?? 30)`; `UVStart` (UV only) `"at-start"` if AtStart else `"at-target"`; `UVRampPercent` always `""`; `CoolingMode` (Cooling only) `(CoolingMode ?? Medium).Wire()`; `Ventilation` (UV-only rows only) `"on"` if `Ventilation == true` else `"off"`; non-applicable columns `""`. `Num(v)` = null -> `""`, else `v.ToString("0.##", Invariant)`.
8. `Parse(text)`: strip a leading BOM (U+FEFF); normalise `\r\n` and `\r` to `\n`; `Trim()`; split on `\n`. Fewer than 2 lines -> errors `["CSV must have a header row and at least one data row"]`. Header (line 0, lower-cased) must contain `"process"` or `"step"`, else `["Missing required header: \"Step\" or \"Process\""]`. Legacy layout when header has >= 5 columns, column 3 contains `"intensity"` and column 4 contains `"time"` (`Step,Process,Temperature,Intensity,Time`).
9. Each data line i (1-based line index, blank/whitespace lines skipped but still counted): split on `','` (no quoting), trim cells. Fewer than 4 cells -> `"Row {i}: Not enough columns (need at least 4)"`, skip. Rejected rows are reported and skipped; parsed rows are returned.
10. Row parse order: (a) process: `Enum.TryParse<ProcessType>(cells[1], ignoreCase:false)` and `Enum.IsDefined`, else `"Row {i}: Invalid process \"{cell}\" (must be Heating, Drying, Cure, Cooling, Bleacher, or Nitrogen)"` (note: numeric strings "0".."5" are accepted by TryParse — as in the source). (b) time (not for Cooling/Nitrogen): column = legacy ? cell 4 : cell 3; invariant float in [1, Bleacher ? 720 : 120] else `"Row {i}: Invalid time \"{cell}\" (must be 1-{max})"`; then `Math.Floor`. (c) step number = cell 0 parsed as int > 0, else i. (d) Nitrogen -> `CureStep{Step, Nitrogen, Temperature null, Intensity null, Time 0}`. (e) `noHeat = isUv && cell2 equals "off" (case-insensitive)`; if not noHeat and cell2 non-empty: range Cooling [30,75], else [30, HeatMaxFor] -> `"Row {i}: Invalid temperature \"{cell}\" (must be {min}-{max} for {Process})"`. Missing temperature defaults: Cooling 25, others 40 (UV-only stays null). NOTE: the 25 °C cooling default is outside the validator's 30-75 range (source behaviour). (f) Cooling -> `{Temperature, Time 0, CoolingMode = CoolingModes.Parse(cell 8) ?? Medium}`. (g) Heating/Drying -> `{Temperature, Time}`. (h) Cure/Bleacher: intensity column = legacy ? cell 3 : cell 5; non-empty must be invariant float in [10,100] else `"Row {i}: Invalid UV intensity \"{cell}\" (must be 10-100)"`; `TimerMode` = (not legacy) cell 4 exactly `"on-ramp"`/`"on-target"` else null; `UvStartMode` = cell 6 exactly `"at-start"`/`"at-target"` else null; `UvRampPercent` = cell 7 if parses and 10..100 else null (not legacy); `Ventilation` = noHeat ? (cell 9 equals "on", case-insensitive) : null; `Intensity` null. Missing cells read as `""`.
11. After all rows: no steps and no errors -> `["No valid steps found"]`. Parsing is structural only; callers run `ProgramValidator` for sequence rules.
**Configuration:** none.
**Acceptance criteria:**
- `Validate([])` -> not Ok, `FirstCode == 6015`.
- Drying 50 valid, Drying 55 -> one 7001 error whose message contains "30-50"; Heating 55 valid; Heating 29.9 / Bleacher 81 / Drying 50.5 fail (7001); Cure 30 valid.
- Cooling after Heat 80: 29 and 76 fail, 30 and 75 pass. Heat 60 -> Cool 55 OK; Cool 56 -> single 7001 at step 2 containing "at least 5".
- Time: Heating 0 and 121, Cure 121, Bleacher 721 fail with 6015; Heating 1/120 and Bleacher 720 pass.
- UV 9 and 101 fail (7002), 10/100 pass; Cure without UvIntensity passes (30), with legacy `Intensity = 5` fails 7002.
- Heat 60 -> Dry 50 fails ("without a Cooling step"); Heat 60 -> Cool 40 -> Dry 50 OK; Heat 50 -> Cure(null) -> Dry 50 OK.
- N2 rules as in rule 4 (three purges -> error at step 9 "maximum of 2", 6015; N2 -> Heat -> error at the Heat "only Cure or Bleaching"; N2 -> Cure -> Cure -> error 7003 "Only Cooling"; N2 last -> "add a Cure or Bleaching step"; N2 -> Cure last -> 7003 "Cooling step").
- `Validate([Heat(1,20,time 0), Cure(2,50,uv 5)])`: >= 3 errors, Summary contains "; ", FirstCode 7001.
- `ToCsv` for the 7-step reference program yields exactly: `"1,Drying,45,10,,,,,,"`, `"2,Cure,60,15,on-ramp,40,at-start,,,"`, `"3,Bleacher,off,20,on-target,25,at-target,,,on"`, `"4,Cooling,30,,,,,,fast,"`, `"5,Nitrogen,,,,,,,,"`, `"7,Cooling,35,,,,,,slow,"`; round trip preserves every field and the result validates.
- Legacy `"Step,Process,Temperature,Intensity,Time\n1,Heating,50,,10\n2,Cure,60,45,15\n3,Cooling,30,,\n"` -> 3 steps, step 2 UvIntensity 45 Time 15, step 3 CoolingMode Medium.
- BOM + CRLF + blank line + `"1,Cure,off,10,on-target,30,at-target,,,on"` -> UV-only step with Ventilation true.
- Header `"a,b,c,d"` -> no steps, an error mentioning "header"; `"Step,Process"` alone -> error containing "header row".
- The 8 bad-row example (invalid process, temp 20, UV 5, time 0, bleacher 721, cooling 80, 2 columns) -> 1 step, 7 errors starting `"Row 2:"`..`"Row 8:"` mentioning "Invalid process", "30-80", "10-100", "1-120", "1-720", "30-75", "columns".
- `"1,Heating,,10,..."` -> temperature 40; `"2,Cooling,,,..."` -> 25.
**Tests:** `ProgramValidatorTests` (Drying_is_capped_at_50_C, Empty_program_is_rejected, Heat_type_temperature_range_is_30_to_80, Cooling_temperature_range_is_30_to_75, Heating_without_temperature_is_rejected_but_uv_only_is_fine, Hold_time_ranges, Uv_intensity_range_is_10_to_100, Uv_intensity_falls_back_to_legacy_intensity_then_30, Cooling_target_must_be_5_below_previous_step, Cooling_as_first_step_has_no_previous_temperature_to_check, Temperature_must_not_decrease_without_cooling, At_most_two_nitrogen_steps, After_nitrogen_only_cure_or_bleacher, After_the_uv_step_that_follows_nitrogen_only_cooling, Nitrogen_block_must_be_completed, All_errors_are_collected_and_summarised, Bundled_presets_load_as_read_only_programs). `ProgramCsvTests` (ToCsv_writes_the_ten_column_format, Round_trip_preserves_every_field, Legacy_five_column_format_is_accepted, Crlf_bom_blank_lines_and_off_temperature_are_handled, Header_must_mention_step_or_process, Bad_rows_are_reported_and_skipped, Missing_temperature_defaults_like_the_ui).
**Reference (source):** `src/SCureBox.Domain/Programs/ProgramValidator.cs`, `ValidationError.cs`, `ValidationResult.cs`, `ProgramCsv.cs`, `CsvParseResult.cs`, `tests/SCureBox.Domain.Tests/Programs/ProgramValidatorTests.cs`, `ProgramCsvTests.cs`

---

### DOM-05 — Program duration estimator
**Project / folder:** `src/SCureBox.Domain/Programs/ProgramEstimator.cs`, `ProgramEstimate.cs`
**Goal:** Estimate what a program really takes (holds + heating ramps + cooling + nitrogen purges) from measured phase rates, per program and per step, and the minutes a print job shows. Rates are linear on purpose and come from phase timings collected on the test machine (reviewed 2026-09-07).
**Depends on:** DOM-03.
**Files to create:** `Programs/ProgramEstimate.cs` (record), `Programs/ProgramEstimator.cs` (`public static class ProgramEstimator`).
**Public contract:**
```csharp
public sealed record ProgramEstimate { double HoldSeconds ["holdSeconds"]; double RampSeconds ["rampSeconds"]; double CoolSeconds ["coolSeconds"];
                                       double NitrogenSeconds ["nitrogenSeconds"]; double TotalSeconds ["totalSeconds"]; }
public static class ProgramEstimator
{
    public const double AmbientC = 25;
    public const double DefaultNitrogenSeconds = 120;
    public static readonly IReadOnlyList<(double UpTo, double SecPerDeg)> HeatRateBands;   // (45,13), (75,50), (+inf,80)
    public static double CoolRateCPerMin(CoolingMode mode);                               // Fast 2.5, Medium 1.5, else 0.8
    public static double EstimateHeatSeconds(double fromC, double toC);
    public static double EstimateCoolSeconds(double fromC, double toC, CoolingMode mode = CoolingMode.Medium);
    public static double HeatSecPerDeg(double atC);
    public static ProgramEstimate EstimateProgram(IReadOnlyList<CureStep> steps, double startC = AmbientC, double nitrogenSeconds = DefaultNitrogenSeconds);
    public static IReadOnlyList<double> EstimateStepSeconds(IReadOnlyList<CureStep> steps, double startC = AmbientC, double nitrogenSeconds = DefaultNitrogenSeconds);
    public static int EstimateProgramMinutes(IReadOnlyList<CureStep> steps, double startC = AmbientC, double nitrogenSeconds = DefaultNitrogenSeconds);
    public static int PrintMinutes(PrintLog print, IEnumerable<Material> programs);
}
```
**Behaviour & rules:**
1. Heating bands: 13 s/°C up to 45 °C, 50 s/°C from 45 to 75 °C, 80 s/°C above 75 °C. `EstimateHeatSeconds(from, to)`: 0 if `to <= from`; otherwise walk the bands accumulating `(min(to, upTo) - t) * secPerDeg` for each band segment above the current `t`; result `Math.Round(x, MidpointRounding.AwayFromZero)`.
2. `HeatSecPerDeg(at)`: secPerDeg of the first band with `at < upTo` (44.9 -> 13, 45 -> 50, 75 -> 80, 90 -> 80).
3. `EstimateCoolSeconds(from, to, mode)`: 0 if `to >= from`; else `Math.Round((from - to) / rate * 60, AwayFromZero)` with rate fast 2.5, medium 1.5, slow 0.8 °C/min.
4. `EstimateProgram`: `temp = startC`; per step `holdSec = max(0, Time*60)`:
   - Heating/Drying/Cure/Bleacher: if Temperature `target` set: `r = EstimateHeatSeconds(temp, target)`; ramp += (TimerMode == OnRamp ? max(0, r - holdSec) : r); `temp = max(temp, target)`. hold += holdSec (also for UV-only, which keeps the temperature).
   - Cooling: `coolTarget = Temperature ?? 25`; cool += EstimateCoolSeconds(temp, coolTarget, CoolingMode ?? Medium); `temp = min(temp, coolTarget)`.
   - Nitrogen: n2 += nitrogenSeconds.
   - Total = hold + ramp + cool + n2.
5. `EstimateStepSeconds`: same walk, one value per step (heated = ramp contribution + hold; cooling = its cool seconds; nitrogen = nitrogenSeconds); values sum exactly to `EstimateProgram(...).TotalSeconds`.
6. `EstimateProgramMinutes` = `(int)Math.Ceiling(TotalSeconds / 60)`.
7. `PrintMinutes(print, programs)`: the first program with `Name == print.MaterialName` (ordinal) and at least one step -> `EstimateProgramMinutes(program.Steps)` (default start 25 °C, 120 s nitrogen); otherwise `(int)Math.Ceiling(print.Duration / 60.0)` (Duration is seconds). Rationale: a job and its program must never disagree.
**Configuration:** none here (callers may pass a nitrogen duration from system config).
**Acceptance criteria:**
- Heat seconds: (25,60) = 1010, (25,45) = 260, (45,75) = 1500, (25,80) = 2160, (60,60) = 0, (60,40) = 0.
- Cool seconds: (60,25) medium 1400, fast 840, slow 2625; (25,60) fast 0.
- Steps [Drying 45/10, Cure 60/5, Nitrogen, Cooling 30 medium, Cooling 40 fast] from 25 with 120 s N2 -> per step `[860, 1050, 120, 1200, 0]`, sum equals program total.
- Program [Drying 45/10, Heating 60/5, Cure 60/15 uv30, Cooling 25 medium, Drying 40/5] with nitrogen 0: hold 2100, ramp 1205, cool 1400, n2 0, total 4705, minutes 79.
- Cure 60/10 on-target ramp 1010; on-ramp 410; on-ramp with 30 min hold -> ramp 0.
- [Heating 60/5, Cure UV-only 10, Cooling 40 fast, Nitrogen, Cure 60/10] -> n2 120, cool 480, ramp 1825.
- Every preset has a positive estimate.
- Job with existing program (Drying 50/8, Cure 60/12 uv100) and stored Duration 55 -> program minutes (> 1); job whose program is missing, Duration 5400 -> 90.
**Tests:** `ProgramEstimatorTests` (Heat_seconds_use_the_three_bands, Cool_seconds_per_mode, Heat_sec_per_deg_at_temperature, Step_estimates_add_up_to_the_program_and_cooling_starts_from_the_reached_temperature, Program_walk_carries_the_chamber_temperature, On_ramp_timer_mode_only_adds_the_ramp_beyond_the_hold, Uv_only_keeps_the_temperature_and_nitrogen_adds_the_purge, Preset_programs_have_a_positive_estimate); `ProgramEstimatorPrintTests` (A_job_shows_its_programs_time_whatever_was_stored_with_it, A_job_whose_program_is_gone_uses_its_stored_seconds).
**Reference (source):** `src/SCureBox.Domain/Programs/ProgramEstimator.cs`, `ProgramEstimate.cs`, `tests/SCureBox.Domain.Tests/Programs/ProgramEstimatorTests.cs`, `tests/SCureBox.Domain.Tests/ProgramEstimatorPrintTests.cs`

---

### DOM-06 — Recipe sequencer state machine
**Project / folder:** `src/SCureBox.Domain/Control/` (`RecipeStateMachine.cs`, `RecipeCommand.cs`, `RecipeCommandKind.cs`, `RecipePhase.cs`, `RecipeState.cs`, `RecipeProgress.cs`)
**Goal:** A pure program sequencer: given wall time and the chamber temperature it walks a `Material`'s steps and emits machine commands (heat, dry, cure with UV, UV-only, cool, nitrogen, stop, phase-ended timing records). It mirrors the UI's cure page rules (ramp band, hold timer modes, cooling band, fixed nitrogen purge, deferred UV) and supports pause/resume, skip, abort and fail. The recipe runner (Application) executes the commands.
**Depends on:** DOM-03.
**Files to create:** the six files above.
**Public contract:**
```csharp
namespace SCureBox.Domain.Control;
public enum RecipeCommandKind { Heat, Dry, CureUv, UvOnly, Cool, Nitrogen, Stop, PhaseEnded }
public enum RecipePhase { Ramping, Holding, Cooling, Nitrogen }                                   // wire = lower-case name
public enum RecipeState { Idle, Preflight, Running, Paused, Completed, Aborted, Error }           // wire = lower-case name
public sealed record RecipeCommand(RecipeCommandKind Kind, double? Target = null, Wavelength? Wavelength = null, double? Intensity = null,
    bool Vent = false, CoolingMode? Mode = null, bool On = false, PhaseTiming? Timing = null)
{
    public static RecipeCommand Heat(double target); public static RecipeCommand Dry(double target);
    public static RecipeCommand CureUv(Wavelength wl, double target, double intensity);
    public static RecipeCommand UvOnly(Wavelength wl, double intensity, bool vent);
    public static RecipeCommand Cool(double target, CoolingMode mode); public static RecipeCommand Nitrogen(bool on);
    public static RecipeCommand Stop(); public static RecipeCommand PhaseEnded(PhaseTiming timing);
}
public sealed record RecipeProgress(int StepIndex, int TotalSteps, string? Process, string? Phase, double? TargetTemp,
    double StepElapsedSec, double? StepRemainingSec, double TotalElapsedSec, double EstimatedTotalSec);
public sealed class RecipeStateMachine
{
    public const double RampBandC = 0.5; public const double CoolBandC = 0.5; public const double NitrogenSec = 120.0; public const double AmbientC = 25.0;
    public RecipeStateMachine(Material material, string? runId = null);
    public Material Material { get; } public RecipeState State { get; } public int StepIndex { get; } public RecipePhase? Phase { get; }
    public string? Message { get; } public int? ErrorCode { get; } public DateTimeOffset? StartedAt { get; } public DateTimeOffset? EndedAt { get; }
    public double EstimatedTotalSec { get; } public int StepsCompleted { get; }
    public static double RampSecPerDegree(double target);
    public static double CoolRateCPerMin(CoolingMode mode);
    public static double EstimateSeconds(Material material, double fromTemp);
    public IReadOnlyList<RecipeCommand> Start(DateTimeOffset now, double? chamberTemp);
    public IReadOnlyList<RecipeCommand> Advance(DateTimeOffset now, double? chamberTemp);
    public IReadOnlyList<RecipeCommand> Pause(DateTimeOffset now);
    public IReadOnlyList<RecipeCommand> Resume(DateTimeOffset now);
    public IReadOnlyList<RecipeCommand> Abort(DateTimeOffset now);
    public void Fail(string message, int? code, DateTimeOffset now);
    public IReadOnlyList<RecipeCommand> SkipStep(DateTimeOffset now, double? chamberTemp);
    public RecipeProgress Progress(DateTimeOffset now);
}
```
**Behaviour & rules:**
1. Factory commands set only their own fields: `CureUv(wl, target, intensity)` -> Target/Wavelength/Intensity; `UvOnly` -> Wavelength/Intensity/Vent; `Cool` -> Target/Mode; `Nitrogen(on)` -> On; `PhaseEnded` -> Timing.
2. `RampSecPerDegree(target)`: `target <= 45 -> 13`, `<= 75 -> 50`, else 80 (a single rate chosen by the TARGET, unlike DOM-05's banded walk). `CoolRateCPerMin`: Fast 2.5, Medium 1.5, else 0.8.
3. `EstimateSeconds(material, fromTemp)`: walk steps, `hold = Time*60`; Cooling: `target = Temperature ?? 25`, total += `max(0, temp - target) / rate(mode ?? Medium) * 60`, temp = min(temp, target); Nitrogen: += 120; others: with Temperature: `ramp = max(0, target - temp) * RampSecPerDegree(target)`, total += (OnRamp ? max(hold, ramp) : ramp + hold), temp = max(temp, target); without Temperature: += hold. No rounding.
4. `Start(now, chamber)`: throws `InvalidOperationException($"cannot start from {State}")` unless Idle. Sets State Preflight, StartedAt = now, total clock anchor = now, lastTemp = chamber, `EstimatedTotalSec = EstimateSeconds(material, chamber ?? 25)`. No steps -> Finish(Completed, "Program has no steps") and return `[Stop]`. Else State Running, Message "Running", return `BeginStep(0)`.
5. `BeginStep(index, now, chamber)`: StepIndex = index, stepStart = now, holdStart = null, rampEnd = null, tempStart = chamber, uvLit = false, uvDeferred = false, `from = chamber ?? lastTemp ?? 25`:
   - Nitrogen: Phase Nitrogen, emit `[Nitrogen(true)]`.
   - Cooling: target = Temperature ?? 25, mode = CoolingMode ?? Medium; coolEstimate = `max(0, from - target) / rate * 60`; Phase Cooling; emit `[Cool(target, mode)]`.
   - Heating: Phase Ramping, ArmRamp, emit `[Heat(target)]`. Drying: same with `[Dry(target)]`.
   - Cure/Bleacher UV-only (null temperature): Phase Holding, rampEnd = holdStart = now, uvLit = true, emit `[UvOnly(UvWavelength, EffectiveUvIntensity, Ventilation ?? false)]`.
   - Cure/Bleacher with temperature: Phase Ramping, ArmRamp; if `UvStartMode == AtStart` -> uvLit = true, emit `[CureUv(UvWavelength, target, EffectiveUvIntensity)]`; else uvDeferred = true, emit `[Heat(target)]` (UV waits for the target; null UvStartMode counts as at-target).
   - ArmRamp: `rampEstimate = max(0, target - from) * RampSecPerDegree(target)`; if TimerMode == OnRamp then holdStart = now (the timer counts through the ramp).
6. `Advance(now, chamber)`: returns empty unless Running. `lastTemp = chamber ?? lastTemp`; `elapsed = now - stepStart` (s).
   - Nitrogen: `elapsed >= 120` -> `[Nitrogen(false), ...EndStep]`.
   - Cooling: done when `chamber <= target + 0.5` (target = Temperature ?? 25), or, without a reading, `elapsed >= coolEstimate` -> EndStep.
   - Heated steps: if rampEnd is null: reached when `chamber >= target - 0.5`, or without a reading `elapsed >= rampEstimate`; on reach: rampEnd = now, Phase Holding, if uvDeferred and not lit -> lit, emit `CureUv(wl, target, intensity)`; `holdStart ??= now`. Then (same tick) if rampEnd set and `now - holdStart >= Time*60` -> EndStep. Hence on-ramp mode: hold counts from the step start, but the step never ends before the target is reached; on-target mode: hold counts from target reach.
7. `EndStep(now, chamber)`: emits `PhaseEnded(PhaseTiming{ Program = material.Name, Step = step.Step, Process = step.Process.ToString(), TargetTemp = step.Temperature, PlannedMin = step.Time, StartedAt = stepStart.ToString("O"), EndedAt = now.ToString("O"), Seconds = Math.Round(now - stepStart, 1), RampSeconds = (rampEnd set && process not Cooling/Nitrogen) ? Math.Round(rampEnd - stepStart, 1) : null, TempStart = tempStart, TempEnd = chamber, CoolingMode = Cooling ? (mode ?? Medium).Wire() : null, Intensity = IsUv ? EffectiveUvIntensity : null, TimerMode = TimerMode set ? "on-ramp"/"on-target" : null, RunId = runId })`. `StepsCompleted = StepIndex + 1`. Last step -> append `Stop`, Finish(Completed, "Program completed"); else append `BeginStep(StepIndex + 1, now, chamber)`.
8. `Pause(now)`: only from Running: State Paused, Message "Paused", pausedAt = now, return `[Stop]`; otherwise empty.
9. `Resume(now)`: only from Paused: shift = now - pausedAt; pausedAt = null; total anchor, stepStart, holdStart (if set), rampEnd (if set) all += shift; State Running, Message "Running"; return `[CurrentPhaseCommand]`: Nitrogen -> `Nitrogen(true)`; Cooling -> `Cool(Temperature ?? 25, mode ?? Medium)`; Heating -> `Heat`; Drying -> `Dry`; UV-only -> `UvOnly(...)`; UV with uvLit -> `CureUv(...)`; otherwise `Heat(target)`.
10. `Abort(now)`: if already Completed/Aborted/Error -> empty; else Finish(Aborted, "Aborted by operator"), return `[Stop]` (allowed from Idle/Preflight/Running/Paused).
11. `Fail(message, code, now)`: if finished -> no-op; else ErrorCode = code, Finish(Error, message). Emits nothing (caller stops outputs).
12. `SkipStep(now, chamber)`: only from Running: `[Nitrogen(false)]` if the current step is Nitrogen, then `EndStep` (RampSeconds null when the ramp had not ended).
13. Finish(state, message, now): State, Message, EndedAt = now, Phase = null, pausedAt = null.
14. `Progress(now)`: Idle or no steps -> `(0, total, null, null, null, 0, null, 0, EstimatedTotalSec)`. `clock = pausedAt ?? EndedAt ?? now`; totalElapsed = clock - totalStart. Finished -> `(StepIndex, total, null, null, null, 0, null, totalElapsed, est)`. Otherwise stepElapsed = clock - stepStart; remaining: Nitrogen `max(0, 120 - stepElapsed)`; Cooling `max(0, coolEstimate - stepElapsed)`; Holding with holdStart `max(0, Time*60 - (clock - holdStart))`; Ramping `max(0, rampEst - stepElapsed) + (OnRamp ? max(0, Time*60 - stepElapsed - max(0, rampEst - stepElapsed)) : Time*60)`; else null. Phase string = `"paused"` while Paused, else the lower-case phase name. Process = enum name, TargetTemp = step temperature.
**Configuration:** none.
**Acceptance criteria (from the source tests; T0 = 2026-09-14 08:00Z):**
- Program [Heating 60/5 on-target, Cure 60/10 uv40, Cooling 30 medium], run "run-1", Start at 25: one `Heat(60)`, Phase Ramping, `EstimatedTotalSec == 35*50 + 300 + 600 + 1200`. Chamber `min(60, 25+0.5 s)`: no command for s<69; at 69 s with 59.5 -> Holding, no command; Progress remaining 300, Process "Heating", Phase "holding". At 369 s -> `[PhaseEnded, Heat]` with timing Step 1, Seconds 369, RampSeconds 69, TempStart 25, TempEnd 60, TimerMode "on-target", RunId "run-1"; StepIndex 1, StepsCompleted 1. At 370 s -> single `CureUv` (405 nm, intensity 40, target 60). At 970 s -> `[PhaseEnded(Intensity 40), Cool(30, Medium)]`, Phase Cooling. At 2170 s with 30.4 -> `[PhaseEnded(CoolingMode "medium", RampSeconds null), Stop]`, Completed, StepsCompleted 3, EndedAt = T0+2170; later Advance empty.
- On-ramp Heating 60/1: at 60 s with 50 °C still Ramping; at 70 s with 59.6 -> `[PhaseEnded(RampSeconds 70), Stop]`.
- Bleacher 50/2 uv60 at-start -> first command `CureUv` 450 nm; ramp end at 49.6 emits nothing; at 170 s the second step (Cure UV-only, Ventilation true) emits `UvOnly` 405 nm Vent true as `cmds[1]`; ends with Stop, Completed.
- Nitrogen step: `[Nitrogen(On=true)]`, Progress remaining 120; nothing at 119 s; at 120 s `[Nitrogen(false), PhaseEnded, Stop]`.
- Pause at 100 s (holding since 70) -> `[Stop]`, Paused, Progress phase "paused", step elapsed frozen at 100; Advance while paused empty; Resume at 1100 -> `[Heat]`, remaining 270; PhaseEnded at 1370 with Seconds 370.
- Resume after the UV was lit re-issues `CureUv`.
- SkipStep at 10 s -> `[PhaseEnded(RampSeconds null), Heat]`, StepIndex 1; Abort -> `[Stop]`, Aborted; second Abort empty. Fail("Door opened", 6016) -> Error, ErrorCode 6016, Message "Door opened".
- No temperature feedback (Start with null): Heating 40 ramps by time 15*13 = 195 s (Ramping at 194, Holding at 195).
- Empty program: Start returns `[Stop]`, Completed.
**Tests:** `RecipeStateMachineTests` (Walks_a_three_step_program, On_ramp_timer_counts_through_the_ramp_and_waits_for_the_target, Uv_at_start_lights_immediately_and_uv_only_skips_the_ramp, Nitrogen_step_is_a_fixed_purge, Pause_freezes_the_clock_and_resume_reissues_the_phase, Resume_reissues_cure_uv_when_the_uv_was_already_lit, Abort_skip_and_fail, Without_temperature_feedback_the_ramp_is_time_based, Empty_program_completes_at_once).
**Reference (source):** `src/SCureBox.Domain/Control/RecipeStateMachine.cs`, `RecipeCommand.cs`, `RecipeCommandKind.cs`, `RecipePhase.cs`, `RecipeState.cs`, `RecipeProgress.cs`, `tests/SCureBox.Domain.Tests/Control/RecipeStateMachineTests.cs`

---

### DOM-07 — Sensor conversion maths and signal helpers
**Project / folder:** `src/SCureBox.Domain/Sensors/` (`NtcMath.cs`, `ChamberTempCalibration.cs`, `PressureConversion.cs`, `PressureResult.cs`, `PressureSensorParameters.cs`) and `src/SCureBox.Domain/Control/` (`SlopeEstimator.cs`, `TachRateTracker.cs`, `SensorGlitchHold.cs`)
**Goal:** Convert raw analog readings into engineering values — NTC tap volts to °C, raw chamber °C to the TC-08-calibrated chamber temperature with rate compensation, N2 sensor volts to MPa/bar — and provide the generic signal helpers used by the hardware and control loops: least-squares slope over a sliding window, a shared-reader tachometer RPM tracker, and a short-glitch hold that keeps the last good value.
**Depends on:** DOM-01.
**Files to create:** the eight files above.
**Public contract:**
```csharp
namespace SCureBox.Domain.Sensors;
public static class NtcMath
{ public const double R0 = 10000.0; public const double Beta = 3934.0; public const double T0Kelvin = 298.15; public const double RSeries = 10000.0;
  public const double VRef = 3.3; public const double ValidMinC = -20.0; public const double ValidMaxC = 120.0;
  public static double? VoltageToResistance(double volts); public static double? ResistanceToTemperature(double? ohms); public static double? VoltageToTemperature(double volts); }
public sealed class ChamberTempCalibration
{ public const double Gain = 1.0979; public const double Offset = -3.9813; public const double Lead = 2.1873; public const double LeadDeadband = 0.3;
  public const double CoolCoef = 0.0956; public const double CoolGate = -1.0; public const double CoolFull = -2.5; public const double Ambient = 25.0;
  public const double RateWindowSec = 45.0; public const int MinSamples = 3; public const double MinSpanSec = 10.0;
  public ChamberTempCalibration(TimeProvider timeProvider); public ChamberTempCalibration();
  public static double Static(double rawC); public double Correct(double rawC); public double Correct(double rawC, double seconds); public void Reset(); }
public sealed record PressureSensorParameters(string Mode, double VMin, double VMax, double IMinMa, double IMaxMa, double ShuntOhms,
    double PAtLowMpa, double PAtHighMpa, double Divider, double AdcSaturationVolts, double OnAboveVolts, double SetPointMpa)
{ public const string ModeAnalogVoltage = "analog_voltage"; public const string ModeAnalogCurrent = "analog_current"; public const string ModeSwitch = "switch";
  public static PressureSensorParameters Default { get; } }   // ("analog_voltage", 1.0, 5.0, 4.0, 20.0, 120.0, 0.0, 1.0, 1.0, 3.2, 2.0, 0.1) - a new instance per get
public sealed record PressureResult(double Volts, double SensorVolts, double? Mpa, double? Bar, bool On, bool Saturated, string Mode, double SetPointMpa);
public static class PressureConversion { public const double MpaToBar = 10.0; public static PressureResult Convert(double vAdc, PressureSensorParameters p); }

namespace SCureBox.Domain.Control;
public sealed class SlopeEstimator
{ public SlopeEstimator(double windowSec, double minSpanSec = 10.0); public double WindowSec { get; } public double MinSpanSec { get; } public int Count { get; }
  public void Add(double tSec, double value); public double? SlopePerSecond(); public double? RatePerMinute();
  public static double? SlopePerSecond(IReadOnlyList<(double t, double v)> samples, double minSpanSec); }
public sealed class TachRateTracker<TKey> where TKey : notnull
{ public const double MinWindowSec = 1.0; public const double SampleSpacingSec = 0.1;
  public TachRateTracker(int pulsesPerRev); public int? Rpm(TKey key, long count, double nowSec); }
public enum GlitchVerdict { Report, HoldStarted, Holding, HoldExpired }
public sealed class SensorGlitchHold<TKey, TValue> where TKey : notnull
{ public TimeSpan? Good(TKey key, TValue value, DateTimeOffset now); public GlitchVerdict Bad(TKey key, DateTimeOffset now, double holdSec, out TValue? held); }
```
**Behaviour & rules:**
1. NTC (Murata NCP21XV103J03RA, 10 kOhm, β 3934, topology 3.3 V -> 10 kOhm -> tap (ADC) -> NTC -> GND): `VoltageToResistance(v)` = null if `v <= 0 || v >= 3.3`, else `10000 * v / (3.3 - v)`. `ResistanceToTemperature(R)` = null if null or `<= 0`, else `1 / (1/298.15 + ln(R/10000)/3934) - 273.15`. Higher tap volts = colder. Valid supervised range -20..120 °C.
2. Chamber calibration (TC-08 reference, 2026-08-04, 724 paired samples): `Static(raw) = 1.0979*raw - 3.9813`. `Correct(raw, seconds)`: enqueue (seconds, raw); drop samples with `seconds - t > 45`; est = Static(raw); if fewer than 3 samples or span (last.t - first.t) < 10 s -> est. Rate = least-squares slope of raw vs t (centred on mean t) * 60 (°C/min); den <= 0 -> est. If `rate > 0.3`: est += `2.1873 * (rate - 0.3)`. Else if `rate < -1.0`: `f = min(1, (-1.0 - rate) / (-1.0 - -2.5))`, est += `f * 0.0956 * (raw - 25)`. Rates between -1.0 and 0.3 add nothing. `Correct(raw)` uses the TimeProvider (seconds elapsed since construction via `GetTimestamp`/`GetElapsedTime`); without a TimeProvider it throws `InvalidOperationException("no TimeProvider: use Correct(rawC, seconds)")`. `Reset()` clears the window. One instance per sensor; not thread-safe.
3. Pressure (SMC ISE20 analog output on ADS1115 U7 AIN3): `saturated = vAdc >= AdcSaturationVolts`; `vSensor = vAdc * Divider`. analog_voltage and not saturated: `mpa = PAtLow + (vSensor - VMin) * (PAtHigh - PAtLow) / (VMax - VMin)` (1 V = 0 MPa, 5 V = 1.000 MPa, 0.6 V = -0.100 MPa). analog_current and not saturated: `iMa = vSensor / ShuntOhms * 1000`, `mpa = PAtLow + (iMa - IMinMa) * (PAtHigh - PAtLow) / (IMaxMa - IMinMa)`. `On`: switch mode -> `vAdc >= OnAboveVolts`; else mpa known -> `mpa >= SetPointMpa` (0.1 MPa = 1 bar); else `On = saturated` (clamped analog = pressure above span). `Bar = mpa * 10`; Mpa/Bar null when saturated or in switch mode. Result carries Volts = vAdc, SensorVolts, Mode, SetPointMpa.
4. `SlopeEstimator.Add(t, v)`: append, then drop from the front while `t - first.t > WindowSec`. `SlopePerSecond(samples, minSpan)`: null if count < 3 or `last.t - first.t < minSpan`; least squares with x = t - t0 centred on its mean; den <= 0 -> null. `RatePerMinute = slope * 60`.
5. `TachRateTracker` (owner locks; all readers share one sample history per key so interleaved readers get the same rate): constructor throws `ArgumentOutOfRangeException` for `pulsesPerRev <= 0` (hardware uses 2). `Rpm(key, count, now)`: if `count < last stored count` clear the samples (counter restarted). Append `(count, now)` if the list is empty or `now - newest.At >= 0.1 - 1e-6`. While there are >= 2 samples and `now - samples[1].At >= 1.0 - 1e-6`, remove samples[0] (keep as reference the newest sample at least one window old). `window = now - samples[0].At`; if `window < 1.0 - 1e-6` return the last rate for the key (null if none). Else `rpm = (int)Math.Round((count - ref.Count) / pulsesPerRev * (60 / window))`, store and return. (Fixes a false Err 9002 where a second reader 4 ms later saw 0 RPM.)
6. `SensorGlitchHold` (owner locks): `Good(key, value, now)`: store last good (value, now), clear the expired flag; if a bad episode was open, remove it and return its duration (`now - badSince`), else null. `Bad(key, now, holdSec, out held)`: `first = badSince.TryAdd(key, now)`; if `holdSec <= 0` or no good value yet -> `Report`; if `(now - lastGood.At).TotalSeconds <= holdSec` -> held = last good value, `HoldStarted` if first else `Holding`; otherwise `HoldExpired` the first time (expired flag added), `Report` afterwards. The window counts from the last GOOD reading, not from the first bad one.
**Configuration:** `PressureSensorParameters` is filled by the Hardware layer from components.json `pressure_sensor`: `mode` "analog_voltage", `v_min` 1.0, `v_max` 5.0, `i_min_ma` 4.0, `i_max_ma` 20.0, `shunt_ohms` 120.0, `p_at_v_min_mpa` 0.0, `p_at_v_max_mpa` 1.0, `divider` 1.0, `adc_saturation_volts` 3.2, `on_above_volts` 2.0, `set_point_mpa` 0.1. The glitch hold seconds come from components.json `sensor_filter.glitch_hold_sec` (15; 0 disables). TachRateTracker pulses per rev = 2 (Hardware `IoBoardMap.PulsesPerRev`).
**Acceptance criteria:**
- NTC: 1.65 V -> 10000 Ohm and 25.0 °C; 10000 Ohm -> 25 °C; 0.0, -0.1, 3.3, 3.5 V -> null; the β-equation 50 °C resistance and its tap voltage both give 50.0 °C; 2.5 V < 25 °C; R null or 0 -> null.
- Calibration: static only for (50,0),(51,5),(52,9); steady 60 °C gives Static(60); raw +1.0 °C/min over 45 s (0.25 °C each 15 s) -> Static(50.75) + 2.1873*0.7; +0.2 °C/min -> static; -3 °C/min -> + 0.0956*(57.75-25); -1.75 °C/min -> + 0.5*0.0956*(58.6875-25); -0.5 °C/min -> static; samples older than 45 s dropped; TimeProvider constructor stamps samples (FakeTimeProvider advancing 15 s).
- Pressure (saturation lifted to 5.5 V): 0.6 V -> -0.100 MPa, 1.0 -> 0, 3.4 -> 0.600, 5.0 -> 1.000, Bar = 10x, Mode "analog_voltage"; Default 1.0 V -> On false; 1.39 V off, 1.41 V on, SetPointMpa 0.1; Default 3.2 / 3.3 V -> Mpa/Bar null, Saturated, On, Volts echoed; divider 2.0 at 1.7 V -> SensorVolts 3.4, 0.6 MPa; current mode 0.288 / 0.48 / 2.4 V -> -0.1 / 0 / 1.0 MPa; switch mode 0.52 V off with null Mpa, 2.0 and 3.3 V on, Mode "switch".
- Slope: null with (0,20),(5,21); null at 9 s span; non-null once (10,23) added; linear -0.1/s -> -6.0 per minute; window 10 keeps 11 samples t=30..40, rate 60; all-equal t -> null.
- Tach (150 edges/s, 2 ppr): null at 0 and 0.5 s, 4500 at 1.0 s; two readers 4 ms apart stay within 4400..4600 for 40 s; stopped fan -> 0 at 6.6 s; independent keys 3000/1500; counter restart returns the last rate (1500) until a new window, then 3000; a reader every 1 ms for 10 s stays within 4400..4600.
- Glitch: Bad without Good -> Report; Good 42.5 at T0 then Bad at +1 HoldStarted (42.5), +30 Holding (42.5), +30.5 HoldExpired, +60 Report; Good at +20 after Bad at +10 returns 10 s, then Bad at +45 HoldStarted (21.0), +51 HoldExpired; keys independent; holdSec 0 -> Report.
**Tests:** `NtcMathTests`, `ChamberTempCalibrationTests`, `PressureConversionTests` (in `tests/.../Sensors/`), `SlopeEstimatorTests`, `TachRateTrackerTests`, `SensorGlitchHoldTests` (in `tests/.../Control/`) — test names as in the source: Mid_tap_is_10k_and_25_degrees, Rails_read_as_open_or_shorted, Beta_equation_known_points; Static_correction_until_the_window_has_three_samples_over_ten_seconds, Steady_state_has_no_rate_term, Heating_adds_the_lead_term_above_the_deadband, Cooling_blends_in_the_ambient_offset_between_the_gate_and_full_rate, Window_drops_samples_older_than_45_seconds, Time_provider_constructor_stamps_samples; Voltage_output_follows_the_datasheet_points, On_means_at_or_above_the_set_point, Saturated_adc_reports_null_pressure_and_on, Divider_scales_the_sensor_volts, Current_output_follows_the_datasheet_points, Switch_mode_only_thresholds; Needs_three_samples_spanning_ten_seconds, Linear_ramp_gives_the_exact_rate_per_minute, Window_drops_old_samples, Degenerate_time_axis_gives_null; Null_until_a_full_window_then_the_rate_over_it, Two_readers_a_few_ms_apart_both_get_the_real_rate_never_zero, A_stopped_fan_reads_zero_after_one_window, Fans_are_independent_and_a_counter_restart_starts_over, Rapid_readers_do_not_grow_the_sample_list_without_bound; Bad_reading_without_a_good_one_is_reported, Glitch_inside_the_window_returns_the_last_good_value_then_expires_once, Window_counts_from_the_last_good_reading_and_recovery_resets_it, Sensors_are_independent_and_zero_disables_the_hold.
**Reference (source):** `src/SCureBox.Domain/Sensors/*.cs`, `src/SCureBox.Domain/Control/SlopeEstimator.cs`, `TachRateTracker.cs`, `SensorGlitchHold.cs`, matching test files under `tests/SCureBox.Domain.Tests/Sensors/` and `tests/SCureBox.Domain.Tests/Control/`

---

### DOM-08 — Heater PI + delta-sigma controller and HDT calibration maths
**Project / folder:** `src/SCureBox.Domain/Control/` (`PiDeltaSigmaController.cs`, `PiDeltaSigmaGains.cs`, `HdtModel.cs`)
**Goal:** The heater control law (PI(D) on a 0..1 power scale streamed as per-cycle ON/OFF by a first-order delta-sigma modulator, port of temperature_control._loop) and the pure maths used by HDT (heat-deflection) calibration: stability test, least-squares slope in °C/min, equilibrium temperature line vs power, first-order time constant and boost time.
**Depends on:** DOM-01.
**Files to create:** the three files above.
**Public contract:**
```csharp
namespace SCureBox.Domain.Control;
public sealed record PiDeltaSigmaGains(double Kp, double Ki, double Kd, double IntegMin, double IntegMax)
{ public static PiDeltaSigmaGains Default { get; } }      // new(0.22, 0.00015, 0.0, 0.0, 0.85)
public sealed class PiDeltaSigmaController
{ public PiDeltaSigmaController(PiDeltaSigmaGains gains); public double Integrator { get; } public double DacAccumulator { get; } public bool LastOutput { get; }
  public (double power, bool elementOn) Step(double err); public void Reset(); }
public static class HdtModel
{ public static double? SlopePerMinute(IReadOnlyList<(double t, double v)> window);
  public static bool IsStable(IReadOnlyList<(double t, double v)> window, double stabilityTimeSec, double bandC, double maxRateCPerMin);
  public static double EquilibriumAt(IReadOnlyList<(double power, double stableTemp)> levels, double power);
  public static double? TimeConstant(double startTemp, double stableTemp, IReadOnlyList<(double t, double avg)> trace);
  public static double? BoostTimeSec(double tau, double tEq, double t0, double limit); }
```
**Behaviour & rules:**
1. `Step(err)` (err = target - measured, °C), once per sample (the heating loop samples every 50 ms): `integ = clamp(integ + Ki*err, IntegMin, IntegMax)`; `deriv = prevErr is null ? 0 : Kd*(err - prevErr)`; `prevErr = err`; `control = Kp*err + integ + deriv`; `power = clamp(control, 0, 1)`; `delta = dacLast ? power - 1 : power`; `sig = dacAccum + delta`; `on = sig > 0.5`; `dacLast = on`; `dacAccum = sig`; return `(power, on)`. The average ON-time equals the commanded power.
2. `Reset()`: integ 0, prevErr null, dacAccum 0, dacLast false. Not thread-safe.
3. `HdtModel.SlopePerMinute`: null if fewer than 2 samples; x = (t - t0)/60 centred on its mean; least squares; den <= 0 -> null.
4. `IsStable(window, stabilityTimeSec, bandC, maxRate)`: false if empty or `last.t - first.t < stabilityTimeSec`; false if `max - min > bandC`; true if `maxRate <= 0` (rate rule disabled); else `SlopePerMinute` non-null and `|slope| <= maxRate`.
5. `EquilibriumAt(levels, p)`: least-squares line through (power, stableTemp): `slope = den > 0 ? num/den : 0`; returns `meanT + slope*(p - meanP)`. (Empty input is not guarded — division by zero gives NaN.)
6. `TimeConstant(start, stable, trace)`: null if `stable - start < 1.0` or trace empty; target = `start + 0.632*(stable - start)`; returns `t - trace[0].t` at the first sample with `avg >= target`, else null.
7. `BoostTimeSec(tau, tEq, t0, limit)`: null if `tEq <= limit`; else `tau * ln((tEq - t0)/(tEq - limit))`.
**Configuration:** gains come from components.json `heating`: `kp` 0.22, `ki` 0.00015, `kd` 0.0, `integ_min` 0.0, `integ_max` 0.85 (also `sample_sec` 0.05, used by the heating loop in Application). The HDT parameters are passed by Application/Dvt-Hdt.
**Acceptance criteria:**
- Default gains, constant err 2: (power, on, accum) sequence (0.4403,false,0.4403), (0.4406,true,0.8809), (0.4409,false,0.3218), (0.4412,true,0.7630), (0.4415,false,0.2045), (0.4418,true,0.6463) (9 decimals).
- err -3 for 20 steps -> power 0, off, integrator 0. err 100 for 10000 steps -> power 1, always on, integrator 0.85.
- Gains (0.1, 0, 0.5, 0, 1): step(1) = 0.1, step(2) = 0.7.
- Gains (0.1, 0, 0, 0, 1), err 3 for 1000 steps -> ON count 295..305.
- After Reset the first step(2) is 0.4403 again.
- HDT: 61 samples rising 0.01 °C/s -> 0.6 °C/min; single sample -> null. A 301 s window alternating 45/45.5 is stable (300 s, band 2, rate 0.5); first 200 samples -> not stable; alternating 45/47.5 -> not stable; drift 0.3 °C/min stable; 0.36 °C/min stable at 0.5, not at 0.3, stable with rate 0. Levels (10,29.5),(20,35),(30,40.5) -> 73.5 at 90; a first-order rise 24->34 with τ 40 s -> TimeConstant 40 (0 decimals); rise 0.5 -> null. Boost(40, 73.5, 35, 48) = 40*ln(38.5/25.5); Boost(40, 45, 35, 48) = null.
**Tests:** `PiDeltaSigmaControllerTests` (Reproduces_the_python_sequence_for_a_constant_error, Negative_error_gives_zero_power_and_element_off, Saturated_error_keeps_the_element_on_and_clamps_the_integrator, Derivative_term_uses_the_previous_error, Average_on_time_tracks_the_commanded_power, Reset_returns_to_the_initial_state); `HdtModelTests` (Slope_per_minute_of_a_linear_window, Stability_needs_the_window_the_band_and_the_rate, Equilibrium_line_and_time_constant, Boost_time_formula).
**Reference (source):** `src/SCureBox.Domain/Control/PiDeltaSigmaController.cs`, `PiDeltaSigmaGains.cs`, `HdtModel.cs`, `tests/SCureBox.Domain.Tests/Control/PiDeltaSigmaControllerTests.cs`, `HdtModelTests.cs`

---

### DOM-09 — Heater and thermistor safety supervision (9010-9014, 9006, 9007) and output watchdog decision (9017)
**Project / folder:** `src/SCureBox.Domain/Control/` (`SensorSupervisionEvaluator.cs`, `SensorSupervisionResult.cs`, `SensorState.cs`, `FrozenReadingEvaluator.cs`, `NoHeatEvaluator.cs`, `WatchdogMonitor.cs`)
**Goal:** The evaluators that protect the heater: open-circuit thermistor supervision with one code per sensor, the plausible-but-frozen chamber reading (a fixed resistor / stuck ADC / stuck reader thread, DVT-SAF-003), the heater that drives without warming the chamber (voltage selector between positions or blown fuse, DVT-SAF-017), and the decision logic of the external output watchdog that cuts heater + UV when the firmware heartbeat goes silent (DVT-SAF-010). Each returns alerts as `code -> detail`; the caller (Application supervision / Hardware watchdog) switches outputs off.
**Depends on:** DOM-01, DOM-02, DOM-07 (NtcMath constants share the same valid range).
**Files to create:** the six files above (`FrozenReadingRules` lives in `FrozenReadingEvaluator.cs`, `NoHeatRules` in `NoHeatEvaluator.cs`, `WatchdogEvent` in `WatchdogMonitor.cs`).
**Public contract:**
```csharp
namespace SCureBox.Domain.Control;
public sealed record SensorState(string Sensor, bool Ok, int? OpenSec, bool Critical);
public sealed record SensorSupervisionResult(IReadOnlyDictionary<string, SensorState> Sensors, IReadOnlyDictionary<int, string> Alerts, IReadOnlySet<TempSensor> OpenNow);
public sealed class SensorSupervisionEvaluator
{ public const string HeaterSensorDetail = "Heater temperature sensor (chamber NTC TEMP_CHAMBER) is not reading - the heater is off";
  public const double ValidMinC = -20.0; public const double ValidMaxC = 120.0;
  public SensorSupervisionEvaluator(double openAlertSec = 60.0); public double OpenAlertSec { get; }
  public IReadOnlyDictionary<int, string> Alerts { get; }
  public static bool ReadOk(double? t);
  public static IReadOnlyList<TempSensor> OpenRequired(IReadOnlyDictionary<TempSensor, double?> readings);
  public SensorSupervisionResult Evaluate(IReadOnlyDictionary<TempSensor, double?> readings, bool heatingWanted, DateTimeOffset now);
  public void NotePreflightRefusal(IReadOnlyList<TempSensor> bad, DateTimeOffset now);
  public static string PreflightRefusal(IReadOnlyList<TempSensor> bad);
  public static string Detail(IEnumerable<TempSensor> open);
  public IReadOnlyDictionary<string, SensorState> SensorsState(DateTimeOffset now); }
public sealed record FrozenReadingRules(bool Enabled, double WindowSec, double MinDeltaC, double MinDutyPct, double RebootAfterSec = 60);
public sealed class FrozenReadingEvaluator
{ public const double ClearDeltaC = 1.0;
  public IReadOnlyDictionary<int, string> Alerts { get; } public string? Detail { get; } public double? FrozenAt { get; }
  public void Restore(double frozenAt, string detail);
  public string? Evaluate(FrozenReadingRules rules, double? chamber, bool heating, double heaterDutyPct, DateTimeOffset now);
  public static string Describe(double reading, FrozenReadingRules rules, double heaterDutyPct); }
public sealed record NoHeatRules(bool Enabled, double WindowSec, double MinRiseC, double MinDutyPct, double AtTargetBandC = 1.5);
public sealed class NoHeatEvaluator
{ public bool ReachedTarget { get; } public IReadOnlyDictionary<int, string> Alerts { get; } public string? Detail { get; }
  public string? Evaluate(NoHeatRules rules, double? chamber, bool heating, double heaterDutyPct, DateTimeOffset now, double? targetC = null);
  public static string Describe(double from, double to, NoHeatRules rules, double heaterDutyPct); }
public enum WatchdogEvent { None, Armed, Tripped, Recut, Recovered, Disarmed }
public sealed class WatchdogMonitor
{ public WatchdogMonitor(double timeoutSec = 20, double recutSec = 5); public double TimeoutSec { get; } public double RecutSec { get; }
  public bool Armed { get; } public bool Tripped { get; } public WatchdogEvent Step(long? heartbeatTickMs, long nowTickMs); }
```
**Behaviour & rules — sensor supervision (9010-9014):**
1. `ReadOk(t)` = t non-null and `-20 <= t <= 120`. Out of range counts as open.
2. `Evaluate(readings, heatingWanted, now)`: for each sensor in `HardwareNames.SupervisedSensors` order (CHAMBER, LEFT, RIGHT, BACK, DOOR), code = `SensorDisconnectedOf(sensor)`: if the reading is OK -> forget its open-since and remove its alert. Else add to `OpenNow`, set open-since if new, and (re)write `alerts[code] = Detail([sensor])` when the alert already exists, OR (sensor is TEMP_CHAMBER and heatingWanted), OR open for `>= OpenAlertSec` (60 s). Return `(SensorsState(now), copy of alerts, OpenNow)`. A sensor missing from the dictionary counts as open. `heatingWanted` = heating active, commanded or just faulted.
3. `Detail(open)`: panels = open minus chamber; no chamber -> `"Temperature sensor disconnected: " + Describe(panels)`; chamber only -> `HeaterSensorDetail`; chamber + panels -> `HeaterSensorDetail + "; also not reading: " + Describe(panels)`. `Describe` joins `"{Location} ({SENSOR})"` with `", "` in SupervisedSensors order.
4. `SensorsState(now)`: keyed by UI name (`chamber`, `left`, `right`, `back`, `door`) -> `SensorState(sensor.ToString(), Ok = not open, OpenSec = (int)(now - openSince) or null, Critical)`.
5. `OpenRequired(readings)`: required (critical) sensors whose reading is missing or not OK, in SupervisedSensors order.
6. `PreflightRefusal(bad)`: `$"[{code of the first bad sensor in SupervisedSensors order}] Temperature sensor disconnected: {Describe(bad)} - reconnect the sensor before starting a process"` (throws if `bad` is empty). `NotePreflightRefusal(bad, now)`: for each, `alerts[code] = Detail([s])` and open-since TryAdd(now).
**Behaviour & rules — frozen reading (9006):**
7. `Evaluate(rules, chamber, heating, dutyPct, now)` returns the detail ONLY on the pass that raises (caller switches the heater off), else null. Disabled -> clear window, return null (an existing latch is NOT cleared). If latched (`FrozenAt` set): clear latch and alert when chamber is null (open — 9010 takes over) or `|chamber - frozenAt| >= 1.0`; otherwise stay latched and return null. If `!heating || dutyPct < MinDutyPct || chamber null` -> clear window, return null (only continuous drive counts). Else add (now, chamber); drop points older than `WindowSec + 1` s; if `now - first < WindowSec` -> null; if `max - min >= MinDeltaC` -> null; else latch `FrozenAt = chamber`, `alerts[9006] = Describe(...)`, clear window, return the detail.
8. `Describe(reading, rules, duty)` = `$"Heater temperature reading (chamber NTC TEMP_CHAMBER) is frozen at {reading:0.0} C - it moved less than {rules.MinDeltaC:0.0#} C in {rules.WindowSec:0} s with the heater at {duty:0} % output, so it is not measuring the chamber. The heater is off"` + (RebootAfterSec > 0 ? `$" and the machine restarts itself in {RebootAfterSec:0} s; heating stays refused after the restart"` : "") + `"; fix the sensor before heating again"`.
9. `Restore(frozenAt, detail)`: re-latch after a reboot from persisted state (the Application layer stores it in data/frozen_reading.json), clear the window.
**Behaviour & rules — heater not heating (9007):**
10. `Evaluate(rules, chamber, heating, dutyPct, now, targetC)` returns the detail only on the raising pass. Disabled -> clear window, REMOVE the alert, null. Then: if `(heating && !wasHeating) || targetC != lastTarget` -> `ReachedTarget = false` (new ramp); update wasHeating, lastTarget. If heating and target and chamber known and `chamber >= target - AtTargetBandC` -> `ReachedTarget = true` (judged during the ramp up only; with `targetC == null` the whole run is judged as a ramp). `powered = heating && duty > 0`; on a rising edge of `powered` remove the 9007 alert (any new drive after the 9007 shutdown re-judges, at any output). `driving = heating && duty >= MinDutyPct && chamber != null`. If `!driving || ReachedTarget || alert latched` -> clear window, null. Else add (now, chamber), drop points older than `WindowSec + 1`, if `now - first < WindowSec` -> null; `from = MIN of window values` (not the first point — a stratified chamber dips at a heating start); `rise = chamber - from`; `rise >= MinRiseC` -> null; else set `alerts[9007] = Describe(from, chamber, rules, duty)`, clear window, return the detail.
11. `Describe` = `$"Heater not heating: the chamber went from {from:0.0} C to {to:0.0} C in {WindowSec:0} s with the heater at {duty:0} % output (less than {MinRiseC:0.0#} C rise) - the heater is getting no power. Check the voltage selector (110 / 230 V) is fully in its position, and check the heater fuse. The heater is off"`.
**Behaviour & rules — watchdog decision (9017 is raised by the firmware from the trip record, not here):**
12. Constructor: `timeoutSec <= 0` throws `ArgumentOutOfRangeException`; `RecutSec = max(0.5, recutSec)`. `Step(heartbeatTickMs, nowTickMs)` (same monotonic ms clock):
    - heartbeat null (no file): if Tripped -> RecutDue; else if not Armed -> None; else Armed = false, return Disarmed (clean stop, no cut).
    - age = (now - beat)/1000 < TimeoutSec: if Tripped -> Tripped = false, Armed = true, Recovered; else if Armed -> None; else Armed = true, Armed event.
    - age >= TimeoutSec: if not Tripped -> Tripped = true, Armed = false, lastCut = now, Tripped event (also for a stale heartbeat found at watchdog start); else RecutDue.
    - RecutDue: `(now - lastCut)/1000 < RecutSec` -> None; else lastCut = now, Recut.
**Configuration:** components.json `frozen_reading` -> `FrozenReadingRules(enabled true, window_sec 90, min_delta_c 0.01, min_duty_pct 50, reboot_after_sec 60)`; `no_heat` -> `NoHeatRules(enabled true, window_sec 600, min_rise_c 0.5, min_duty_pct 99, AtTargetBandC = heating.at_temp_band 1.5)`; open-alert time 60 s (constructor default; no config key); watchdog timeout 20 s / re-cut 5 s (the Hardware watchdog passes them). Mapping is done in Application (`SupervisionService.ToRules`); the rules are re-read live.
**Acceptance criteria:**
- Sensor: TEMP_LEFT open 0..59 s -> no alert, `Sensors["left"]` Ok false, OpenSec 59, Critical true; at 60 s alerts == {9011: "Temperature sensor disconnected: Left LED panel (TEMP_LEFT)"}. Each sensor CHAMBER/LEFT/RIGHT/BACK/DOOR raises exactly 9010/9011/9012/9013/9014 after 60 s, family 9001 for 9010-9012 and 9050 for 9013-9014; `Sensors["back"].Critical == false`. Chamber open with heatingWanted -> 9010 = HeaterSensorDetail at once; idle -> only at 60 s. Left+right open then left reads -> only 9012 remains, `Sensors["left"].Ok`; all read -> empty. Right reading 150 -> in OpenNow and `OpenRequired == [TEMP_RIGHT]`. `PreflightRefusal([CHAMBER, LEFT]) == "[9010] Temperature sensor disconnected: Chamber (TEMP_CHAMBER), Left LED panel (TEMP_LEFT) - reconnect the sensor before starting a process"`; `[LEFT]` starts "[9011] "; NotePreflightRefusal sets 9010 = HeaterSensorDetail, 9011 = left text, chamber OpenSec 0. Door detail "Temperature sensor disconnected: Door LED panel (TEMP_DOOR)". Chamber+right while heating: 9010 at once, 9012 only at 60 s.
- Frozen (rules 90 s, 0.1, 50): 41.5 °C flat at 100 % -> null for 0..89 s, raised in 90..92 s, text contains "TEMP_CHAMBER", "frozen at 41.5 C", "90 s", "100 % output", equals `Alerts[9006]` and `Detail`; stays latched (no second raise) while 41.5 even when not heating; 55.2 clears. Rising 0.02 °C/s never raises. Duty dipping to 20 every 10 s or steady 30 % never raises. Heating off at 81 s restarts the window (fresh 90 s from 82 s; raised at 172 s); null reading clears the latch. Disabled never raises.
- No-heat (rules 120 s, 0.5, 50, no target): 35.0 - 0.02 °C/s -> null 0..119, raised at 120 with text containing "voltage selector", "fuse", "The heater is off"; latched, not raised again. +0.066 °C/s and +0.006 °C/s never raise. Duty 30 never raises. Duty dip to 20 at 101 s restarts the window (raised only by 222 s). After a raise, heater off keeps the alert; driven again clears it. Mixing dip 40.5 -> 28.7 in 60 s then +0.1 °C/s -> no alert. With target 80: ramp into the band -> ReachedTarget, dip to 72.2 and flat for 1500 s -> no alert; ramp that never reaches the target is judged (raised, ReachedTarget false); new target 75 after reaching 60 is judged again; a new heating start after reaching the target is judged again. Disabled never raises.
- Watchdog (20, 5): no heartbeat ever -> None, not armed/tripped; live heartbeat -> Armed once then None; heartbeat at 10 s: None at 29.9 s, Tripped at 30 s, None at 34, Recut at 35, None at 36, Recut at 40; fresh heartbeat after trip -> Recovered (Armed, not Tripped), then None; heartbeat removed -> Disarmed then None; stale heartbeat at start (100 s old) -> Tripped; tripped then heartbeat removed -> None at +1 s, Recut at +5 s.
**Tests:** `SensorSupervisionEvaluatorTests` (Required_sensor_open_alerts_its_own_code_after_sixty_seconds, Every_thermistor_has_its_own_code [Theory], Warning_sensor_open_alerts_9013, Chamber_open_while_heating_alerts_immediately_with_the_heater_detail, Chamber_open_while_idle_waits_the_full_minute, Each_alert_clears_when_its_own_sensor_reads, Out_of_range_reading_counts_as_open, Preflight_refusal_text_and_note, Warning_detail_names_the_door_panel, Chamber_and_a_panel_open_raise_two_codes); `FrozenReadingEvaluatorTests` (in Sensors/ folder; 5 facts above); `NoHeatEvaluatorTests` (12 facts above); `WatchdogMonitorTests` (7 facts above).
**Reference (source):** `src/SCureBox.Domain/Control/SensorSupervisionEvaluator.cs`, `SensorSupervisionResult.cs`, `SensorState.cs`, `FrozenReadingEvaluator.cs`, `NoHeatEvaluator.cs`, `WatchdogMonitor.cs`, `tests/SCureBox.Domain.Tests/Control/SensorSupervisionEvaluatorTests.cs`, `NoHeatEvaluatorTests.cs`, `WatchdogMonitorTests.cs`, `tests/SCureBox.Domain.Tests/Sensors/FrozenReadingEvaluatorTests.cs`

---

### DOM-10 — Fan, LED-panel and UV-light supervision (902x, 903x, 904x, 906x, 9046/9047)
**Project / folder:** `src/SCureBox.Domain/Control/` (`FanHealthEvaluator.cs`, `FanHealthRules.cs`, `FanHealthEntry.cs`, `FanHealthOutcome.cs`, `LedHeatingEvaluator.cs`, `LedHeatingRules.cs`, `LedHealthEntry.cs`, `LedHeatingResult.cs`, `UvLightEvaluator.cs`)
**Goal:** Per-component supervision of the cooling/heater fans (wear warning, critical stop latch, operator override and acknowledge, pre-flight not-spinning verdicts), of the UV LED panels' thermal proof of current (panel must warm its thermistor; mid-process temperature drop), and of the UV-on light confirmation by the Left/Right photoresistors. One alert code per fan / panel (since 2026-10-21); the grouped codes are never raised.
**Depends on:** DOM-01, DOM-02, DOM-09 (`SensorSupervisionEvaluator.ReadOk`), DOM-07 (`NtcMath.VRef`).
**Files to create:** the nine files above (`UvLightRules` lives in `UvLightEvaluator.cs`).
**Public contract:**
```csharp
namespace SCureBox.Domain.Control;
public sealed record FanHealthRules(double WarnBelowPct, double CriticalBelowPct, double PersistSec, double SettleSec, double MinEvalDuty,
    double StoppedPersistSec, IReadOnlyDictionary<Fan, IReadOnlyList<(double duty, double rpm)>> Nominal,
    IReadOnlyDictionary<Fan, double>? CriticalBelowPctByFan = null)
{ public double CriticalFor(Fan fan); }
public sealed record FanHealthEntry(double Duty, int? Rpm, int? Expected, double? DeficitPct, string Status, int? Since);
    // Status: idle | ok | warn | critical | warn-pending | critical-pending | overridden
public sealed record FanHealthOutcome(IReadOnlyDictionary<int, string> Alerts, IReadOnlyList<Fan> NewlyCritical);
public sealed class FanHealthEvaluator
{ public IReadOnlySet<Fan> OverriddenFans { get; } public IReadOnlyList<Fan> BlockingCritical { get; }
  public IReadOnlyDictionary<Fan, FanHealthEntry> Health { get; } public IReadOnlyDictionary<int, string> Alerts { get; }
  public static double? ExpectedRpm(IReadOnlyList<(double duty, double rpm)>? points, double duty);
  public FanHealthEntry Evaluate(FanHealthRules rules, Fan fan, double duty, int? rpm, DateTimeOffset now);
  public FanHealthOutcome Finish(FanHealthRules rules, DateTimeOffset now);
  public void SetOverride(IEnumerable<Fan> fans, bool on);
  public IReadOnlyList<string> Acknowledge();
  public void SetFanStopped(IEnumerable<Fan> tested, IReadOnlyDictionary<Fan, string> stopped); }
public sealed record LedHeatingRules(double MinEvalIntensity, double CheckAfterSec, double MinRiseC, double RestSec, double DropC,
    double DropPersistSec, double DropSettleSec, IReadOnlyDictionary<LedPanel, TempSensor> Panels);
public sealed record LedHealthEntry(bool Lit, double Intensity, double? Baseline, double? Rise, double LitSec, string Status, double? Peak, double? Drop);
    // Status: off | low | warming | ok | fail | drop | no-sensor
public sealed record LedHeatingResult(IReadOnlyDictionary<LedPanel, LedHealthEntry> Health, IReadOnlyDictionary<int, string> Alerts);
public sealed class LedHeatingEvaluator
{ public static string Label(LedPanel p); public IReadOnlyDictionary<int, string> Alerts { get; }
  public LedHeatingResult Evaluate(LedHeatingRules rules, IReadOnlySet<LedPanel> lit, double intensity, double? chamber, Func<TempSensor, double?> readTemp, DateTimeOffset now); }
public sealed record UvLightRules(bool Enabled, double MinIntensity, double ConfirmSec, double LitRatio);
public sealed class UvLightEvaluator
{ public IReadOnlyDictionary<int, string> Alerts { get; } public double? Baseline(UvSensor sensor);
  public static bool? IsLit(double volts, double? baseline, double litRatio);
  public void Evaluate(UvLightRules rules, IReadOnlySet<LedPanel> lit, double intensity, Func<UvSensor, double?> readVolts, DateTimeOffset now);
  public static string Describe(UvSensor sensor, double litSec, double volts, double dark); }
```
**Behaviour & rules — fans:**
1. `CriticalFor(fan)` = per-fan override if present, else `CriticalBelowPct`.
2. `ExpectedRpm(points, duty)`: null if null/empty; sort by duty; `duty <= first.duty` -> `first.rpm * duty / first.duty` (proportional); between two points -> linear interpolation; above the last -> `last.rpm * duty / last.duty`.
3. `Evaluate(rules, fan, duty, rpm, now)` (call once per fan per tick, then `Finish`): if no duty seen or `|seenDuty - duty| > 0.5` -> remember (duty, now) (settle clock). `expected = duty > 0 ? ExpectedRpm(Nominal[fan], duty) : null`. Base entry `(duty, rpm, expected > 0 ? (int)expected : null, null, "idle", null)`. Judged only if `duty >= MinEvalDuty && expected > 0 && rpm != null && now - dutySeenAt >= SettleSec`; otherwise forget below-since and record "idle". `deficit = Math.Round((1 - rpm/expected) * 100, 1)`; `persist = rpm <= 0.05*expected ? StoppedPersistSec : PersistSec`; `level = deficit >= CriticalFor(fan) ? "critical" : deficit >= WarnBelowPct ? "warn" : "ok"`. ok -> forget below-since, record `(DeficitPct = deficit, Status "ok")`. Else below-since = existing (level0, since) or (level, now); if level0 was critical and level is warn -> since = now (a shallower deficit restarts the clock); store (level, since); `below = now - since`; status = below >= persist ? level : level + "-pending"; entry with DeficitPct, `Since = (int)below`. When `below >= persist`: detail = `$"{HardwareNames.Label(fan)}: {rpm} RPM measured, {(int)expected} RPM expected at {duty:0} % duty ({deficit:0} % below nominal for {(int)below} s)"`; overridden fan -> Status "overridden" (no action); critical -> critical detail stored, add to the critical latch set and, if new, to NewlyCritical; warn -> warn detail stored.
4. Record: store Health[fan]; if Status != "warn" drop the fan's warn detail; Rebuild: drop critical details of fans no longer latched; for family 9002 remove 9002 and all members then add `FanFailureOf(fan) -> detail` for every critical detail; same for 9051 with `FanWearOf` and warn details.
5. `Finish(rules, now)`: for each latched critical fan: if its Health status is "ok", start/keep ok-since and release the latch once `now - okSince >= PersistSec`; else forget ok-since. Rebuild; return `(copy of Alerts, NewlyCritical since last Finish)` and clear NewlyCritical. A latched fan that goes idle (because 9002 stopped every output) stays latched.
6. `BlockingCritical` = latched fans not overridden, ordered by name (ordinal) — they block every process start. `SetOverride(fans, on)`: on -> add to override set and remove from the latch; off -> remove override; Rebuild; on also clears all 9030-9034 alerts. Overridden fans are still reported (status "overridden") but never latch, alert or block.
7. `Acknowledge()` (operator deletes the alarm): release the latch of every latched fan whose Health status is not "critical" (idle or ok), also forgetting ok-since and below-since, adding `"{FanFailureOf(fan)} {fan}"` (e.g. `"9022 FAN_LEFT"`) to the result; remove all 9030-9034 alerts and if any was removed add `"903x"`; Rebuild; return the list. A fan driven and failing right now keeps its latch.
8. `SetFanStopped(tested, stopped)`: remove grouped 9003; for each tested fan: `alerts[FanStoppedOf(fan)] = detail` if in `stopped`, else remove that code. Untested fans keep their state (LED-fan and cooling-fan pre-flights run at different starts). (FAN_HEATER in `tested` throws.)
**Behaviour & rules — LED panels (9040-9045 not heating, 9042/9043 drop):**
9. `Label`: `"Left LED"`, `"Right LED"`, `"Back LED"`, default `"Door LED"`.
10. Per panel in `rules.Panels` (panel -> its thermistor), with a per-panel window {Base, LitSec, LitAt?, LastLit, Verdict?, FailAt, Peak?, PeakChamber?, IntSeen?, SettleUntil, DropSince?}: base entry `(isLit, isLit ? intensity : 0, null, null, 0, "off", null, null)`.
11. Lit and `intensity >= MinEvalIntensity`: `t = readTemp(sensor)`; not `ReadOk` -> status "no-sensor", window untouched, next panel. Window: if none, or (not lit last tick and `now - LastLit > RestSec`) -> new window {Base = temp, LitSec 0, LitAt now, LastLit now, FailAt = CheckAfterSec, SettleUntil = MinValue}; else if not lit last tick (re-lit within RestSec) -> keep Base and LitSec, LitAt = now, FailAt = LitSec + CheckAfterSec, Verdict/Peak/DropSince/IntSeen = null, SettleUntil = now; else LitSec += now - LitAt, LitAt = now. LastLit = now. `rise = temp - Base`; entry Baseline = round(Base,1), Rise = round(rise,2), LitSec = (int)LitSec. `dropped` = panel currently in the drop latch. If Verdict "ok" or rise >= MinRiseC -> status "ok", Verdict "ok", and if latched not-heating and rise >= MinRiseC release it. Else if LitSec >= FailAt and not dropped -> status "fail", Verdict "fail", latch not-heating with `$"{label}: +{rise:0.0} C after {(int)LitSec} s at {intensity:0} % (at least {MinRiseC:0.0} C expected) - check that the {label} connector is plugged in"`. Else "warming".
12. Drop tracking when Verdict "ok": first time IntSeen = intensity; a change `> 0.5` -> IntSeen = intensity, Peak = null, DropSince = null, SettleUntil = now + DropSettleSec. When `now >= SettleUntil`: if Peak null or temp > Peak -> Peak = temp, PeakChamber = chamber; `comp = max(0, PeakChamber - chamber)` when both known else 0; `drop = (Peak - temp) - comp`; entry Peak = round(Peak,1), Drop = round(drop,2). `drop >= DropC` -> DropSince ??= now; lasted >= DropPersistSec -> latch drop with `$"{label}: fell {drop:0.0} C below its {Peak:0.0} C peak while lit at {intensity:0} % (chamber cooling taken off) for {(int)lasted} s - the panel stopped heating mid-process, check the {label} connector and driver output"`. Else DropSince = null and, if it was dropped and `drop <= DropC/2`, release the drop latch. If drop-latched -> status "drop".
13. Not lit, or lit below MinEvalIntensity: if the window was lit (LitAt set) -> LastLit = LitAt, LitAt = null (only light seen between lit ticks counts). Status "low" if lit (too dim); then "fail" if not-heating latched; then "drop" if drop latched. Latches survive the panel going off.
14. Alerts: remove 9004 and its members, then add `LedNotHeatingOf(panel) -> detail` for latched panels in order LEFT, RIGHT, BACK, DOOR; same for 9005 with `LedTempDropOf` (throws for BACK/DOOR — only Left/Right are ever configured).
**Behaviour & rules — UV light (9046 / 9047, warning only, thresholds not yet calibrated on a unit):**
15. `IsLit(volts, baseline, ratio)` = null without baseline, else `volts <= baseline * ratio`.
16. `Evaluate`: disabled -> clear baselines, lit-since and alerts, return. For UV_LEFT then UV_RIGHT (panel = `sensor.Panel()`, code = `UvLightNotDetectedOf(panel)`, `v = readVolts(sensor)`, `usable = 0 < v < 3.3`): panel not lit -> forget lit-since, remove the alert, and if usable store v as dark baseline. Lit but `intensity < MinIntensity` -> forget lit-since, remove alert. Otherwise start lit-since if new; if v null or no baseline -> no judgement; if `IsLit == true` -> remove alert; else if `now - litSince >= ConfirmSec` and no alert yet -> `alerts[code] = Describe(sensor, litSec, v, dark)`. Back/Door panels have no photoresistor and are never judged. Nothing is stopped.
17. `Describe` = `$"{Left|Right} UV panel lit for {(int)litSec} s but its UV sensor ({sensor}) still reads dark: {volts:0.00} V (dark {dark:0.00} V)"`.
**Configuration:** components.json (mapped by Application `SupervisionService.ToRules`, re-read live):
- `fan_health`: `warn_below_pct` 10, `critical_below_pct` 20, `persist_sec` 60, `settle_sec` 5, `min_eval_duty` 30, `stopped_persist_sec` (absent in the file; Hardware default 5), `critical_below_pct_by_fan` {FAN_HEATER: 11.8}, `nominal_rpm` {FAN_HEATER {100:5925, 80:5227, 50:3669, 30:2363}, FAN_COOLING {100:4790, 60:2690, 30:1235}, FAN_LEFT/RIGHT/BACK/DOOR {100:3560, 30:1135}}; `nominal_rpm_damper_open` {FAN_COOLING {100:4075, 60:2470}} REPLACES the fan's table while the damper is open.
- `led_heating`: `enabled` false (no LED checks run unless enabled; the caller decides), `min_eval_intensity` 30, `check_after_sec` 90, `min_rise_c` 1.0, `rest_sec` 120, `drop_c` 1.0, `drop_persist_sec` 30, `drop_settle_sec` 120, `panels` {LED_LEFT: TEMP_LEFT, LED_RIGHT: TEMP_RIGHT} (never use the ORIGIN thermistors).
- `uv_light_check`: `enabled` true, `min_intensity` 10, `confirm_sec` 5, `lit_ratio` 0.6.
**Acceptance criteria (T0 = 2026-09-14 08:00Z; test rules `FanHealthRules(10, 20, 60, 5, 30, 5, {HEATER [(30,915),(50,1870),(80,2925),(100,3530)], COOLING [(30,1235),(60,2690),(100,4790)], LEFT [(100,3560)]})`):**
- ExpectedRpm(heater) 65 -> 2397.5, 100 -> 3530, 20 -> 610, 110 -> 3883; null/empty points -> null.
- Override {HEATER: 80}: CriticalFor(HEATER) 80, CriticalFor(LEFT) 20; heater at 1765 (50 % low) for 70 s -> "warn", left at 1780 -> "critical"; heater at 600 (83 % low) -> "critical".
- Duty 20 -> idle; duty 100 at t0 and t+4 -> idle (settle); t+5 -> "critical-pending".
- 3000 RPM (15 % low): "warn-pending" with DeficitPct 15.0 at 64 s, "warn" at 65 s; Finish alerts keys == [9060] with text containing "Heater fan (FAN_HEATER): 3000 RPM measured, 3530 RPM expected at 100 % duty"; no NewlyCritical.
- 2647 RPM (25 % low) to 65 s: NewlyCritical [HEATER], alerts [9020], BlockingCritical [HEATER]; next pass NewlyCritical empty, status "critical".
- LEFT 0 RPM 0..10 s latches (stopped persist 5 s after 5 s settle; "critical-pending" at 9 s, "critical" at 10 s); then duty 0 for 300 s keeps the latch (9022 present, 9002 absent); SetFanStopped([LEFT], {LEFT: ...}); Acknowledge returns ["9022 FAN_LEFT", "903x"], clears 9022 and 9030; driven again dead -> NewlyCritical [LEFT] at 310 s. Acknowledge while driven at 100 % and 0 RPM -> empty, latch kept.
- Latch released only after 60 s of ok (still latched through 125 s, released at 126 s, alerts empty).
- Override COOLING then 1000 RPM 70 s -> "overridden", nothing latched/alerted. Override of a latched heater clears 9020 and the 9030 alert.
- 2647 until 40 s then 3000 at 41 s -> "warn-pending", Since 0.
- Heater and left both 0 RPM: 9020 starts "Heater fan (FAN_HEATER): 0 RPM measured", 9022 starts "Left LED fan (FAN_LEFT): 0 RPM measured", 9020 text does not contain FAN_LEFT; left recovers -> 9022 released after 60 s ok, 9020 stays.
- LED (rules (30, 90, 1.0, 120, 1.0, 30, 120, {LEFT: TEMP_LEFT, RIGHT: TEMP_RIGHT})): off -> "off", Lit false, no alerts; intensity 20 -> "low"; left flat 30 °C, right rising 1.5 °C: at 89 s left "warming", right "ok", no alerts; at 90 s left "fail", LitSec 90, alert keys == [9040] text containing "Left LED: +0.0 C after 90 s at 50 % (at least 1.0 C expected) - check that the Left LED connector is plugged in"; off at 91 s still "fail"; lit at 32 °C at 92 s -> "ok", no alerts. Null reading -> "no-sensor". Rise to 33 by 21 s then 31.8 from 22..51 s: "ok", Drop 1.2, Peak 33.0; at 52 s "drop", 9042 contains "Left LED: fell 1.2 C below its 33.0 C peak", 9043 contains "Right LED: fell 1.2 C", 9042 does not contain "Right"; chamber 25 -> 23.8 at 53 s -> Drop 0.0 and alerts empty. Power change 50 -> 80 at 21 s -> Peak null; at 141 s Peak 31.0. Re-light within 120 s keeps Baseline 30.0 (Rise 1.5, "ok"); re-light after 400 s -> Baseline 40.0.
- UV (rules (true, 10, 5, 0.6)): dark pass sets baselines 2.79/2.83; 3.3 V at the rail is not a baseline; lit at 0.6/0.7 V -> no alerts, IsLit true; lit and dark: no alert after 4 s, both 9046 and 9047 at 5 s with exact texts "Left UV panel lit for 5 s but its UV sensor (UV_LEFT) still reads dark: 2.79 V (dark 2.80 V)" / "Right UV panel lit for 5 s but its UV sensor (UV_RIGHT) still reads dark: 2.80 V (dark 2.81 V)"; only the dark panel alerts; clears when light is seen or the panel goes off; intensity 9 never alerts; Back/Door lit never alert; no baseline or null volts -> no judgement; disabled -> no alerts and baselines forgotten, and disabling clears existing alerts.
**Tests:** `FanHealthEvaluatorTests` (Expected_rpm_interpolates_the_table, The_heater_fan_stops_the_machine_only_eighty_percent_low_other_fans_at_twenty, Expected_rpm_without_points_is_null, Idle_below_min_duty_and_during_settle, Warn_after_sixty_seconds_at_fifteen_percent_deficit, Critical_after_sixty_seconds_at_twenty_five_percent_blocks_and_latches, Acknowledge_releases_the_latch_of_a_fan_that_9002_left_idle, Acknowledge_keeps_the_latch_of_a_fan_failing_right_now, Latch_releases_only_after_persist_seconds_of_ok, Stopped_fan_trips_after_five_seconds, Override_reports_but_never_acts, Override_clears_an_existing_latch_and_the_led_fan_alert, A_shallower_deficit_restarts_the_clock, Every_critical_fan_has_its_own_code_and_a_released_one_clears); `LedHeatingEvaluatorTests` (Off_panels_report_off, Below_min_intensity_is_low_and_not_judged, No_rise_after_ninety_lit_seconds_fails_with_the_panel_code_9040, Open_thermistor_is_no_sensor, Drop_below_peak_for_thirty_seconds_raises_9042_9043_and_releases_near_the_peak, Power_change_settles_before_the_peak_is_tracked_again, Relight_within_rest_keeps_the_baseline); `UvLightEvaluatorTests` (Dark_readings_become_the_baseline, Lit_and_light_seen_raises_nothing, Lit_but_still_dark_after_confirm_sec_raises_9046_and_9047, Only_the_dark_panel_alerts, Clears_when_light_is_seen, Clears_when_the_panel_goes_off, Below_min_intensity_is_not_judged, Back_and_door_panels_have_no_photoresistor, No_dark_baseline_or_no_reading_means_no_judgement, Disabled_raises_nothing_and_forgets, Codes_and_panel_mapping, Left_and_right_panel_thermistors_are_the_supervised_left_right_sensors).
**Reference (source):** `src/SCureBox.Domain/Control/FanHealthEvaluator.cs`, `FanHealthRules.cs`, `FanHealthEntry.cs`, `FanHealthOutcome.cs`, `LedHeatingEvaluator.cs`, `LedHeatingRules.cs`, `LedHealthEntry.cs`, `LedHeatingResult.cs`, `UvLightEvaluator.cs`, `tests/SCureBox.Domain.Tests/Control/FanHealthEvaluatorTests.cs`, `LedHeatingEvaluatorTests.cs`, `UvLightEvaluatorTests.cs`; config mapping in `src/SCureBox.Application/Supervision/SupervisionService.cs` (`ToRules`)

---

### DOM-11 — RGB status-strip priority ladder and animation maths
**Project / folder:** `src/SCureBox.Domain/Control/` (`StripModeLadder.cs`, `StripInputs.cs`)
**Goal:** Decide which status the RGB LED strip shows (fault, door, warning, manual heat, busy, no internet, normal) from machine flags, and provide the pure colour maths for blinking, brightness scaling and the "comet" busy animation (port of StatusLeds._mode / _paint_chase). The Application status-LED service drives the strip with these.
**Depends on:** DOM-01.
**Files to create:** `Control/StripModeLadder.cs`, `Control/StripInputs.cs`.
**Public contract:**
```csharp
namespace SCureBox.Domain.Control;
public sealed record StripInputs(bool DriverFault, bool UiCritical, bool DoorAbortLatched, bool DoorOpen, bool UiWarning,
    bool ManualHeat, bool AnyProcess);
public static class StripModeLadder
{ public const string Fault = "fault"; public const string Door = "door"; public const string Warn = "warn"; public const string ManualHeat = "manual_heat";
  public const string Busy = "busy"; public const string Normal = "normal";
  public static string Mode(StripInputs i); public static bool BlinkOn(double unixSeconds, double blinkSec);
  public static int Scale(int color, double level);
  public static int[] CometFrame(int count, int offset, int tail, int color, bool rtl, double level); }
```
**Behaviour & rules:**
1. `Mode` priority (first match wins): DriverFault or UiCritical or DoorAbortLatched -> "fault"; DoorOpen -> "door"; UiWarning -> "warn"; ManualHeat -> "manual_heat"; AnyProcess -> "busy"; else "normal". OWNER DECISION 2026-11-05 (v1.0.153): the strip has NO internet marking - there is no no_net / busy_no_net mode and StripInputs has no internet field; an idle machine stays green with or without internet.
2. `BlinkOn(t, half)` = `(long)Math.Floor(t / half) % 2 == 0` (ON half first).
3. `Scale(color, level)`: clamp level to [0,1]; each 8-bit channel of 0xRRGGBB multiplied by level and truncated with `(int)` (like Python int()); recombine.
4. `CometFrame(count, offset, tail, color, rtl, level)`: count <= 0 -> empty array; tail = max(1, tail); level clamped [0,1]; head = rtl ? mod(count-1-offset, count) : mod(offset, count); for each LED i: d = rtl ? mod(i - head, count) : mod(head - i, count); value = d < tail ? Scale(color, level * (1 - d/tail)) : 0. `mod` is the non-negative modulo.
**Configuration:** components.json `rgb.status` (used by Application, not the domain): `blink_sec` 0.5 (blink half period), `chase_sec` 0.12, `chase_tail` 5, `busy_direction` "rtl", `busy_style` "solid", `brightness` 100, `count` 21 LEDs; colours normal green, fault red, door_open ff7800, busy blue
**Acceptance criteria:**
- Idle (all false) -> "normal"; process -> "busy"; + ManualHeat -> "manual_heat"; + UiWarning -> "warn"; UiWarning + DoorOpen -> "door"; DoorOpen + DoorAbortLatched -> "fault"; DoorOpen + UiCritical -> "fault"; AnyProcess + DriverFault -> "fault".
- `CometFrame(21, 0, 5, 0xAA00FF, rtl, 1.0)`: length 21, frame[20] = 0xAA00FF, frame[0] = Scale(c, 0.8), frame[3] = Scale(c, 0.2), frame[4] = 0, frame[19] = 0; with offset 1 the head is frame[19].
- `CometFrame(10, 3, 3, 0xFFFFFF, ltr, 0.5)`: frame[3] = 0x7F7F7F, frame[2] = Scale(0xFFFFFF, 0.5*(1-1/3)), frame[0] = 0, frame[4] = 0; count 0 -> empty.
- `Scale(0xFFB45A, 0.5) == 0x7F5A2D`; level 0 -> 0; level 2 -> clamped (0xFFFFFF stays).
- `BlinkOn(0.0,0.5)` true, `(0.49,0.5)` true, `(0.5,0.5)` false, `(1.0,0.5)` true.
**Tests:** `StripModeLadderTests` (Priorities_top_to_bottom, Comet_frame_rtl_head_and_tail, Comet_frame_ltr_and_brightness, Scale_truncates_each_channel, Blink_phase_from_wall_time).
**Reference (source):** `src/SCureBox.Domain/Control/StripModeLadder.cs`, `StripInputs.cs`, `tests/SCureBox.Domain.Tests/Control/StripModeLadderTests.cs`
