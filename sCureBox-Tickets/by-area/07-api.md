## API — overview

`SCureBox.Api` (assembly name `scurebox`, namespace root `SCureBox.Api`) is the HTTP host of the firmware. It composes the
Hardware, Application-Process and Application-Platform layers into one ASP.NET Core minimal-API `WebApplication`, serves the
`/api` contract the React kiosk UI and the native Avalonia UI depend on, serves the built React UI as static files with an SPA
fallback, and hosts two safety liveness services (systemd watchdog keep-alive and the output-watchdog heartbeat file). The same
`ScureApiHost.Build(...)` is used by the API executable and in-process by the native UI (which adds its own `/api/ui/*` routes
through `IApiEndpointMapper`).

Global conventions (detailed in API-02):
* Port 3001 (env `PORT`) on all interfaces, unless `ASPNETCORE_URLS` is set. CORS wide open. No authentication, no PIN, no
  SSE / WebSocket — the UI polls. The only access control is a loopback check on a few DVT routes (API-12).
* Almost every response is HTTP 200, also on logical failure: `{ok:false, code?, message}`. Exceptions to 200 are listed per route.
* Command routes take query-string parameters; data routes take JSON bodies (read leniently: bad / empty JSON = "no body").
* An unhandled exception under `/api` becomes `200 {ok:false, message:<exception message>}`.
* While a DVT hang is active every non-GET/HEAD `/api/*` request answers `409` except an allow-list (API-12).

Ticket list: API-01 host/bootstrap · API-02 HTTP infrastructure · API-03 liveness services · API-04 static UI ·
API-05 state & NFC · API-06 cure process commands · API-07 direct hardware & diagnostics · API-08 data (materials, print
history, cure runs, phase timings) · API-09 recipe runner · API-10 system, network, cloud · API-11 developer mode ·
API-12 DVT bench endpoints & hang gate · API-13 integration test harness.

### All routes

| Method | Route | Ticket | Notes |
|---|---|---|---|
| GET | `/api/state` | API-05 | 1 Hz poll, not logged |
| GET | `/api/nfc` | API-05 | |
| POST | `/api/nfc?on=` | API-05 | 9052 |
| POST | `/api/cure/heat?target=` | API-06 | 7001 / hw result |
| POST | `/api/cure/dry?target=` | API-06 | 7001 (30–50) |
| POST | `/api/cure/cure-405?target=&intensity=` | API-06 | 7001/7002 |
| POST | `/api/cure/cure-450?target=&intensity=` | API-06 | 7001/7002 |
| POST | `/api/cure/uv-only?intensity=&wavelength=&vent=` | API-06 | 7002, bad wavelength no code |
| POST | `/api/cure/cool?target=&mode=` | API-06 | 7001/7003 |
| POST | `/api/cure/nitrogen?on=` | API-06 | hw result |
| POST | `/api/cure/stop?immediate=` | API-06 | always ok |
| POST | `/api/door/open` | API-07 | always ok |
| POST | `/api/door-abort/ack` | API-07 | always ok |
| POST | `/api/watchdog/ack` | API-07 | Err 9017 ack, always ok |
| POST | `/api/fans/ack` | API-07 | always ok |
| POST | `/api/chamber/temperature?target=` | API-07 | 7001 |
| POST | `/api/chamber/stop` | API-07 | always ok |
| POST | `/api/rgb/alerts?critical=&warning=` | API-07 | |
| POST | `/api/rgb?on=&color=` | API-07 | envelope |
| POST | `/api/fans/override?fan=&on=` | API-07 | |
| POST | `/api/fans/{fan}?speed=` | API-07 | always ok |
| POST | `/api/damper/{action}` | API-07 | always ok |
| POST | `/api/uv?on=&intensity=&wavelength=` | API-07 | 7002 / hw result |
| POST | `/api/bofa?on=` | API-07 | hw result |
| GET | `/api/bofa/policy` | API-07 | |
| POST | `/api/bofa/policy?connected=&dutyPercent=` | API-07 | 7002 |
| POST | `/api/diagnostics/fan-test?fan=` | API-07 | |
| POST | `/api/diagnostics/led-test?seconds=&min_rise=&wavelength=` | API-07 | |
| GET | `/api/materials/presets` | API-08 | |
| GET | `/api/materials/user` | API-08 | |
| POST | `/api/materials/user` | API-08 | 400 on non-array |
| GET | `/api/print-history` | API-08 | |
| POST | `/api/print-history` | API-08 | 400 on non-array |
| GET | `/api/cure-history` | API-08 | |
| DELETE | `/api/cure-history/{id}` | API-08 | 404 |
| DELETE | `/api/cure-history` | API-08 | |
| GET | `/api/phase-timings` | API-08 | |
| POST | `/api/cure-runs/{extId}/start` | API-08 | |
| POST | `/api/cure-runs/{extId}/telemetry` | API-08 | |
| POST | `/api/cure-runs/{extId}/finish` | API-08 | |
| POST | `/api/cure-runs/{extId}/report` | API-08 | |
| GET | `/api/cure-runs/{extId}/report` | API-08 | 404 |
| POST | `/api/cure-runs/{extId}/phase` | API-08 | 400 |
| GET | `/api/recipe/status` | API-09 | |
| POST | `/api/recipe/start` | API-09 | |
| POST | `/api/recipe/pause` | API-09 | |
| POST | `/api/recipe/resume` | API-09 | |
| POST | `/api/recipe/abort` | API-09 | |
| POST | `/api/recipe/skip` | API-09 | |
| POST | `/api/system/reboot` | API-10 | |
| POST | `/api/system/shutdown` | API-10 | |
| POST | `/api/system/datetime` | API-10 | |
| GET | `/api/system/version` | API-10 | |
| GET | `/api/system/network-time` | API-10 | |
| POST | `/api/system/network-time` | API-10 | 400 |
| POST | `/api/system/export-logs` | API-10 | 9083 |
| POST | `/api/system/export-csv` | API-10 | 9081/9082 |
| POST | `/api/system/export-report` | API-10 | 9081/9082 |
| GET | `/api/system/update/manifest` | API-10 | 404 |
| GET | `/api/system/update/package` | API-10 | file / 404 |
| POST | `/api/system/update` | API-10 | |
| GET | `/api/network/policy` | API-10 | |
| POST | `/api/network/policy` | API-10 | |
| POST | `/api/cloud/config` | API-10 | 400 |
| GET | `/api/network/status` | API-10 | |
| POST | `/api/network/diagnostics` | API-10 | 9080/9085 |
| POST | `/api/network/static` | API-10 | 9084 |
| POST | `/api/dev/log` | API-11 | |
| GET | `/api/dev/led-calibration` | API-11 | |
| POST | `/api/dev/led-calibration` | API-11 | 400 |
| POST | `/api/dev/led-calibration/reset` | API-11 | |
| POST | `/api/dev/led-power` | API-11 | 400 |
| GET | `/api/dev/picolog/status` | API-11 | |
| POST | `/api/dev/picolog/release` | API-11 | |
| POST | `/api/dev/picolog/resume` | API-11 | |
| POST | `/api/dev/hdt/start` | API-11 | |
| POST | `/api/dev/hdt/abort` | API-11 | |
| POST | `/api/dev/hdt/reset` | API-11 | |
| GET | `/api/dev/hdt/status?samplesFrom=` | API-11 | |
| GET | `/api/dev/hdt/report.csv` | API-11 | text/csv file |
| GET | `/api/dvt/meter?identify=` | API-12 | |
| GET | `/api/dvt/bench` | API-12 | |
| POST | `/api/dvt/bench/claim?who=&lease_s=` | API-12 | |
| POST | `/api/dvt/bench/release?who=` | API-12 | |
| POST | `/api/dvt/meter/wavelength?nm=` | API-12 | |
| POST | `/api/dvt/uv-sweep?...` | API-12 | |
| GET | `/api/dvt/uv-sweep?samples=` | API-12 | |
| POST | `/api/dvt/uv-sweep/abort` | API-12 | |
| POST | `/api/dvt/uv-off?...` | API-12 | |
| GET | `/api/dvt/uv-off?samples=` | API-12 | |
| POST | `/api/dvt/uv-off/abort?by=` | API-12 | |
| POST | `/api/dvt/hang?sec=` | API-12 | loopback only, 400/403/409 |
| POST | `/api/dvt/led-checks?on=` | API-12 | loopback only, 400/403 |
| GET | `/api/dvt/led-checks` | API-12 | |
| POST | `/api/dvt/remote-confirm` | API-12 | loopback only, 400/403 |
| GET | `/api/dvt/remote-confirm/{id}` | API-12 | loopback only, 403 |
| DELETE | `/api/dvt/remote-confirm/{id}` | API-12 | loopback only, 403 |
| (any) | `/api/ui/*` | Native UI | contributed via `IApiEndpointMapper` |
| (any) | unknown `/api/...` | API-04 | 404 `{ok:false,message:"Not found"}` |
| GET | `/`, `/{**path}` | API-04 | static files + SPA fallback |

The DVT bench process (`scurebox --dvt-bench`, port 3002, `/bench/*`, folder `src/SCureBox.Api/Bench`) is covered by the
Dvt-Hdt area, not here; API-01 only dispatches to it from the command line.

---

### API-01 — Host bootstrap and composition (`ScureApiHost`, `Program`, `HostSettings`, command-line modes, logging)
**Summary**
- **What it is for:** This is the start-up code of the machine software. It builds the one program that runs the web server, connects all software layers, and also offers a few command-line tools (version, watchdog, update package).
- **Problem it solves:** Without one clear start-up place, settings, logging, layers and routes would be set up in different ways, and the machine would not shut down its outputs and save data safely when it stops.
- **How we solve it:** One builder reads settings from the environment, sets the port (3001), logs in one simple style, registers every layer in a fixed order, adds all routes, and runs boot and safe-shutdown steps.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — root folder + `Infrastructure/`
**Goal:** Build the single firmware process: resolve host settings from the environment, configure Kestrel, systemd integration,
house-style console logging, CORS and JSON options, register all firmware layers in DI, install middleware and map every
endpoint group, then run the boot / graceful-shutdown hooks. Also provide the non-server command-line tool modes of the
`scurebox` executable.
**Depends on:** API-02, API-03, API-04, API-05..API-12 (endpoint maps); Hardware (`AddSCureBoxHardware`, `HardwareOptions`,
`OutputWatchdog`, `HeartbeatFile`, `OutputFreeze`); Application-Process (`AddSCureBoxProcess`, `ICureController`, `IHeatingLoop`,
`RecipeValidator`, `StripStatus`); Application-Platform (`AddSCureBoxPlatform`, `DataOptions`, `DatabaseOptions`,
`InternetReachability`, `ILedCalibrationStore`, `ICureRunStore`, `IComponentCounters`, `HeaterRunOnMarker`, `UpdatePackageBuilder`);
Dvt-Hdt (`Bench.DvtBenchHost.Run`); Native UI (consumes `Build(args, configure)` and `IApiEndpointMapper`); Deploy-Ops (systemd units).
**Files to create:**
* `src/SCureBox.Api/SCureBox.Api.csproj` — `Microsoft.NET.Sdk.Web`; `RootNamespace=SCureBox.Api`, `AssemblyName=scurebox`,
  `PublishTrimmed=false`, `StaticWebAssetsEnabled=false`; PackageReference `Microsoft.Extensions.Hosting.Systemd` 10.0.13;
  ProjectReference `../SCureBox.Application/SCureBox.Application.csproj`; Content items: `../../ui/dist/**/*` linked as
  `wwwroot/%(RecursiveDir)%(Filename)%(Extension)` (only when `../../ui/dist/index.html` exists), `../../config/**/*` linked as
  `config/...`, `../../VERSION` linked as `VERSION`; all `CopyToOutputDirectory/CopyToPublishDirectory=PreserveNewest`.
* `src/SCureBox.Api/appsettings.json` — `Logging:LogLevel:Default=Information`, `Logging:LogLevel:Microsoft.AspNetCore=Warning`, `AllowedHosts=*`.
* `src/SCureBox.Api/GITINFO` — two lines: short git commit, commit date (`yyyy-MM-dd`) (written by the build/deploy scripts; read by the system service for `/api/system/version` — OPEN QUESTION: the reader lives in Application-Platform `ISystemService`; confirm there).
* `src/SCureBox.Api/Program.cs` — top-level statements + `public partial class Program { }` (marker for `WebApplicationFactory<Program>`).
* `src/SCureBox.Api/ScureApiHost.cs` — `public static class ScureApiHost` with `public static WebApplication Build(string[] args, Action<WebApplicationBuilder>? configure = null)`; `public interface IApiEndpointMapper { void Map(RouteGroupBuilder api); }` (namespace `SCureBox.Api`).
* `src/SCureBox.Api/Infrastructure/HostSettings.cs` — `public sealed record HostSettings` + `static HostSettings FromConfiguration(IConfiguration cfg)`.
* `src/SCureBox.Api/Infrastructure/CommandLine.cs` — `public static class CommandLine` with `static bool TryRun(string[] args, TextWriter stdout, TextWriter stderr, out int exitCode)` and `static string ReadAppVersion(string baseDir)`.
* `src/SCureBox.Api/Infrastructure/ScureConsoleFormatter.cs` — `public sealed class ScureConsoleFormatter : ConsoleFormatter`, `const string FormatterName = "scure"`, `static string Tag(string category)`.
**Public contract:**
* `HostSettings` properties (init): `int Port` (default 3001), `bool Simulate`, `string ComponentsPath` (default `<AppContext.BaseDirectory>/config/components.json`), `string DataDir` (default `<base>/data`), `string ConfigDir` (always `<base>/config`, not configurable), `string? DatabaseUrl`, `string UiDir` (default `<base>/wwwroot`).
* `ScureApiHost.Build(args, configure)` returns a built-but-not-running `WebApplication`.
* `IApiEndpointMapper.Map(RouteGroupBuilder api)` — every DI-registered mapper is called once under the `/api` group.
* Command line (`Program`): `scurebox --version` | `--watchdog [args]` | `--dvt-bench [args]` | `--make-update-package <folder> <privateKeyPem> <out.scu>` | anything else / no args → server.
**Behaviour & rules:**
1. `Program`: call `CommandLine.TryRun(args, Console.Out, Console.Error, out exit)`; if true return `exit`; else `ScureApiHost.Build(args).Run(); return 0;`.
2. `CommandLine.TryRun`: empty args → false. `args[0]` switch: `--version` → print `ReadAppVersion(AppContext.BaseDirectory)`, exit 0; `--watchdog` → `exitCode = SCureBox.Hardware.Safety.OutputWatchdog.Run(args[1..], stdout, stderr)`; `--dvt-bench` → `exitCode = Bench.DvtBenchHost.Run(args[1..], stderr)`; `--make-update-package` with fewer than 4 args → stderr `usage: scurebox --make-update-package <folder> <privateKeyPem> <out.scu>`, exit 2; otherwise `UpdatePackageBuilder.Build(args[1], args[3], File.ReadAllText(args[2]))` then stdout `update package written: <full path of args[3]>`; on IOException / UnauthorizedAccessException / CryptographicException / ArgumentException stderr `package build failed: <message>`, exit 1. Any other first arg → false (server starts; ASP.NET treats args as configuration).
3. `ReadAppVersion(baseDir)`: trimmed content of `<baseDir>/VERSION` if present and non-empty (IO/permission errors ignored), else the assembly version `ToString(3)`, else `"unknown"`.
4. `HostSettings.FromConfiguration`: `PORT` parsed as int > 0 else 3001; `SCURE_SIMULATE` truthy when trimmed lower-case value ∈ {`1`,`true`,`yes`}; `SCURE_COMPONENTS`, `SCURE_DATA_DIR`, `DATABASE_URL`, `SCURE_UI_DIR` used when non-blank (trimmed) else defaults (`DatabaseUrl` null).
5. Kestrel: if configuration `ASPNETCORE_URLS` is blank → `UseUrls("http://*:" + Port)` (all interfaces, IPv4+IPv6). Always `Host.UseSystemd()`.
6. Logging: `ClearProviders()`, `AddConsole(o => o.FormatterName = "scure")`, `AddConsoleFormatter<ScureConsoleFormatter, ConsoleFormatterOptions>(o => o.TimestampFormat = "yyyy-MM-dd HH:mm:ss ")`.
7. `ScureConsoleFormatter.Write`: skip when the message is empty and there is no exception. Line = timestamp (UTC if `UseUtcTimestamp`, format default `yyyy-MM-dd HH:mm:ss `) + `[` + `Tag(category)` + `] ` + level prefix (`WARN `, `ERROR `, `CRITICAL `, `debug ` for Debug/Trace, nothing for Information) + message + (exception ? ` | <ExceptionTypeName>: <exception message>` : ``) + newline. No stack traces.
8. `Tag(category)`: no `.` in the category → category verbatim (e.g. `API`, `DVT`). `SCureBox.Api*` → `API`; `SCureBox.Hardware*` → `HW`; `SCureBox.Application.<Area>...` → `Supervision`→`SAFETY`, `Process`/`Devices`→`HW`, `Status`→`LED`, `Recipe`→`RECIPE`, `Hdt`→`HDT`, `Persistence`→`DATA`, `Platform`→`SYS`, other → `APP`; `Microsoft.Hosting*` → `HOST`; other `Microsoft.*` / `System.*` → `ASP`; else category verbatim.
9. CORS: `AddCors(default policy AllowAnyOrigin + AllowAnyMethod + AllowAnyHeader)`; `app.UseCors()`. (The UI uses the absolute base URL `http://localhost:3001/api`, so CORS must stay open.)
10. `ConfigureHttpJsonOptions` copies from `ApiJson.Options`: PropertyNamingPolicy, DictionaryKeyPolicy, DefaultIgnoreCondition, NumberHandling, Encoder (API-02).
11. DI registration order (order matters; later layers use TryAdd so earlier registrations win):
    a. `AddSingleton(settings)` (HostSettings);
    b. `AddSCureBoxHardware(new HardwareOptions { ComponentsPath = settings.ComponentsPath, ForceSimulation = settings.Simulate, NativeDir = env SCURE_NATIVE_DIR or null when blank })`;
    c. `AddSingleton<InternetReachability>(sp => () => sp.GetRequiredService<StripStatus>().InternetOk)`;
    d. `AddSingleton(RecipeValidation.Create())` — registered BEFORE `AddSCureBoxProcess` so it replaces the default validator (API-09);
    e. `AddSCureBoxProcess()`;
    f. `AddSCureBoxPlatform(new DataOptions { DataDir = settings.DataDir, ConfigDir = settings.ConfigDir }, new DatabaseOptions { ConnectionString = settings.DatabaseUrl })`;
    g. `AddSingleton<RunIssueTracker>()` (API-08);
    h. `AddHostedService<SystemdWatchdogService>()` (API-03);
    i. only when `OperatingSystem.IsLinux()` AND `HeartbeatFile.ConfiguredPath()` is non-null AND its directory exists: `AddHostedService(sp => new HeartbeatService(logger, path, sp.GetService<OutputFreeze>()))` (API-03);
    j. `configure?.Invoke(builder)` (the native UI adds its services here).
12. Pipeline after `builder.Build()`: `UseCors()` → `UseScureApi()` (API-02) → `UseDvtHangGate()` (API-12) → `var api = app.MapGroup("/api")` → in this order `StateEndpoints.Map`, `CureEndpoints.Map`, `HardwareEndpoints.Map`, `DiagnosticsEndpoints.Map`, `MaterialEndpoints.Map`, `HistoryEndpoints.Map`, `CureRunEndpoints.Map`, `SystemEndpoints.Map`, `NetworkEndpoints.Map`, `DevEndpoints.Map`, `DvtEndpoints.Map`, `RecipeEndpoints.Map` → each `IApiEndpointMapper` from DI → `StaticUi.Map(app, settings.UiDir)` (API-04, last).
13. Boot hooks (inside `Build`, after mapping): resolve `ICureController` and call `SetLedFactors(ILedCalibrationStore.Factors)` (persisted LED calibration applied at boot). Create `HeaterRunOnMarker(DataOptions, TimeProvider?, ILogger<HeaterRunOnMarker>?)`; if `Take()` returns a value ≥ 1 s → log warning `heater fan run-on cut by the last stop: resuming it for {Sec:0} s` and `IHeatingLoop.StartRunOn(left)`; exceptions logged as warning `heater run-on resume failed`, never thrown.
14. `ApplicationStopping` hook, each step in its own try/catch (warning on failure): log `shutting down: outputs off, data flushed`; if `IHeatingLoop.PendingRunOnSec()` > 0 → `runOn.Save(pending)` + warning `stopping with the heater fan run-on due ({Sec:0} s): it resumes on the next start`; `controller.Shutdown()`; `ICureRunStore.Flush()`; `IComponentCounters.Flush()`.
15. Startup log (category `API`): `sCureBox {Version} starting - hardware: {Hw}, data: {Data}, ui: {Ui}` with Hw = `SIMULATION (forced)` when `Simulate` else `auto`.
16. No authentication, no API key, no PIN anywhere in the host (Developer Mode is a UI-side concept). OPEN QUESTION: none found in the API project; if the UI requires a PIN it is enforced only in the UI.
**Configuration:** env / host config `PORT` (3001), `ASPNETCORE_URLS` (overrides PORT binding; the shipped unit sets `http://*:3001`), `SCURE_SIMULATE` (off), `SCURE_COMPONENTS` (`<app>/config/components.json`; units use `/etc/scurebox/components.json`), `SCURE_DATA_DIR` (`<app>/data`; units `/var/lib/scurebox`), `DATABASE_URL` (none = file stores), `SCURE_UI_DIR` (`<app>/wwwroot`), `SCURE_NATIVE_DIR` (none = `<app>/native`), `SCURE_HEARTBEAT_FILE` (API-03), `WATCHDOG_USEC` (API-03). appsettings.json as above.
**Acceptance criteria:**
* `scurebox --version` prints the VERSION file content (e.g. `1.0.152`) and exits 0 without starting Kestrel.
* `scurebox --make-update-package a b` prints the usage line to stderr and exits 2.
* `scurebox --watchdog --bogus` exits 2 and stderr contains `usage: scurebox --watchdog`.
* With no `ASPNETCORE_URLS` and `PORT=4000` the server listens on `http://*:4000`.
* `SCURE_SIMULATE=1` → `/api/state` `hwSource` is `"simulation"`.
* Log lines look like `2026-09-14 10:00:00 [API] GET /api/nfc -> 200 (3 ms)`; `Tag("SCureBox.Application.Supervision.X")=="SAFETY"`, `Tag("API")=="API"`, `Tag("Microsoft.Hosting.Lifetime")=="HOST"`.
* A cross-origin request receives `Access-Control-Allow-Origin: *`.
* A registered `IApiEndpointMapper` route appears under `/api`.
* Stopping the host calls `ICureController.Shutdown()` and flushes run store and counters.
**Tests:** `WatchdogHeartbeatTests.Watchdog_mode_rejects_unknown_arguments` (CommandLine dispatch). Add unit tests for `HostSettings.FromConfiguration` (defaults, truthy values, blank → default), `ScureConsoleFormatter.Tag` mapping table, `CommandLine.ReadAppVersion` (file vs fallback) — none exist today. Integration tests use the API-13 fixture.
**Reference (source):** `src/SCureBox.Api/Program.cs`, `src/SCureBox.Api/ScureApiHost.cs`, `src/SCureBox.Api/SCureBox.Api.csproj`, `src/SCureBox.Api/appsettings.json`, `src/SCureBox.Api/GITINFO`, `src/SCureBox.Api/Infrastructure/HostSettings.cs`, `src/SCureBox.Api/Infrastructure/CommandLine.cs`, `src/SCureBox.Api/Infrastructure/ScureConsoleFormatter.cs`, `deploy/scurebox.service`, `docs/01-api-contract.md` (header, §13, §14).

---

### API-02 — HTTP infrastructure: JSON conventions, envelopes, query parsing, exception envelope, request log
**Summary**
- **What it is for:** These are the shared rules that every web route uses: how JSON looks, how replies say ok or failed, how URL values are read, and how requests are logged.
- **Problem it solves:** If each route did this on its own, the screens would get mixed reply formats, bad input could crash a request, and error codes from the hardware could be lost.
- **How we solve it:** One small toolbox builds every reply as {ok, code, message}, reads URL values the same way, pulls error codes out of hardware messages, and turns any crash into a clear JSON error. Each request is logged.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Infrastructure/`
**Goal:** One place for the wire conventions every endpoint uses: serializer options, the lenient body reader, the
`{ok, code?, message}` envelopes and the hardware-refusal mapping, Flask-compatible query-string parsing, and the middleware that
turns unhandled exceptions into JSON envelopes and logs every request.
**Depends on:** Domain (`OpResult`, `OpResult.SplitCode`, `ErrorCodes.HardwareRefused` = 6015).
**Files to create:**
* `src/SCureBox.Api/Infrastructure/ApiJson.cs` — `public static class ApiJson`.
* `src/SCureBox.Api/Infrastructure/Query.cs` — `public static class Query`.
* `src/SCureBox.Api/Infrastructure/ApiMiddleware.cs` — `public static class ApiMiddleware` with extension `UseScureApi(this IApplicationBuilder app)`.
**Public contract:**
* `ApiJson.Options` (`JsonSerializerOptions`, from `JsonSerializerDefaults.Web`): `PropertyNamingPolicy = JsonNamingPolicy.CamelCase`, `DictionaryKeyPolicy = null` (dictionary keys verbatim, e.g. `FAN_HEATER`, `"9052"`), `DefaultIgnoreCondition = JsonIgnoreCondition.Never` (nulls always written), `NumberHandling = JsonNumberHandling.AllowReadingFromString`, `Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping` (so `°C`, `—` are written literally).
* `Task<T?> ReadBodyAsync<T>(HttpRequest) where T : class` — null when `ContentLength == 0` or the body is not valid JSON of the shape (`JsonException` caught). No Content-Type check.
* `Task<JsonElement?> ReadObjectAsync(HttpRequest)` — body as a JSON object element, null when absent / not an object.
* `IResult Ok(string message)` → `{ok:true, message}` (200).
* `IResult Fail(string message, int? code = null, int status = 200)` → `{ok:false, code, message}` when code given, else `{ok:false, message}` (no `code` key).
* `IResult Envelope(OpResult r)` → `Ok(r.Message)` or `Fail(r.Message, r.Code)`.
* `IResult HwResult(OpResult r, string successMessage)` → success: `Ok(successMessage)`; failure: message = `r.Message` or `"Hardware refused the operation"` when empty; `(embedded, stripped) = OpResult.SplitCode(message)`; `Fail(stripped, embedded ?? r.Code ?? 6015)`.
* `IResult Json<T>(T value, int status = 200)` — serialize with `Options`.
* `string Num(double)` — `value.ToString("0.0###", InvariantCulture)` (Python-like: `60` → `"60.0"`, `62.5` → `"62.5"`).
* `Query.Str(req, key, fallback)` — last value of the key, else fallback.
* `Query.On(req, key, fallback = "1")` — true unless value ∈ {`0`,`false`,`off`} (case-sensitive).
* `Query.OnLoose(req, key, fallback = "0")` — true unless value ∈ {`0`,`false`,``} — so `off` counts as TRUE (Flask fidelity).
* `Query.Double(req, key, fallback)` — empty/absent → fallback; else invariant float parse, must be finite, else `throw new ArgumentException($"Invalid {key} '{s}'")`.
* `Query.Int(req, key, fallback)` — same with integer parse; malformed → `ArgumentException("Invalid {key} '{s}'")`.
* `Query.IntOrNull(req, key)` — null when absent or malformed.
**Behaviour & rules:**
1. Every `/api` response is written with `ApiJson.Options` (endpoints call `ApiJson.Json`/`Ok`/`Fail`).
2. `OpResult.SplitCode(reason)`: when the reason is longer than 7 chars, starts with `[`, and the text between `[` and the first `]` parses as int → (code, rest trimmed at start); else (null, reason). Hardware/supervision refusals arrive as `"[9001] ..."` this way.
3. `UseScureApi` middleware (logger category `API`): wraps `next`; catches any exception that is not `OperationCanceledException` while the response has not started: logs error `{Method} {Path} failed`, clears the response, and for paths starting with `/api/` or equal to `/api` (case-insensitive) writes `ApiJson.Fail(e.Message)` (HTTP 200, no code); for other paths writes 500 `Internal server error` (text). So a malformed numeric query (`?target=abc`) becomes `200 {ok:false, message:"Invalid target 'abc'"}`.
4. After every request except exactly `GET|POST /api/state` (path equality, any method) it logs Information `{Method} {Path}{Query} -> {Status} ({Ms} ms)`.
5. No SSE, no WebSocket, no authentication middleware.
**Configuration:** none.
**Acceptance criteria:**
* `POST /api/cure/heat?target=abc` → 200 `{"ok":false,"message":"Invalid target 'abc'"}`.
* Null-valued properties appear in JSON (e.g. `/api/state` `targetTemp: null`).
* `Num(40)=="40.0"`, `Num(62.5)=="62.5"`.
* `On` with `off` → false; `OnLoose` with `off` → true, with `""` → false.
* `HwResult(Fail("[9001] Chamber sensor open"), ...)` → `{ok:false, code:9001, message:"Chamber sensor open"}`; `HwResult(Fail("Door open"))` → code 6015.
* `GET /api/state` produces no request log line; other requests do.
**Tests:** Covered indirectly by `CureTests.Invalid_parameters_are_rejected_with_the_registry_code`, `CureTests.Stop_is_always_ok_and_off_counts_as_immediate`, `CureTests.Door_open_..._refuses_a_start_with_6015`. Add unit tests for `Query` (On/OnLoose/Double/Int/IntOrNull), `ApiJson.Num`, `ApiJson.HwResult` code extraction, and a middleware test that an endpoint throwing yields 200 JSON under `/api` and 500 text elsewhere.
**Reference (source):** `src/SCureBox.Api/Infrastructure/ApiJson.cs`, `src/SCureBox.Api/Infrastructure/Query.cs`, `src/SCureBox.Api/Infrastructure/ApiMiddleware.cs`, `src/SCureBox.Domain/Errors/ErrorCodes.cs` (`OpResult`), `docs/01-api-contract.md` (Conventions).

---

### API-03 — Liveness services: systemd watchdog keep-alive and output-watchdog heartbeat
**Summary**
- **What it is for:** Two background services that tell the system the machine software is still alive: one talks to the Linux service manager, one writes a heartbeat file every second.
- **Problem it solves:** If the software crashes or freezes, heaters and UV LEDs could stay on with nobody in control. That is a safety risk.
- **How we solve it:** The software sends regular 'I am alive' signals. A separate watchdog watches the heartbeat file; if it stops for 20 seconds, the watchdog turns heaters and UV off. A clean stop removes the file.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Infrastructure/`
**Goal:** Keep systemd's `WatchdogSec=` satisfied while the process is healthy, and write the heartbeat file that the separate
output watchdog (`scurebox --watchdog`, scurebox-watchdog.service) monitors: when the firmware crashes, is killed or hangs, the
heartbeat goes silent and the watchdog switches heaters and UV LEDs off after 20 s.
**Depends on:** API-01 (registration); Hardware (`SCureBox.Hardware.Safety.HeartbeatFile`, `OutputFreeze`, `OutputWatchdog`, `WatchdogTripFile`); Dvt-Hdt / API-12 (DVT hang sets `OutputFreeze`); Deploy-Ops (units).
**Files to create:**
* `src/SCureBox.Api/Infrastructure/SystemdWatchdogService.cs` — `public sealed class SystemdWatchdogService : BackgroundService`; ctor `(ILogger<SystemdWatchdogService> log, ISystemdNotifier? notifier = null)`; `public static TimeSpan? ReadInterval(string? watchdogUsec)`.
* `src/SCureBox.Api/Infrastructure/HeartbeatService.cs` — `public sealed class HeartbeatService : IHostedService, IDisposable`; `public static readonly TimeSpan Interval = 1 s`; ctor `(ILogger<HeartbeatService> log, string? path = null, OutputFreeze? freeze = null)`; `public string Path`.
**Public contract:** hosted services only, no routes.
**Behaviour & rules:**
1. `ReadInterval(usec)`: null when not a positive long; else `TimeSpan.FromMilliseconds(Math.Max(usec / 2000.0, 500))` (half the timeout, never under 500 ms).
2. `SystemdWatchdogService.ExecuteAsync`: interval read from env `WATCHDOG_USEC` in the ctor; returns immediately when no notifier, no interval, or `!SystemdHelpers.IsSystemdService()`. Else logs `systemd watchdog armed - keepalive every {Interval}` and on a `PeriodicTimer` sends `_notifier.Notify(new ServiceState("WATCHDOG=1"))` until cancelled.
3. `HeartbeatService` path: ctor argument, else `HeartbeatFile.ConfiguredPath()` (env `SCURE_HEARTBEAT_FILE`; `off` disables → null), else `HeartbeatFile.DefaultPath` = `/run/scurebox-heartbeat`.
4. `StartAsync`: write one beat immediately, start a background thread named `heartbeat` that beats every `Interval` until stop; log `watchdog heartbeat -> {Path} every {Interval}`.
5. Beat: if `freeze?.Active == true` → write nothing; log warning `watchdog heartbeat paused - the firmware is hung on purpose (DVT)` once per pause; when it beats again after a pause log `watchdog heartbeat resumed`. Else `HeartbeatFile.Write(path, Environment.TickCount64, Environment.ProcessId)`; IO/permission errors → warning `watchdog heartbeat write failed: {Reason}`.
6. `StopAsync`: signal stop, join the thread (≤2 s), `HeartbeatFile.Delete(path)` — a clean stop removes the file and disarms the watchdog.
7. Registration only on Linux with an existing heartbeat directory (API-01 rule 11i).
**Configuration:** `WATCHDOG_USEC` (set by systemd), `SCURE_HEARTBEAT_FILE` (default `/run/scurebox-heartbeat`; `off` disables).
**Acceptance criteria:**
* `ReadInterval`: null/""/"abc"/"0" → null; "60000000" → 30000 ms; "500" → 500 ms.
* After start the heartbeat file holds a tick within 2 s of now; after 2.3 s the tick has increased; after stop the file is gone.
* While `OutputFreeze.Hang()` is active the tick does not change for 2.3 s; after `Recover(...)` it increases again.
* Trip record path `WatchdogTripFile.PathFor(hb)` ends in `.trip` and round-trips `(at, cutOk)`.
**Tests:** `SystemdWatchdogTests.Interval_is_half_the_watchdog_timeout` (theory above); `WatchdogHeartbeatTests`: `Heartbeat_is_written_at_start_refreshed_every_second_and_removed_on_a_clean_stop`, `No_heartbeat_is_written_while_the_firmware_is_hung_on_purpose_and_it_resumes_after`, `The_watchdog_trip_record_round_trips_next_to_the_heartbeat`, `Watchdog_mode_rejects_unknown_arguments`.
**Reference (source):** `src/SCureBox.Api/Infrastructure/SystemdWatchdogService.cs`, `src/SCureBox.Api/Infrastructure/HeartbeatService.cs`, `src/SCureBox.Hardware/Safety/HeartbeatFile.cs`, `tests/SCureBox.Api.Tests/SystemdWatchdogTests.cs`, `tests/SCureBox.Api.Tests/WatchdogHeartbeatTests.cs`.

---

### API-04 — Static kiosk UI, SPA fallback and unknown-route 404
**Summary**
- **What it is for:** This part serves the touch-screen web app (the kiosk UI) and its config files from the machine itself.
- **Problem it solves:** Without it, the screen app could not load, page links inside the app would break on reload, and wrong API addresses would return a web page instead of a clear error.
- **How we solve it:** Serve the built app files directly, send the main page for any other screen address, and answer unknown API addresses with a JSON 'Not found' (404).

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/StaticUi.cs`
**Goal:** Serve the built React UI (and its `/config/*.json` assets) from `SCURE_UI_DIR` at `/`, fall back to `index.html` for
client-side routes, and give unknown `/api` routes a JSON 404 instead of the SPA page.
**Depends on:** API-01, API-02; Kiosk-Web (the `ui/dist` build, which contains `index.html` with `<div id="root"` and `config/errors.json`, `config/system.json`, `config/versions.json`).
**Files to create:** `src/SCureBox.Api/Endpoints/StaticUi.cs` — `public static class StaticUi { public static void Map(WebApplication app, string uiDir) }`.
**Public contract:**
| Method | Route | Response |
|---|---|---|
| GET/HEAD | any existing file under uiDir (e.g. `/assets/x.js`, `/config/errors.json`) | the file (content type by extension; unknown types served too) |
| any | non-file path not under `/api` | `index.html` as `text/html; charset=utf-8`, 200 |
| any | non-file path under `/api` with no endpoint | 404 `{ok:false, message:"Not found"}` |
| any | non-file path, no `index.html` | 404 `{ok:false, message:"UI not built"}` |
**Behaviour & rules:**
1. When `uiDir` exists: `app.UseStaticFiles(new StaticFileOptions { FileProvider = new PhysicalFileProvider(Path.GetFullPath(uiDir)), ServeUnknownFileTypes = true })`.
2. `app.MapFallback(handler)` (default ASP.NET fallback pattern `{*path:nonfile}`, so paths that look like files — containing a dot in the last segment — are NOT handled by the fallback and get the framework's empty 404). Handler: path starts with `/api/` or equals `/api` (case-insensitive) → `ApiJson.Fail("Not found", status: 404)`; else if `<uiDir>/index.html` exists → `Results.File(index, "text/html; charset=utf-8")`; else `ApiJson.Fail("UI not built", status: 404)`.
3. `/api/*` endpoints always win over the fallback (fallback has the lowest order). The fallback matches every HTTP method.
4. `StaticUi.Map` is called last in `Build` (after all `/api` maps).
**Configuration:** `SCURE_UI_DIR` (default `<app>/wwwroot`, filled by the csproj Content link of `ui/dist`).
**Acceptance criteria:**
* `GET /api/no-such-route` and `POST /api/nothing/here` → 404 `{ok:false, message:"Not found"}`.
* With a UI build: `GET /` → 200 text/html containing `<div id="root"`; `GET /settings` and `/cure/process/123` → identical HTML body.
* `GET /config/errors.json` → 200 `application/json` with `errors[]` (≥ 46 records, each with `code,key,severity,category,layer,message,description,troubleshooting,supportUrl`, including 7001); `/config/system.json` object; `/config/versions.json` 200.
* With a missing UI dir: `GET /` → 404 `{ok:false, message:"UI not built"}`, while `GET /api/state` still 200.
**Tests:** `StaticUiTests`: `Unknown_api_path_is_a_json_404`, `Index_and_spa_fallback_serve_the_built_ui` (skips when `ui/dist` is not built), `Config_assets_come_from_the_ui_dir` (skips without UI), `Missing_ui_build_is_a_json_404` (nested `NoUiFixture` overriding `SCURE_UI_DIR`).
**Reference (source):** `src/SCureBox.Api/Endpoints/StaticUi.cs`, `tests/SCureBox.Api.Tests/StaticUiTests.cs`, `docs/01-api-contract.md` §10–11.

---

### API-05 — Machine state poll and NFC setting
**Summary**
- **What it is for:** The main status route that the screens ask once a second to learn everything about the machine, plus routes to read and switch the NFC tag reader.
- **Problem it solves:** The screens need one full, up-to-date picture of the machine (temperatures, fans, alerts, counters, cloud, NFC, program). Without it they cannot show what is happening.
- **How we solve it:** Take the machine state and add counters, cloud status, offline mode, NFC info and the running program. During a planned test freeze, return the last saved state. Turning NFC on without a reader is refused with code 9052.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/StateEndpoints.cs`
**Goal:** `GET /api/state` is the 1 Hz poll of the UIs: the controller's `MachineState` decorated by the host with component
counters, cloud-sync status, offline mode, NFC reader info and the recipe runner status; during a DVT hang it returns the frozen
pre-hang state. The NFC routes read and switch the NFC feature.
**Depends on:** API-02; Application-Process (`ICureController.GetState()`, `MachineState`, `IRecipeRunner.GetStatus()` / `RecipeStatus`); Application-Platform (`IComponentCounters.Hours()`, `ICloudSync.Status()`, `INfcReaderDetector` (`Enabled`, `Status()`, `Decorate(MachineState)`, `TrySetEnabled(bool, out reader)`), `INfcTagReader.Status()`, `NetworkPolicy.OfflineMode`); Dvt-Hdt (`SCureBox.Application.Dvt.DvtHang`: `Active`, `LastState`, `Until`; `DvtHangDto`).
**Files to create:** `src/SCureBox.Api/Endpoints/StateEndpoints.cs` — `public static class StateEndpoints { public static void Map(RouteGroupBuilder api) }`.
**Public contract:**
| Method | Route | Request | Response |
|---|---|---|---|
| GET | `/api/state` | — | `MachineState` JSON (200) |
| GET | `/api/nfc` | — | `{ok:true, enabled, reader, tag}` |
| POST | `/api/nfc` | query `on` (default `1`, `Query.On`) | ok: `{ok:true, message, enabled, reader}`; refused: `{ok:false, code, message, enabled, reader}` (200) |
`MachineState` top-level keys (all always present except `dvtHang`): `chamberTemp, targetTemp, internetOk, offlineMode, doorClosed, doorAborted, isHeating, isCooling, coolingMode, uvOn, uvIntensity, uvWavelength, uvOutputs, ventOn, damperOpen, damperDriver, fans, fanRpm, fanRpmEach, fanDutyEach, fanOverride, stripMode, uiAlerts, ledTemps, uvSensors, nitrogenActive, n2Pressure, n2LinePressure, n2Sensor, bofaOn, bofaConnected, bofaDutyPercent, bofaPowered, bofaDetected, atTemp, heaterPwm, heaterOut, coolingRate, coolingFanPwm, faults, sensors, fanHealth, ledHealth, ledChecksEnabled, alerts, alertDetails, hwSource, counters, cloudSync, nfcEnabled, nfcReader, recipe, dvtHang?` (field semantics are owned by Application-Process; see docs/01 §1).
**Behaviour & rules:**
1. `/api/state`: if `hang.Active` and `hang.LastState` is not null → return `LastState with { DvtHang = new DvtHangDto(true, (Until unix ms)/1000.0 or 0) }` (no fresh read). Otherwise `state = controller.GetState() with { Counters = counters.Hours(), CloudSync = cloud.Status(), OfflineMode = policy.OfflineMode }`; `state = nfc.Decorate(state)` (sets `nfcEnabled`, `nfcReader`, and adds 9052 to alerts/alertDetails when enabled with no reader); `run = recipe.GetStatus()`; when `run.State != "idle"` set `Recipe = run`, else `recipe` stays null. `dvtHang` is omitted (WhenWritingNull) except during a hang.
2. `/api/state` is never request-logged (API-02).
3. `GET /api/nfc` → `{ok:true, enabled: nfc.Enabled, reader: nfc.Status(), tag: tags.Status()}`; `reader` = `{detected, port, model, serial, usbId, ...}`; `tag` = `{connected, firmware, tagPresent, lastTag, lastTagAt, error}` (shape owned by Platform).
4. `POST /api/nfc?on=`: `r = nfc.TrySetEnabled(on, out reader)`. Enabling without a detected reader is refused by the detector with code 9052 and message `No NFC reader detected - connect the reader (data USB cable) and try again`. Disabling always succeeds.
**Configuration:** `SCURE_SIM_NFC=1` simulates a reader (Platform).
**Acceptance criteria:**
* Every contract key listed in `StateTests.ContractKeys` is present; `hwSource == "simulation"` in simulation.
* Nested: `fans` / `fanRpm` keys `led_cooling, chamber_intake, chamber_heating`; `fanRpmEach` keys `FAN_HEATER, FAN_DOOR, FAN_RIGHT, FAN_LEFT, FAN_BACK, FAN_COOLING`; `ledTemps` exactly `back, door, left, right`; `uvSensors.left|right` with `volts, kOhm, lit`; `faults.heater|cooling|led`; `counters.led405|led450|coolingFan|heater|heaterFan`; `cloudSync.enabled|lastSyncOk|error`; `nfcReader.detected|port|model|serial|usbId|seenSinceBoot`; `alerts` array, `alertDetails` object; simulation `n2LinePressure == 2.0`, `n2Pressure.mpa == 0.2`, `minBar 0.5`, `maxBar 3.0`.
* After the first supervision tick `sensors.chamber|left|right|back|door` each have `sensor, ok, openSec, critical`; `fanHealth` has all six FAN_*; `ledHealth` has `LED_LEFT, LED_RIGHT`.
* With a recipe running `state.recipe.state == "running"`; idle → `recipe: null`.
* `GET /api/nfc` ok with `enabled:false` by default; `POST /api/nfc?on=1` without reader → 200 `{ok:false, code:9052}` with `enabled` and `reader` keys; `on=0` → ok, `enabled:false`.
* During a DVT hang: `dvtHang.active == true`, `dvtHang.until` > now (unix s), and the body reflects the pre-hang state (e.g. `isHeating:true`).
**Tests:** `StateTests`: `State_has_every_contract_key`, `State_nested_shapes_match_the_contract`, `State_sensors_and_supervision_fill_in_after_the_first_tick`, `Nfc_get_and_refusal_9052_without_a_reader`; hang part of `DvtHangApiTests.Hang_contract_end_to_end`; recipe part of `RecipeTests`.
**Reference (source):** `src/SCureBox.Api/Endpoints/StateEndpoints.cs`, `src/SCureBox.Application/Contracts/MachineState.cs`, `tests/SCureBox.Api.Tests/StateTests.cs`, `docs/01-api-contract.md` §1.

---

### API-06 — Cure process commands (`/api/cure/*`)
**Summary**
- **What it is for:** Commands that start each step of a cure: heat, dry, cure with 405 or 450 nm UV, UV only, cool, nitrogen, and stop.
- **Problem it solves:** The screen drives the cure step by step. Without checked commands, wrong values (like too-high temperature) could reach the machine, and hardware refusals would not be explained.
- **How we solve it:** One command per step. Values are checked against allowed ranges first, with clear error codes; then the request goes to the machine control, and any refusal comes back with its code.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/CureEndpoints.cs`
**Goal:** One POST per recipe process (heat, dry, cure-405, cure-450, uv-only, cool, nitrogen, stop) used by the UI's
phase-by-phase cure flow. The API validates the parameter ranges with registry codes, then forwards to `ICureController`, mapping
refusals through `ApiJson.HwResult`.
**Depends on:** API-02; Application-Process (`ICureController` methods `HeatToTarget, DryToTarget, CureUv, UvOnly, CoolToTarget, SetNitrogen, StopAll`; `RecipeValidator` constants `HeatTargetMin=30, TempMax=80, DryTempMax=50, CoolTargetMin=20, UvIntensityMin=10`); Domain (`Wavelength.Nm405/Nm450`, `WavelengthExtensions.TryParse(int, out Wavelength)`, `CoolingModes.Parse(string)` + `.Wire()`, `CoolingMode`, `ErrorCodes.InvalidTemperature=7001, InvalidIntensity=7002, InvalidCoolingMode=7003`).
**Files to create:** `src/SCureBox.Api/Endpoints/CureEndpoints.cs` — `public static class CureEndpoints { public static void Map(RouteGroupBuilder api) }` (group `/cure`), private helpers `CureUv`, `BadHeat`, `BadIntensity`.
**Public contract (all POST, query parameters, HTTP 200):**
| Route | Query (default) | Validation (→ `{ok:false, code, message}`) | Controller call | Success message |
|---|---|---|---|---|
| `/api/cure/heat` | `target` (60) | 30–80 else 7001 `Invalid target {t} (30-80°C)` | `HeatToTarget(t)` | `Heating to {t}°C` |
| `/api/cure/dry` | `target` (50) | > 50 → 7001 `Invalid target {t} (30-50°C for drying)`; < 30 → 7001 `Invalid target {t} (30-80°C)` | `DryToTarget(t)` | `Drying to {t}°C` |
| `/api/cure/cure-405` | `target` (60), `intensity` (30, int) | 7001 as heat; intensity 10–100 else 7002 `Invalid intensity {i} (10-100%)` | `CureUv(Nm405, t, i)` | `Cure UV 405nm @ {i}%, {t}°C` |
| `/api/cure/cure-450` | same | same | `CureUv(Nm450, t, i)` | `Bleaching UV 450nm @ {i}%, {t}°C` |
| `/api/cure/uv-only` | `intensity` (30), `wavelength` (405), `vent` (0, `OnLoose`) | 7002; wavelength not 405/450 → `{ok:false, message:"Invalid wavelength {w} (405|450)"}` (NO code) | `UvOnly(wl, i, vent)` | `UV {w}nm @ {i}% — no heating` + (vent ? `, fresh-air vent` : ``) |
| `/api/cure/cool` | `target` (25), `mode` (`medium`) | 20–80 else 7001 `Invalid target {t} (20-80°C)`; mode must parse AND equal its wire form (`fast`/`medium`/`slow`, exact case) else 7003 `Invalid cooling mode {mode}` | `CoolToTarget(t, mode)` | `Cooling ({mode}) to {t}°C` |
| `/api/cure/nitrogen` | `on` (1, `On`) | — | `SetNitrogen(on)` | `Nitrogen valve opened` / `Nitrogen valve closed` |
| `/api/cure/stop` | `immediate` (0, `OnLoose`) | — | `StopAll(immediate)` | always `{ok:true, message:"All cure outputs stopped"}` + ` immediately` when immediate |
`{t}` is formatted with `ApiJson.Num` (`60.0`), `{i}` as an integer.
**Behaviour & rules:**
1. Validation order: cure-405/450 → target first, then intensity. uv-only → intensity first, then wavelength. Cool → target, then mode.
2. All except stop return `ApiJson.HwResult(result, successMessage)`: controller refusals give 6015 by default, or the embedded `[NNNN]` code (9001/9002/9003/9004..., N2 codes 9008/9009/9015/9016) with the prefix stripped.
3. Admission rules live in the controller (Application-Process), not in the API: e.g. door open → refused 6015 with a message containing `Door` (LEDs are door-interlocked); required sensor open → 9001; fans failing → 9002/9003; N2 pressure outside 0.5–3 bar → 9008/9009. During a DVT hang the hang gate answers 409 before the endpoint (API-12). OPEN QUESTION: whether the controller refuses these manual commands while the server-side recipe runner is executing is decided inside `CureController`/`RecipeRunner`, not visible in the API code.
4. `stop` never fails; `immediate=off` counts as immediate (Flask quirk via `OnLoose`).
5. Malformed numbers → `ArgumentException` → 200 `{ok:false, message:"Invalid target 'x'"}` via middleware.
**Configuration:** none.
**Acceptance criteria:**
* Each of these returns 200, `ok:false`, the code, non-empty message: `heat?target=99` 7001, `heat?target=10` 7001, `dry?target=81` 7001, `dry?target=51` 7001, `cure-405?target=60&intensity=5` 7002, `cure-450?target=60&intensity=101` 7002, `uv-only?intensity=0` 7002, `cool?target=15` 7001, `cool?target=25&mode=turbo` 7003.
* `uv-only?intensity=30&wavelength=500` → `ok:false`, no `code`, message `Invalid wavelength 500 (405|450)`.
* `heat?target=40` → `Heating to 40.0°C`; state then `isHeating:true`, `targetTemp:40`. `stop?immediate=1` → `All cure outputs stopped immediately`, then `isHeating:false`.
* `stop` → `All cure outputs stopped`; `stop?immediate=off` → `... immediately`.
* `cure-405?target=60&intensity=30` → `Cure UV 405nm @ 30%, 60.0°C`, state `uvOn:true, uvWavelength:405`. `cool?target=25&mode=fast` → `Cooling (fast) to 25.0°C`, state `isCooling:true, coolingMode:"fast"`. `nitrogen?on=1|0` → opened/closed messages.
* After `POST /api/door/open`, `uv-only?intensity=30` → 200 `{ok:false, code:6015}` with `Door` in the message.
**Tests:** `CureTests`: `Invalid_parameters_are_rejected_with_the_registry_code` (theory, also covers `/api/chamber/temperature` and `/api/uv`), `Bad_wavelength_is_refused_without_a_code`, `Heat_then_stop_reflects_in_state`, `Stop_is_always_ok_and_off_counts_as_immediate`, `Cure_405_and_cool_and_nitrogen_succeed_in_simulation`, `Door_open_is_always_ok_reads_open_then_recloses_after_5_s_and_refuses_a_start_with_6015`.
**Reference (source):** `src/SCureBox.Api/Endpoints/CureEndpoints.cs`, `src/SCureBox.Application/Recipe/RecipeValidator.cs`, `src/SCureBox.Application/Contracts/ICureController.cs`, `tests/SCureBox.Api.Tests/CureTests.cs`, `docs/01-api-contract.md` §8.

---

### API-07 — Direct hardware, acknowledgements, BOFA policy and diagnostics
**Summary**
- **What it is for:** Service and settings routes that control single parts directly: door, chamber heating, light strip, fans, damper, UV, fume extractor (BOFA), alarm acknowledgements, and fan and LED tests.
- **Problem it solves:** Service people and settings screens need to test and control each part alone, clear alarms, and save the extractor settings. Without these routes they could not.
- **How we solve it:** Simple routes, one per action, that pass the request to the machine control. Some always answer ok for compatibility with the old system. Test routes return fan speed and LED heating results.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/HardwareEndpoints.cs`, `Endpoints/DiagnosticsEndpoints.cs`
**Goal:** Service / settings-screen routes that drive single outputs (door, manual chamber heating, RGB strip, fans, damper, UV,
BOFA extractor), operator acknowledgements of latched alarms, the persisted BOFA policy, and the fan RPM and LED heating
diagnostics. Several routes answer `ok:true` unconditionally (Flask fidelity).
**Depends on:** API-02; Application-Process (`ICureController`: `OpenDoor, AckDoorAbort, AckWatchdogTrip, AckFanAlarms, SetTargetTemperature, StopHeating, ReportUiAlerts, SetRgb, SetFanOverride, SetFanSpeed, SetDamper, SetUv, SetBofa, SetBofaConnected, RunFanTest, RunLedTest`; `FanTestResult`, `FanTestEntry`, `LedTestResult`, `LedTestEntry`); Application-Platform (`BofaPolicy`: `Connected`, `DutyPercent`, `Choose(bool?, int?)`, persisted `bofa.json`, default duty 10); Domain (`HardwareNames.TryParseFanGroup` (exact-case enum `FanGroup { led_cooling, chamber_intake, chamber_heating }`), `WavelengthExtensions.TryParse`, `Wavelength.Nm405`, `ErrorCodes`).
**Files to create:**
* `src/SCureBox.Api/Endpoints/HardwareEndpoints.cs` — `public static class HardwareEndpoints { public static void Map(RouteGroupBuilder api) }`.
* `src/SCureBox.Api/Endpoints/DiagnosticsEndpoints.cs` — `public static class DiagnosticsEndpoints { public static void Map(RouteGroupBuilder api) }`.
**Public contract (all 200 unless noted):**
| Method | Route | Query / body | Response |
|---|---|---|---|
| POST | `/api/door/open` | — | always `{ok:true, message:"Door opened"}` (calls `OpenDoor()`, result ignored) |
| POST | `/api/door-abort/ack` | — | always `{ok:true, message:"Door abort acknowledged"}` |
| POST | `/api/watchdog/ack` | — | `{ok:true, message: AckWatchdogTrip().Message}` (Err 9017; default `Watchdog alert acknowledged`) |
| POST | `/api/fans/ack` | — | `{ok:true, message: AckFanAlarms().Message}` (e.g. `Fan alarm acknowledged: 9022 FAN_LEFT, ...`) — always ok |
| POST | `/api/chamber/temperature` | `target` (25) | 30–80 else `{ok:false, code:7001, message:"Invalid target {t} (30-80°C)"}`; else `{ok: r.Ok, message: ok ? "Target set to {t}°C" : r.Message}` (no code on refusal) |
| POST | `/api/chamber/stop` | — | always `{ok:true, message:"Heating stopped"}` |
| POST | `/api/rgb/alerts` | `critical` (0), `warning` (0) ints | `{ok:true, critical, warning}` (calls `ReportUiAlerts`) |
| POST | `/api/rgb` | `on` (1, `On`), `color` (empty → null) | `Envelope(SetRgb(on, color))` |
| POST | `/api/fans/override` | `fan` (""), `on` (1) | `{ok: r.Ok, message: ok ? "fan override on|off: {fan}" : r.Message}`; unknown fan → controller message `unknown fan: X` |
| POST | `/api/fans/{fan}` | route `fan`, `speed` (0) | always `{ok:true, message:"{fan} set to {speed}%"}`; `SetFanSpeed` only called when `{fan}` parses as a `FanGroup` (exact case) |
| POST | `/api/damper/{action}` | route `action` | `SetDamper(action == "open")`; always `{ok:true, message:"Damper opened"}` or `"Damper closed"` (any action other than `open` closes) |
| POST | `/api/uv` | `on` (0!), `intensity` (30), `wavelength` (405) | when on: intensity 10–100 else 7002 `Invalid intensity {i} (10-100%)`; unknown wavelength → `{ok:false, message:"Invalid wavelength {w} (405|450)"}`; then `HwResult(SetUv(on, i, wl), "UV on"|"UV off")` (when off, validation is skipped) |
| POST | `/api/bofa` | `on` (1) | `HwResult(SetBofa(on), "BOFA on"|"BOFA off")` |
| GET | `/api/bofa/policy` | — | `{ok:true, connected, dutyPercent}` |
| POST | `/api/bofa/policy` | `connected` (present → `On(...,"1")`, absent → unchanged), `dutyPercent` (int, absent/malformed → unchanged) | neither → `{ok:false, message:"connected=0|1 and/or dutyPercent=0..100 required"}`; duty outside 0..100 → `{ok:false, code:7002, message:"dutyPercent must be 0..100"}`; else `Choose(connected, duty)`, `SetBofaConnected(p.Connected)`, `{ok:true, connected, dutyPercent}` |
| POST | `/api/diagnostics/fan-test` | `fan` (`all`) | `{ok:true, rpm, status, fans:{FAN_X:{rpm,status,duty,expected,deficitPct}}, message}` |
| POST | `/api/diagnostics/led-test` | `seconds` (15, rounded to int), `min_rise` (0.8), `wavelength` (405; unknown → default enum value) | `{ok:true, status, stage, seconds, wavelength, precooled, intensity, min_rise_c, results:[{name,start,temp,rise,status}], message}` |
**Behaviour & rules:**
1. `fans/{fan}` refusals by a control loop (heater fan while heating, intake while cooling, LED fans during fast-cool boost) are silent; the API still reports ok.
2. `bofa/policy` after a change always calls `ICureController.SetBofaConnected(policy.Connected)` so a disconnect drops the output at once and a re-tuned duty applies immediately if the intake fan runs.
3. Diagnostics always return `ok:true`; the verdict is `status` (`OK`/`FAIL`, fan test also `WARN`). Unknown fan → `rpm:0, status:"FAIL", message:"unknown fan: <fan>"`. LED test refused while a process runs → `stage:"busy"` (controller).
4. `led-test` passes `intensity` default 100 (interface default) to `RunLedTest(seconds, minRise, wl)`.
5. Hang gate (API-12) answers 409 for all these POSTs during a DVT hang.
**Configuration:** none (BOFA persisted by Platform in `<data>/bofa.json`).
**Acceptance criteria:**
* `fans/chamber_intake?speed=40` → `chamber_intake set to 40%`; state `fans.chamber_intake == 40`, simulated `fanRpmEach.FAN_COOLING == 1720`.
* `damper/open` → `Damper opened`, state `damperOpen:true`; `damper/close` → `Damper closed`.
* `fans/override?fan=FAN_DOOR&on=1` → ok, `fanOverride` contains `FAN_DOOR`; `fan=FAN_NOPE` → ok:false, message contains `unknown fan`.
* `uv?on=1&intensity=30&wavelength=450` → `UV on`, state `uvWavelength:450`, `uvOutputs` object; `uv?on=0` → `UV off`; `uv?on=1&intensity=200` → 7002.
* `bofa?on=1|0` → `BOFA on|off`.
* `rgb/alerts?critical=1&warning=2` → echoes 1 and 2; `rgb?on=1&color=blue` has `ok` and `message`.
* `chamber/temperature?target=45` → `Target set to 45.0°C`; `target=99` → 7001; `chamber/stop` → `Heating stopped`.
* `diagnostics/fan-test?fan=all` (sim) → `status:"OK"`, `rpm:3560`, all six FAN_* with `rpm,status`, `message` key present; `fan=nope` → `ok:true, status:"FAIL", rpm:0, message:"unknown fan: nope"`.
* `diagnostics/led-test?seconds=1&min_rise=0.1&wavelength=405` → all keys present, `wavelength:405`, `results` array of `{name,start,temp,rise,status}`.
* `watchdog/ack` → ok (also right after a DVT hang).
**Tests:** `HardwareTests`: `Fan_speed_is_always_ok_and_damper_reports_its_direction`, `Fan_override_round_trip_and_unknown_fan`, `Uv_and_bofa_direct_control`, `Rgb_alerts_and_manual_strip`, `Fan_test_shape_and_unknown_fan`, `Led_test_shape`; `CureTests.Chamber_temperature_manual_heating`, door test. Add: `bofa/policy` GET/POST validation (missing both → message; duty 101 → 7002; round trip).
**Reference (source):** `src/SCureBox.Api/Endpoints/HardwareEndpoints.cs`, `src/SCureBox.Api/Endpoints/DiagnosticsEndpoints.cs`, `src/SCureBox.Application/Platform/BofaPolicy.cs`, `src/SCureBox.Domain/Models/HardwareNames.cs`, `tests/SCureBox.Api.Tests/HardwareTests.cs`, `docs/01-api-contract.md` §7.

---

### API-08 — Data endpoints: materials, print history, cure history, cure runs, reports, phase timings
**Summary**
- **What it is for:** Routes that save and read the machine's data: preset and user programs, print history, cure runs with their reports, cure history, and phase-timing statistics.
- **Problem it solves:** Without stored data, users would lose their programs and history, and there would be no record or report of each cure.
- **How we solve it:** The screen saves full lists and follows a cure run by its own id: start, send readings, finish, save report. While a run is active, the server also records sensor and fan problems and adds them to the run.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/MaterialEndpoints.cs`, `Endpoints/HistoryEndpoints.cs`, `Endpoints/CureRunEndpoints.cs`, `Infrastructure/RunIssueTracker.cs`
**Goal:** Persisted data the UI reads and writes: bundled preset programs, user programs and print history (full-replace
arrays), the cure-run lifecycle keyed by the UI's external id (start → telemetry → finish → report), cure-history listing and
deletion, and the phase-timing analytics. During a run the host samples open sensors and fan deficits and attaches them to the
finished run.
**Depends on:** API-02; Application-Platform / Persistence (`IMaterialStore`: `GetPresets, GetUserMaterials, ReplaceUserMaterials, Find`; `IPrintHistoryStore`: `GetAll, ReplaceAll`; `ICureRunStore`: `Start, AddTelemetry, Finish, SaveReport, GetReport, GetHistory, Delete, DeleteAll, Flush`; `IPhaseTimingStore`: `Append, GetAll`; `CureHistoryDeletion`: `Delete(id)`, `DeleteAll()`); Domain models (`Material`, `PrintLog`, `CureRunStart`, `TelemetrySample`, `CureRunFinish`, `CureReport`, `PhaseTiming`, `SensorIssue`, `FanIssue`); Application-Process (`ICureController.GetState()`, `MachineState.Sensors`, `MachineState.FanHealth`).
**Files to create:**
* `src/SCureBox.Api/Endpoints/MaterialEndpoints.cs` — `public static class MaterialEndpoints`.
* `src/SCureBox.Api/Endpoints/HistoryEndpoints.cs` — `public static class HistoryEndpoints`.
* `src/SCureBox.Api/Endpoints/CureRunEndpoints.cs` — `public static class CureRunEndpoints` (group `/cure-runs/{extId}`).
* `src/SCureBox.Api/Infrastructure/RunIssueTracker.cs` — `public sealed class RunIssueTracker` with `void Note(string extId, MachineState state)` and `(List<SensorIssue> Sensors, List<FanIssue> Fans) Take(string extId)`; singleton.
**Public contract:**
| Method | Route | Body | Response |
|---|---|---|---|
| GET | `/api/materials/presets` | — | `Material[]` (bundled presets, always 200) |
| GET | `/api/materials/user` | — | `Material[]` |
| POST | `/api/materials/user` | `Material[]` | `{ok:true}`; not a JSON array → 400 `{ok:false, message:"Expected a JSON array of materials"}` |
| GET | `/api/print-history` | — | `PrintLog[]` |
| POST | `/api/print-history` | `PrintLog[]` | `{ok:true}`; not an array → 400 `{ok:false, message:"Expected a JSON array of print logs"}` |
| GET | `/api/cure-history` | — | `CureLog[]` from `GetHistory()` (newest first) |
| DELETE | `/api/cure-history/{id}` | — | `{ok:true}`; unknown or still running → 404 `{ok:false, message:"Unknown run or still running"}` |
| DELETE | `/api/cure-history` | — | `{ok:true, deleted:<int>}` (finished runs only) |
| GET | `/api/phase-timings` | — | `PhaseTiming[]` |
| POST | `/api/cure-runs/{extId}/start` | `CureRunStart {materialName, steps, phases[], targetTemp, serialNumber}` (bad/empty → defaults) | `{ok:true}` |
| POST | `/api/cure-runs/{extId}/telemetry` | `TelemetrySample {t, chamberTemp, uvOn, uvType, fanRpm{FAN_*}, ledTemps{...}}` | `{ok: AddTelemetry(...)}` (false for unknown id) |
| POST | `/api/cure-runs/{extId}/finish` | `CureRunFinish {status ("completed" default), stepsCompleted?, alerts?}` | `{ok, sensorIssues:[{sensor,critical}], fanIssues:[{fan,deficitPct,critical}]}` |
| POST | `/api/cure-runs/{extId}/report` | `CureReport {content, summary (any JSON), format ("html")}` | `{ok:true, reportId}` |
| GET | `/api/cure-runs/{extId}/report` | — | `{ok:true, content, summary, format}`; none → 404 `{ok:false, message:"No report"}` |
| POST | `/api/cure-runs/{extId}/phase` | `PhaseTiming {program, step, process, targetTemp, plannedMin, startedAt, endedAt, seconds, rampSeconds, tempStart, tempEnd, coolingMode, intensity, timerMode}` | `{ok:true, count}`; body null or `process` empty or `seconds` null → 400 `{ok:false, message:"process and seconds required"}` |
**Behaviour & rules:**
1. Bodies are read with `ApiJson.ReadBodyAsync<T>`; for start/telemetry/finish/report a missing or malformed body falls back to `new T()` (no error).
2. `phase`: the stored record is `timing with { RunId = extId }`; `count` = the store's count after append.
3. Telemetry and finish both call `issues.Note(extId, controller.GetState())` BEFORE the store call; finish then `Take(extId)` and passes the lists to `store.Finish(extId, finish, sensorIssues, fanIssues)`, returning them in the response.
4. `RunIssueTracker.Note` (thread-safe, one lock): for each `state.Sensors` entry with `Ok == false` record `key → Critical` (sorted ordinal by key; last value wins). For each `state.FanHealth` entry whose `Status` is `warn` or `critical` keep, per fan, the entry with the largest `DeficitPct` (null treated as 0) as `new FanIssue(fan, DeficitPct, Status == "critical")`. `Take` removes and returns both, sorted by name; unknown id → empty lists.
5. Cure-history deletion also queues the ids for deletion on the cloud portal (Platform `CureHistoryDeletion`); a running run is never deleted.
6. Store semantics owned by Platform (docs/01 §5): start idempotent, inserts at index 0 with status `running`; runs left `running` after a power cut become `error` on load; `cure_history.json` etc. under `SCURE_DATA_DIR`; user materials in `user_materials.json`.
7. No admission rules (these routes work during a run); during a DVT hang all POST/DELETE here answer 409 (API-12).
**Configuration:** `SCURE_DATA_DIR`, `DATABASE_URL` (via Platform).
**Acceptance criteria:**
* Presets: 200 non-empty array containing `id == "preset-ST45"`; each has `id, name, isPreset, createdAt, steps, totalDuration`; steps have `step, process, temperature, intensity, time`.
* User materials round trip preserves `timerMode:"on-target"`, `coolingMode:"medium"`; writes `<data>/user_materials.json`; posting `[]` clears; posting `not json` → 400.
* Print history round trip keeps all keys `id, printName, materialName, printerName, date, duration, status, steps, csvFile`.
* Cure run: start ok; telemetry ok for the id, `ok:false` for an unknown id; history shows `running`; finish ok with `sensorIssues`/`fanIssues` arrays; history then `completed`, `stepsCompleted 2`, `serialNumber "SN-QA"`, one telemetry row, and keys `materialName, steps, startedAt, endedAt, duration, phases, targetTemp, sensorIssues, fanIssues`.
* Report: GET before save → 404 `No report`; POST → `reportId` key; GET → 200 with same `content`, `format:"html"`, `summary.steps == 2`.
* Phase: missing process/seconds → 400 `process and seconds required`; valid → `count >= 1`, and `/api/phase-timings` contains `process:"Heating", seconds:612.5`.
* `DELETE /api/cure-history/<unknown>` → 404; `DELETE /api/cure-history` → `{ok:true, deleted:n}`.
**Tests:** `DataTests`: `Presets_are_served_from_the_bundled_file`, `User_materials_replace_round_trip`, `Print_history_replace_round_trip`, `Cure_run_round_trip_with_qa_test_run`, `Phase_timing_requires_process_and_seconds`. Add: cure-history delete tests and a `RunIssueTracker` unit test (worst deficit kept, sorted output, Take clears).
**Reference (source):** `src/SCureBox.Api/Endpoints/MaterialEndpoints.cs`, `src/SCureBox.Api/Endpoints/HistoryEndpoints.cs`, `src/SCureBox.Api/Endpoints/CureRunEndpoints.cs`, `src/SCureBox.Api/Infrastructure/RunIssueTracker.cs`, `src/SCureBox.Domain/Models/History.cs`, `src/SCureBox.Application/Platform/CloudReportDeletions.cs`, `tests/SCureBox.Api.Tests/DataTests.cs`, `docs/01-api-contract.md` §3–5.

---

### API-09 — Server-side recipe runner endpoints and recipe validation wiring
**Summary**
- **What it is for:** Routes to run a whole cure program on the machine by itself: start, pause, resume, abort, skip a step, and read the status.
- **Problem it solves:** If only the screen drives each step, a screen problem can break the cure. Programs also need one shared check before they run.
- **How we solve it:** The machine runs the whole program itself. A program can be picked by id or sent in full. Before start, one checker combines the range checks and the program rules.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/RecipeEndpoints.cs`, `Infrastructure/RecipeValidation.cs`
**Goal:** Run a whole program (Material) on the machine without the UI driving each phase: start by preset/user id or inline
material, pause, resume, abort, skip a step, read the status. The host supplies the recipe validator that combines the API range
checks with the Domain program rules.
**Depends on:** API-02, API-08 (`IMaterialStore.Find`); Application-Process (`IRecipeRunner`: `GetStatus()` → `RecipeStatus`, `Start(Material, string? runId, string? serialNumber)`, `Pause()`, `Resume()`, `Abort()`, `SkipStep()`; `RecipeValidator` record (`Func<Material,(bool ok,string? message,int? code)> Validate`), `RecipeValidator.BasicChecks`, constants `CoolTargetMin`, `TempMax`); Domain (`Material`, `ProgramValidator.Validate(steps)` → errors with `Field`, `Step`, `Message`, `Code`; `ProcessType.Cooling`).
**Files to create:**
* `src/SCureBox.Api/Endpoints/RecipeEndpoints.cs` — `public static class RecipeEndpoints` (group `/recipe`).
* `src/SCureBox.Api/Infrastructure/RecipeValidation.cs` — `public static class RecipeValidation { static RecipeValidator Create(); static (bool ok, string? message, int? code) Validate(Material material); }`.
**Public contract (200 always):**
| Method | Route | Body | Response |
|---|---|---|---|
| GET | `/api/recipe/status` | — | `RecipeStatus`: `{state ("idle"|"running"|"paused"|"aborted"|...), runId, materialId, materialName, stepIndex, totalSteps, process, phase, targetTemp, stepElapsedSec, stepRemainingSec, totalElapsedSec, estimatedTotalSec, startedAt, endedAt, message, errorCode}` |
| POST | `/api/recipe/start` | `{materialId}` or `{material:{...Material}}`, optional `runId`, `serialNumber` | `Envelope(runner.Start(...))` |
| POST | `/api/recipe/pause` | — | `Envelope(Pause())` |
| POST | `/api/recipe/resume` | — | `Envelope(Resume())` |
| POST | `/api/recipe/abort` | — | `Envelope(Abort())` |
| POST | `/api/recipe/skip` | — | `Envelope(SkipStep())` |
**Behaviour & rules:**
1. `start`: body not a JSON object → `{ok:false, message:"Body {materialId} or {material} required"}`. If `material` is an object → deserialize with `ApiJson.Options` (JsonException → `{ok:false, message:"Invalid material: <e.Message>"}`). Else if `materialId` (string or number text) is non-empty → `store.Find(id)`; null → `{ok:false, message:"Unknown material: <id>"}`. Still no material → the "Body ... required" message. Then `Envelope(r.Start(material, runId, serialNumber))`.
2. Runner refusals (Application-Process, all code 6015): `A program is already running - abort it first`; `A process is active - stop it before starting a program` (admission: refused while any manual process is active); pause/abort/skip without a run → `No program is running`; resume without pause → `No paused program`. Validation failure → `{ok:false, code, message}` with the validator's code (default 7001). Success messages: `Program '<name>' started`, `Program paused`, `Program resumed`, `Program aborted`, `Step skipped`.
3. `RecipeValidation.Validate`: first `RecipeValidator.BasicChecks(material)` (API ranges, codes 7001/7002); if it fails return it. Then `ProgramValidator.Validate(material.Steps)`; drop errors that are a Cooling-step temperature range error (`Field == "temperature"`, step found by `Step` number or index `n-1`, `Process == Cooling`, temperature within 20–80, message contains `Invalid temperature`) — the Domain step-editor window 30–75 °C is relaxed to the API window. No errors → (true, null, null); else (false, messages joined with `"; "`, first error's code). Other Domain rules (nitrogen block e.g. `After nitrogen...`, hold times, UV range, temperature chain) are enforced.
4. `RecipeValidation.Create()` → `new RecipeValidator(Validate)`, registered in DI before `AddSCureBoxProcess` (API-01).
5. While running, `/api/state.recipe` carries the status (API-05). An aborted run appears in `/api/cure-history` with status `aborted` under the given `runId`.
**Configuration:** none.
**Acceptance criteria:**
* Idle status has `state:"idle"` and every key listed above.
* `start {materialId:"preset-ST45", runId:"qa-recipe-run", serialNumber:"SN-1"}` → ok; status becomes `running` with `runId`, `materialName "Ultracur3D ST45"`, `totalSteps 3`, `process "Drying"`; second start → `ok:false, code:6015`.
* pause → `paused`; resume ok; abort → `aborted`; cure-history entry `qa-recipe-run` status `aborted`; skip when idle → `ok:false`.
* Unknown id → message contains `Unknown material`; inline Heating 99 °C → 7001; inline Cure uvIntensity 5 → 7002; Nitrogen followed by Heating → message contains `After nitrogen`; `{}` → ok:false.
**Tests:** `RecipeTests`: `Preset_runs_shows_in_state_double_start_is_6015_and_abort_works`, `Invalid_programs_are_refused_with_validation_codes`. Add a unit test that a Cooling step at 20 °C passes `RecipeValidation.Validate` while 15 °C fails with 7001.
**Reference (source):** `src/SCureBox.Api/Endpoints/RecipeEndpoints.cs`, `src/SCureBox.Api/Infrastructure/RecipeValidation.cs`, `src/SCureBox.Application/Recipe/RecipeValidator.cs`, `src/SCureBox.Application/Recipe/RecipeRunner.cs`, `src/SCureBox.Application/Contracts/IRecipeRunner.cs`, `tests/SCureBox.Api.Tests/RecipeTests.cs`.

---

### API-10 — System, update, network, network policy and cloud configuration
**Summary**
- **What it is for:** Settings-screen system actions: restart and power off, clock and network time, version, USB exports, software update from USB, offline mode, cloud settings, and network status and setup.
- **Problem it solves:** Users and service need to manage the machine, update it safely and set up the network from the screen. Without these routes they would need a computer and command line.
- **How we solve it:** Thin routes that pass each request to the system services, which do the real work. Errors come back with clear codes (for example USB or network problems). Updates must be signed.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/SystemEndpoints.cs`, `Endpoints/NetworkEndpoints.cs`
**Goal:** Settings-screen system actions: reboot/shutdown, clock and network time, version, USB exports, signed software update
from USB, offline/network policy, cloud sync configuration, wired-network status, safe network diagnostics and static IP. The API
is a thin adapter; behaviour lives in Platform services.
**Depends on:** API-02; Application-Platform (`ISystemService`: `Reboot, Shutdown, SetDateTime(date,time), Version(), NetworkTimeEnabled(), SetNetworkTime(bool), ExportLogs(), ExportCsv(filename, content), ExportReport(filename, content)`; `IUpdateService`: `Manifest()` (has `Ok`), `FindPackage()` (`Ok, Path, FileName, Message, Code`), `RunUpdate()`; `NetworkPolicy`: `OfflineByChoice, OfflineMode, ExpectsNetwork, Choose(bool?)`; `ICloudSync.Configure(url, key, name, interval)`; `INetworkService`: `Status(), Diagnostics(tool, address), SetStatic(dhcp, ip, gateway, subnet, dns)`).
**Files to create:**
* `src/SCureBox.Api/Endpoints/SystemEndpoints.cs` — `public static class SystemEndpoints` (group `/system` + `/network/policy` + `/cloud/config` on the api group) with `internal static string? Str(JsonElement? body, string name)`.
* `src/SCureBox.Api/Endpoints/NetworkEndpoints.cs` — `public static class NetworkEndpoints` (group `/network`).
**Public contract:**
| Method | Route | Body | Response |
|---|---|---|---|
| POST | `/api/system/reboot` | — | `Envelope(Reboot())` — `Rebooting...` / off-device `Reboot simulated` |
| POST | `/api/system/shutdown` | — | `Envelope(Shutdown())` — `Shutting down...` / `Shutdown simulated` |
| POST | `/api/system/datetime` | `{date:"YYYY-MM-DD", time:"HH:MM[:SS]"}` | `Envelope(SetDateTime(...))`; bad/missing → 200 `{ok:false, message:"Invalid date/time format"}` |
| GET | `/api/system/version` | — | `{appVersion, gitCommit, gitDate, lastBoot, os, kernel, python, runtime, emmcSerial}` |
| GET | `/api/system/network-time` | — | `{enabled}` (no `ok`) |
| POST | `/api/system/network-time` | `{enabled: true|false}` | `{ok, message, enabled}`; `enabled` missing or not a JSON boolean → 400 `{ok:false, message:"enabled must be true or false"}` |
| POST | `/api/system/export-logs` | — | `Envelope(ExportLogs())` — ok `Logs exported to USB` or `{ok:false, code:9083}` |
| POST | `/api/system/export-csv` | `{filename, content}` | `Json(ExportCsv(...))` — `{ok:true, message, path}` (`.csv`) or 9081 (`No Disk-on-Key found. Please connect a Disk-on-Key (USB drive).`) / 9082 |
| POST | `/api/system/export-report` | `{filename, content}` | same with `.html` |
| GET | `/api/system/update/manifest` | — | manifest JSON `{ok:true, version, sha256}` 200, or 404 with `{ok:false, code:9081|9086|9087, message}` |
| GET | `/api/system/update/package` | — | `.scu` bytes, `application/octet-stream`, attachment name `FileName` or the file's name; else 404 `{ok:false, code?, message (default "No update package")}` |
| POST | `/api/system/update` | — | `Json(RunUpdate())` — `{ok, steps:[{step,status}], version, message, code?}` |
| GET | `/api/network/policy` | — | `{ok:true, offline: bool|null, offlineMode, expectsNetwork}` |
| POST | `/api/network/policy` | `{offline: true|false|null}` | `Choose(offline)`; `{ok:true, offline, offlineMode, message}` |
| POST | `/api/cloud/config` | `{url, key, name?, interval?}` | missing url or key → 400 `{ok:false, message:"url and key required"}`; else `Envelope(Configure(url, key, name, interval))` |
| GET | `/api/network/status` | — | `{connected, ip, mac, gateway, interfaces:[{name,status:"UP"|"DOWN",ip}], internet, wireguardIp}` (+`code:9084` on error) |
| POST | `/api/network/diagnostics` | `{tool (default "ping"), address (default "8.8.8.8")}` | `Json(Diagnostics(...))` — `{ok, result, code?}` |
| POST | `/api/network/static` | `{dhcp: bool (only JSON true counts), ip (""), gateway (""), subnet ("255.255.255.0"), dns ("")}` | `Envelope(SetStatic(...))` |
**Behaviour & rules:**
1. `Str(body, name)`: string value; number / true / false → raw JSON text; absent / other kinds → null.
2. `network/policy` POST: `offline` = JSON true → true, false → false, anything else or missing → null (follow cloud enrolment); never refused. Message: offlineMode true → `Working without a network - the missing connection is not reported`; else `A network is expected - a missing connection is shown as before`. Persisted by Platform in `data/network-policy.json`.
3. `cloud/config`: `interval` only when a JSON number; `name` via `Str`. Writes `<data>/cloud.json` (Platform).
4. Diagnostics: unknown tool → `{ok:false, code:9080, result:"Unknown tool"}`; invalid address (e.g. shell metacharacters) → `{ok:false, code:9085, result:"Invalid address..."}`. The address is validated and never passed through a shell (Platform).
5. Static IP off-Linux → `{ok:true, message:"Network config simulated (off-device)"}`; nmcli error → 9084.
6. `datetime` switches network time off (Platform); `network-time` POST is the only way back on.
7. No admission rules in the API (reboot is not refused during a run — OPEN QUESTION whether `ISystemService.Reboot` checks for an active process; not visible here). During a DVT hang all POSTs answer 409.
**Configuration:** none in the API; Platform uses data dir, `keys/scure-update.pub`, USB mount detection.
**Acceptance criteria:**
* Version has all nine keys; `appVersion` matches `^\d+\.\d+\.\d+`.
* `datetime {date:"14/09/2026", time:"10:00"}` → 200 `{ok:false, message:"Invalid date/time format"}`; no body → ok:false; `{date:"2026-09-14", time:"10:00"}` → ok (simulated off-device).
* Exports: 200 and either ok (csv `path` ends `.csv`) or 9081/9082 with `Disk-on-Key` in the message; logs ok or 9083.
* Without a package: manifest 404, `ok:false`, code ∈ {9081, 9086, 9087}; package 404 `ok:false`.
* `cloud/config {url}` → 400 `url and key required`; full body → 200 ok and `<data>/cloud.json` exists.
* Network status keys present; interfaces have `name, status ∈ {UP, DOWN}, ip`.
* Diagnostics `nmap` → 9080 `Unknown tool`; `ping` of `127.0.0.1; rm -rf /` → 9085 with `Invalid address`; `ping 127.0.0.1` returns `ok` and `result` keys.
* Static `{dhcp:true}` → 200 with `ok`, `message`; off Linux `ok:true`.
* `network-time {enabled:"yes"}` → 400.
**Tests:** `SystemTests`: `Version_has_every_key`, `Datetime_validation`, `Exports_report_no_usb_with_9081_or_succeed`, `Update_manifest_and_package_are_404_without_a_package`, `Cloud_config_requires_url_and_key`, `Network_status_shape`, `Network_diagnostics_reject_unknown_tools_and_shell_injection`, `Network_static_is_simulated_off_device`. Add: network-time 400 and network/policy round trip.
**Reference (source):** `src/SCureBox.Api/Endpoints/SystemEndpoints.cs`, `src/SCureBox.Api/Endpoints/NetworkEndpoints.cs`, `src/SCureBox.Application/Platform/NetworkPolicy.cs`, `src/SCureBox.Application/Platform/ISystemService.cs`, `src/SCureBox.Application/Platform/IUpdateService.cs`, `src/SCureBox.Application/Platform/INetworkService.cs`, `tests/SCureBox.Api.Tests/SystemTests.cs`, `docs/01-api-contract.md` §2, §6.

---

### API-11 — Developer Mode endpoints (`/api/dev/*`): event log, LED calibration, LED power drive, PicoLog, HDT calibration
**Summary**
- **What it is for:** Engineering routes for Developer Mode: an event log, LED power calibration, an LED power test, the PicoLog temperature logger, and material heat-deflection (HDT) calibration.
- **Problem it solves:** Engineers need to calibrate and test the machine. Without these tools LED output could be uneven and material calibration could not be done or reported.
- **How we solve it:** Routes that save and apply LED calibration factors for four zones (checked to 0-1.5), drive LEDs with test factors, hand the PicoLog to the test bench, and run HDT calibration with a CSV report.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/DevEndpoints.cs`
**Goal:** Engineering routes behind the UI's Developer Mode: an append-only event log, the four-zone LED calibration factors
(persisted and applied to the controller), a calibrated LED power test drive with optional preview factors, the PicoLog TC-08
status and its hand-over to the DVT bench process, and the material HDT calibration state machine with CSV report.
**Depends on:** API-02; Application-Platform (`IDevEventLog.Append(string, object?)`, `ILedCalibrationStore`: `Factors`, `Validate(factors)` → reason or null, `Save(factors)` → stored, `Reset()` → stored, `ScaledOutputs(power, preview)`); Application-Process (`ICureController.SetLedFactors`, `SetUv`); Dvt-Hdt (`ITemperatureProbe`: `Status()`, `Release()`, `Resume()`; `IHdtCalibration`: `Running`, `Start(HdtStartRequest)`, `Abort()`, `Reset()`, `Status(int? samplesFrom)`, `ReportCsv()`; `HdtStartRequest`).
**Files to create:** `src/SCureBox.Api/Endpoints/DevEndpoints.cs` — `public static class DevEndpoints` (group `/dev`), zones `back, door, left, right`, factor range 0.0–1.5, private `ParseFactors(JsonElement? body, string name, bool clamp, out string error)`.
**Public contract:**
| Method | Route | Body / query | Response |
|---|---|---|---|
| POST | `/api/dev/log` | `{event, detail?}` | `{ok:true}`; event truncated to 200 chars (missing → ""), `detail` any JSON (cloned) |
| GET | `/api/dev/led-calibration` | — | `{ok:true, factors:{back,door,left,right}}` |
| POST | `/api/dev/led-calibration` | `{factors:{back,door,left,right}}` numbers | `{ok:true, factors:<stored>}`; malformed → 400 `{ok:false, message:"Invalid factors: <reason>"}` |
| POST | `/api/dev/led-calibration/reset` | — | `{ok:true, factors:{all 1.0}}` |
| POST | `/api/dev/led-power` | `{power: 0..100 (number or numeric string, default 0), factors?: {...}}` | `{ok, message: ok ? null : reason, outputs:{back,door,left,right}}` |
| GET | `/api/dev/picolog/status` | — | `{connected, ch1Available, temperature, deviceInfo, error}` (no `ok`) |
| POST | `/api/dev/picolog/release` | — | `{ok:true, message:"PicoLog TC-08 released to the DVT bench"}`; HDT running → `{ok:false, message:"HDT calibration is running - abort it first"}` |
| POST | `/api/dev/picolog/resume` | — | `{ok:true, message:"PicoLog TC-08 back with the firmware"}` |
| POST | `/api/dev/hdt/start` | `HdtStartRequest {hdtC, safetyMarginC?, samplingIntervalSec?, movingAverageWindowSec?, stabilityBandC?, stabilityTimeMin?, stabilityMaxRateCPerMin?, maxStabilizationTimeMin?, nextStepMaxTempDeltaC?, cooldownMaxWaitMin?, boostPower?, boostStartTempC?}` (bad body → defaults) | `Envelope(hdt.Start(req))` |
| POST | `/api/dev/hdt/abort` | — | always `{ok:true, message:"Abort requested - LEDs off"}` |
| POST | `/api/dev/hdt/reset` | — | `{ok, message: ok ? null : "Calibration is running"}` |
| GET | `/api/dev/hdt/status` | `samplesFrom` (int or null) | HDT status object (owned by Dvt-Hdt; keys below) |
| GET | `/api/dev/hdt/report.csv` | — | file `text/csv`, download name `hdt-calibration.csv` (UTF-8 bytes) |
**Behaviour & rules:**
1. `ParseFactors`: body must have `factors` as an object (else error `factors object required`); each of the four zones must be a JSON number (else error `'<zone>'`); with `clamp` each is clamped to 0..1.5.
2. `POST led-calibration`: parse without clamp → on error 400 `Invalid factors: <error>`; then `cal.Validate(factors)` (range 0..1.5) → on reason 400 `Invalid factors: <reason>`; `stored = cal.Save(factors)`; `controller.SetLedFactors(stored)`; dev-log `LED calibration saved` with the stored factors.
3. `reset`: `stored = cal.Reset()`, `SetLedFactors(stored)`, dev-log `LED calibration reset`.
4. `led-power` order: parse `power` (number; string parsed invariant; any other kind → 400 `Invalid power`); not finite or outside 0..100 → 400 `Invalid power {p} (0-100%)`; **admission: HDT running → 200 `{ok:false, message:"HDT calibration is running - abort it first"}`**; when `factors` is an object parse with clamp (failure → 400 `Invalid preview factors`); apply preview factors to the controller for this drive only; `power <= 0` → `SetUv(false, 0, Nm405)` else `SetUv(true, power, Nm405)`; restore `SetLedFactors(cal.Factors)` if a preview was used; `outputs = cal.ScaledOutputs(power, preview)`; dev-log `Physical LED outputs updated` with `{power, outputs, preview: bool}`.
5. `report.csv` dev-logs `Report exported` with `{rows: number of '\n'}`.
6. HDT refusals (Dvt-Hdt): `HDT calibration already running`, `Invalid material HDT {x} (30-200degC)`, `PicoLog TC-08 CH1 has no valid temperature - ...`, `A cure process is active - stop it before HDT calibration`.
7. HDT status keys: `state, running, finalStatus, message, hdtC, safetyMarginC, currentPower, stepIndex, totalSteps (9), rawTemp, rateCPerMin, avgTemp, stepElapsedSec, totalElapsedSec, startedAt, endedAt, picolog, factors, outputs, results, recommendedPower, boost, maxMeasuredTemp, heaterFanPwm, config (with powerLevels[]), sampleCount, samples?`.
8. Hang gate (API-12) exempts `/api/dev/picolog*` POSTs; every other POST here answers 409 during a hang.
9. No authentication — Developer Mode gating is UI-side only.
**Configuration:** `SCURE_SIM_TC08=1` simulated TC-08 (Dvt-Hdt); files `<data>/dev_events.jsonl`, `<data>/led_calibration.json` (Platform).
**Acceptance criteria:**
* `dev/log {event:"QA event", detail:{page:"settings"}}` → ok; `<data>/dev_events.jsonl` contains `QA event`.
* Calibration GET has four zones; save `{back:0.9, door:1.1, left:1.0, right:0.8}` → 200 ok, `back 0.9`, `<data>/led_calibration.json` exists; `back:2.0` → 400 starting `Invalid factors`; only `back` → 400; `back:"x"` → 400; reset → all 1.0.
* `led-power {power:101}` → 400; `{power:"abc"}` → 400; `{power:40, factors:{back:0.5, door:1, left:1, right:1}}` → 200 ok, `outputs.back 20`, `outputs.left 40`, state `uvOn:true`; `{power:0}` → ok, all outputs 0.
* PicoLog status keys; HDT status idle: `state "IDLE"`, `running false`, `totalSteps 9`, `config.powerLevels` array; reset → ok with `message:null`; abort → `Abort requested - LEDs off`; start `{hdtC:5}` → 200 ok:false containing `Invalid material HDT`; report.csv → 200 `text/csv`, filename `hdt-calibration.csv`.
**Tests:** `DevTests`: `Dev_log_appends_a_json_line`, `Led_calibration_get_save_validate_reset`, `Led_power_drive_validates_and_reports_outputs`, `Picolog_and_hdt_status_shapes`. Add: picolog release refused while HDT runs.
**Reference (source):** `src/SCureBox.Api/Endpoints/DevEndpoints.cs`, `src/SCureBox.Application/Hdt/IHdtCalibration.cs`, `src/SCureBox.Application/Hdt/ITemperatureProbe.cs`, `src/SCureBox.Application/Hdt/HdtStartRequest.cs`, `src/SCureBox.Application/Platform/ILedCalibrationStore.cs`, `tests/SCureBox.Api.Tests/DevTests.cs`, `docs/01-api-contract.md` §9.

---

### API-12 — DVT bench endpoints (`/api/dvt/*`), loopback-only switches and the DVT hang gate
**Summary**
- **What it is for:** Routes for design-verification (DVT) tests: UV meter control, a bench lock, UV sweep and UV-off timing tests, a planned software freeze test, LED check switch, and 'confirm at the machine' for cloud-started tests.
- **Problem it solves:** Safety and optical tests must be run and measured in a repeatable way. Some test actions are dangerous, so they must not be started by any remote caller.
- **How we solve it:** Special test routes run each test and return the measurements. Risky switches only accept calls from the machine itself. During a planned freeze, most changing requests are blocked with 409.

**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Endpoints/DvtEndpoints.cs`
**Goal:** Routes used by the DVT console, the DVT web page and the on-machine DVT runner: the Ophir StarBright meter on the
machine's USB, the bench lock lease, the UV linearity sweep (DVT-OPT-001/002), the UV-off-on-door-open timing (DVT-SAF-008), the
deliberate firmware hang (DVT-SAF-010) with its 409 gate, the in-memory LED panel check override (DVT-SAF-016) and the
"confirm at the machine" requests raised for tests started from sCure Cloud. JSON uses snake_case keys identical to sCure-A
`server/uv_sweep.py`.
**Depends on:** API-02, API-05 (hang state in `/api/state`), API-03 (heartbeat pause); Dvt-Hdt / Application (`SCureBox.Application.Dvt`: `UvSweep` (`Meter(identify)` → `MeterStatus {Present, Identity, ReadingMwCm2, Message}`, `SetMeterWavelength(int)` → `{Ok, WavelengthNm, Message}`, `Start(UvSweepRequest)`, `Status(samples)`, `Abort()` → string), `UvSweepRequest(int Wavelength, IReadOnlyList<int>? Steps, double Dwell=10, double Baseline=5, double Settle=5, double Tail=3, double Hz=5, bool Force=false)`, `UvOffTiming` (`Start(UvOffRequest)`, `Status(samples)`, `Abort(string by)`), `UvOffRequest(int Wavelength=405, int Intensity=100, double PlateauMaxSec=30, double StableSec=2, double OpenTimeoutSec=30, double TailSec=3, double Hz=20, bool Force=false, double AlarmWatchSec=15, bool Release=false)`, start results `{Ok, Message, Code, MeterWavelengthNm, MeterWavelengthVerified}`, `DvtBench` (`Owner`, `TryAcquire(who, TimeSpan?)`, `Release(who)`), `DvtHang` (`Prepare(int)` → `DvtHangStart(Ok, Status, Message, Sec)`, `Begin()`, `Active`, `Until`, `MinSec=5`, `MaxSec=300`, `DefaultSec=60`, `HeartbeatTimeoutSec`=20), `RemoteConfirm` (`Ask(id,title,detail,TimeSpan?)` → `Request{Id,...,Expires}`, `Status(id)` → `State {Pending, Accepted, Declined, Expired, Withdrawn, Unknown}`, `Withdraw(id)`; default timeout 10 min, max 60 min)); `SCureBox.Application.Supervision.LedCheckOverride` (`On`, `static Effective(LedHeatingConfig, LedCheckOverride?)` → `{Enabled, Panels: dict panel→sensor}`); Hardware (`SCureBox.Hardware.IHardwareConfig.LedHeating`, `OutputFreeze`); Native UI (shows the remote-confirm dialog and calls `Resolve`).
**Files to create:** `src/SCureBox.Api/Endpoints/DvtEndpoints.cs` — `public static class DvtEndpoints` with `public static void Map(RouteGroupBuilder api)`, extension `public static IApplicationBuilder UseDvtHangGate(this IApplicationBuilder app)`, `internal static readonly string[] HangAllowed`, `internal static bool IsLocal(HttpContext ctx)`, private `LedChecks`, `LocalOnly`, `Flatten<T>` (serialize with `ApiJson.Options` to a `JsonObject`).
**Public contract:**
| Method | Route | Query / body | Response |
|---|---|---|---|
| GET | `/api/dvt/meter` | `identify` (`OnLoose`, default false) | no meter → `{ok:false, present:false, message}`; else the flattened identity (`transport, path, firmware, instrument, head, head_type, units, unit_name, ranges, range_in_use, wavelengths, measurement_mode, wavelength_nm, errors`; empty when never identified) + `ok:true, present:true, reading_mw_cm2, message` |
| GET | `/api/dvt/bench` | — | `{ok:true, owner: string|null}` |
| POST | `/api/dvt/bench/claim` | `who` (required), `lease_s` (30, clamped 1..300) | `{ok:true, owner, lease_s, message:"bench held by {who} for {lease:0} s"}`; blank who → `{ok:false, message:"who= is required"}`; busy → `{ok:false, message:"the DVT bench is busy ({owner})"}` |
| POST | `/api/dvt/bench/release` | `who` | `{ok:true, owner, message:"released"}` (only the owner's release takes effect) |
| POST | `/api/dvt/meter/wavelength` | `nm` (0) | `{ok, wavelength_nm, message}` |
| POST | `/api/dvt/uv-sweep` | `wavelength` (405), `steps` (comma ints, optional), `dwell` (10), `baseline` (5), `settle` (5), `tail` (3), `hz` (5), `force` (`OnLoose`) | `{ok, message, code, meter_wavelength_nm, meter_wavelength_verified}`; a non-int step → `{ok:false, message:"bad parameter: steps '<raw>'"}` |
| GET | `/api/dvt/uv-sweep` | `samples` (`On`, default true) | flattened sweep status + `ok:true` |
| POST | `/api/dvt/uv-sweep/abort` | — | `{ok:true, message}` (`no sweep running` when idle) |
| POST | `/api/dvt/uv-off` | `wavelength` (405), `intensity` (100), `plateau_max` (30), `stable` (2), `open_timeout` (30), `tail` (3), `hz` (20), `force`, `alarm_watch` (15), `release` (`OnLoose`) | `{ok, message, code, meter_wavelength_nm, meter_wavelength_verified}` |
| GET | `/api/dvt/uv-off` | `samples` (`On`) | flattened UV-off status + `ok:true` |
| POST | `/api/dvt/uv-off/abort` | `by` (default the User-Agent, or `api`) | `{ok:true, message}` |
| POST | `/api/dvt/hang` | `sec` (60; whole number) | loopback only; `{ok:true, sec, heartbeatTimeoutSec}` |
| POST | `/api/dvt/led-checks` | `on` ∈ {1,true,on,0,false,off} (trimmed, lower-cased) | loopback only; LedChecks shape |
| GET | `/api/dvt/led-checks` | — | `{ok:true, enabled, override: bool?, panels:[...], sensors:{panel: sensor}}` (no loopback check) |
| POST | `/api/dvt/remote-confirm` | JSON `{id, title?, detail?, timeoutSec?}` | loopback only; `{ok:true, id, state:"pending", expires:<unix s>}`; empty id → 400 `{ok:false, message:"a confirmation needs an id"}` |
| GET | `/api/dvt/remote-confirm/{id}` | — | loopback only; `{ok:true, id, state}` with state lower-case enum name |
| DELETE | `/api/dvt/remote-confirm/{id}` | — | loopback only; withdraw, then `{ok:true, id, state}` |
**Behaviour & rules:**
1. `IsLocal(ctx)`: `RemoteIpAddress` non-null and `IPAddress.IsLoopback(ip.IsIPv4MappedToIPv6 ? ip.MapToIPv4() : ip)` (Kestrel on `*:3001` hands IPv4 as `::ffff:127.0.0.1`). Non-local → 403 with `only the DVT runner on this CureBox may hang the firmware` (hang), `... may switch the LED checks` (led-checks POST), `... may ask for a confirmation` (all remote-confirm routes). A `TestServer` request has no remote IP → treated as not local.
2. `hang`: order = local check → `sec` parse (non-integer → 400 `sec must be a whole number 5-300 (got '<raw>')`) → `hang.Prepare(sec)`: out of 5..300 → 400 `sec must be 5-300 (got N)`; already hung → 409 `the firmware is already hung for a DVT test`; neither heating nor UV on → 409 `nothing is on (heater or UV) - start heating or a UV output first; there is nothing for the watchdog to cut`; else capture state. The 200 reply is sent first; `hang.Begin()` runs in `ctx.Response.OnCompleted`. During the hang: no heartbeat (API-03), outputs frozen, `/api/state` returns the captured state + `dvtHang`. After it: outputs off, program ended as failed, Err 9017 when the watchdog trip record shows a cut (acknowledged via `POST /api/watchdog/ack`), else 7005.
3. `UseDvtHangGate` (installed after `UseScureApi`, before endpoints): when `DvtHang` is registered and `Active`, and the method is not GET/HEAD, and the path starts with `/api/` and does not start (case-insensitive) with any of `/api/dvt/meter`, `/api/dvt/bench`, `/api/dvt/remote-confirm`, `/api/dev/picolog` → 409 `{ok:false, message:"the firmware is hung for a DVT test (DVT-SAF-010) until <unix s> - no output commands"}` (the ` until N` part only when `Until` is known). GETs keep answering.
4. `led-checks` POST: invalid/missing `on` → 400 `on must be 1 or 0 (got '<raw>')`; sets `LedCheckOverride.On` in memory only (never written to components.json); logs warning (category `DVT`) `[DVT] LED panel checks override ON (all four panels, in memory)` / `off (components.json again)`. Response from `LedCheckOverride.Effective(cfg.LedHeating, o)`: `enabled`, `override` = `o.On`, `panels` = panel names sorted ordinal, `sensors` = panel → sensor name. With the override on, `/api/state.ledChecksEnabled` is true; panels `LED_LEFT`→`TEMP_LEFT`, `LED_RIGHT`→`TEMP_RIGHT`.
5. `remote-confirm` POST: body fields read only when JSON strings (`id`, `title`, `detail`); `timeoutSec` any JSON number (`TryGetDouble`); asking again with a pending id returns the same request. Only the screen (Native UI) resolves a request.
6. Sweep / UV-off refusals (Dvt-Hdt): already running; `wavelength must be 405 or 450...`; steps outside 10–100; intensity too low (e.g. 5); process active; HDT running; door open; program running (UV-off); meter unreachable; meter on another wavelength (`code:"METER_WAVELENGTH"` unless `force=1`); bench lease held → message starts `the DVT bench is busy`. While someone else holds the bench, `/api/dvt/meter` returns `ok:true, present:true, message:"the meter is in use by <owner>", reading_mw_cm2:null`.
7. `Flatten`: serialize the status record with `ApiJson.Options` and add `ok` (and for the meter `present`, `reading_mw_cm2`, `message`) as JSON object keys.
**Configuration:** `SCURE_SIM_METER=1` simulated StarBright (head `PD300RM-8W SIM-0001`).
**Acceptance criteria:**
* Meter (sim): ok, `present:true`, `head:"PD300RM-8W SIM-0001"`, numeric `reading_mw_cm2`; `meter/wavelength?nm=450` → `wavelength_nm:450`; `nm=365` → ok:false.
* Bench: claim without who → ok:false; claim `who=DVT bench recording&lease_s=30` → ok; `GET /api/dvt/bench` owner = that string; meter then `the meter is in use by DVT bench recording` and `reading_mw_cm2:null`; uv-sweep message starts `the DVT bench is busy`; same-who claim renews; release → owner null; meter reading numeric again.
* Sweep idle status has `running, status, phase, config, steps, error, meter, meter_wavelength_verified, dark_mw_cm2, n_samples`; `wavelength=365` → message starts `wavelength must be 405 or 450`; abort idle → `no sweep running`; a short sweep `steps=30,60` ends `status:"OK"` with two steps, rising mean, samples of 6 elements with first phase `baseline`, UV off after.
* UV-off: `intensity=5` refused; a short run ends `status:"OK"`, `mode:"program"`, `plateau_mw_cm2 > 30`, UV off afterwards, recipe not running.
* Hang from loopback: idle → 409; `sec=4`, `301`, `abc` → 400; with heating on → 200 `{ok:true, sec:5, heartbeatTimeoutSec:20}`; state shows `dvtHang.active`; `POST /api/cure/stop` → 409 containing `hung`; second hang → 409; `GET /api/dev/picolog/status` and `GET /api/dvt/meter` → 200; after it `dvtHang` absent, `isHeating:false`, `uvOn:false`, commands ok, `watchdog/ack` ok.
* From a non-loopback client: `POST /api/dvt/led-checks?on=1` and `POST /api/dvt/hang?sec=60` → 403; `ledChecksEnabled` stays false.
* LED checks from loopback: no `on` / `on=maybe` → 400; `on=1` → `enabled:true`, `panels ["LED_LEFT","LED_RIGHT"]`, sensors `TEMP_LEFT`/`TEMP_RIGHT`; `on=0` → `enabled:false`; components.json unchanged.
**Tests:** `DvtTests`: `Meter_reports_itself_and_takes_a_wavelength`, `The_bench_process_can_hold_the_meter_lock_on_a_lease`, `Sweep_validates_runs_and_reports_in_the_python_json`, `Uv_off_runs_a_real_program_and_reports_how_it_ended`. `DvtHangApiTests.Hang_contract_end_to_end`, `DvtLedChecksApiTests.Led_checks_override_on_off_and_validation` (both on `LoopbackApiFixture`), `DvtLocalOnlyTests.Hang_and_led_checks_are_refused_from_another_host`. Add: remote-confirm 403 off-loopback, 400 without id, pending → withdrawn state.
**Reference (source):** `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`, `src/SCureBox.Application/Dvt/DvtHang.cs`, `src/SCureBox.Application/Dvt/DvtBench.cs`, `src/SCureBox.Application/Dvt/RemoteConfirm.cs`, `src/SCureBox.Application/Dvt/UvSweep.cs`, `src/SCureBox.Application/Dvt/UvOffTiming.cs`, `src/SCureBox.Application/Supervision/LedCheckOverride.cs`, `tests/SCureBox.Api.Tests/DvtTests.cs`, `tests/SCureBox.Api.Tests/DvtHangApiTests.cs`, `docs/01-api-contract.md` §9a.

---

### API-13 — Integration test harness (`SCureBox.Api.Tests`)
**Summary**
- **What it is for:** A test setup that runs the full machine software inside the tests, with simulated hardware and a temporary data folder.
- **Problem it solves:** Without it, the web routes could only be checked on a real machine, which is slow, risky and hard to repeat.
- **How we solve it:** Start the whole software in memory with fake hardware and send real web requests to every route. A second variant acts as a local caller to test the machine-only DVT routes.

**Project / folder:** `tests/SCureBox.Api.Tests/SCureBox.Api.Tests.csproj` — root
**Goal:** Host the complete firmware in-process with simulated hardware and a throw-away data directory so every endpoint ticket
can be verified over real HTTP, plus a loopback variant for the DVT routes that require a local caller.
**Depends on:** API-01 (the `Program` marker and `ScureApiHost`), all API endpoint tickets; Hardware simulation (`SCURE_SIMULATE`), Dvt-Hdt simulations (`SCURE_SIM_TC08`, `SCURE_SIM_METER`).
**Files to create:**
* `tests/SCureBox.Api.Tests/SCureBox.Api.Tests.csproj` — `IsPackable=false`, `IsTestProject=true`, RootNamespace `SCureBox.Api.Tests`; packages `Microsoft.NET.Test.Sdk` 18.11.0, `xunit` 2.9.3, `xunit.runner.visualstudio` 4.0.1, `coverlet.collector` 10.1.0, `Microsoft.Extensions.TimeProvider.Testing` 10.11.0, `Microsoft.AspNetCore.Mvc.Testing` 10.0.13; ProjectReference `..\..\src\SCureBox.Api\SCureBox.Api.csproj`.
* `ApiFixture.cs` — `public class ApiFixture : WebApplicationFactory<Program>`; `public sealed record ApiResponse(HttpStatusCode Status, string Body, string? ContentType)`.
* `DvtHangApiTests.cs` also defines `public sealed class LoopbackApiFixture : ApiFixture` (an `IStartupFilter` that sets `ctx.Connection.RemoteIpAddress = IPAddress.Loopback` first in the pipeline).
* Test classes: `StateTests`, `CureTests`, `HardwareTests`, `DataTests`, `RecipeTests`, `SystemTests`, `DevTests`, `DvtTests`, `DvtHangApiTests`, `DvtLedChecksApiTests`, `DvtLocalOnlyTests`, `StaticUiTests`, `SystemdWatchdogTests`, `WatchdogHeartbeatTests`, `DvtBenchHostTests` (Dvt-Hdt area).
**Public contract:**
* `ApiFixture`: static ctor sets env `SCURE_SIMULATE=1`, `SCURE_SIM_TC08=1`, `SCURE_SIM_METER=1`, clears `SCURE_SIM_NFC`. Instance: `DataDir` = `<temp>/scurebox-api-tests/<guid>` (created), `UiDir` = first `ui/dist` with `index.html` walking up from `AppContext.BaseDirectory`, else `<base>/wwwroot` if it has `index.html`, else null; `Client`; `HasUi`. `ConfigureWebHost` sets `SCURE_SIMULATE=1`, `SCURE_DATA_DIR=DataDir`, `SCURE_UI_DIR=UiDir ?? DataDir/no-ui`, `DATABASE_URL=""`. Dispose deletes DataDir (IO errors ignored).
* Helpers: `GetAsync(path)`, `PostAsync(path, object? body = null)` (JSON body via `JsonContent.Create`), `PostRawAsync(path, string json)`, `StateAsync()`, `WaitStateAsync(Func<JsonElement,bool> until, TimeSpan timeout)` (polls every 200 ms, returns last state).
* `ApiResponse`: `Json` (parsed root), `Ok` (`ok` is JSON true), `Code` (`code` number or null), `Message` (`message` string or null), `static Task<ApiResponse> From(HttpResponseMessage)`.
**Behaviour & rules:**
1. One host per test class (`IClassFixture<ApiFixture>`); tests in a class share machine state, so each test that starts outputs stops them (`/api/cure/stop`).
2. Static-UI tests return early (pass) when `HasUi` is false.
3. Tests must not touch real hardware or network beyond loopback (`ping 127.0.0.1`; cloud URL `http://127.0.0.1:9/`).
**Configuration:** the env vars above.
**Acceptance criteria:** `dotnet test tests/SCureBox.Api.Tests` passes on Windows and Linux without hardware, USB drive or UI build (UI tests skip).
**Tests:** this ticket is the harness; the per-ticket test lists above enumerate the facts to port.
**Reference (source):** `tests/SCureBox.Api.Tests/ApiFixture.cs`, `tests/SCureBox.Api.Tests/DvtHangApiTests.cs`, `tests/SCureBox.Api.Tests/SCureBox.Api.Tests.csproj`, all `tests/SCureBox.Api.Tests/*Tests.cs`.
