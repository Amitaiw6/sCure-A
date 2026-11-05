## Application: platform, persistence, reports — overview

This area is the "platform" half of `src/SCureBox.Application` (namespace roots `SCureBox.Application.Persistence`, `SCureBox.Application.Platform`, `SCureBox.Application.Reports`). It has no UI and no hardware drivers of its own; it gives the rest of the system:

* **Durable data** — a directory of JSON files (`DataOptions.DataDir`, env `SCURE_DATA_DIR`, default `<app>/data`) written power-cut-safe (tmp + fsync + rename), with an optional PostgreSQL backend (env `DATABASE_URL`) chosen once at boot and falling back to JSON when the database is not usable. Bundled read-only config lives in `DataOptions.ConfigDir` (default `<app>/config`: `presets.json`, `errors.json`, `system.json`, `origin.json`, `versions.json`, `components.json`).
* **Platform services** — external commands without a shell, power/clock/version/USB exports, network status/diagnostics/static IP, signed `.scu` software update (or the Origin supervisor on :8080), outbound-only cloud sync agent, component ON-hour counters, LED calibration factors, BOFA extractor setting, the serial-number backup on a removable card, USB NFC reader detection + Eccel Pepper C2 tag reading, developer event log.
* **Reports** — self-contained HTML cure report (inline SVG charts + timing diagram), HDT calibration report (HTML + CSV), and the save-to-store + export-to-USB helper.

Project: `src/SCureBox.Application/SCureBox.Application.csproj` (net10.0 via Directory.Build props; packages `Microsoft.Extensions.Hosting.Abstractions` 10.0.13, `Microsoft.Extensions.Logging.Abstractions` 10.0.13, `Microsoft.Extensions.DependencyInjection.Abstractions` 10.0.13, `Microsoft.Extensions.Options` 10.0.13, `Npgsql` 10.0.3; references `SCureBox.Domain`, `SCureBox.Hardware`; `InternalsVisibleTo SCureBox.Application.Tests`). Tests: `tests/SCureBox.Application.Tests` (xunit 2.9.3, Microsoft.Extensions.TimeProvider.Testing 10.11.0 `FakeTimeProvider`).

Cross-cutting rules for every ticket:
1. Every file write of durable state goes through `AtomicFile` (PLAT-01). Readers are tolerant: missing/corrupt file = defaults + a `LogWarning`, never an exception at boot.
2. External tools are run through `ProcessRunner` (PLAT-05): `ProcessStartInfo.ArgumentList`, never a shell, never throws.
3. Off-Linux (developer PC) every machine action (reboot, clock, nmcli, mount, install.sh) is **simulated** and returns success with a "simulated" message, so the UI is exercisable on Windows.
4. Error codes come from `SCureBox.Domain.Errors.ErrorCodes` (Domain area, mirror of `config/errors.json`). Codes used here: 3001 SerialRestoreFailed ("Serial Number Restore Failed", critical), 4003 SdBackupWriteFailed (warning), 9006 (frozen reading latch, raised by Process), 9052 NfcReaderNotDetected (warning), 9080 UnknownDiagnosticTool, 9081 NoUsbDrive ("No Disk-on-Key Connected"), 9082 UsbWriteFailed, 9083 LogExportFailed, 9084 NetworkError ("Network Status Unavailable"), 9085 DiagnosticFailed, 9086 UpdateFailed (critical), 9087 NoUpdatePackage. `OpResult(bool Ok, string Message, int? Code = null)` with `Success(msg)` / `Fail(msg, code?)` is a Domain record.
5. Log prefixes used: `[DATA]`, `[DB]`, `[BOOT]`, `[SYSTEM]`, `[NET]`, `[UPDATE]`, `[CLOUD]`, `[COUNTERS]`, `[LED-CAL]`, `[NFC]`, `[DEV]`, `[REPORT]`.
6. Not in this area (despite the area description): there is **no** Wi-Fi, licensing or NetBird-enrolment code in `SCureBox.Application`. NetBird appears only as "tunnel IP" detection (PLAT-09). Origin sign-in (`config/origin.json` consumer `OriginBrowserSignIn`), `system.json` consumer (`UiSettingsStore`) and `versions.json` consumer (`VersionsDialogViewModel`) live in **Native UI**; their file formats are documented in PLAT-16. NetBird enrolment is **Deploy-Ops** (`deploy/netbird-enroll.sh`).

Ticket list: PLAT-01 persistence foundation · PLAT-02 JSON data stores · PLAT-03 PostgreSQL backend + store selector · PLAT-04 restart markers & latches · PLAT-05 process runner & small platform utilities · PLAT-06 USB mounts + system service · PLAT-07 clock / network time + Origin supervisor client · PLAT-08 software update · PLAT-09 network service + network policy · PLAT-10 cloud sync agent · PLAT-11 component counters · PLAT-12 LED calibration, BOFA policy, serial backup · PLAT-13 NFC reader · PLAT-14 cure report builder + SVG · PLAT-15 HDT report + report persistence · PLAT-16 DI composition + shipped config files.

---

### PLAT-01 — Persistence foundation (data dir, atomic writes, JSON settings, base store)
**Summary**
- **What it is for:** The basic building blocks for saving data on the sCure Box: where data and config files live, and a safe way to write a file.
- **Problem it solves:** If power is cut during a save, a file can be left half-written and the machine may fail to start or lose data.
- **How we solve it:** Write to a temporary file, force it to disk, then swap it in. Readers treat a missing or broken file as default values and only log a warning.

**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Persistence/`
**Goal:** Provide the common plumbing every durable store uses: where data and bundled config live, a power-cut-safe file write, the shared `System.Text.Json` options, and an abstract one-file JSON store with a lock and a tolerant loader.
**Depends on:** none in this area. Domain (nothing beyond BCL).
**Files to create:**
- `Persistence/DataOptions.cs` — `DataOptions`
- `Persistence/DatabaseOptions.cs` — `DatabaseOptions`
- `Persistence/AtomicFile.cs` — `static class AtomicFile`
- `Persistence/JsonDefaults.cs` — `static class JsonDefaults`
- `Persistence/JsonFileStore.cs` — `abstract class JsonFileStore<T> where T : class`
**Public contract:**
```csharp
public sealed class DataOptions {
  public string DataDir { get; set; }   = Path.Combine(AppContext.BaseDirectory, "data");
  public string ConfigDir { get; set; } = Path.Combine(AppContext.BaseDirectory, "config");
  public string PresetsPath => Path.Combine(ConfigDir, "presets.json");
  public string ErrorsPath  => Path.Combine(ConfigDir, "errors.json");
  public string File(string name);      // Directory.CreateDirectory(DataDir) then Path.Combine(DataDir, name)
}
public sealed class DatabaseOptions {
  public string? ConnectionString { get; set; }   // DATABASE_URL form or Npgsql key=value; null/empty = JSON only
  public string? SchemaDir { get; set; }          // dir with schema.sql + seed_presets.sql; null = probe (PLAT-03)
  public bool IsConfigured => !string.IsNullOrWhiteSpace(ConnectionString);
}
public static class AtomicFile {
  public static void WriteAllText(string path, string content);           // UTF-8 WITHOUT BOM
  public static void WriteAllBytes(string path, ReadOnlySpan<byte> content);
}
public static class JsonDefaults {
  public static readonly JsonSerializerOptions Options;   // Encoder=JavaScriptEncoder.UnsafeRelaxedJsonEscaping, PropertyNameCaseInsensitive=true, ReadCommentHandling=Skip, AllowTrailingCommas=true
  public static readonly JsonSerializerOptions Indented;  // new(Options){ WriteIndented = true }
}
public abstract class JsonFileStore<T> where T : class {
  protected JsonFileStore(string path, ILogger? logger);
  protected object Sync { get; }
  protected string FilePath { get; }
  protected ILogger? Logger { get; }
  protected T Load(Func<T> fallback);
  protected void Save(T value, bool indented = false);
}
```
**Behaviour & rules:**
1. `AtomicFile.WriteAllBytes`: create parent dir if non-empty; write to `<path>.tmp` with `FileMode.Create, FileShare.None`; `Flush(flushToDisk: true)`; then `File.Move(tmp, path, overwrite: true)`. An existing target is never half-written; no `.tmp` file remains on success.
2. Property names are attribute-driven (`[JsonPropertyName]` on models, camelCase); no naming policy is set in `JsonDefaults`.
3. `JsonFileStore.Load`: file missing → `fallback()`; deserialize with `JsonDefaults.Options`; null result → fallback; `IOException`/`JsonException`/`UnauthorizedAccessException` → `LogWarning("[DATA] read failed ({File}): {Error}")` and fallback.
4. `JsonFileStore.Save`: `AtomicFile.WriteAllText(FilePath, JsonSerializer.Serialize(value, indented ? Indented : Options))`. Caller holds `Sync` when value is shared.
5. Host maps env vars: `SCURE_DATA_DIR` → `DataDir`, `DATABASE_URL` → `DatabaseOptions.ConnectionString` (done in Api `HostSettings`, see Api area).
**Configuration:** `SCURE_DATA_DIR`, `DATABASE_URL` (resolved by the host, not here).
**Acceptance criteria:**
- Writing twice to the same path replaces content; `<path>.tmp` does not exist afterwards.
- Written text starts with no UTF-8 BOM (first bytes are the content).
- A store over a corrupt file returns the fallback and does not throw.
**Tests:** `Persistence/AtomicFileTests` (`Write_replaces_the_target_and_leaves_no_tmp_file`, `Writes_utf8_without_bom`). Test helper `Persistence/TempDataDir` (temp dir under `%TEMP%/scurebox-tests/<guid>`, `Options = new DataOptions{ DataDir = Path, ConfigDir = <repo>/config }`, deleted on Dispose; finds repo `config/` above the caller source file or the test output dir).
**Reference (source):** `src/SCureBox.Application/Persistence/{DataOptions,DatabaseOptions,AtomicFile,JsonDefaults,JsonFileStore}.cs`, `tests/SCureBox.Application.Tests/Persistence/{AtomicFileTests,TempDataDir}.cs`

---

### PLAT-02 — JSON data stores (materials, print history, cure runs + telemetry + reports, phase timings)
**Summary**
- **What it is for:** The default data storage in plain JSON files: cure programs, print history, cure runs with their sensor data and reports, and measured phase times.
- **Problem it solves:** Without it the machine cannot remember programs, show history or reports, or improve its time estimates.
- **How we solve it:** One file per data type. Keep only the newest 25 runs, save sensor data every 15 samples, and mark runs cut off by a power loss as errors.

**Project / folder:** `SCureBox.Application.csproj` — `Persistence/`, interfaces in `Contracts/IStores.cs`
**Goal:** The default (no-database) implementation of the four data stores the process engine, API and UI use: bundled preset programs + user programs, print history, cure runs with telemetry and saved reports (keeping only the newest 25), and the append-only measured phase timings that feed the program estimate model.
**Depends on:** PLAT-01. Domain (`Material`, `CureStep`, `PrintLog`, `CureLog`, `TelemetrySample`, `CureRunStart`, `CureRunFinish`, `CureReport`, `SensorIssue`, `FanIssue`, `RunAlert`, `PhaseTiming`).
**Files to create:**
- `Contracts/IStores.cs` — `IMaterialStore`, `IPrintHistoryStore`, `ICureRunStore`, `IPhaseTimingStore`, `static class CureHistoryRetention`
- `Persistence/JsonMaterialStore.cs`, `Persistence/JsonPrintHistoryStore.cs`, `Persistence/JsonCureRunStore.cs`, `Persistence/JsonPhaseTimingStore.cs`
**Public contract:**
```csharp
public interface IMaterialStore {
  IReadOnlyList<Material> GetPresets();
  IReadOnlyList<Material> GetUserMaterials();
  void ReplaceUserMaterials(IReadOnlyList<Material> materials);
  Material? Find(string id);
}
public interface IPrintHistoryStore { IReadOnlyList<PrintLog> GetAll(); void ReplaceAll(IReadOnlyList<PrintLog> prints); }
public interface ICureRunStore {   // keyed by UI-supplied external id (UUID or "qa-test-run")
  IReadOnlyList<CureLog> GetHistory();
  void Start(string extId, CureRunStart start);                       // idempotent per ext id
  bool AddTelemetry(string extId, TelemetrySample sample);            // false = unknown id
  bool Finish(string extId, CureRunFinish finish, IReadOnlyList<SensorIssue> sensorIssues, IReadOnlyList<FanIssue> fanIssues);
  string SaveReport(string extId, CureReport report);
  CureReport? GetReport(string extId);
  bool Delete(string extId);                                          // false = unknown or still running
  IReadOnlyList<string> DeleteAll();                                  // every finished run; returns ids removed
  void Flush();
}
public static class CureHistoryRetention { public const int KeepRuns = 25; }
public interface IPhaseTimingStore { IReadOnlyList<PhaseTiming> GetAll(); int Append(PhaseTiming timing); }

public sealed class JsonMaterialStore : JsonFileStore<List<Material>>, IMaterialStore { public JsonMaterialStore(DataOptions options, ILogger<JsonMaterialStore>? logger = null); }
public sealed class JsonPrintHistoryStore : JsonFileStore<List<PrintLog>>, IPrintHistoryStore { public JsonPrintHistoryStore(DataOptions options, ILogger<JsonPrintHistoryStore>? logger = null); }
public sealed class JsonCureRunStore : JsonFileStore<List<CureLog>>, ICureRunStore {
  public const int TelemetryFlushEvery = 15;
  public JsonCureRunStore(DataOptions options, TimeProvider? time = null, ILogger<JsonCureRunStore>? logger = null);
}
public sealed class JsonPhaseTimingStore : JsonFileStore<List<PhaseTiming>>, IPhaseTimingStore { public JsonPhaseTimingStore(DataOptions options, ILogger<JsonPhaseTimingStore>? logger = null); }
```
On-disk files (all in `DataDir`):
| file | content |
|---|---|
| `user_materials.json` | `Material[]` (indented) — user programs |
| `print_history.json` | `PrintLog[]` |
| `cure_history.json` | `CureLog[]` newest first, each with its `telemetry[]` |
| `cure_reports.json` | `{ "<extId>": CureReport{content, summary, format} }` |
| `phase_timings.json` | `PhaseTiming[]` newest last |
Presets: `ConfigDir/presets.json` (`Material[]`), read-only.
**Behaviour & rules:**
1. Materials: presets load lazily (`Lazy<>`) from `PresetsPath`; every preset is returned with `IsPreset = true`. Missing file → `LogWarning("[DATA] presets file missing: {Path}")` and empty list; unreadable → warning + empty. User programs = `user_materials.json`, replaced as a whole (`ReplaceUserMaterials` saves indented). `Find(id)`: presets first, then user materials. Preset JSON keeps its wire shape (round-trips the `steps` fields as read).
2. Print history: `ReplaceAll` replaces and saves the whole list; `GetAll` returns a copy.
3. Cure runs — constructor: load `cure_history.json` (fallback empty), load `cure_reports.json` (own tolerant loader; warning `"[DATA] read failed (cure_reports.json)"`). Every run whose `Status == "running"` is rewritten to `"error"` (a power-cut run can never finish). Then `Trim()`. If anything changed, save the history.
4. `Start(extId, start)`: if the id is not present, insert at index 0 a `CureLog{ Id=extId, MaterialName, Steps, StepsCompleted=0, StartedAt=local now "yyyy-MM-ddTHH:mm:ss" (invariant), EndedAt=null, Duration=null, Status="running", Phases, TargetTemp, SerialNumber, Telemetry=new list }` then `Trim()`. Always save (idempotent: a second Start with same id does not add a row).
5. `Trim()`: keep the first `KeepRuns` (25) runs; for removed runs drop their in-memory telemetry and their entries in `cure_reports.json` (rewritten only if one was removed).
6. `AddTelemetry`: unknown id → false. Append sample; increment an unflushed counter; when it reaches `TelemetryFlushEvery` (15) save history and reset counter. (Power cut loses ≤ last few samples, never the run.)
7. `Finish`: unknown → false. `duration = floor((localNow - parse(StartedAt, "yyyy-MM-ddTHH:mm:ss")).TotalSeconds)` (keep previous if unparsable); set `Status=finish.Status`, `EndedAt=stamp(now)`, `StepsCompleted = finish.StepsCompleted ?? previous`, `SensorIssues`, `FanIssues`, `Alerts = finish.Alerts ?? previous`, `Duration`. Save, reset unflushed counter.
8. `SaveReport(extId, report)`: store under `extId` (no check that the run exists), rewrite `cure_reports.json`, return `extId`. `GetReport` returns it or null.
9. `Delete(extId)`: false if unknown or `Status=="running"`; else remove run + telemetry + report, save. `DeleteAll()`: remove every non-running run, return their ids.
10. `Flush()`: save history now. `GetHistory()` returns deep-ish copies (telemetry list copied).
11. Phase timings: `Append` adds at end, saves, returns new count.
12. All public methods lock `Sync`.
**Configuration:** `ConfigDir/presets.json`.
**Acceptance criteria:**
- Start twice with the same id → 1 run; new runs appear first.
- After 26 starts only 25 runs remain; the oldest's report is gone from `cure_reports.json`.
- 14 telemetry samples do not rewrite the file, the 15th does; `Flush()` writes immediately.
- Reloading a file that has a `running` run yields `error`.
- `Finish` with `StepsCompleted=null` keeps the previous value; duration computed in whole seconds.
- A running run is never deleted by `Delete`/`DeleteAll`.
- Corrupt `cure_history.json` → empty history, no exception.
**Tests:** `Persistence/JsonCureRunStoreTests` (Start_is_idempotent_and_inserts_newest_first, Delete_removes_a_finished_run_with_its_report_but_never_a_running_one, History_keeps_the_newest_25_runs, Telemetry_flushes_every_15_samples_and_on_flush, Finish_computes_duration_and_records_issues, Finish_without_steps_completed_keeps_the_previous_value, Runs_left_running_become_error_on_reload, Report_round_trip, Corrupt_history_file_starts_empty) with `FakeTimeProvider`; `JsonMaterialStoreTests` (Presets_come_from_config_presets_json, User_materials_are_replaced_as_a_whole_and_persist, Missing_presets_file_gives_an_empty_list, Preset_json_keeps_the_wire_shape); `JsonPrintHistoryStoreTests` (Replace_all_persists_and_reloads); `JsonPhaseTimingStoreTests` (Append_returns_the_count_and_keeps_order).
**Reference (source):** `src/SCureBox.Application/Contracts/IStores.cs`, `src/SCureBox.Application/Persistence/Json{Material,PrintHistory,CureRun,PhaseTiming}Store.cs`, `src/SCureBox.Domain/Models/History.cs`, `tests/SCureBox.Application.Tests/Persistence/*`

---

### PLAT-03 — PostgreSQL backend, schema and sticky store selector
**Summary**
- **What it is for:** An optional PostgreSQL database that can store the same data as the JSON files.
- **Problem it solves:** Some setups want the data in a real database, but the machine must still work if the database is missing or down.
- **How we solve it:** At startup, use the database only if it is set up and reachable, create its tables if needed, and otherwise use the JSON files. The choice does not change until restart.

**Project / folder:** `SCureBox.Application.csproj` — `Persistence/`; schema `deploy/db/schema.sql`, `deploy/db/seed_presets.sql`
**Goal:** Optional relational backend (port of the Python `db.py`) implementing the same three store interfaces over a normalized ER schema with convenience views that return the UI's JSON shapes. A selector picks Postgres once at startup when configured AND reachable, else JSON — never retried during the process lifetime.
**Depends on:** PLAT-01, PLAT-02. Deploy-Ops (ships `deploy/db/*.sql` beside the app).
**Files to create:**
- `Persistence/PostgresDb.cs` — `PostgresDb : IDisposable`
- `Persistence/IDatabaseInitializer.cs`, `Persistence/PostgresDatabaseInitializer.cs`
- `Persistence/PostgresMaterialStore.cs`, `Persistence/PostgresPrintHistoryStore.cs`, `Persistence/PostgresCureRunStore.cs`
- `Persistence/StoreSelector.cs`
- `deploy/db/schema.sql`, `deploy/db/seed_presets.sql`
**Public contract:**
```csharp
public sealed class PostgresDb : IDisposable {
  public PostgresDb(string connectionString);             // NpgsqlDataSource.Create(Normalize(cs))
  public NpgsqlDataSource DataSource { get; }
  public NpgsqlConnection Open();
  public static string Normalize(string connectionString);
  public static NpgsqlParameter Json<T>(T value); JsonOrNull<T>(T? value) where T: class; Text(string?); Int(int?); Numeric(double?); Bool(bool?); Timestamp(DateTime?); TextArray(IEnumerable<string>);
  public static string? GetString(NpgsqlDataReader r, string column); int? GetInt(..); double? GetDouble(..); bool GetBool(..);
  public static string? GetLocalStamp(..);   // timestamptz -> local "yyyy-MM-ddTHH:mm:ss"
  public static string? GetIsoStamp(..);     // timestamptz -> UTC ToString("O")
  public static T? GetJson<T>(..) where T: class;   // JsonException -> null
  public static DateTime? ParseStamp(string? s);    // trailing 'Z' -> "+00:00"; AssumeLocal; -> UtcDateTime; null if unparsable
}
public interface IDatabaseInitializer { bool TryInitialize(out string? error); }
public sealed class PostgresDatabaseInitializer : IDatabaseInitializer { public PostgresDatabaseInitializer(PostgresDb db, DatabaseOptions options, ILogger<PostgresDatabaseInitializer>? logger = null); }
public sealed class PostgresMaterialStore : IMaterialStore { public PostgresMaterialStore(PostgresDb db); }
public sealed class PostgresPrintHistoryStore : IPrintHistoryStore { public PostgresPrintHistoryStore(PostgresDb db);
  internal static Guid? UpsertPrinter(NpgsqlConnection, NpgsqlTransaction, string? serial);
  internal static Guid FindOrCreateMaterial(NpgsqlConnection, NpgsqlTransaction, string name); }
public sealed class PostgresCureRunStore : ICureRunStore { public PostgresCureRunStore(PostgresDb db); }
public sealed class StoreSelector : IDisposable {
  public StoreSelector(DataOptions data, DatabaseOptions database, TimeProvider? time = null, ILoggerFactory? loggers = null);
  public bool UsingPostgres { get; }
  public IMaterialStore Materials { get; } public IPrintHistoryStore Prints { get; } public ICureRunStore CureRuns { get; }
}
```
Schema (`schema.sql`, idempotent: `CREATE EXTENSION IF NOT EXISTS pgcrypto`, `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE .. ADD COLUMN IF NOT EXISTS`, `CREATE OR REPLACE VIEW`; all ids `UUID PRIMARY KEY DEFAULT gen_random_uuid()`):
- `resins(id, name TEXT NOT NULL, supplier, lot_number, created_at TIMESTAMPTZ NOT NULL DEFAULT now())`
- `materials(id, ext_id TEXT UNIQUE, resin_id→resins ON DELETE SET NULL, name TEXT NOT NULL, version, is_preset BOOLEAN NOT NULL DEFAULT FALSE, created_at)`
- `cure_profiles(id, cure_unit_id UUID, resin_id→resins SET NULL, material_id→materials ON DELETE CASCADE, parameters JSONB NOT NULL DEFAULT '{}', created_at)`; indexes `ix_cure_profiles_material`, `ix_cure_profiles_resin`
- `printers(id, serial_number TEXT UNIQUE, model, status)`; `jobs(id, material_id→materials SET NULL, print_spec_id UUID, created_at)`
- `prints(id, ext_id TEXT UNIQUE, job_id→jobs SET NULL, printer_id→printers SET NULL, name, start_time, end_time, status)`; `ix_prints_printer`, `ix_prints_start(start_time DESC)`
- `build_heads(id, serial_number UNIQUE, hw_revision, status)`, `tray_membranes(id, serial_number UNIQUE, membrane_type, max_slices INTEGER, status)`, `print_hardware(print_id PK→prints CASCADE, build_head_id SET NULL, tray_membrane_id SET NULL, bound_at)`
- `cure_boxes(id, serial_number UNIQUE, model, status)`, `cure_sessions(id, cure_box_id SET NULL, started_at, ended_at, status)`
- `cure_runs(id, ext_id TEXT UNIQUE, print_id, build_head_id, cure_box_id, cure_session_id, curing_profile_id (all SET NULL), steps INTEGER, steps_completed INTEGER, target_temp NUMERIC, phases JSONB, started_at, ended_at, status TEXT NOT NULL DEFAULT 'running')` + `sensor_issues JSONB NOT NULL DEFAULT '[]'`, `fan_issues JSONB NOT NULL DEFAULT '[]'`, `run_alerts JSONB NOT NULL DEFAULT '[]'`; indexes `ix_cure_runs_print`, `ix_cure_runs_session`, `ix_cure_runs_started(started_at DESC)`
- `cure_run_telemetry(id BIGSERIAL PK, cure_run_id→cure_runs ON DELETE CASCADE NOT NULL, t INTEGER NOT NULL, chamber_temp NUMERIC, uv_on BOOLEAN, uv_type TEXT, led_right, led_left, led_door, led_back NUMERIC, recorded_at DEFAULT now())` + `fan_rpm JSONB`; `ix_telemetry_run(cure_run_id, t)`
- `cure_reports(id, cure_run_id→cure_runs CASCADE NOT NULL, format TEXT NOT NULL DEFAULT 'html', content TEXT, summary JSONB, generated_at DEFAULT now())`; `ix_reports_run`
- Views: `v_materials(id = COALESCE(ext_id,id::text), name, "isPreset", "createdAt", steps = COALESCE(cp.parameters->'steps','[]'), "totalDuration" = COALESCE((parameters->>'totalDuration')::int,0))` LEFT JOIN cure_profiles on material_id, ORDER BY is_preset DESC, created_at. `v_print_history(id, "printName"=COALESCE(p.name,'Print'), "materialName" (via jobs→materials), "printerName"=printers.serial_number, date=COALESCE(p.start_time, cr.started_at), duration=EPOCH(end-start) of print else of cure run, status=COALESCE(cr.status,p.status), steps=cr.steps, "csvFile"=cp.parameters->>'csvFile')` ORDER BY date DESC. `v_cure_history(id, "materialName", steps, "stepsCompleted", "startedAt", "endedAt", duration=EPOCH(ended-started)::int, status, phases, "targetTemp", "sensorIssues", "fanIssues", "serialNumber"=cure_boxes.serial_number, telemetry = jsonb_agg({t, chamberTemp, uvOn, uvType, ledTemps:{right,left,door,back}, fanRpm} ORDER BY t) or '[]', alerts=run_alerts)` ORDER BY started_at DESC.
- `seed_presets.sql`: per preset `WITH ins AS (INSERT INTO materials (ext_id, name, is_preset) VALUES ('preset-<Name>', '<Name>', TRUE) ON CONFLICT (ext_id) DO NOTHING RETURNING id) INSERT INTO cure_profiles (material_id, parameters) SELECT id, '<{"steps":[...],"totalDuration":N,"isPreset":true}>'::jsonb FROM ins;` (generated from presets.json; e.g. `preset-ST45` totalDuration 79).
**Behaviour & rules:**
1. `Normalize`: if the string does not start with `postgres://`/`postgresql://` (case-insensitive) parse as key=value with `NpgsqlConnectionStringBuilder`, and if `Timeout == 15` (default) set it to 5. URL form: Host, Port (5432 when default), Database = path trimmed of '/', Timeout=5, Username/Password from userinfo (URL-unescaped, split on first ':'), query `sslmode=X` → `"SSL Mode"`.
2. `TryInitialize`: open a connection; resolve schema dir = `options.SchemaDir` if set, else first existing of `<app>/db`, `<app>/deploy/db`, then `<dir>/deploy/db` walking up from `AppContext.BaseDirectory` (must contain `schema.sql`). None → `LogWarning("[DB] schema.sql not found - using the database as-is")` and still succeed. Execute `schema.sql` then `seed_presets.sql` (each only if it exists; `CommandTimeout = 60`). Catch `NpgsqlException, IOException, InvalidOperationException, TimeoutException, ArgumentException` → false + message. Never throws.
3. `StoreSelector`: if `database.IsConfigured`: construct `PostgresDb`, run initializer; success → Postgres stores, `UsingPostgres = true`, log `"[DB] data store: POSTGRES (schema ensured)"`. Failure → `"[DB] Postgres unavailable ({Error}) - falling back to JSON files"`, dispose. `ArgumentException/FormatException/UriFormatException` from a bad string → `"[DB] bad connection string"` warning. Otherwise JSON stores (PLAT-02). Decision is sticky; `Dispose()` disposes the data source.
4. `PostgresMaterialStore`: presets = `SELECT * FROM v_materials WHERE "isPreset"`, user = `NOT "isPreset"`, Find = `WHERE id = $1`. Row → `Material{Id, Name, IsPreset, CreatedAt=GetIsoStamp, Steps=GetJson<List<CureStep>> ?? [], TotalDuration ?? 0}`. `ReplaceUserMaterials` in one transaction: per material `INSERT INTO materials(ext_id,name,is_preset) VALUES($1,$2,FALSE) ON CONFLICT(ext_id) DO UPDATE SET name=EXCLUDED.name RETURNING id` (empty name → "Untitled"); `DELETE FROM cure_profiles WHERE material_id=$1`; insert profile `parameters = {steps, totalDuration, isPreset:false}`; then prune `DELETE FROM materials WHERE is_preset=FALSE AND ext_id IS NOT NULL AND NOT (ext_id = ANY($1))` (or all user materials when the list is empty). Presets untouched.
5. `PostgresPrintHistoryStore.GetAll`: from `v_print_history`; defaults printName "Print", status "completed", date via `GetLocalStamp`. `ReplaceAll` (transaction): per log → `UpsertPrinter(serial)` (`INSERT .. ON CONFLICT(serial_number) DO UPDATE .. RETURNING id`, null when empty), `FindOrCreateMaterial(name)` (`SELECT id FROM materials WHERE name=$1 ORDER BY is_preset DESC LIMIT 1`, else insert), start=`ParseStamp(Date)`, end=start+floor(Duration) s; upsert `prints` by ext_id returning `id, job_id`; if no job and a material: insert `jobs(material_id)` and link; upsert `cure_runs(ext_id=log.Id, print_id, steps, started_at, ended_at, status)`. Then prune `cure_runs` and `prints` rows whose ext_id not in the list. NOTE: `PrintLog.NfcTag` is not persisted in Postgres (OPEN QUESTION: intended?).
6. `PostgresCureRunStore`: `GetHistory` from `v_cure_history` (status default "running"). `Start` (transaction): upsert `cure_boxes(serial_number)` when serial given; `FindOrCreateMaterial(MaterialName)` when given (linkage is via the print, so not stored on the run); `INSERT INTO cure_runs (ext_id, cure_box_id, steps, steps_completed=0, target_temp, phases, started_at=now(), status='running') ON CONFLICT(ext_id) DO UPDATE ...status='running'`; then trim `DELETE FROM cure_runs WHERE id IN (SELECT id FROM cure_runs ORDER BY started_at DESC NULLS LAST OFFSET 25)` (telemetry/reports cascade). `AddTelemetry`: run id lookup (false when unknown); insert telemetry row with `t = round(sample.T)`, led temps from `LedTemps["right"/"left"/"door"/"back"]`, `fan_rpm` jsonb or null. Only these columns are stored (timing-diagram fields are lost in Postgres). `Finish`: `UPDATE cure_runs SET status, ended_at=now(), steps_completed=COALESCE($2,steps_completed), sensor_issues, fan_issues, run_alerts=COALESCE($6,run_alerts) WHERE ext_id=$5`; true when a row changed. `SaveReport`: create a minimal run (`status 'completed'`) when the id is unknown; insert `cure_reports(cure_run_id, format, content, summary)` (summary raw JSON or NULL when undefined/null); returns the **report row UUID** (differs from JSON store which returns extId). `GetReport`: newest by `generated_at`; format default "html", content default "". `Delete`: `DELETE ... WHERE ext_id=$1 AND status <> 'running'`. `DeleteAll`: `DELETE ... WHERE status <> 'running' RETURNING ext_id`. `Flush`: no-op.
**Configuration:** `DatabaseOptions.ConnectionString` (env `DATABASE_URL`), `DatabaseOptions.SchemaDir`.
**Acceptance criteria:**
- `Normalize("postgresql://u:p%40ss@h:6543/db?sslmode=require")` yields Host=h, Port=6543, Database=db, Username=u, Password=p@ss, SSL Mode=Require, Timeout=5; key=value strings get Timeout 5 unless one was set.
- An unreachable database leaves `UsingPostgres == false` and JSON stores in use, without throwing.
- Against a real server (only when `SCURE_TEST_DATABASE_URL` is set): start/telemetry/finish/report/history round-trip; re-running schema.sql is harmless.
**Tests:** `Persistence/PostgresSmokeTests` (Connection_string_normalisation_accepts_urls_and_key_values, Unreachable_database_falls_back_to_json_stores, Round_trip_against_a_real_server_when_configured — skipped unless env `SCURE_TEST_DATABASE_URL`).
**Reference (source):** `src/SCureBox.Application/Persistence/{PostgresDb,IDatabaseInitializer,PostgresDatabaseInitializer,PostgresMaterialStore,PostgresPrintHistoryStore,PostgresCureRunStore,StoreSelector}.cs`, `deploy/db/schema.sql`, `deploy/db/seed_presets.sql`

---

### PLAT-04 — Restart markers and safety latches on disk (planned restart, heater run-on, frozen reading)
**Summary**
- **What it is for:** Three tiny files that remember important state across a restart: planned restart, remaining heater-fan cooling time, and a frozen temperature reading lock.
- **Problem it solves:** After a restart the machine would forget it should boot quickly, stop cooling too early, or allow a heater that was refused for safety.
- **How we solve it:** Write a small marker file before the restart and read it once at the next start; old markers are ignored and deleted.

**Project / folder:** `SCureBox.Application.csproj` — `Persistence/`
**Goal:** Three tiny files that carry state across a firmware stop/start: "this restart was planned" (quick boot, skip self-tests), "the heater fan run-on still has N seconds to go" (resume cooling after a restart), and the Err 9006 frozen-reading latch (a restart must not re-allow a refused heater).
**Depends on:** PLAT-01. Consumers: Application-Process (registers `FrozenReadingStore`, `PlannedRestart` in `ProcessServiceCollectionExtensions`), Api (`HeaterRunOnMarker` in `ScureApiHost`).
**Files to create:** `Persistence/PlannedRestart.cs` — `PlannedRestart`; `Persistence/HeaterRunOnMarker.cs` — `HeaterRunOnMarker`; `Persistence/FrozenReadingStore.cs` — `FrozenReadingRecord`, `FrozenReadingStore`
**Public contract:**
```csharp
public sealed class PlannedRestart {
  public const string FileName = "planned_restart";
  public static readonly TimeSpan MaxAge = TimeSpan.FromMinutes(10);
  public PlannedRestart(DataOptions options, TimeProvider? time = null, ILogger<PlannedRestart>? log = null);
  public PlannedRestart(string path, TimeProvider? time = null, ILogger? log = null);
  public void Mark(string reason);
  public bool Consume();
}
public sealed class HeaterRunOnMarker {
  public const string FileName = "heater_runon";
  public HeaterRunOnMarker(DataOptions options, TimeProvider? time = null, ILogger<HeaterRunOnMarker>? log = null);
  public HeaterRunOnMarker(string path, TimeProvider? time = null, ILogger? log = null);
  public void Save(double seconds);
  public double? Take();
}
public sealed record FrozenReadingRecord(
  [property: JsonPropertyName("frozenAtC")] double FrozenAtC,
  [property: JsonPropertyName("detail")] string Detail,
  [property: JsonPropertyName("since")] DateTimeOffset Since);
public sealed class FrozenReadingStore : JsonFileStore<FrozenReadingRecord> {
  public const string FileName = "frozen_reading.json";
  public FrozenReadingStore(DataOptions options, ILogger<FrozenReadingStore>? logger = null);
  public FrozenReadingStore(string path, ILogger? logger = null);
  public FrozenReadingRecord? Read(); public void Write(FrozenReadingRecord record); public void Clear();
}
```
**Behaviour & rules:**
1. `PlannedRestart.Mark(reason)`: atomically write `"<utcNow:O> <reason>\n"`; IO errors only logged.
2. `Consume()`: no file → false. Read and **delete** the file (always). Stamp = text before first space, parsed RoundtripKind; unparsable → false. Fresh = `0 <= age <= 10 min` → true. Log `"[BOOT] planned-restart marker {Age:0} s old ({Reason}) - quick boot|stale, full self-test"`. Meaning (consumer): planned restart skips the LED + fan self-tests at boot; no/stale marker = cold start = full self-test.
3. `HeaterRunOnMarker.Save(seconds)`: `seconds <= 0` → nothing; else write `(utcNow + seconds).ToString("O") + "\n"`. Context: after every heating the heater fan runs at its cooldown duty for `heating.cooldown_sec` (900 s); a restart resumes the remainder.
4. `Take()`: no file → null; read, delete, parse; remaining = until - now; return remaining if > 0 else null.
5. `FrozenReadingStore`: `Read()` returns null when absent (else tolerant `Load`); `Write` saves indented; `Clear` deletes (errors logged). The latch is cleared by Process when the reading moves away from `FrozenAtC` or goes open (Application-Process area).
**Configuration:** none (files in `DataDir`).
**Acceptance criteria:**
- Mark then Consume within 10 min → true once, second Consume → false; marker older than 10 min → false; file gone either way.
- Save(120) then Take after 30 s (fake clock) → ≈90; Take again → null; Save(0) writes nothing.
- Frozen record round-trips with `frozenAtC`, `detail`, `since` property names.
**Tests:** `Persistence/HeaterRunOnMarkerTests` (The_run_on_left_at_a_stop_is_handed_to_the_next_start_once). OPEN QUESTION: no dedicated tests in this project for `PlannedRestart`/`FrozenReadingStore` (they may be covered in Process tests) — add the acceptance tests above.
**Reference (source):** `src/SCureBox.Application/Persistence/{PlannedRestart,HeaterRunOnMarker,FrozenReadingStore}.cs`

---

### PLAT-05 — Process runner and small platform utilities (platform info, eMMC identity, dev event log)
**Summary**
- **What it is for:** Shared helpers: running outside programs safely, knowing the operating system, reading the unit's fixed storage serial number, and a developer event log.
- **Problem it solves:** Outside programs can hang or crash the app, and the unit needs a stable ID and a simple debug log.
- **How we solve it:** Run programs without a shell, with a time limit, never throwing errors. Read the serial from the built-in storage only, and append events as one line each.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Safe execution of external tools (no shell, timeouts, never throws), OS detection, reading the unit's immutable eMMC serial, and the append-only Developer Mode event log.
**Depends on:** PLAT-01.
**Files to create:** `Platform/ProcessResult.cs`, `Platform/ProcessRunner.cs`, `Platform/PlatformInfo.cs`, `Platform/EmmcIdentity.cs`, `Platform/IDevEventLog.cs`, `Platform/DevEventLog.cs`
**Public contract:**
```csharp
public sealed record ProcessResult(int ExitCode, string Stdout, string Stderr) { public bool Ok => ExitCode == 0; }
public static class ProcessRunner {
  public static ProcessResult Run(string file, IEnumerable<string> args, TimeSpan timeout);
  public static string Output(string file, params string[] args);                 // 15 s timeout
  public static string Output(TimeSpan timeout, string file, params string[] args);
  public static bool Fire(string file, params string[] args);                      // fire-and-forget
}
public static class PlatformInfo { public static bool IsLinux { get; } public static bool IsWindows { get; } }
public static class EmmcIdentity { public const string SysBlockDir = "/sys/block"; public static string? ReadSerial(string sysBlockDir = SysBlockDir); }
public interface IDevEventLog { void Append(string? eventText, object? detail = null); }
public sealed class DevEventLog : IDevEventLog { public const int MaxEventLength = 200; public DevEventLog(DataOptions options, TimeProvider? time = null, ILogger<DevEventLog>? logger = null); }
```
**Behaviour & rules:**
1. `Run`: `UseShellExecute=false`, redirect stdout/stderr, `CreateNoWindow`, args via `ArgumentList`. Start failure → `(-1, "", "could not start <file>")`. Read stdout/stderr asynchronously; `WaitForExit(timeout)` false → kill entire process tree, return `(-1, <stdout so far>, "<file> timed out after <N> s")`. Exceptions `Win32Exception/InvalidOperationException/IOException` → `(-1, "", message)`. Pending stream reads are awaited max 2 s each (else "").
2. `Output` = trimmed stdout when exit 0, else "".
3. `Fire`: start without redirection; true when the process started.
4. `EmmcIdentity.ReadSerial`: enumerate `<sysBlockDir>/mmcblk*` sorted ordinal; skip unless `device/type` (trimmed) == `"MMC"` (SD cards are "SD"; boot partitions have no device type); return first non-empty trimmed `device/serial` (e.g. `0x9d63faba`). Missing dir / IO / access errors → null.
5. `DevEventLog`: file `DataDir/dev_events.jsonl`. Trim event; empty → ignored; cap at 200 chars. Line = `{"ts":"yyyy-MM-dd HH:mm:ss" (local), "event": text, "detail": <detail serialized with JsonDefaults.Options or {}>}` + `\n`, appended under a lock (never rewritten). IO errors → `LogWarning("[DEV] event log write failed")`.
**Configuration:** none.
**Acceptance criteria:**
- A command that does not exist returns exit -1 with a message, no exception.
- A command exceeding its timeout is killed and returns -1 with "timed out".
- Fake `/sys/block` with `mmcblk0` (type MMC, serial 0xabc), `mmcblk1` (type SD), `mmcblk0boot0` (no type) → `0xabc`; no eMMC → null.
- Two `Append` calls produce two JSON lines with `ts`, `event`, `detail`.
**Tests:** `Platform/EmmcIdentityTests` (Reads_the_serial_of_the_eMMC_not_of_an_SD_card_or_a_boot_partition, Null_without_an_eMMC_or_off_Linux), `Platform/DevEventLogTests` (Appends_one_json_line_per_event).
**Reference (source):** `src/SCureBox.Application/Platform/{ProcessResult,ProcessRunner,PlatformInfo,EmmcIdentity,IDevEventLog,DevEventLog}.cs`

---

### PLAT-06 — USB drive discovery and the system service (power, version info, log/CSV/report export)
**Summary**
- **What it is for:** Finds a plugged-in USB drive and handles system actions: reboot, shut down, show version info, and export logs, program CSV files or cure reports to USB.
- **Problem it solves:** Operators need to restart the machine, see what version runs, and take data off the machine.
- **How we solve it:** Look for a mounted removable drive, write files there with safe names, and return a clear message or error code (for example no USB drive).

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Find a mounted removable USB drive ("Disk-on-Key") on the Pi or a PC, and implement the `/api/system/*` actions: reboot, shutdown, version info, export logs / program CSV / cure report HTML to USB. (Clock/NTP methods are on the same class, specified in PLAT-07.)
**Depends on:** PLAT-05, PLAT-07 (ISupervisorClient, optional ctor arg). Domain (`OpResult`, `ErrorCodes`).
**Files to create:** `Platform/IUsbMounts.cs`, `Platform/UsbMounts.cs`, `Platform/ISystemService.cs`, `Platform/SystemService.cs`, `Platform/VersionInfoDto.cs`, `Platform/ExportResultDto.cs`
**Public contract:**
```csharp
public interface IUsbMounts { IReadOnlyList<string> Mounts(); string? Find(); }
public sealed class UsbMounts : IUsbMounts { }
public interface ISystemService {
  OpResult Reboot(); OpResult Shutdown();
  OpResult SetDateTime(string? date, string? time);       // PLAT-07
  bool NetworkTimeEnabled(); OpResult SetNetworkTime(bool on);   // PLAT-07
  VersionInfoDto Version();
  OpResult ExportLogs();
  ExportResultDto ExportCsv(string? filename, string? content);
  ExportResultDto ExportReport(string? filename, string? content);
}
public sealed partial class SystemService : ISystemService {
  public const string NoUsbMessage = "No Disk-on-Key found. Please connect a Disk-on-Key (USB drive).";
  public static readonly string[] RebootCommand = { "sudo", "reboot" };
  public SystemService(IUsbMounts usb, TimeProvider? time = null, ILogger<SystemService>? logger = null, string? baseDir = null, ISupervisorClient? supervisor = null);
  public static string SanitizeFileName(string? filename, string fallback);
}
public sealed record VersionInfoDto {   // JSON: appVersion, gitCommit, gitDate, lastBoot, os, kernel, python, runtime, emmcSerial
  string AppVersion = "unknown"; string? GitCommit, GitDate, LastBoot, Os, Kernel, Python, Runtime, EmmcSerial; }
public sealed record ExportResultDto { bool Ok "ok"; string Message "message" = ""; string? Path "path" (omit null); int? Code "code" (omit null); }
```
**Behaviour & rules:**
1. `UsbMounts.Mounts()` on Linux: (a) lines of `/proc/mounts` starting `/dev/sd`, mount point (`\040` → space) under `/media/`, `/run/media/` or one of fixed `/media/usb`, `/media/pi`, `/mnt/usb`; (b) two-level scan of `/media/*/*` and `/run/media/*/*` keeping mount points; (c) `/mnt/usb*` mount points; (d) fixed points that are mount points; keep existing dirs, distinct, **writable first** (writability probe: create+delete `.scure-write-<pid>`). Mount point test = `mountpoint -q <path>` exit 0 (3 s timeout). Off-Linux: `DriveInfo` removable + ready drives.
2. `Find()`: first of `Mounts()`; else (Linux only) last resort: for `/dev/sda1`, `/dev/sdb1` that exist, create `/media/usb`, run `mount <dev> /media/usb` (10 s), return it if now a mount point; else null.
3. `Reboot`: log `"[SYSTEM] Rebooting: sudo reboot"`; off-Linux → Success "Reboot simulated"; else `Fire("sudo","reboot")` → "Rebooting..." or Fail "sudo reboot could not be started". `Shutdown`: `systemctl poweroff` → "Shutting down..." / "Shutdown simulated".
4. `Version()`: `AppVersion` = first line of `<baseDir>/VERSION` (trimmed, non-empty) else entry assembly `AssemblyInformationalVersion` up to '+', else `Version.ToString(3)`, else "unknown". `GITINFO` file in baseDir: line 1 = commit, line 2 = date (null if blank). `LastBoot` = `uptime -s` on Linux, else now − `Environment.TickCount64` formatted `yyyy-MM-dd HH:mm:ss`. `Os` = `PRETTY_NAME` from `/etc/os-release` (quotes stripped) else `RuntimeInformation.OSDescription`. `Kernel` = `uname -r` (Linux) or `Environment.OSVersion.Version`. `Python` = null always. `Runtime` = `RuntimeInformation.FrameworkDescription`. `EmmcSerial` = `EmmcIdentity.ReadSerial()`.
5. `ExportLogs`: no USB → Fail("No USB drive found", 9083). Stamp `yyyyMMdd-HHmmss` (local). If `/var/log/scure` exists → recursive copy to `<usb>/scure-logs-<stamp>/`; else write `<usb>/scure-logs-<stamp>.txt` with `journalctl -u scurebox --no-pager` stdout (30 s, Linux) or `"No logs available on this host (<OSDescription>)\n"`. Then `sync` (Linux, 30 s). Success "Logs exported to USB". IO/access errors → Fail(msg, 9083).
6. `ExportCsv` / `ExportReport`: name = `SanitizeFileName(filename, "untitled.csv" | "cure-report.html")`; append `.csv`/`.html` if missing (case-insensitive). No USB → `{Ok=false, Code=9081, Message=NoUsbMessage}`. Write UTF-8 no BOM to `<usb>/<name>`, `sync`; → `{Ok=true, Message="Saved <name> to USB", Path=dest}`. IO/access/NotSupported → `{Ok=false, Code=9082, Message=e.Message}`.
7. `SanitizeFileName`: replace `\` by `/`, take text after last `/`, trim, replace every `Path.GetInvalidFileNameChars()` with `_`; empty, `.` or `..` → fallback.
**Configuration:** `<baseDir>/VERSION`, `<baseDir>/GITINFO` (baseDir default `AppContext.BaseDirectory`).
**Acceptance criteria:**
- Export with `FakeUsbMounts` returning null → code 9081 and the exact NoUsbMessage.
- `ExportCsv("../../etc/passwd", "x")` writes `passwd.csv` inside the USB dir.
- A read-only/invalid target → code 9082.
- `Version()` reads VERSION + GITINFO from baseDir; without VERSION falls back to the assembly version.
- Off Windows/Linux-less tests: Reboot/Shutdown report "simulated"; on Linux `RebootCommand` is exactly `sudo reboot`.
**Tests:** `Platform/SystemServiceTests` (Export_without_a_usb_drive_is_9081, Export_writes_sanitised_file_names_with_the_forced_extension, Export_write_error_is_9082, File_names_are_reduced_to_a_safe_basename, Version_reads_the_version_and_gitinfo_files_next_to_the_executable, Version_falls_back_to_the_assembly_version_without_a_version_file, Date_time_format_is_validated, Power_actions_are_simulated_off_device, Reboot_runs_sudo_reboot); helper `Platform/FakeUsbMounts`.
**Reference (source):** `src/SCureBox.Application/Platform/{IUsbMounts,UsbMounts,ISystemService,SystemService,VersionInfoDto,ExportResultDto}.cs`

---

### PLAT-07 — Clock and network time (timedatectl) + Origin supervisor client
**Summary**
- **What it is for:** Lets the operator set the date and time and turn network time on or off, and talks to the Origin device supervisor.
- **Problem it solves:** On an Origin image, clock changes made the normal way are lost after a reboot.
- **How we solve it:** When the Origin supervisor is present, send clock settings to it so it re-applies them at boot; otherwise use the normal system time tool.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/SystemService.cs` (clock part), `Platform/SupervisorClient.cs`
**Goal:** Let the operator set date/time and switch network time (NTP) on/off such that it survives reboots on an Origin image (where the supervisor owns `/opt/config/clock.conf` and `origin-apply-clock.service` re-applies it at boot). Provide the HTTP client to the Origin device supervisor (ASP.NET service on `127.0.0.1:8080`) used for clock and for software updates (PLAT-08).
**Depends on:** PLAT-05, PLAT-06.
**Files to create:** `Platform/SupervisorClient.cs` — `SupervisorInstaller`, `SupervisorApplication`, `ISupervisorClient`, `HttpSupervisorClient`
**Public contract:**
```csharp
public sealed record SupervisorInstaller(string Name, string Version, string Path);
public sealed record SupervisorApplication(string State, string? Version, bool InstallFailed, string? InstallError);
public interface ISupervisorClient {
  bool IsAvailable();
  IReadOnlyList<SupervisorInstaller> FindInstallers();
  bool Install(string path, out string error);
  SupervisorApplication? GetApplication();
  bool? NetworkTimeEnabled();
  bool SetNetworkTime(bool on, out string error);
}
public sealed class HttpSupervisorClient : ISupervisorClient {
  public const string DefaultUrl = "http://127.0.0.1:8080";
  public HttpSupervisorClient(ILogger<HttpSupervisorClient>? log = null, string? url = null);
  public static SupervisorApplication ParseApplication(JsonElement root);
}
```
**Behaviour & rules:**
1. Supervisor URL: ctor `url` ?? env `SCURE_SUPERVISOR_URL`. **Off** when the value is `"off"` (case-insensitive) or when not Linux and no URL is given (an unrelated :8080 service on a PC must not be mistaken for it). HttpClient timeout 20 s; base address = given URL or DefaultUrl.
2. Endpoints: `IsAvailable` = `GET /api/status` success within 1.5 s (off → false). `FindInstallers` = `GET /api/external-storage/find-app-installers` → JSON array of `{name, version, path}` (items without `path` skipped; errors → empty, warning `"[UPDATE] supervisor: installers not readable"`). `Install` = `POST /api/application/install` body `{"path": "<path>"}`; non-success → error = problem-details `detail` ?? `title` ?? `"HTTP <code>"`. `GetApplication` = `GET /api/application` → `ParseApplication`. `NetworkTimeEnabled` = `GET /api/machine/clock` → `ntpEnabled` bool or null (off/err/missing → null). `SetNetworkTime` = `POST /api/machine/clock` `{"ntpEnabled": on}`; off → false with error `"no supervisor"`.
3. `ParseApplication(root)`: `{state, version, install:{state?, exitCode?, error?}}`; InstallFailed when `install.error` non-blank, or `install.state` contains "fail"/"error"/"cancel" (case-insensitive), or numeric `exitCode != 0`. InstallError = blank → null. Missing state → "".
4. `SystemService.SetDateTime(date, time)`: date must match `^\d{4}-\d{2}-\d{2}$`, time `^\d{2}:\d{2}(:\d{2})?$`, else Fail("Invalid date/time format") (no code) **and network time is not touched**. Valid: switch network time OFF first — via `supervisor.SetNetworkTime(false)`; if that is not true and on Linux, `timedatectl set-ntp false` (15 s). Off-Linux: remember NTP off, Success "Clock set simulated (<date> <time>)". Linux: `timedatectl set-time "<date> <HH:MM:00 or HH:MM:SS>"` (15 s); failure → Fail(stderr or "set-time failed"); success "Clock set to <date> <time>".
5. `NetworkTimeEnabled()`: supervisor answer when non-null; else off-Linux simulated flag (initially **true**); else `timedatectl show -p NTP --value` == "yes" (10 s).
6. `SetNetworkTime(on)`: log `"[SYSTEM] network time synchronisation ON|OFF"`. Supervisor present and `SetNetworkTime` ok → Success "Network time on|off". If refused with a reason other than "no supervisor" → warning and fall back. Off-Linux → simulated flag, "Network time on|off simulated". Linux → `timedatectl set-ntp true|false`; fail → Fail(stderr or "set-ntp failed"). Rationale (SRS OI-54): units have no RTC; a clock left manual stays months behind and HTTPS fails ("certificate is not yet valid").
**Configuration:** env `SCURE_SUPERVISOR_URL` (URL or `off`).
**Acceptance criteria:**
- A fresh (simulated) machine reports network time enabled; a valid manual clock set turns it off; `SetNetworkTime(true)` turns it back on; a malformed date leaves it unchanged.
- With a fake supervisor: SetNetworkTime goes through `POST /api/machine/clock`; manual clock sends `ntpEnabled:false` to the supervisor; a silent supervisor (null) falls back to the machine's own setting.
- `ParseApplication` flags failure for `install.exitCode: 1`, `install.state: "Failed"`, or a non-empty error.
**Tests:** `Platform/NetworkTimeTests` (A_machine_keeps_its_clock_synchronised_until_something_says_otherwise, Setting_the_clock_by_hand_switches_network_time_off, Network_time_can_be_switched_back_on_after_a_manual_clock, A_malformed_date_leaves_network_time_alone, Network_time_is_set_through_the_supervisor_so_it_survives_a_restart, A_manual_clock_switches_network_time_off_in_the_supervisor, A_silent_supervisor_falls_back_to_the_machines_own_setting); `SupervisorUpdateTests.The_application_reply_is_read_leniently`.
**Reference (source):** `src/SCureBox.Application/Platform/{SystemService,SupervisorClient}.cs`

---

### PLAT-08 — Software update: signed `.scu` package from USB, or through the Origin supervisor
**Summary**
- **What it is for:** Installs a new software version from a USB stick.
- **Problem it solves:** Machines need safe updates; a fake or broken package must not be installed, and a failed install must not leave the machine broken.
- **How we solve it:** Standalone machines check a signed package, run its install script, and roll back on failure. Origin devices hand the update to the supervisor, which checks and switches versions.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Install a new firmware version from a USB stick. Standalone machines use the `.scu` format (outer tar with an RSA-SHA256-signed inner tar.gz carrying `manifest.json` + `install.sh`, run with `--pre`/`--post`, `--rollback` on failure). On an Origin device (supervisor answering) the update is delegated to the supervisor, which verifies SHA256SUMS + manifest of a `.tgz` and switches `current`.
**Depends on:** PLAT-05, PLAT-06 (IUsbMounts), PLAT-07 (ISupervisorClient). Deploy-Ops (`deploy/keys/scure-update.pub`, package scripts `deploy/package-origin-app.*`, `make-installer.ps1`).
**Files to create:** `Platform/IUpdateService.cs`, `Platform/UpdateService.cs`, `Platform/UpdatePackage.cs`, `Platform/UpdatePackageBuilder.cs`, `Platform/IScriptRunner.cs`, `Platform/BashScriptRunner.cs`, `Platform/UpdatePackageDto.cs`, `Platform/UpdateManifestDto.cs`, `Platform/UpdateResultDto.cs`, `Platform/UpdateStepDto.cs`
**Public contract:**
```csharp
public interface IUpdateService { UpdatePackageDto FindPackage(); UpdateManifestDto Manifest(); UpdateResultDto RunUpdate(); }
public sealed class UpdateService : IUpdateService {
  public const string NoUsbMessage = "No USB drive found. Please insert a USB stick.";
  public const string NoPackageMessage = "No .scu update file found on USB.";
  public UpdateService(IUsbMounts usb, IScriptRunner? scripts = null, ILogger<UpdateService>? logger = null, string? publicKeyPath = null, string? workRoot = null, ISupervisorClient? supervisor = null);
  public string? PublicKeyPath { get; }
  public static TimeSpan SupervisorInstallTimeout { get; set; } = 300 s;
  public static TimeSpan SupervisorPoll { get; set; } = 500 ms;
  public static SupervisorInstaller? NewestInstaller(IEnumerable<SupervisorInstaller> installers);
}
public static class UpdatePackage {
  public sealed record Extracted(string? UpdateDir, string Message);
  public static bool VerifySignature(ReadOnlySpan<byte> payload, ReadOnlySpan<byte> signature, string publicKeyPem);
  public static Extracted ExtractAndVerify(string scuPath, string workDir, string? publicKeyPath);
  public static string? ReadVersion(string updateDir);
  public static string Sha256Hex(string path);   // lower-case hex
}
public static class UpdatePackageBuilder {
  public static void Build(string sourceDir, string outputScuPath, string privateKeyPem);
  public static (string PrivatePem, string PublicPem) GenerateKeyPair();   // RSA 2048, PKCS#8 + SubjectPublicKeyInfo PEM
}
public interface IScriptRunner { ProcessResult Run(string scriptPath, string argument, TimeSpan timeout); }
public sealed class BashScriptRunner : IScriptRunner { }
public sealed record UpdateStepDto(string Step "step", string Status "status");   // running | ok | error
public sealed record UpdatePackageDto { bool Ok "ok"; [JsonIgnore] string? Path; string? FileName "fileName"; int? Code "code"; string? Message "message"; }   // nulls omitted
public sealed record UpdateManifestDto { bool Ok "ok"; string? Version "version"; string? Sha256 "sha256"; int? Code "code"; string? Message "message"; }
public sealed record UpdateResultDto { bool Ok "ok"; IReadOnlyList<UpdateStepDto> Steps "steps"; string? Version "version"; string Message "message" = ""; int? Code "code" (omit null); }
```
**`.scu` format:** uncompressed tar (PAX) containing `<name>.tar.gz` and `<name>.tar.gz.sig`, where `<name>` = output file name without `.scu`. Signature = RSA PKCS#1 v1.5 over SHA-256 of the exact `.tar.gz` bytes (`openssl dgst -sha256 -sign` compatible). Inner tar.gz (PAX, gzip optimal) = directory `<name>/` with the source tree (dirs and files sorted ordinal; modes: dirs and `*.sh` 0755, other files 0644); must contain `manifest.json` (`{"version": "...", ...}`) and `install.sh`.
**Behaviour & rules:**
1. Public key lookup (first existing): `<app>/keys/scure-update.pub`, `/opt/scurebox/keys/scure-update.pub`, `/opt/scure/keys/scure-update.pub`, then `<dir>/deploy/keys/scure-update.pub` walking up from the app dir. PEM SubjectPublicKeyInfo or PKCS#1. Private key is never on the device (builder only).
2. `ExtractAndVerify`: extract outer tar to workDir; first `*.tar.gz` and `*.sig` required else "Invalid package structure"; no key → "Public key not found"; `CryptographicException` → "Invalid signature: <msg>"; false → "Invalid signature". Then gunzip+untar payload into workDir; UpdateDir = first subdirectory (ordinal) holding `manifest.json`, else workDir if it holds one, else "No manifest found in package". IO/InvalidData/Format errors → message.
3. `NewestPackage(usb)`: `*.scu` in the USB root plus `<usb>/scure-update/*.scu`, newest `LastWriteTimeUtc` first, ties by path ordinal.
4. Work dir: `<workRoot or temp>/scure-update-<guid N>`, always deleted (finally).
5. `FindPackage` (no supervisor): no USB → `{Code 9081, "No USB drive found"}`; none → `{Code 9087, "No .scu update file found on USB"}`; IO → 9086.
6. `Manifest`: package + SHA-256 of the `.scu`; version = manifest `version` when it verifies, else the file name.
7. `RunUpdate` (`.scu` path) step list, each marked running→ok/error in order: `find_usb` (fail 9081 NoUsbMessage) → `find_package` (fail 9087 NoPackageMessage; IO 9086) → `verify_signature` (a failure whose message contains "signature" or "key" fails here: "Verification failed: <msg>", 9086; other extract failures mark verify ok and fail `extract`) → `extract` ok → `manifest` (version or "unknown") → `install_pre` (`bash install.sh --pre`, 300 s) → `install_post` (`--post`, 300 s); a non-zero exit runs `install.sh --rollback` (120 s) and fails with "Failed at 'Pre-install backup'|'Installing update': <stderr>" code 9086 + Version → `cleanup` (delete work dir; Linux `umount <usb>` 10 s) → `{Ok, Version, Message "Updated to version <v>"}`.
8. `BashScriptRunner`: `bash <script> <arg>`; off-Linux, exit -1 not caused by a timeout → simulated `(0, "simulated: install.sh <arg>", "")`.
9. Supervisor path (used by all three methods whenever `supervisor.IsAvailable()`): `NewestInstaller` = installers whose Name contains "scurebox" (ci) or file name starts with "scurebox" (ci), highest `System.Version.TryParse(Version)` (unparsable = 0.0), then version string ordinal desc. None → 9087 "No sCureBox package found on USB". Manifest = installer version + SHA-256 of its path. RunUpdate steps: `find_usb` ok → `find_package` (9087 NoPackageMessage) → if `GetApplication().Version == installer.Version` fail `install_post` "Version <v> is already installed" (9086) → `verify_signature`: `Install(path)` refused → "The supervisor refused the package: <reason>" (9086) → `install_post`: poll `GetApplication` every `SupervisorPoll` while it is null or `State == "Installing"` (ci) up to `SupervisorInstallTimeout` → "The supervisor did not finish the installation in time"; `InstallFailed` → "Failed at 'Installing update': <error or 'the supervisor reported a failure'>"; resulting version ≠ installer → "The supervisor reports version <x> instead of <v>"; all 9086 with Version. Success "Updated to version <v>". Note (ops): supervisor install does not restart the app; the host restarts afterwards (Api/Deploy-Ops).
**Configuration:** key file locations above; `SCURE_SUPERVISOR_URL` (via PLAT-07).
**Acceptance criteria:**
- A package built with `UpdatePackageBuilder` + key pair verifies and installs (fake script runner records `--pre`, `--post`).
- Signed with another key, or a tampered payload → fails at `verify_signature` with 9086.
- Missing USB → 9081; USB without `.scu` → 9087; newest file wins including `scure-update/`.
- A failing `--post` triggers `--rollback`.
- Builder throws `FileNotFoundException` without `manifest.json` or `install.sh`.
- Supervisor: picks newest sCureBox installer ignoring others; refused / failed / wrong-version / already-installed cases fail with 9086; without a supervisor the `.scu` flow is used.
**Tests:** `Platform/UpdateServiceTests` (Package_builds_verifies_and_installs, Extracted_package_contains_the_tree_and_the_signature_verifies_directly, Package_signed_with_another_key_is_rejected, Tampered_payload_is_rejected, Missing_usb_and_missing_package_have_their_own_codes, Newest_package_wins_including_the_scure_update_folder, Failed_install_rolls_back, Builder_requires_manifest_and_install_script); `Platform/SupervisorUpdateTests` (The_newest_scurebox_package_is_chosen_and_other_installers_are_ignored, An_update_installs_the_package_through_the_supervisor, No_package_on_the_stick_is_reported_as_no_update_package, A_package_the_supervisor_refuses_fails_the_update_with_its_reason, A_failed_install_and_a_wrong_resulting_version_both_fail_the_update, The_version_that_is_already_installed_is_not_installed_again, The_application_reply_is_read_leniently, Without_a_supervisor_the_scu_flow_is_used) with a fake `ISupervisorClient` and tiny `SupervisorPoll`.
**Reference (source):** `src/SCureBox.Application/Platform/{IUpdateService,UpdateService,UpdatePackage,UpdatePackageBuilder,IScriptRunner,BashScriptRunner,Update*Dto}.cs`, `deploy/keys/scure-update.pub`

---

### PLAT-09 — Network service (status, diagnostics, static IP, NetBird/WireGuard tunnel IP) and network policy
**Summary**
- **What it is for:** Shows network status, runs network tests, sets a fixed or automatic IP address, and decides if having no network is a problem.
- **Problem it solves:** Operators and support need to see and fix network issues, but units that are offline on purpose should not show a fault.
- **How we solve it:** Read interface and tunnel status, run ping and similar tools only on checked addresses, apply IP settings through the network manager, and stay green when offline by choice.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Report the wired interface (eth0) state, all interfaces, gateway and the remote-access tunnel IP; run ping/traceroute/nslookup safely against validated addresses; apply DHCP/static IPv4 via NetworkManager; and decide whether "no network" is a fault at all (offline-by-choice / not cloud-enrolled units stay green).
**Depends on:** PLAT-05, PLAT-10 (`ICloudSync.Status().Enabled` for the policy). Application-Process (registers `NetworkPolicy`, consumes it in `StatusLedService`; supplies `InternetReachability`).
**Files to create:** `Platform/INetworkService.cs`, `Platform/NetworkService.cs`, `Platform/NetworkAddress.cs`, `Platform/NetworkStatusDto.cs`, `Platform/NetworkInterfaceDto.cs`, `Platform/DiagnosticsResultDto.cs`, `Platform/InternetReachability.cs`, `Platform/NetworkPolicy.cs`
**Public contract:**
```csharp
public delegate bool? InternetReachability();   // null = unknown (no TCP-443 watch running)
public interface INetworkService {
  NetworkStatusDto Status();
  DiagnosticsResultDto Diagnostics(string? tool, string? address);
  OpResult SetStatic(bool dhcp, string? ip, string? gateway, string? subnet, string? dns);
}
public sealed class NetworkService : INetworkService {
  public NetworkService(InternetReachability? internet = null, ILogger<NetworkService>? logger = null);
  public static string WireguardIpOf(IEnumerable<NetworkInterfaceDto> interfaces);
}
public static partial class NetworkAddress {
  public static bool IsValidHostOrIp(string? address);
  public static bool IsValidIPv4(string? address);
  public static int? PrefixLength(string? subnet);
}
public sealed record NetworkStatusDto { bool Connected "connected"; string Ip "ip" = "0.0.0.0"; string Mac "mac" = "00:00:00:00:00:00"; string Gateway "gateway" = ""; IReadOnlyList<NetworkInterfaceDto> Interfaces "interfaces"; bool Internet "internet"; string WireguardIp "wireguardIp" = ""; int? Code "code" (omit null); }
public sealed record NetworkInterfaceDto(string Name "name", string Status "status" /*UP|DOWN*/, string Ip "ip");
public sealed record DiagnosticsResultDto(bool Ok "ok", string Result "result", int? Code "code" = null /*omit null*/);
public sealed class NetworkPolicy {
  public NetworkPolicy(Func<bool> cloudEnrolled, DataOptions? data = null);
  public bool? OfflineByChoice { get; }
  public bool ExpectsNetwork { get; }
  public bool OfflineMode => !ExpectsNetwork;
  public void Choose(bool? offline);
}
```
**Behaviour & rules:**
1. `Status()` Linux: ip = first `inet` `local` of `ip -4 -j addr show eth0`; if no eth0 at all (neither that nor `ip link show eth0`) use first address of `hostname -I`. `carrier`/`address` from `/sys/class/net/eth0/`; gateway = `gateway` of first entry of `ip -j route show default`; interfaces from `ip -j addr show` (`ifname`, UP when `flags` contains "UP", first inet). `Connected = ip != "0.0.0.0" && (carrier missing || carrier == "1")`. Off-Linux: `NetworkInterface.GetAllNetworkInterfaces()` excluding loopback; the first UP non-tunnel NIC with IPv4 gives ip/mac (lower-case hex with ':')/gateway. Exceptions (IO/Json/NetworkInformation/Access/InvalidOperation) → `{Connected=false, Code=9084}` + warning `"[NET] status failed"`. Finally `Internet = internet() ?? Connected`.
2. `WireguardIpOf`: first interface with non-empty IP and Status "UP" whose lower-case name is `wt<digits>` or `wg<digits>` (length > 2), or contains "netbird" or "wireguard"; else "".
3. `Diagnostics(tool, address)`: tool default "ping"; address default "8.8.8.8" (trimmed). Unknown tool → `(false, "Unknown tool", 9080)`; invalid address → `(false, "Invalid address", 9085)` — nothing is run. Commands (45 s timeout): Linux `ping -c 4 -W 3 <a>`, `traceroute -m 15 -w 3 <a>`, `nslookup <a>`; Windows `ping -n 4 -w 3000`, `tracert -h 15 -w 3000`. Exit -1 → `(false, stderr, 9085)`; otherwise `(true, (stdout + "\n" + stderr).Trim())` even on a non-zero exit (unreachable host output is the diagnostic).
4. `NetworkAddress.IsValidHostOrIp`: null/blank or > 253 chars → false; valid IPv4 (regex `^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(...)){3}$` + `IPAddress.TryParse` InterNetwork) → true; IPv6 chars `^[0-9A-Fa-f:.]{2,45}(%[A-Za-z0-9]{1,15})?$` + parses as InterNetworkV6 → true; hostname RFC1123 `^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$` and NOT all-numeric `^[0-9.]+\.?$`. Rejects spaces, `;`, `|`, `-c` style options.
5. `PrefixLength(mask)`: valid IPv4 whose bits are contiguous ones → popcount (255.255.255.0 → 24, 0.0.0.0 → 0); else null.
6. `SetStatic`: off-Linux → Success "Network config simulated (off-device)". subnet default "255.255.255.0". Connection name = NAME of `nmcli -t -f NAME,DEVICE connection show --active` line whose device (after last ':') is `eth0`, else "eth0". DHCP: `nmcli connection modify <c> ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""`. Static: validate ip ("Invalid IP address '<ip>'"), gateway ("Invalid gateway '<g>'"), mask ("Invalid subnet mask '<m>'"), DNS list split on ',' or ' ' all IPv4 ("Invalid DNS '<d>'"), all code 9084; `nmcli connection modify <c> ipv4.method manual ipv4.addresses <ip>/<prefix> ipv4.gateway <gw> [ipv4.dns a,b]` (15 s). Then `nmcli connection up <c>` (30 s). Failures → Fail(stderr or "nmcli modify failed"/"nmcli up failed", 9084). Success "Network configuration applied".
7. `NetworkPolicy`: file `DataDir/network-policy.json` = `{"offline": true|false|null}` (indented, atomic). `ExpectsNetwork` = operator choice when set (`!offline`), else `cloudEnrolled()`; if that throws → false (cannot tell = do not complain). `Choose(null)` returns to "follow cloud enrolment". Unreadable file → choice null. Save errors swallowed. `/api/state` exposes `offlineMode` (Api area).
**Configuration:** `data/network-policy.json`.
**Acceptance criteria:**
- `Diagnostics("ping", "8.8.8.8; rm -rf /")` → code 9085 without running anything; `Diagnostics("curl", ...)` → 9080.
- `PrefixLength("255.255.255.0") == 24`, `PrefixLength("255.0.255.0") == null`.
- Interfaces `[eth0 UP 192.168.1.5, wt0 UP 100.106.37.62]` → wireguardIp 100.106.37.62; a DOWN wt0 is ignored.
- Status internet = probe value when non-null, else equals `connected`.
- Policy: no cloud + no choice → OfflineMode; cloud enrolled → ExpectsNetwork; explicit choice wins and survives a new instance on the same data dir.
**Tests:** `Platform/NetworkServiceTests` (Wireguard_ip_is_the_up_netbird_or_wireguard_tunnel_address, Address_validation, Subnet_mask_to_prefix, Diagnostics_reject_injection_and_unknown_tools_without_running_anything, Status_reports_the_internet_probe_or_mirrors_the_lan_state, Static_config_is_simulated_off_device); `Platform/NetworkPolicyTests` (A_machine_without_a_cloud_account_is_offline_on_purpose, A_machine_enrolled_in_the_cloud_still_expects_a_network, The_operators_choice_wins_over_the_enrolment_and_survives_a_restart, A_cloud_check_that_throws_never_turns_into_a_network_complaint, The_strip_stays_green_offline_and_goes_blue_only_when_a_network_was_expected — the last one exercises Process `StatusLedService`).
**Reference (source):** `src/SCureBox.Application/Platform/{INetworkService,NetworkService,NetworkAddress,NetworkStatusDto,NetworkInterfaceDto,DiagnosticsResultDto,InternetReachability,NetworkPolicy}.cs`

---

### PLAT-10 — Cloud sync agent (outbound-only portal sync, data-only commands, report upload/deletion)
**Summary**
- **What it is for:** A background service that keeps the machine in sync with the sCure Cloud portal.
- **Problem it solves:** Without it the portal cannot see machine status, alerts or reports, and cannot send programs and prints to the machine.
- **How we solve it:** The machine regularly sends its status to the portal (outbound only), accepts only data commands (never hardware control), uploads each finished report once, and reports deleted runs.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** A background service that, when `data/cloud.json` holds a portal URL and machine key, periodically POSTs a machine snapshot to the sCure Cloud portal (Flask `/api/agent/sync` or a Google Apps Script `/exec` URL), applies the portal's DATA-ONLY commands (programs and prints — never hardware), acks them on the next sync, keeps a 48 h alert log for the portal, uploads each finished run's HTML report once and propagates local run deletions.
**Depends on:** PLAT-01, PLAT-02, PLAT-11 (`IComponentCounters`), PLAT-14 (`ICureReportBuilder`, `CureReportContext`). Domain (`ProgramEstimator.EstimateProgramMinutes`, `NfcUid`, `Material`, `PrintLog`). Application-Process (`MachineState`, `CloudSyncDto`, `ICureController` via `MachineStateSource`).
**Files to create:** `Platform/CloudConfig.cs`, `Platform/ICloudSync.cs`, `Platform/CloudSyncAgent.cs`, `Platform/CloudReportDeletions.cs` (also `CureHistoryDeletion`), `Platform/MachineStateSource.cs`
**Public contract:**
```csharp
public delegate MachineState MachineStateSource();
public sealed record CloudConfig { string? Url "url"; string? Key "key"; string Name "name" = "CureBox"; double Interval "interval" = 10; [JsonIgnore] bool IsComplete; }   // IsComplete = Url and Key non-blank
public interface ICloudSync { CloudSyncDto Status(); OpResult Configure(string? url, string? key, string? name, double? interval); }
// CloudSyncDto (Contracts/MachineState.cs): { bool Enabled "enabled"; double? LastSyncOk "lastSyncOk" (unix s); string? Error "error"; }
public sealed class CloudSyncAgent : BackgroundService, ICloudSync {
  public const double MinIntervalSeconds = 3.0;
  public const int AlertLogHours = 48;
  public CloudSyncAgent(DataOptions options, HttpClient http, TimeProvider time, IMaterialStore materials, IPrintHistoryStore prints,
      ICureRunStore cures, IComponentCounters counters, MachineStateSource state, ILogger<CloudSyncAgent>? logger = null,
      ICureReportBuilder? reports = null, IPhaseTimingStore? timings = null, CloudReportDeletions? deletions = null);
  public bool Enabled { get; }
  public JsonObject Snapshot();
  internal void SampleAlerts();
  public Task<bool> SyncOnceAsync(CancellationToken ct);
}
public sealed class CloudReportDeletions {
  public CloudReportDeletions(DataOptions options, ILogger<CloudReportDeletions>? logger = null);
  public IReadOnlyList<string> Pending(); public void Enqueue(IEnumerable<string> runIds); public void Done(IEnumerable<string> runIds);
}
public sealed class CureHistoryDeletion {
  public CureHistoryDeletion(ICureRunStore runs, CloudReportDeletions cloud, ILogger<CureHistoryDeletion>? logger = null);
  public bool Delete(string runId); public int DeleteAll();
}
```
Files: `data/cloud.json` (CloudConfig, indented), `data/cloud_reports.json` (sorted string array of run ids already uploaded), `data/cloud_deletes.json` (sorted string array of run ids to delete on the portal).
**Behaviour & rules:**
1. Security: the machine key is a shared secret stored in plain text in `data/cloud.json`; it is sent both as header `X-Machine-Key` and as body field `machineKey` (Apps Script cannot read headers). Outbound only; no command actuates hardware.
2. Load at construction: no file → off; incomplete → error `cloud.json needs "url" and "key"`; parse error → `bad cloud.json: <msg>`. Complete → enabled, log `"[CLOUD] sync agent ON -> <url>"`.
3. `Configure`: url or key blank → Fail("url and key required"). Else write cloud.json (`name` blank → "CureBox", `interval ?? 10`), enable, clear error; message "Cloud sync agent started" or "Cloud sync config updated" when already enabled.
4. URL: base = `Url.TrimEnd('/')`; if it ends with `/exec` use as-is, else append `/api/agent/sync`. Request timeout 30 s.
5. `Snapshot()` JSON: `name`, `state{chamberTemp, doorClosed, isHeating, isCooling, uvOn, internetOk, counters (= Hours())}` (state read failure → `{}`), `programs` (user materials), `presets` (built-in catalog, separate field so the portal never offers edit/delete), `prints` (first 20), `cures` (first 10 runs serialized **without** `telemetry`), `alertLog[{code, message, raised, cleared}]` (unix s), `ackIds` (command ids applied in the previous sync). `SyncOnceAsync` adds `machineKey`.
6. `SyncOnceAsync`: not configured → false. Sample alerts, POST snapshot (JSON, `JsonDefaults.Options`), `EnsureSuccessStatusCode`; reply `{"ok": false, "message"}` (Apps Script always 200) → error. For each object in `commands[]`: apply; acked ids = applied ones and also failed ones (exceptions Json/InvalidOperation/IO/Argument are logged and acked to avoid loops); unknown types are NOT acked. On success: `LastSyncOk = unix now`, error null, ack list replaced. If reply `acceptsReports == true`: run DeleteReports then UploadNextReport (their errors only logged). Transport errors (HttpRequest/TaskCanceled/Json/IO/InvalidOperation) → `Error = message`, return false; cancellation of the host token rethrows `OperationCanceledException`.
7. Commands: `upsert_program` (payload → `Material`; replace same id or append; `ReplaceUserMaterials`), `delete_program` (`payload.id`), `delete_print` (`payload.id`; empty id → acked no-op; cure runs/reports stay), `send_print`: material by name among user + presets; duration minutes = `payload.duration` (minutes, number or numeric string) ?? `ProgramEstimator.EstimateProgramMinutes(prog.Steps)` when the program has steps ?? 20; `PrintLog{ Id="cloud-<unix ms>", PrintName=payload.printName or "Job", MaterialName, PrinterName=payload.printerName or "CLOUD", Date=local "yyyy-MM-ddTHH:mm:ss", Duration=floor(minutes*60) seconds, Status="completed", Steps=program step count when >0 else payload.steps else 0, CsvFile=payload.csvFile or "", NfcTag=NfcUid.Display(payload.nfcTag) (malformed → null) }` inserted first.
8. Alert log (`SampleAlerts`, called every 1 s between syncs and before each sync): for each distinct code in `state.Alerts` open an entry `{code, message = AlertDetails["<code>"] ?? "", raised = now}` (an open entry's message is refreshed when a non-empty detail arrives); codes no longer present get `cleared = now`. Closed entries older than 48 h dropped; list capped at 300 (oldest removed).
9. Report upload (one per sync): first run among the newest 10 with status ≠ "running" not in cloud_reports.json. Content = stored report when `Format == "html"` and non-empty; else build with `ICureReportBuilder` when the run has telemetry (context: material name, steps of the matching program by name, phase timings for the run id). Neither → mark done forever. POST `{machineKey, kind:"report", runId, fileName (default "cure-report-<id>.html" or the builder's), materialName, startedAt, status, content}` (60 s timeout); reply must be `ok: true`; then mark done.
10. Deletions: `CureHistoryDeletion.Delete/DeleteAll` delete from the run store and `Enqueue` the ids. On a sync with `acceptsReports`, POST `{machineKey, kind:"delete_reports", runIds:[...]}`; on `ok: true` → `Done(ids)` and remove them from cloud_reports.json.
11. `ExecuteAsync` loop: if enabled `SyncOnceAsync`; interval = `max(3, enabled ? cfg.Interval ?? 10 : 3)` s, waited in 1 s steps (via `TimeProvider`) calling `SampleAlerts` each second. Stops on cancellation.
**Configuration:** `data/cloud.json` `{url, key, name="CureBox", interval=10}`.
**Acceptance criteria:**
- Unconfigured: `Status().Enabled == false`; `Configure(null, "k", ..)` fails "url and key required".
- A sync posts to `<url>/api/agent/sync` with header `X-Machine-Key` and body `machineKey`; `.../exec` URL is posted as-is.
- Commands applied in sync N are listed in `ackIds` of sync N+1.
- HTTP 500 or `{ok:false}` sets `Status().Error`.
- A portal with `acceptsReports:true` receives each finished run's report exactly once; a deleted run's id is sent in `delete_reports` once; without `acceptsReports` nothing is uploaded.
- `send_print` for a catalog program uses its steps for steps/duration; a malformed `nfcTag` is dropped; `delete_print` removes the print.
- An alert raised and cleared between syncs appears in `alertLog` with both times.
**Tests:** `Platform/CloudSyncAgentTests` (FakePortal `HttpMessageHandler`, Harness): The_snapshot_carries_the_catalog_and_a_print_for_a_catalog_program_uses_its_steps, A_print_can_be_deleted_from_the_portal, A_malformed_nfc_tag_is_dropped, Unconfigured_agent_is_off_and_configure_requires_url_and_key, Sync_posts_the_snapshot_applies_commands_and_acks_them_next_time, Portal_errors_are_reported_in_the_status, An_ok_false_reply_is_an_error_even_with_status_200, A_google_apps_script_portal_is_posted_at_its_exec_url, A_portal_that_takes_reports_gets_each_finished_run_report_once, A_run_deleted_on_the_machine_is_deleted_on_the_portal_once, A_portal_that_does_not_take_reports_gets_none, Alerts_raised_between_syncs_are_logged_with_their_times, Incomplete_config_file_reports_an_error_and_stays_off.
**Reference (source):** `src/SCureBox.Application/Platform/{CloudConfig,ICloudSync,CloudSyncAgent,CloudReportDeletions,MachineStateSource}.cs`, `src/SCureBox.Application/Contracts/MachineState.cs` (`CloudSyncDto`), portal side `cloud/google/Code.gs` (in sCure-A, Kiosk-Web/cloud area)

---

### PLAT-11 — Component ON-hour counters (wear tracking)
**Summary**
- **What it is for:** Counts how many hours each wearing part has been on: the 405 nm and 450 nm LEDs, cooling fan, heater and heater fan.
- **Problem it solves:** Without on-time counts there is no way to know when parts are worn and need service.
- **How we solve it:** Add up on-time from the live machine state, save it so it survives reboots and power cuts, and show it in hours in the app and the cloud.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Accumulate the real ON-time of the wear components (405 nm LEDs, 450 nm LEDs, chamber cooling fan, heater, heater fan) from the live machine state and persist it across reboots and power cuts; exposed as hours in `/api/state.counters` and the cloud snapshot.
**Depends on:** PLAT-01. Application-Process (`MachineState` fields `UvOn`, `UvWavelength`, `HeaterOut`, `HeaterPwm`, `IsHeating`, `FanRpmEach`, `Fans`).
**Files to create:** `Platform/IComponentCounters.cs`, `Platform/ComponentCounters.cs`, `Platform/ComponentCountersHostedService.cs`
**Public contract:**
```csharp
public interface IComponentCounters { Dictionary<string, double> Hours(); Dictionary<string, double> Seconds(); void Flush(); }
public sealed class ComponentCounters : IComponentCounters, IDisposable {
  public static readonly IReadOnlyList<string> Keys = { "led405", "led450", "coolingFan", "heater", "heaterFan" };
  public const double TickSeconds = 2.0;
  public const double FlushSeconds = 60.0;
  public ComponentCounters(DataOptions options, TimeProvider time, Func<MachineState> state, ILogger<ComponentCounters>? logger = null);
  public static Dictionary<string, bool> Sample(MachineState s);
  public void Tick();
  public Task RunAsync(CancellationToken ct);
}
public sealed class ComponentCountersHostedService : BackgroundService { public ComponentCountersHostedService(ComponentCounters counters); }   // ExecuteAsync => counters.RunAsync
```
**Behaviour & rules:**
1. File `data/component_counters.json` = `{"led405": s, "led450": s, "coolingFan": s, "heater": s, "heaterFan": s}` (seconds, rounded to 1 decimal on write). Load: missing keys 0, negatives clamped to 0; load error → warning `"[COUNTERS] load failed (...) - starting from zero"`.
2. `Sample(s)`: `led405 = UvOn && UvWavelength == 405`; `led450 = UvOn && UvWavelength == 450`; `heater = HeaterOut ?? (HeaterPwm > 0 when HeaterPwm not null) ?? IsHeating`; `heaterFan = FanRpmEach["FAN_HEATER"] > 0 || Fans["chamber_heating"] > 0`; `coolingFan = FanRpmEach["FAN_COOLING"] > 0 || Fans["chamber_intake"] > 0`.
3. `Tick()`: state read throws (InvalidOperation/NullReference) → skip; add 2.0 s to each ON component, mark dirty.
4. `RunAsync`: `PeriodicTimer(2 s, TimeProvider)`; after each tick, if dirty and ≥ 60 s since last flush → flush. On cancellation exit and flush once more. `Dispose()` flushes. Flush IO errors → warning.
5. `Hours()` = seconds / 3600 rounded to 1 decimal.
**Configuration:** none.
**Acceptance criteria:**
- With a FakeTimeProvider and UV 405 on: after 60 s advanced, file exists with led405 = 60; heater off stays 0.
- Reload from file; `Hours()` of 5400 s = 1.5.
- Heater fallbacks: HeaterOut wins; else PWM > 0; else IsHeating.
- A throwing state source does not advance counters.
**Tests:** `Platform/ComponentCountersTests` (Sampling_loop_accumulates_seconds_with_a_fake_clock_and_flushes_after_60s, Counters_are_reloaded_from_disk_and_hours_are_rounded, Sample_rules_follow_the_python_fallbacks, Tick_skips_when_the_state_source_throws).
**Reference (source):** `src/SCureBox.Application/Platform/{IComponentCounters,ComponentCounters,ComponentCountersHostedService}.cs`

---

### PLAT-12 — Machine setting stores: LED calibration factors, BOFA extractor policy, serial-number backup
**Summary**
- **What it is for:** Three small saved settings: LED output calibration per zone, whether a BOFA fume extractor is connected, and a backup copy of the serial number.
- **Problem it solves:** LED output varies between units, the extractor setting must be remembered, and the serial number can be lost if storage is replaced.
- **How we solve it:** Save each setting in its own file, and keep a second copy of the serial number on a removable card so it can be restored.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Three small persisted settings: per-zone LED output calibration factors; whether a BOFA fume extractor is connected and its speed reference; and a second copy of the unit's serial number on a removable card so a reinstalled/swapped storage can restore it.
**Depends on:** PLAT-01. Consumers: Application-Process (`CureController` uses `BofaPolicy` and LED factors; BOFA 24 V supply / Err 9048 logic is there), Dvt-Hdt (HDT uses factors), Native UI (`UiSettingsStore` uses `SerialBackup`).
**Files to create:** `Platform/ILedCalibrationStore.cs`, `Platform/LedCalibrationStore.cs`, `Platform/BofaPolicy.cs`, `Platform/SerialBackup.cs` (`SerialBackupFile`, `SerialBackupResult`, `SerialBackup`)
**Public contract:**
```csharp
public interface ILedCalibrationStore {
  IReadOnlyDictionary<string, double> Factors { get; }
  string? Validate(IReadOnlyDictionary<string, double>? factors);
  IReadOnlyDictionary<string, double> Save(IReadOnlyDictionary<string, double> factors);   // throws ArgumentException when invalid
  IReadOnlyDictionary<string, double> Reset();
  Dictionary<string, double> ScaledOutputs(double requestedPower, IReadOnlyDictionary<string, double>? factors = null);
}
public sealed class LedCalibrationStore : ILedCalibrationStore {
  public static readonly IReadOnlyList<string> Zones = { "back", "door", "left", "right" };
  public const double FactorMin = 0.0; public const double FactorMax = 1.5;
  public LedCalibrationStore(DataOptions options, ILogger<LedCalibrationStore>? logger = null);
}
public sealed class BofaPolicy {
  public const int DefaultDutyPercent = 10;
  public BofaPolicy(DataOptions? data = null);     // null = memory only
  public bool Connected { get; } public int DutyPercent { get; }
  public void Choose(bool? connected, int? dutyPercent = null);
}
public sealed class SerialBackupFile { string SerialNumber "serialNumber" = ""; string? DeviceName "deviceName"; string? SavedAt "savedAt"; }
public readonly record struct SerialBackupResult(bool Ok, int Code = 0, string? Detail = null) { static Success; static Failed(int code, string detail); }
public sealed class SerialBackup {
  public const string DefaultDirectory = "/mnt/ssd2/scure";
  public const string FileName = "config_backup.json";
  public SerialBackup(string? directory = null, TimeProvider? timeProvider = null);
  public string Directory { get; } public string Path { get; }
  public bool Available { get; } public bool Exists { get; }
  public string? Read(out string? problem);
  public SerialBackupResult Write(string serial, string? deviceName = null);
}
```
**Behaviour & rules:**
1. LED calibration file `data/led_calibration.json` = `{"back":f,"door":f,"left":f,"right":f}` (indented). Load: defaults 1.0; each saved value clamped to [0, 1.5]; error → warning `"[LED-CAL] load failed (...) - all factors 1.0"`. `Validate`: null → "factors object required"; missing zone → "'<zone>' missing"; NaN or outside → "<zone> factor <v> outside 0-1.5"; else null. `Save`: validate (throw ArgumentException with the reason), round each to 4 decimals, write atomically, activate, log `"[LED-CAL] saved factors: back=1.00, ..."`. `Reset` = Save(all 1.0). `ScaledOutputs(p, f?)` = per zone `round(clamp(p × factor(default 1.0), 0, 100), 2)`. Physical output = clamp(requested × factor, 0..100).
2. BOFA file `data/bofa.json` = `{"connected": bool, "dutyPercent": int}` (indented, atomic). Defaults: not connected, 10 %. Load clamps duty to 0..100; unreadable → not connected, 10 %. `Choose(connected?, duty?)` updates given fields (duty clamped 0..100) and saves (errors swallowed). Semantics (enforced in Process): only when Connected is the extractor ever driven; it runs whenever the air-intake fan runs; duty is a 0–10 V speed reference (PCA9685 ch 10, ×3.3 amplifier, ~0–10.9 V; scale not measured on a unit).
3. SerialBackup: directory = ctor arg ?? env `SCURE_SD_DIR` (trimmed) ?? `/mnt/ssd2/scure`; file `config_backup.json` `{serialNumber, deviceName, savedAt}` (indented). `Available` = directory exists OR its parent exists (never create `/mnt/ssd2` itself — that would put the "backup" on the system disk). `Read(out problem)`: no file → null, problem null; empty serial → null + problem "the backup on the card (<path>) has no serial number in it"; parse error → null + "...could not be read: <msg>" (caller raises Err 3001). `Write`: blank serial → Failed(4003, "no serial number to back up"); not Available → Failed(4003, "no card mounted at <dir>: the serial number has no second copy"); else create dir, write `<path>.tmp` then move over (savedAt = UTC "O"); exception → Failed(4003, "could not write <path>: <msg>"). Note: Origin images have no removable medium and read-only root, so 4003 is raised on every Origin unit (known).
**Configuration:** env `SCURE_SD_DIR`; files above.
**Acceptance criteria:**
- LED: defaults all 1.0; `{back:1.6,...}` rejected; save persists and reloads; corrupt file → 1.0; out-of-range file values clamped.
- BOFA: fresh → Connected false, duty 10; `Choose(true, 150)` → duty 100 and survives a new instance; unreadable file → not connected.
- Serial: written serial reads back; writing again replaces; with no card (parent missing) Read → null and Write → code 4003; damaged file → problem text non-null; empty serial never written; default path is `/mnt/ssd2/scure/config_backup.json` and an unmounted dir is not created.
**Tests:** `Platform/LedCalibrationStoreTests` (Defaults_are_all_one, Validate_rejects_out_of_range_and_missing_zones, Save_persists_atomically_and_reset_restores_defaults, Corrupt_or_out_of_range_file_is_clamped_or_defaulted); `Platform/BofaPolicyTests` (first three tests are store-level; the remainder — extractor follows the intake fan, 24 V only while extracting, Err 9048 switch/connector contradiction — exercise Application-Process `CureController`); `Platform/SerialBackupTests` (6 tests listed above).
**Reference (source):** `src/SCureBox.Application/Platform/{ILedCalibrationStore,LedCalibrationStore,BofaPolicy,SerialBackup}.cs`

---

### PLAT-13 — NFC reader: USB detection, enable setting, Eccel Pepper C2 tag reading
**Summary**
- **What it is for:** Supports the USB NFC reader (Eccel Pepper C2) used to read tags that start a job.
- **Problem it solves:** The machine must know if the reader is there, warn when it is unplugged, and read tags reliably.
- **How we solve it:** Detect the reader by its USB ID without opening it, refuse to enable NFC without a reader, raise error 9052 when it is unplugged, and send one event per tag.

**Project / folder:** `SCureBox.Application.csproj` — `Platform/`
**Goal:** Detect the Eccel Pepper C2 USB NFC reader by USB identity (never opening the port for detection), persist the operator's "NFC enabled" setting (refused while no reader is present), raise Err 9052 when an enabled reader is unplugged, and — as a hosted service — read tags over the reader's binary protocol, raising one event per tag arrival (a tag starts the job it was sent with).
**Depends on:** PLAT-01. Domain (`NfcUid`), Application-Process (`MachineState` with `NfcEnabled`, `NfcReader`, `Alerts`, `AlertDetails`; `NfcReaderDto`).
**Files to create:** `Platform/INfcProbe.cs`, `Platform/UsbNfcProbe.cs`, `Platform/INfcReaderDetector.cs`, `Platform/NfcReaderDetector.cs`, `Platform/NfcSerialLink.cs` (`INfcSerialLink`, `LinuxTtyLink`), `Platform/PepperC2Protocol.cs` (`PepperC2Protocol`, `NfcTagRead`), `Platform/NfcTagReader.cs` (`NfcTagReaderStatus`, `INfcTagReader`, `PepperC2TagReader`)
**Public contract:**
```csharp
// NfcReaderDto (Contracts/MachineState.cs): detected, port, model, serial, usbId, seenSinceBoot
public interface INfcProbe { NfcReaderDto? Scan(); }
public sealed partial class UsbNfcProbe : INfcProbe { public const string UsbId = "0483:5740"; public UsbNfcProbe(); public UsbNfcProbe(bool simulated); }
public interface INfcReaderDetector { bool Enabled { get; } NfcReaderDto Status(); OpResult TrySetEnabled(bool on, out NfcReaderDto reader); MachineState Decorate(MachineState state); }
public sealed class NfcReaderDetector : INfcReaderDetector {
  public const double CacheSeconds = 2.0;
  public const string NotDetectedMessage = "No NFC reader detected - connect the reader (data USB cable) and try again";
  public const string UnpluggedDetail = "The NFC reader was disconnected from USB while in use";
  public NfcReaderDetector(DataOptions options, TimeProvider time, INfcProbe? probe = null, ILogger<NfcReaderDetector>? logger = null);
}
public interface INfcSerialLink : IDisposable { void Open(string path); void Write(ReadOnlySpan<byte> data); int Read(Span<byte> buffer, TimeSpan timeout); void DiscardInput(); }
public sealed class LinuxTtyLink : INfcSerialLink { }
public static class PepperC2Protocol {
  public const byte Start = 0xF5, Ack = 0x00;
  public const byte CmdDummy = 0x01, CmdGetTagCount = 0x02, CmdGetTagUid = 0x03, CmdSetPolling = 0x06, CmdGetVersion = 0x0B;
  public static ushort Crc16(ReadOnlySpan<byte> data);
  public static byte[] Frame(params byte[] body);
  public static bool TryReadHeader(ReadOnlySpan<byte> header, out int bodyLength);
  public static bool CrcMatches(ReadOnlySpan<byte> body, ReadOnlySpan<byte> crc);
  public static int? ParseTagCount(ReadOnlySpan<byte> reply);
  public static NfcTagRead? ParseTagUid(ReadOnlySpan<byte> reply);
  public static string? ParseVersion(ReadOnlySpan<byte> reply);
}
public sealed record NfcTagRead(string Uid, byte TypeCode);
public sealed record NfcTagReaderStatus(bool Connected, string? Firmware, string? TagPresent, string? LastTag, long? LastTagAt, string? Error);
public interface INfcTagReader { event EventHandler<NfcTagRead>? TagPresented; NfcTagReaderStatus Status(); }
public sealed class PepperC2TagReader : BackgroundService, INfcTagReader {
  public static readonly TimeSpan PollInterval = TimeSpan.FromMilliseconds(300);
  public PepperC2TagReader(INfcReaderDetector detector, TimeProvider time, ILogger<PepperC2TagReader>? log = null, Func<INfcSerialLink>? newLink = null, bool? onMachine = null);
  public void Connect(string port); public void PollOnce();
  public static byte[]? Command(INfcSerialLink link, params byte[] body);
}
```
**Behaviour & rules:**
1. `UsbNfcProbe.Scan`: simulated (env `SCURE_SIM_NFC == "1"`, read once at construction) → `{Detected, Port="/dev/ttyACM0", Model="Eccel Pepper C2", Serial="SIM", UsbId}`. Off-Linux → null. Linux: (a) `/dev/serial/by-id` entries (sorted) whose name contains "eccel" or "pepper" (ci), e.g. `usb-Eccel_Eccel_C2_Virtual_ComPort_<serial>-if00`; serial = regex `_([0-9A-Za-z]+)-if\d+$`; Port = resolved final link target; (b) else `/sys/bus/usb/devices/*` with `idVendor:idProduct == 0483:5740` AND `product` containing a hint → Port null, Model=product, Serial=`serial` attr.
2. Detector: setting file `data/nfc.json` `{"enabled": bool}`. `Status()` caches the probe result for 2 s (TimeProvider timestamps); any detection sets the seen-since-boot latch; returns `cache with { SeenSinceBoot }`. `TrySetEnabled(true)` with no reader → Fail(NotDetectedMessage, 9052) and setting unchanged; otherwise set + persist atomically (persist errors only logged), "NFC enabled"/"NFC disabled". `Decorate(state)`: sets `NfcEnabled`, `NfcReader`; only if enabled AND not detected AND seen since boot → add 9052 to `Alerts` (sorted, no duplicate) and `AlertDetails["9052"] = UnpluggedDetail`. A machine that boots without a reader raises nothing.
3. Frame: `F5 | n LE16 | (n XOR 0xFFFF) LE16 | body (cmd + params) | CRC16(body) LE16`, where **n = body length + 2** (counts the CRC). CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final XOR (check value of "123456789" = 0x29B1). `TryReadHeader`: needs 4 bytes, n XOR 0xFFFF == check and n ≥ 2 → bodyLength = n − 2. Reply body = `ACK(0x00)|cmd|...` or `0xFF` error. `ParseTagCount` = reply[2] when len ≥ 3 and ACK. `ParseTagUid`: len ≥ 5, ACK; type = reply[2]; UID = hex of reply[4..] → `NfcUid.Display` (upper-case byte pairs with ':', 2–16 bytes valid) else null. `ParseVersion`: ASCII of reply[2..] trimmed of '\0' and ' '.
4. `Command(link, body)`: `DiscardInput`, write frame; read single bytes until `0xF5` within 1 s total (else null); then exactly 4 header bytes, bodyLength bytes and 2 CRC bytes each within 500 ms; CRC mismatch → null.
5. `LinuxTtyLink.Open`: libc `open(O_RDWR|O_NOCTTY|O_NONBLOCK)`, `tcgetattr` into a 256-byte buffer, `cfmakeraw`, `c_cflag |= CREAD|CLOCAL` (cflag at offset 8), `VMIN=VTIME=0` (c_cc at offset 17, indices 6/5), then set speed **9600 and then 115200** with `tcsetattr(TCSANOW)` and 50 ms sleep after each — mandatory on every open: the C2 only listens after a SET_LINE_CODING, which cdc_acm sends only when the rate changes. Then `tcflush(TCIOFLUSH)`. Constants: B9600=0x0D, B115200=0x1002, CREAD=0x80, CLOCAL=0x800. `Read` uses `poll(POLLIN, ceil(ms))`; readable-but-0 bytes → IOException "the reader closed the port" (unplug). EAGAIN/EINTR retried/ignored. Not `System.IO.Ports.SerialPort` (hung on this device).
6. `PepperC2TagReader.ExecuteAsync`: does nothing off-machine (`onMachine ?? OperatingSystem.IsLinux()`). Loop: if NFC disabled, no reader or no port → disconnect, wait 2 s; else connect if needed and `PollOnce`, wait 300 ms. IO/InvalidOperation/DllNotFound/EntryPointNotFound → disconnect with error, wait 2 s.
7. `Connect(port)`: open; `CmdDummy` must return an ACK reply ("the NFC reader did not answer" / "...refused the first command"); `CmdGetVersion` → firmware; `CmdSetPolling, 0` (reader's own polling off). Log `"[NFC] reader connected on <port>, firmware <fw>"`.
8. `PollOnce`: `CmdGetTagCount` (no reply → IOException); if count > 0, `CmdGetTagUid, 0`. Update present / lastTag / lastTagAt (unix s). Raise `TagPresented` only when a tag is present and its UID differs from the previous look (one event per arrival); handler exceptions are logged, not propagated.
**Configuration:** env `SCURE_SIM_NFC=1`; `data/nfc.json`.
**Acceptance criteria:**
- `Frame(0x01)` equals the bytes the Python reader sent (`F5 03 00 FC FF 01 <crc lo> <crc hi>`).
- Enabling without a reader → 9052; enabled flag survives a new detector instance; the probe is not called again within 2 s.
- Decorate adds 9052 only after a detected reader disappears while enabled.
- A fake link returning a valid UID reply yields `E0:07:C0:...`; a corrupted CRC reply → null; same tag on two polls → one event; reader that does not answer → `Connect` throws and Status().Connected is false.
**Tests:** `Platform/NfcReaderDetectorTests` (Sim_env_simulates_a_reader, Enabling_without_a_reader_is_refused_with_9052, Enabled_flag_persists_and_status_is_cached_for_two_seconds, Decorate_raises_9052_only_when_an_enabled_reader_disappears); `Platform/NfcTagReaderTests` (Frames_match_the_python_reader_that_worked_on_the_unit, Crc_is_ccitt_false, A_uid_reply_from_the_reader_is_read_back, A_corrupted_reply_is_refused, A_tag_is_reported_once_per_arrival, A_reader_that_does_not_answer_is_not_connected, One_tag_however_it_is_written, Not_a_tag) with a scripted fake `INfcSerialLink` (`Inject` replies).
**Reference (source):** `src/SCureBox.Application/Platform/{INfcProbe,UsbNfcProbe,INfcReaderDetector,NfcReaderDetector,NfcSerialLink,PepperC2Protocol,NfcTagReader}.cs`

---

### PLAT-14 — Cure report builder (self-contained HTML + inline SVG line charts and timing diagram)
**Summary**
- **What it is for:** Builds the printable Process Report for one cure run.
- **Problem it solves:** Users need a clear record of each cure: settings, measured times, alerts and temperature, LED and fan data.
- **How we solve it:** Create one self-contained HTML page with built-in charts and a timing diagram, plus a short summary saved next to it.

**Project / folder:** `SCureBox.Application.csproj` — `Reports/`
**Goal:** Build the printable, self-contained HTML "Process Report" of one cure run — a port of the React `src/lib/cure-report.ts` with Chart.js replaced by inline SVG — including metric cards, phase ribbon, program-steps table with measured phase times, a logic-analyser-style timing diagram, run alerts, chamber/LED/fan charts and sensor/fan issue notes; plus the summary object stored next to it.
**Depends on:** PLAT-02 (`IPhaseTimingStore`). Domain (`CureLog`, `TelemetrySample`, `CureStep`, `ProcessType`, `TimerMode`, `PhaseTiming`, `SensorIssue`, `FanIssue`, `RunAlert`, `ErrorRegistry`, `ErrorCodes.SensorDisconnectedOf/FanFailureOf/FanWearOf`, `HardwareNames.SupervisedSensors`, `Fan` enum).
**Files to create:** `Reports/CureReportContext.cs` (`CureReportContext`, `CureReportSummary`, `CureReportDocument`, `ICureReportBuilder`), `Reports/CureReportBuilder.cs`, `Reports/SvgLineChart.cs`, `Reports/SvgTimingDiagram.cs` (internal), `Reports/ReportText.cs` (internal)
**Public contract:**
```csharp
public sealed record CureReportContext {
  string? SystemName;  string? SerialNumber;  string? MaterialName;
  IReadOnlyList<CureStep> Steps = [];  IReadOnlyList<PhaseTiming> PhaseTimings = [];
  string? FirmwareVersion;  ErrorRegistry? Errors;  DateTimeOffset? GeneratedAt;
  public static IReadOnlyList<PhaseTiming> TimingsFor(IPhaseTimingStore store, string runId);   // RunId == runId
}
public sealed record CureReportSummary { materialName, status, duration(double?), steps(int), stepsCompleted(int), targetTemp(double?), serialNumber, startedAt, endedAt, sensorIssues, fanIssues }
public sealed record CureReportDocument(string Html, CureReportSummary Summary, string FileName);
public interface ICureReportBuilder { CureReportDocument Build(CureLog run, CureReportContext ctx); }
public sealed class CureReportBuilder : ICureReportBuilder {
  public CureReportBuilder(TimeProvider time);
  public static string FileName(string materialName, string? startedAt, DateTimeOffset generatedAt);
}
public sealed class SvgLineChart {   // public (HDT uses it too)
  public const string GridColor = "#E6ECF2", AxisColor = "#5A6B7A", FontFamily = "Inter, 'Helvetica Neue', Arial, sans-serif";
  public sealed class Series { Label; IReadOnlyList<double?> Values; Stroke="#000"; Fill; StrokeWidth=2; PointRadius; PointFill; PointStroke; PointStrokeWidth=1; Tension; SpanGaps; Stepped; Dash; RightAxis; }
  public sealed class Band { IReadOnlyList<bool> On; Fill="rgba(0,0,0,0.1)"; double Top; }
  int Width=800; int Height=260; string? Id; string? Title; IReadOnlyList<double> X; string XTitle="Time (min:sec)"; int MaxXTicks=25;
  double YMin; double YMax=100; double YStep=10; string YTitle="Temperature (°C)"; double? Y2Min, Y2Max; double Y2Step=20; string Y2Title="";
  List<Series> Lines; List<Band> Bands;
  public string Render();
  public static (double Min, double Max, double Step) NiceRange(double dataMin, double dataMax, bool beginAtZero);
}
internal sealed class SvgTimingDiagram { LaneBackground="#F7F9FB"; Lane{Label, Caption, Height=30}; SegmentLane{Segments (Start,End,Text,Color)}; AnalogSeries{Label,Values,Stroke,StrokeWidth=1.5,Dash}; AnalogLane{YMin,YMax=100,YStep=10,Unit="°C",Series}; LevelLane{Values,Max=100,Colors,Color="#0072CE",Line,LineMax=1,LineColor="#0A1929",Summary}; DigitalLane{Values(bool?),OnColor="#16A34A",OnText="ON"}; Width=1000; LabelWidth=168; SummaryWidth=118; X; Lanes; Markers; Render(); internal static List<double> TimeTicks(double xMin, double xMax); }
internal static class ReportText { Esc, N(double), N(int), C1, F(v,decimals), C (svg coord), MinSec, MinutesSeconds, HmsDur, ReportDate, SafeFileToken }
```
**Behaviour & rules:**
1. `Build` throws `InvalidOperationException("No telemetry recorded")` for zero samples. materialName = ctx.MaterialName (non-blank) else run's; systemName = ctx.SystemName else "sCure"; serial = ctx ?? run ?? "------"; generatedAt = ctx.GeneratedAt ?? local now; date text `dd/MM/yyyy, HH:mm:ss`.
2. Derived values: sampleInterval = t[1]−t[0] (5 if single sample); UV 405 time = count(UvOn && UvType=="405nm") × interval → "Xm Ys" or "Not used" (same for "450nm"). maxTemp for scale = max(measured chamber, 40); uvScale = maxTemp+10. Duration card = `MinutesSeconds(floor(duration))` or "— —".
3. Status: class ok/stopped(aborted)/warn(running)/err; label "Stopped" for aborted else capitalised; pill colours completed `#DCFCE7/#166534/#86EFAC/#16A34A`, aborted `#FFEDD5/#9A3412/#FDBA74/#EA580C`, running `#FEF3C7/#92400E/#FCD34D/#D97706`, else `#FEE2E2/#991B1B/#FCA5A5/#DC2626`.
4. Document order: `<title>Cure Report · <material> · Stratasys</title>`; brand bar (inline STRATASYS SVG logo, product name, "Process Report", "S/N · <serial>", "Report · <first 8 chars of run id>", date); title block "Cure Report — <material>", subline "Post-process curing cycle · UV + thermal · 4-LED chamber", material chip, status pill; metric grid cards in order: Status, Duration, Steps ("<completed> / <steps>"), Max Temp (measured max, 1 decimal, "—" if none), "Cure · 405 nm", "Bleaching · 450 nm", "Temperature Sensors" ("All sensors read" / "n/a" when running / "<labels> disconnected"), "Fans" ("All fans at nominal" / "n/a" / "<label> -<deficit> %"); phase ribbon (labels Cure → "Cure · 405 nm", Bleacher → "Bleaching · 450 nm", Nitrogen → "N₂ Purge"; class `phase-<lower>`); Program steps table; Timing diagram; Alerts during the run; Chamber chart; LED chart (only if any LED temp); Fan chart (only if any fan RPM); Sensor & fan notes; footer "<system> · Report generated <date>", "Software v<firmware or 'unknown'> · Confidential — for internal process review".
5. Program steps rows: from ctx.Steps (each matched to the first unused timing with same Step and (null or same Process), else unused timing with null Step and same Process); mode = cooling mode lower-case for Cooling, "on-ramp"/"on-target" for UV steps, UV % = `EffectiveUvIntensity` for UV steps; else rows from timings; else from run phases. Columns Step, Process, Target ("N °C"), UV ("N %"), Planned ("N min" when > 0), Measured (`MinSec(round(seconds))`), Ramp, Chamber ("a → b °C"), Mode; "—" when absent. Sub-line notes whether measured times exist.
6. Timing diagram (≥ 2 samples): SegmentLane "Program step" (height 24) from timings sorted by StartedAt, offset from first start + t[0], end from EndedAt or start+Seconds, colours Heating `#EA580C`, Cure `#6D28D9`, Bleacher `#0891B2`, Cooling `#0D9488`, Drying/Dry `#1D4ED8`, other `#64748B`, step starts as markers; AnalogLane "Temperatures" (height 150, `NiceRange(min,max,false)`, YStep = step×2) with Chamber `#EA580C` 2.5, Left `#0072CE`, Right `#DC2626`, Back `#D97706`, Door `#16A34A` (1.4) from `Temps[key]` else chamberTemp / LedTemps, plus Target dashed "6 4" `#0A1929`; LevelLane "Heater" ("PI output %", h 34, `#DC2626`, "max N %"); per fan (FAN_HEATER "Heater fan" `#DC2626`, FAN_COOLING "Chamber cooling fan" `#0072CE`, FAN_LEFT `#16A34A`, FAN_RIGHT `#D97706`, FAN_BACK `#7C3AED`, FAN_DOOR `#0891B2`) duty bars + RPM line (LineMax = max(5000, maxRpm)); per LED zone back/door/left/right output % coloured by wavelength (405nm `#6D28D9`, 450nm `#0891B2`, else `#64748B`), from `UvOutputs` when recorded else `UvIntensity ?? 100` while UvOn ("UV on (zone not recorded)"); DigitalLanes Damper (`#0D9488` OPEN), N₂ (`#64748B` ON, only if any true), Door (`#DC2626` OPEN, only if ever open). Lanes without data are omitted (older runs).
7. Charts: chamber (YMin 0, YMax uvScale+5, step 10; UV bands 405 `rgba(109, 40, 217, 0.18)` and 450 `rgba(8, 145, 178, 0.15)` up to uvScale; line `#EA580C` tension 0.3 points 2.5); LED (top = ceil(max(ledMax,5)/5)·5, +5 if not above max; step 5; null temps drawn as 0); fan (top = ceil(max(fanMax,1000)/1000)·1000, +1000 if not above; step 1000; sub-line "<label>: avg N RPM (min, max, running P % of the run)" or "<label>: off").
8. Issue notes: sensor → `Err <SensorDisconnectedOf(sensor)>` when the sensor's UI name is in `HardwareNames.SupervisedSensors`, else 9001 (critical) / 9050; fan → `FanFailureOf(fan)` (critical) / `FanWearOf(fan)` when the name parses as `Fan`, else 9002 / 9051. Names from `ErrorRegistry.Get(code).Message` else "Error <code>". Run alerts: "<MinutesSeconds(t)> · Err <code> · <name> — <message>", class err when no code or severity "critical".
9. `SvgLineChart.Render`: plot area left 56, right Width−16 (Width−56 with right axis), top 12, bottom Height−46; clipPath; y grid every YStep; x ticks every ceil(n/min(MaxXTicks,19)) samples labelled `MinSec`; bands drawn as rects from first on-sample to the sample after the last; lines split at nulls unless SpanGaps; Chart.js-style spline control points for tension > 0; stepped paths; optional fill to baseline; points as circles. `NiceRange`: raw=(max−min)/10, step ∈ {1,2,5,10}×10^k, min floored, max ceiled and +step if not above data.
10. `SvgTimingDiagram`: lanes stacked with gap 4, axis height 34, plot from LabelWidth+8 to Width−SummaryWidth−8; x span includes one extra sample step; level lanes merge equal consecutive values into one bar; TimeTicks step = first of {15,30,60,120,300,600,900,1800,3600} s giving ≤ 12 ticks.
11. `FileName` = `scure-report-<SafeFileToken(material)>-<yyyyMMdd-HHmm>.html` from run start, or generatedAt when unparsable. SafeFileToken keeps letters/digits/`.`/`-`/`_`, others → `-`, trims `-`/`.`, empty → "material".
12. Numbers: invariant culture; `N` = shortest round-trip; `C1` one decimal away-from-zero; `MinSec` = "m:ss"; `MinutesSeconds` = "Xm Ys"; all text HTML-escaped (`& < > " '`). CSS: Stratasys tokens (`--sts-blue-900 #0A1929`, `--sts-blue-700 #003DA5`, `--sts-blue-500 #0072CE`, grays `#1C2733/#5A6B7A/#8A97A3/#C9D3DC/#DDE4EB/#E6ECF2/#F4F7FA`, success `#16A34A`, warning `#D97706`, error `#DC2626`, cure `#6D28D9`, bleach `#0891B2`, heat `#EA580C`, cool `#0D9488`, dry `#1D4ED8`), 6-column info grid (3 under 880 px, 2 under 520 px), print media rule; class names `brandbar, title-block, status-pill, info-grid, info-card, phases, phase-badge, chart-section, chart-container, legend-row, table.steps, ul.notes, footer` (copy the CSS block from the reference file verbatim).
13. Output is deterministic for a fixed `GeneratedAt`/clock.
**Configuration:** none.
**Acceptance criteria:** see tests; additionally the HTML contains no external resource (no `<script src>`, no `<link>`), and `Summary` carries exactly the keys listed.
**Tests:** `Reports/CureReportBuilderTests` (Report_has_the_react_sections_labels_and_values, Max_temp_card_shows_the_measured_maximum_with_one_decimal, Summary_carries_the_keys_the_react_ui_posts, Alerts_raised_during_the_run_are_listed_with_their_time, Output_is_deterministic_for_a_fixed_clock, Stopped_run_reads_orange_and_issues_are_named_from_the_registry, Missing_context_falls_back_to_the_run_and_hides_optional_charts, Timing_diagram_shows_phases_thermistors_heater_every_fan_and_led_zone_on_one_time_axis, Older_runs_get_the_timing_lanes_they_have_data_for, Timing_ticks_stay_round_and_few, No_telemetry_is_refused_like_the_react_ui, File_name_uses_the_report_time_when_the_start_is_unparsable).
**Reference (source):** `src/SCureBox.Application/Reports/{CureReportContext,CureReportBuilder,SvgLineChart,SvgTimingDiagram,ReportText}.cs`

---

### PLAT-15 — HDT calibration report (HTML + CSV) and report persistence / USB export
**Summary**
- **What it is for:** Builds the material HDT calibration report and helps save and export cure reports.
- **Problem it solves:** Calibration results must be readable and exportable, and cure reports must be kept and copied to USB.
- **How we solve it:** Create an HTML report with a chart plus a CSV file, save the cure report in the run store when possible, and export it to USB with a clear result message.

**Project / folder:** `SCureBox.Application.csproj` — `Reports/`
**Goal:** Render the Material HDT Calibration report (port of `src/lib/hdt-report.ts` with an inline SVG chart, and the CSV layout of `hdt_calibration.py csv_report`), and provide the helper that persists a built cure report in the run store (best effort) and exports it to the USB drive, returning an outcome the UI shows.
**Depends on:** PLAT-06 (`ISystemService.ExportReport`), PLAT-02 (`ICureRunStore`), PLAT-14 (`SvgLineChart`, `ReportText`, `CureReportDocument`). Dvt-Hdt (`HdtStatusDto`, `HdtSample`, `HdtLevelResult`, `HdtConfigDto`, boost/picolog DTOs).
**Files to create:** `Reports/HdtReportBuilder.cs` (`IHdtReportBuilder`, `HdtReportBuilder`), `Reports/ReportPersistence.cs` (`ReportExportOutcome`, `ReportPersistence`), `Reports/ReportServiceCollectionExtensions.cs`
**Public contract:**
```csharp
public interface IHdtReportBuilder { string BuildHtml(HdtStatusDto status, string factorsLine); string BuildCsv(HdtStatusDto status); }
public sealed class HdtReportBuilder : IHdtReportBuilder {
  public static readonly string[] Zones = { "back", "door", "left", "right" };
  public HdtReportBuilder(TimeProvider time);
  public static string FileName(DateTimeOffset now, string extension = ".html");   // hdt-calibration-report-yyyy-MM-dd<ext>
  public static IReadOnlyDictionary<string, double> ApplyLedFactors(double requestedPower, IReadOnlyDictionary<string, double> factors);
}
public sealed record ReportExportOutcome { bool Ok "ok"; bool Usb "usb"; string Message "message" = ""; int? Code "code"; string? Path "path"; string? ReportId "reportId"; string FileName "fileName" = ""; }   // code/path/reportId omitted when null
public static class ReportPersistence {
  public const string SavedToUsb = "Saved to USB";
  public static ReportExportOutcome SaveAndExport(ICureRunStore store, ISystemService system, string extId, CureReportDocument doc, ILogger? logger = null);
  public static ReportExportOutcome Export(ISystemService system, string fileName, string content, ILogger? logger = null);
}
public static class ReportServiceCollectionExtensions { public static IServiceCollection AddSCureBoxReports(this IServiceCollection services); }
```
**Behaviour & rules:**
1. HDT HTML: title "HDT Calibration Report · sCure"; final status labels COMPLETED "Completed", HDT_LIMIT_REACHED "HDT Limit Reached", ABORTED_BY_USER "Aborted by User", SENSOR_ERROR "Sensor Error", NOT_CONVERGED "Not Converged" (default when null); pill green for COMPLETED, amber for HDT_LIMIT_REACHED/NOT_CONVERGED, red otherwise. Sublines: "Calibrated system LED power sweep · PicoLog TC-08 · Channel CH1 · <deviceInfo or 'PicoLog TC-08'>", "Started … · Ended … · Duration <HmsDur>". Cards: Material HDT, Safety Margin, Max Model Temp (= HDT − margin), Max Measured (1 decimal), Recommended Power ("N%" or "None"), "Boost <power or 90>%: <start or 35>°C → <target 1 decimal>°C" with time or "N/A" (+ method, note), Levels Tested (non-NOT_TESTED / total). Factors table (Factor 2 decimals per zone; "Output @ R%" row = `ApplyLedFactors(R)` 1 decimal) + optional `factorsLine`. Chart "Model temperature vs time": samples downsampled with stride ceil(n/2000) (always keeping the last), y from `NiceRange` over raw/avg/HDT/HDT−margin, right axis 0–100 step 20 "System LED power (%)"; series Raw CH1 `#0072CE` w1, Average `#D97706` w2.5, Material HDT `#DC2626` dash "6 4", HDT − margin `#EA580C` dash "3 3", System power % `#8A97A3` stepped on right axis. Results table per level (step labels PASS, RUNNING, NOT_CONVERGED → "NOT CONVERGED", HDT_LIMIT → "HDT LIMIT", ABORTED, NOT_TESTED → "NOT TESTED"; css class `st-<status>`). Footer: "Stability: ±<band/2>°C band (<band>°C total) for <min> min · Max stabilization <min> min · Sampling <s>s / avg <s>s" from `HdtConfigDto`.
2. `ApplyLedFactors(p, f)` = per zone `min(100, max(0, p × (f[z] or 1.0)))` (no rounding).
3. HDT CSV (comma separated, `\n` lines; cells quoted with `"` doubling when they contain `,`, `"` or newline; doubles invariant; null = empty): metadata rows `# sCure Material HDT Calibration Report`, `# Started,<>`, `# Ended,<>`, `# Device,<device>,Channel,CH1`, `# Material HDT degC,<hdt>,Safety Margin degC,<m>`, `# Final Status,<final or state>`, `# Recommended System LED Power %,<>`, `# Max Measured Temp degC,<>`, blank; `# Per-level results`, header `System Power %,Status,Start Temp degC,Stable Temp degC,Min Temp degC,Max Temp degC,Time To Stability s,Duration s,Started,Ended,Back Output %,Door Output %,Left Output %,Right Output %` + rows; blank; sample header `Timestamp,Elapsed Time s,Test Step,Requested System LED Power %,Back LED Factor,Door LED Factor,Left LED Factor,Right LED Factor,Actual Back LED Output %,Actual Door LED Output %,Actual Left LED Output %,Actual Right LED Output %,Raw CH1 Temperature degC,Average Temperature degC,Material HDT degC,HDT Safety Margin degC,Stability Status,Test Status` + one row per sample (Test Step = step+1 when step ≥ 0; Test Status = results[step].Status when in range).
4. `SaveAndExport`: null args → ArgumentNullException. Try `store.SaveReport(extId, CureReport{Content=Html, Summary=SerializeToElement(Summary), Format="html"})`; IO/Access/InvalidOperation/Json errors → warning `"[REPORT] Could not persist the report of run …"` and `ReportId = null`. Then `Export(...) with { ReportId }`.
5. `Export`: call `system.ExportReport(fileName, content)`; exceptions IO/Access/InvalidOperation → `{Ok=false, Usb=false, Message}`. `res.Ok` → `{Ok=true, Usb=true, Message = res.Message or "Saved to USB" when blank, Path}`. Not ok with a code (9081/9082) → `{Ok=false, Usb=true, Code}`; not ok without code → `{Ok=false, Usb=false}`. `FileName` always set.
6. `AddSCureBoxReports`: `TryAddSingleton(TimeProvider.System)`, `TryAddSingleton<ICureReportBuilder, CureReportBuilder>()`, `TryAddSingleton<IHdtReportBuilder, HdtReportBuilder>()`.
**Configuration:** none.
**Acceptance criteria:**
- HDT HTML contains the React section titles/labels; deterministic for a fixed clock; an empty run (no samples/results) renders.
- CSV matches the Python layout line-for-line for a fixture; a cell `a,b` is written `"a,b"`.
- File names: `hdt-calibration-report-2026-11-04.html` / `.csv`.
- SaveAndExport saves then exports; blank export message reads "Saved to USB"; 9081/9082 keep their code with `usb:true`; a throwing store still exports; a throwing system → `usb:false`.
**Tests:** `Reports/HdtReportBuilderTests` (Html_has_the_react_sections_labels_and_values, Html_is_deterministic_and_handles_an_empty_run, Csv_matches_the_python_layout, Csv_quotes_cells_with_separators, File_names_follow_the_react_pattern); `Reports/ReportPersistenceTests` (Saves_the_report_then_exports_to_usb, Blank_export_message_reads_saved_to_usb, No_usb_and_write_failure_keep_their_codes, Store_failure_is_best_effort_and_service_exceptions_are_not_usb) using `Fakes/FakeSystemService`.
**Reference (source):** `src/SCureBox.Application/Reports/{HdtReportBuilder,ReportPersistence,ReportServiceCollectionExtensions}.cs`

---

### PLAT-16 — Platform DI composition and shipped config files (system.json, origin.json, versions.json)
**Summary**
- **What it is for:** Connects all the platform parts together when the app starts, and defines the read-only config files shipped with the app.
- **Problem it solves:** Without one central setup, services would be missing or wired wrongly, and the app would not know its default settings.
- **How we solve it:** One setup method registers storage, platform services, background services and report builders, and the app reads its bundled config files from one folder.

**Project / folder:** `SCureBox.Application.csproj` — `PlatformServiceCollectionExtensions.cs`; repo `config/`
**Goal:** One extension method that wires persistence, platform services, hosted services and report builders into the host container, and the bundled read-only configuration files the platform and UI read from `DataOptions.ConfigDir`.
**Depends on:** PLAT-01…PLAT-15. Api (calls `AddSCureBoxPlatform` in `ScureApiHost`), Application-Process (`ICureController` for `MachineStateSource`; registers `NetworkPolicy`, `BofaPolicy`, `FrozenReadingStore`, `PlannedRestart`), Native UI (consumers of system/origin/versions json, `SerialBackup` registration), Domain (`ErrorRegistry.Load`).
**Files to create:** `PlatformServiceCollectionExtensions.cs`; `config/system.json`, `config/origin.json`, `config/versions.json` (also present, other areas: `config/errors.json` Domain, `config/presets.json` Recipe/Domain, `config/components.json` Hardware)
**Public contract:**
```csharp
public static class PlatformServiceCollectionExtensions {
  public static IServiceCollection AddSCureBoxPlatform(this IServiceCollection services, DataOptions data, DatabaseOptions database);
}
```
**Behaviour & rules:**
1. Registrations (in order): `TryAddSingleton(TimeProvider.System)`; singletons `data`, `database`; `StoreSelector(data, database, TimeProvider, ILoggerFactory?)`; `IMaterialStore`/`IPrintHistoryStore`/`ICureRunStore` forwarded from the selector (backend fixed at first resolution); `IPhaseTimingStore → JsonPhaseTimingStore` (always JSON); `ErrorRegistry.Load(data.ErrorsPath)` singleton; `TryAddSingleton<MachineStateSource>(sp => () => sp.GetRequiredService<ICureController>().GetState())` (lazy so the controller may be registered later); `ComponentCounters` (+ `IComponentCounters`) + hosted `ComponentCountersHostedService`; `ILedCalibrationStore → LedCalibrationStore`; `INfcProbe → UsbNfcProbe`; `INfcReaderDetector → NfcReaderDetector`; `TryAddSingleton<InternetReachability>(_ => () => null)`; `INetworkService → NetworkService`; `IUsbMounts → UsbMounts`; `ISystemService → SystemService`; `IScriptRunner → BashScriptRunner`; `ISupervisorClient → HttpSupervisorClient`; `IUpdateService → UpdateService`; `TryAddSingleton(_ => new HttpClient())`; `CloudReportDeletions`; `CureHistoryDeletion`; `CloudSyncAgent` as itself, as `ICloudSync` and as hosted service (same instance); `PepperC2TagReader` as itself, `INfcTagReader` and hosted service; `IDevEventLog → DevEventLog`; `AddSCureBoxReports`.
2. Note for rebuilders: `SystemService`/`UpdateService` constructors accept an optional `ISupervisorClient`; with default DI constructor selection the registered `HttpSupervisorClient` is injected (OPEN QUESTION: confirm the container picks the longest satisfiable ctor — it does in Microsoft.Extensions.DependencyInjection).
3. `config/system.json` (read by Native UI `UiSettingsStore.SystemConfig`; replaced by every install, so per-unit values set on the machine live in the data dir instead): `{ "serialNumber": "", "firmware": "0.1.0", "lastBoot": "2026-03-29T08:23:00", "deviceName": "OR200001", "leadOnTimeHours": 10, "model": "S-Cure A", "hardwareRevision": "CM5-rev1.0", "manufacturer": "S-Cure Ltd.", "organizationId": "", "setupComplete": false }`.
4. `config/origin.json` (read by Native UI `OriginBrowserSignIn.OriginConfig`): `_comment` (a headless browser opens `sign_in_url`, its picture is shown in the Sign-in dialog, taps/keyboard go back to the page, the app reads only `organizationId` from site replies whose URL contains `api_host`; nothing about the sign-in is stored), `sign_in_url` "https://app.origin.io/models", `api_host` "api.origin.io", `browser_path` "", `run_as` "scure", `language` "en-US", `reveal_delay_sec` 10, `fade_ms` 900, `timeout_sec` 300. Other `OriginConfig` keys with code defaults: `mode` "auto", `keyboard` "button", `frame` "fullscreen". No credentials are stored.
5. `config/versions.json` (read by Native UI `VersionsDialogViewModel.LoadHistory`, case-insensitive): `{ "_comment": "...", "history": [ { "version": "1.0.152", "date": "2026-11-04", "notes": ["...", ...] }, ... ] }` newest first. Release rule: every release bumps the repo-root `VERSION` file AND prepends an entry here; `SystemService.Version()` reads `VERSION` next to the executable.
**Configuration:** `ConfigDir` files above; env vars consumed transitively: `SCURE_DATA_DIR`, `DATABASE_URL`, `SCURE_SUPERVISOR_URL`, `SCURE_SIM_NFC`, `SCURE_SD_DIR`.
**Acceptance criteria:**
- A host calling `AddSCureBoxPlatform` + a registered `ICureController` resolves every interface above; `ICloudSync` and the hosted `CloudSyncAgent` are the same instance; same for `INfcTagReader`/`PepperC2TagReader`.
- With no `DATABASE_URL`, `ICureRunStore` is `JsonCureRunStore`.
- `config/system.json`, `origin.json`, `versions.json` parse with the schemas above.
**Tests:** No dedicated test class in this project (composition is exercised by Api host tests — Api area). Add a composition test that builds a `ServiceCollection` with a fake `ICureController` and resolves all registrations.
**Reference (source):** `src/SCureBox.Application/PlatformServiceCollectionExtensions.cs`, `src/SCureBox.Application/ProcessServiceCollectionExtensions.cs` (lines registering NetworkPolicy/BofaPolicy/FrozenReadingStore/PlannedRestart), `config/system.json`, `config/origin.json`, `config/versions.json`, `src/SCureBox.Ui/Services/UiSettingsStore.cs`, `src/SCureBox.Ui/Services/OriginBrowserSignIn.cs`, `src/SCureBox.Ui/ViewModels/Dialogs/VersionsDialogViewModel.cs`
