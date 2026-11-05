## DVT bench & HDT — overview

The DVT (design verification testing) and HDT (heat deflection test / material calibration) area gives engineers machine-side, machine-clock instruments for verification tests and material calibration. It has two halves:

1. **Inside the firmware process** (`scurebox`, API on :3001, project `SCureBox.Application`):
   - `DvtBench`: one lock for the shared bench instruments (the LEDs and the StarBright meter). Holds can be leased.
   - The UV power meter: the Ophir StarBright over libusb, plus a simulated meter.
   - `UvSweep`: UV linearity sweep (DVT-OPT-001 at 405 nm, DVT-OPT-002 at 450 nm).
   - `UvOffTiming`: UV off when the door opens (DVT-SAF-008 step 2).
   - `DvtHang`: firmware hang on purpose, so the output watchdog has to cut (DVT-SAF-010).
   - `RemoteConfirm`: a test asked for from the cloud must be confirmed at the machine.
   - The PicoLog TC-08 thermocouple probe (native `libusbtc08`) and its simulation.
   - `HdtCalibration`: material HDT calibration, a 10..90 % LED power ladder.
2. **The separate DVT bench process** (`scurebox --dvt-bench`, :3002, systemd `scurebox-dvt-bench.service`, code in `SCureBox.Application/Dvt/Bench` + `SCureBox.Api/Bench`). It talks to the firmware only over HTTP and keeps measuring even when the firmware is frozen, killed or restarting:
   - `BenchRecorder`: a generic recording at 1..20 Hz of TC-08 + StarBright + firmware state, with marks and auto-events.
   - `BenchRunner`: runs one whole catalog test (DVT-SAF-002, heater thermistor open) on its own clock, with prompts to the operator.
   - `SimulatedBenchWorld`: a complete fake machine for the tests and for `SCURE_SIMULATE=1`.

Instrument ownership rules (they hold across all tickets):
- The TC-08 is normally open in the firmware (`PicoLogTc08Probe`). The bench takes it with `POST /api/dev/picolog/release` and gives it back with `POST /api/dev/picolog/resume`.
- Two handles on the StarBright at the same time wedge it (LIBUSB_ERROR_IO). Inside one process, a static semaphore admits one conversation at a time. Across processes, the bench claims the firmware's `DvtBench` on a 30 s lease (`/api/dvt/bench/claim`) and renews it every 10 s.
- Every exit path of every measurement leaves the LEDs and the heater OFF.

All "now" values come from an injected `TimeProvider`, so tests drive a `FakeTimeProvider`. Blocking waits use the extension `TimeProvider.Wait(TimeSpan, CancellationToken) -> bool cancelled` (DVT-01).

Ticket list:
- DVT-01: DVT bench lock, clock waits and UV meter abstraction (StarBright libusb + simulated).
- DVT-02: UV linearity sweep + meter endpoints.
- DVT-03: UV-off-on-door-open timing.
- DVT-04: Firmware hang for the watchdog test (DvtHang).
- DVT-05: Remote confirmation at the machine (RemoteConfirm).
- DVT-06: PicoLog TC-08 probe (native interop, firmware-side reader, simulation).
- DVT-07: Material HDT calibration (state machine, model, CSV report, LED-calibration math).
- DVT-08: Bench-process contracts, trace math, TC-08 bench source and BenchRecorder.
- DVT-09: BenchRunner (DVT-SAF-002) and SimulatedBenchWorld.
- DVT-10: DVT bench host process (HTTP API, firmware client, safety net, systemd unit).

---

### DVT-01 — DVT bench lock, clock waits and UV meter abstraction (StarBright over libusb + simulated meter)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — folders `Dvt/` and `Devices/`
**Goal:** Lets only one DVT measurement own the shared bench instruments (LEDs + StarBright) at a time. An outside process can hold the lock on a renewable lease. Also defines the UV power meter abstraction, a real driver for the Ophir StarBright (raw libusb vendor control transfers, no Ophir software) and a simulated meter, and gives the blocking, fake-clock-friendly waits that every DVT thread uses.
**Depends on:** Domain (Wavelength). The consumers are DVT-02, DVT-03, DVT-08, DVT-10 and Api (`/api/dvt/bench*`, `/api/dvt/meter*`).
**Files to create:**
- `src/SCureBox.Application/Dvt/DvtBench.cs` — `DvtBench`
- `src/SCureBox.Application/Devices/TimeProviderWaits.cs` — `internal static class TimeProviderWaits` (needs `InternalsVisibleTo` for the test project, or keep it internal to the assembly)
- `src/SCureBox.Application/Dvt/UvMeter.cs` — `UvMeterException`, `IUvMeter`, `IUvMeterSource`, `MeterIdentity`
- `src/SCureBox.Application/Dvt/StarBrightUsbMeter.cs` — `StarBrightUsbSource`, `StarBrightUsbMeter` (nested `private static class LibUsb`)
- `src/SCureBox.Application/Dvt/SimulatedUvMeter.cs` — `SimulatedUvMeterSource`
**Public contract:**
```csharp
namespace SCureBox.Application.Dvt;
public sealed class DvtBench {
  public DvtBench();                       // uses TimeProvider.System
  public DvtBench(TimeProvider timeProvider);
  public string? Owner { get; }            // expires a lapsed lease first
  public bool TryAcquire(string who, TimeSpan? lease = null);
  public bool Renew(string who, TimeSpan? lease);
  public void Release(string who);
}
namespace SCureBox.Application.Devices;
internal static class TimeProviderWaits {
  public static bool Wait(this TimeProvider tp, TimeSpan delay, CancellationToken ct); // true = cancelled
  public static void Sleep(this TimeProvider tp, TimeSpan delay);                       // not cancellable
}
public sealed class UvMeterException(string message, Exception? inner = null) : Exception;
public interface IUvMeter : IDisposable {
  MeterIdentity Identify(); int? WavelengthNm(); void SetWavelength(int nm); double? PowerMwCm2();
}
public interface IUvMeterSource { IUvMeter Open(); }   // throws UvMeterException when none
public sealed record MeterIdentity {   // JSON names in brackets
  string Transport = "usb" [transport]; string? Path [path]; string? Firmware [firmware]; string? Instrument [instrument];
  string? Head [head]; string? HeadType [head_type]; string? Units [units]; string? UnitName [unit_name];
  string? Ranges [ranges]; string? RangeInUse [range_in_use]; string? Wavelengths [wavelengths];
  string? MeasurementMode [measurement_mode]; int? WavelengthNm [wavelength_nm]; IReadOnlyList<string>? Errors [errors];
}  // all init-only properties
public sealed class StarBrightUsbSource : IUvMeterSource {
  public static readonly TimeSpan GateWait = TimeSpan.FromSeconds(10);
  public IUvMeter Open();
}
public sealed class StarBrightUsbMeter : IUvMeter {
  public const ushort VendorOphir = 0x0BD3;
  public static DateTimeOffset? StuckSince { get; }
  public StarBrightUsbMeter(int timeoutMs = 6000, Action? release = null);
  public string Path { get; }                 // "usb:{bus}-{address}"
  public string Query(string cmd);
  public static int? ParseWavelength(string reply);
}
public sealed class SimulatedUvMeterSource : IUvMeterSource {
  public SimulatedUvMeterSource(Func<(bool On, double Pct, int? Nm)> uv, double noise = 0.003, int? seed = null);
  public int Wavelength { get; set; } = 405;
  public IUvMeter Open();
}
```
**Behaviour & rules:**
1. `DvtBench`: every member takes one lock. `Expire()` clears the owner when `_leaseEnd` is set and now >= `_leaseEnd`. `TryAcquire`:
   - Bench free: set the owner. `_leaseEnd` = now + lease, or null for a hold without a lease (that hold stays until released).
   - Bench held by the same `who`: renew and return the result of `Renew`.
   - Bench held by another owner: return false.
2. `Renew(who, lease)`: false when `who` is not the owner (after expiry). Otherwise `_leaseEnd` = now + lease (or null) and true. `Release(who)` clears only when `who` is the owner.
3. `Wait`: return true at once if `ct` is already cancelled. Otherwise `Task.Delay(delay, tp, ct).GetAwaiter().GetResult()` and return false; `OperationCanceledException` returns true. `Sleep` is `Task.Delay(delay, tp)` blocking.
4. `StarBrightUsbSource.Open()`: a process-wide `static SemaphoreSlim Gate = new(1,1)`. If it cannot be entered within `GateWait` (10 s), throw `UvMeterException("the StarBright is busy - another request is using it")`. Then create a `StarBrightUsbMeter(release: Release)`. `Release` frees the gate exactly once (an Interlocked flag), whether the meter's `Dispose` or a failed constructor gets there first.
5. libusb library name `"libusb-1.0.so.0"`. Error constants: ErrorIo = -1, ErrorAccess = -3, ErrorPipe = -9. P/Invokes: libusb_init, libusb_exit, libusb_get_device_list, libusb_free_device_list, libusb_ref_device, libusb_unref_device, libusb_get_device_descriptor (packed 18-byte DeviceDescriptor struct), libusb_get_bus_number, libusb_get_device_address, libusb_open, libusb_close, libusb_kernel_driver_active, libusb_detach_kernel_driver, libusb_set_configuration, libusb_control_transfer, libusb_error_name. `ErrorName(code)` falls back to the number.
6. Constructor:
   - `libusb_init`. A `DllNotFoundException` becomes `UvMeterException("libusb-1.0 is not installed on the machine (apt install libusb-1.0-0) - the StarBright needs it")`; a non-zero rc becomes "libusb init failed (…)".
   - Find the first device with idVendor 0x0BD3. If none is found:
     - `StuckSince` is set and less than 2 h ago: "the StarBright stopped answering at HH:mm and has dropped off the USB - switch it off, unplug it, wait 10 s, switch it on and plug it back in".
     - Otherwise: "no Ophir StarBright on USB - plug the meter into the machine and switch it on".
   - `libusb_open`. ErrorAccess gives "USB access denied - the service must run as root or a udev rule must allow VID 0bd3".
   - Detach the kernel driver on interface 0 if one is active.
   - `libusb_set_configuration(1)`: ErrorAccess gives the same "access denied" message; any other result is ignored.
   - `Path = "usb:{bus}-{address}"`. On any failure call Dispose, then rethrow.
7. `Query(cmd)`:
   - If the meter is already stuck, throw the stored stuck message.
   - Send ASCII `"$" + cmd + "\r\n"` with control transfer OUT (bmRequestType 0x40, request 2, value 0, index 0), then read the reply with IN (0xC0, request 4) into a 4096-byte buffer. Timeout `timeoutMs` (default 6000).
   - rc < 0 with ErrorIo or ErrorPipe: set `StuckSince = UtcNow` and the stuck message "the StarBright stopped answering (ERR) - switch the meter off, unplug it, wait 10 s, switch it on and plug it back in", then throw `'cmd': <stuck>`. Every later command of this conversation then fails at once. NEVER do a USB reset.
   - Any other negative rc: "'cmd': USB transfer failed (…)".
   - Trim the reply of CR, LF, space and NUL. A reply starting with `*` returns the rest, trimmed. Anything else throws "'cmd' -> reply".
8. `Identify()`:
   - Sends SI (units), VE (firmware), II (instrument), HI (head), HT (head type), AR (ranges), GU (range in use), AW (wavelengths), MM (measurement mode), then `WavelengthNm()`.
   - A failing command adds its message to `Errors` and leaves the field null, unless the meter is stuck (then the exception propagates).
   - Units map to UnitName: w→"W/cm2", W→"W", j→"J/cm2", J→"J", d→"dBm", X→"(passive)", l→"lux", c→"fc", u→"lm"; otherwise the raw value.
9. `WavelengthNm()` sends `AW` and parses the reply; on error it returns null. `ParseWavelength(reply)` splits on whitespace:
   - First token "CONTINUOUS": idx = f[3] and the result is f[3+idx]. Check: "CONTINUOUS 190 1100 2 365 405 450" → 405.
   - Otherwise: idx = f[0] (1-based) and the result is f[idx]. Checks: "2 405 450" → 450; "1 405" → 405.
   - An out-of-range index or an empty reply → null. Check: "3 405 450" → null.
10. `SetWavelength(nm)` sends `"WL {nm}"`. `PowerMwCm2()` sends `SP` and returns the invariant double × 1000 (W/cm2 → mW/cm2). A parse failure or a `UvMeterException` returns null.
11. `Dispose()`: run the release callback once, `libusb_close`, `libusb_exit`.
12. Simulated meter:
    - dark = 0.002.
    - UV off or no wavelength → dark.
    - Otherwise gain = 0.5 at 450 nm, else 0.9, and value = gain × pct × (1 − 0.0012 × pct).
    - ×0.85 when the commanded nm ≠ the meter's `Wavelength`.
    - Then × (1 + U(−1,1) × noise) and add dark.
    - Identify returns Transport "simulated", Path "sim", Firmware "SIM", Instrument "StarBright (simulated)", Head "PD300RM-8W SIM-0001", HeadType "SI", Units "w", UnitName "W/cm2", Wavelengths `"2 405 450 (set {Wavelength})"`, WavelengthNm = Wavelength.
    - The wavelength setting persists across opens.
**Configuration:** `SCURE_SIM_METER` (firmware DI: anything but "", "0", "false" → `SimulatedUvMeterSource` fed from `CureController.GetState()` → `(UvOn, UvIntensity, UvWavelength)`; otherwise `StarBrightUsbSource`). Registered with `TryAddSingleton<DvtBench>()` and `TryAddSingleton<IUvMeterSource>`.
**Acceptance criteria:**
- A 30 s lease renewed at 20 s is still held at 40 s and gone at 51 s. After that `Renew` returns false and a new owner can acquire. A hold without a lease survives 1 h.
- The same owner calling `TryAcquire` again returns true and extends the lease; a different owner gets false.
- `ParseWavelength` gives exactly the values listed in rule 9.
- A second `StarBrightUsbSource.Open()` while one meter is undisposed waits up to 10 s and then throws "the StarBright is busy …".
- After one IO/PIPE failure, every further `Query` on that meter throws the stuck message without touching USB.
**Tests:** `BenchRecorderTests.A_firmware_bench_lease_runs_out_by_itself` (lease semantics with FakeTimeProvider); `UvSweepTests.Meter_wavelength_reply_parsing` (Theory with the 5 inline cases above); `UvSweepTests` absent-meter case ("no Ophir StarBright" message prefix via an `AbsentMeter` source).
**Reference (source):** `src/SCureBox.Application/Dvt/DvtBench.cs`, `src/SCureBox.Application/Devices/TimeProviderWaits.cs`, `src/SCureBox.Application/Dvt/UvMeter.cs`, `src/SCureBox.Application/Dvt/StarBrightUsbMeter.cs`, `src/SCureBox.Application/Dvt/SimulatedUvMeter.cs`, `src/SCureBox.Application/ProcessServiceCollectionExtensions.cs`

---

### DVT-02 — UV linearity sweep (DVT-OPT-001 / DVT-OPT-002) and meter endpoints
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/`; endpoints in `src/SCureBox.Api` `Endpoints/DvtEndpoints.cs` (Api area hosts the endpoints)
**Goal:** Measures StarBright irradiance at a ladder of LED intensities on one wavelength, using the machine's own clock. Every lit step gets a mean and standard deviation, plus a dark baseline. Also answers "is a meter present / what does it read" and sets the meter's wavelength. The JSON is identical to the Python `server/uv_sweep.py`.
**Depends on:** DVT-01, DVT-07 (IHdtCalibration.Running), Application-Process (`ICureController`: `AnyProcessActive`, `GetState()` → `MachineState.DoorClosed/UvOn/LedTemps`, `SetUv(bool, double, Wavelength)`), Domain (`Wavelength`, `WavelengthExtensions.TryParse(int, out Wavelength)`), Api.
**Files to create:** `src/SCureBox.Application/Dvt/UvSweep.cs`, which holds `UvSweep`, `UvSweepRequest`, `UvSweepConfig`, `UvSweepStep`, `UvSweepStatus`, `UvSweepStartResult`, `MeterStatus`, `MeterWavelengthResult`.
**Public contract:**
```csharp
public sealed class UvSweep {
  public static readonly IReadOnlyList<int> DefaultSteps = { 30, 40, 50, 60, 70, 80, 90, 100 };
  public UvSweep(ICureController hardware, IUvMeterSource meters, IHdtCalibration hdt, TimeProvider timeProvider, ILogger<UvSweep> log, DvtBench? bench = null);
  public bool Running { get; }
  public MeterStatus Meter(bool identify = false);
  public MeterWavelengthResult SetMeterWavelength(int nm);
  public UvSweepStartResult Start(UvSweepRequest r);
  public UvSweepStatus Status(bool samples = true);
  public string Abort();
}
public sealed record UvSweepRequest(int Wavelength, IReadOnlyList<int>? Steps, double Dwell = 10, double Baseline = 5, double Settle = 5, double Tail = 3, double Hz = 5, bool Force = false);
public sealed record UvSweepConfig(int Wavelength [wavelength], IReadOnlyList<int> Steps [steps], double Dwell [dwell], double Baseline [baseline], double Settle [settle], double Tail [tail], double Hz [hz]);
public sealed record UvSweepStep(int Intensity [intensity], double? MeanMwCm2 [mean_mw_cm2], double? SdMwCm2 [sd_mw_cm2], int N [n], double DwellS [dwell_s], double? LedMaxC [led_max_c]);
public sealed record UvSweepStatus { running, status="IDLE", phase="idle", config, samples (List<object?[]>), n_samples (omitted when null), steps, error, aborted, started (unix s double?), finished, elapsed, step_index, intensity, reading, meter, meter_wavelength_nm, meter_wavelength_verified, dark_mw_cm2 }
public sealed record UvSweepStartResult(bool Ok, string Message, string? Code, int? MeterWavelengthNm, bool? MeterWavelengthVerified) { public static UvSweepStartResult Fail(string message); }
public sealed record MeterStatus(bool Present, MeterIdentity? Identity, double? ReadingMwCm2, string? Message);
public sealed record MeterWavelengthResult(bool Ok, int? WavelengthNm, string? Message);
```
Sample row format: `[t_s (3 dp), mW/cm2 (4 dp) | null, intensity %, phase ("baseline"|"step"|"tail"), hottest LED °C (2 dp) | null, uv_on bool]`.
**Behaviour & rules:**
1. `Meter(identify)`:
   - While a sweep runs: `(true, sweep identity, last reading, "a sweep is running - values from the sweep")`.
   - While `DvtBench.Owner` is set: `(true, cached identity (may be null), null, "the meter is in use by {owner}")`, without opening the meter.
   - Otherwise open the meter. Run Identify only when `identify` is set or nothing is cached (Identify is nine commands). Then refresh `WavelengthNm` and return one `PowerMwCm2()` reading.
   - On `UvMeterException`: clear the cache and return `(false, null, null, msg)`.
2. `SetMeterWavelength(nm)`:
   - Only 405 or 450, else "wavelength must be 405 or 450 (got N)".
   - Refused while running: "a sweep is running - the meter is busy".
   - Open, set, read back. Ok = (read == nm); otherwise the message is "meter reports X nm after setting Y".
3. `Start` checks, in order:
   - Already running: "a sweep is already running".
   - Wavelength not parsable: "wavelength must be 405 or 450 (got N)".
   - Steps: null or empty → DefaultSteps. Any step < 10 or > 100: "steps must be percentages between 10 and 100".
   - dwell ≤ 0, baseline < 0, tail < 0 or settle ≤ 0: "dwell and settle must be above 0 s, baseline and tail not below 0 s".
   - Build the config with settle = min(settle, dwell) and hz = clamp(hz, 0.5, 10).
   - `AnyProcessActive`: "a process is running (heating, cooling or UV) - stop it first".
   - HDT running: "HDT calibration is running - abort it first".
   - `DoorClosed == false`: "door open - close the door (the LEDs are interlocked)".
   - Open the meter and read Identify + WavelengthNm. A `UvMeterException` gives "StarBright not reachable: …".
   - Meter wavelength ≠ request and not forced: `(false, "the StarBright is set to X nm but this test is at Y nm - set the meter to Y nm first (or force=1 to record it as unverified)", "METER_WAVELENGTH", X, false)`.
   - `bench.TryAcquire("uv-sweep")` fails: "the DVT bench is busy ({owner})".
   - Success: start a background thread named "dvt-uv-sweep" and return ok with "UV sweep started at Y nm: [s1, s2, …] x D s", plus the meter wavelength and the verified flag.
4. Run:
   - Open the meter.
   - `Hold(seconds, phase, intensity, uvOn)` paces samples on an absolute schedule (`next += period`). When it falls behind, it does not wait (only checks cancel). It returns false when cancelled.
   - Each sample reads the meter and `CachedState()` (`GetState()` at most once per 1.0 s), and records the row.
   - While uvOn: `DoorClosed == false` throws "the door opened during the {p} % step - sweep stopped, LEDs off"; `!st.UvOn` throws "the LEDs went off during the {p} % step (a supervision fault) - sweep stopped". Both end as status ERROR.
5. Sequence:
   - Phase "baseline": `SetUv(false,0,wl)` and hold `Baseline` s. `DarkMwCm2` = mean of the baseline readings (4 dp), or null.
   - For each step: phase "step" with `StepIndex = i`, then `SetUv(true, pct, wl)`. A refusal sets Error "UV refused at {p} %: {msg}" and breaks the loop. Otherwise reset the state cache and hold `Dwell`.
   - Step result = the readings of this pct with t ≥ now − settle: mean (4 dp), population SD (4 dp; 0.0 for one reading; null for none), N, dwell_s (1 dp), LedMax from a forced state read.
   - Phase "tail": UV off, and hold `Tail` only when every step completed and nothing was cancelled.
   - LedMax = max of the non-null `MachineState.LedTemps` values, rounded to 2 dp.
6. `finally`:
   - UV off (best effort), dispose the meter, `bench.Release("uv-sweep")`.
   - Status: ABORTED if cancelled; ERROR if Error is set; OK when every step has a non-null mean; INCOMPLETE otherwise.
   - Phase "done", Intensity 0, Running false, Finished = unix s, Elapsed (1 dp).
   - Other exceptions are logged, and the error is truncated to 300 chars.
7. `Abort()`: with no sweep it returns "no sweep running" and touches nothing (the UV may belong to a cure). Otherwise cancel and return "abort requested - LEDs go off".
8. Endpoints (Api; all answer HTTP 200 with `ok`):
   - `GET /api/dvt/meter?identify=` → `{ok:false,present:false,message}`, or the flattened `MeterIdentity` plus `ok,present,reading_mw_cm2,message`.
   - `POST /api/dvt/meter/wavelength?nm=` → `{ok,wavelength_nm,message}`.
   - `POST /api/dvt/uv-sweep?wavelength=405&steps=30,40&dwell=10&baseline=5&settle=5&tail=3&hz=5&force=` → `{ok,message,code,meter_wavelength_nm,meter_wavelength_verified}`. A step that does not parse gives `{ok:false,message:"bad parameter: steps '…'"}`.
   - `GET /api/dvt/uv-sweep?samples=1` → flattened status + `ok`.
   - `POST /api/dvt/uv-sweep/abort` → `{ok:true,message}`.
   - The lease endpoints `GET /api/dvt/bench` → `{ok,owner}`. `POST /api/dvt/bench/claim?who=&lease_s=30`: lease clamped to 1..300, an empty who gives "who= is required", success `{ok,owner,lease_s,message:"bench held by {who} for {lease:0} s"}`, busy "the DVT bench is busy ({owner})". `POST /api/dvt/bench/release?who=` → `{ok,owner,message:"released"}`.
**Configuration:** none (DI singletons `UvSweep`, `DvtBench`).
**Acceptance criteria:**
- A simulated sweep records every step with a mean > dark and ends OK with the LEDs off.
- A meter set to the other wavelength is refused with code METER_WAVELENGTH unless force=1. After `SetMeterWavelength` it is accepted.
- The door opening while a step is lit → ERROR, LEDs off, no dark readings stored as a step. The door opening between steps refuses the next step (the same error path).
- Refused when the door is open, when a process is active, when HDT is running, or when the meter is missing.
- While another bench owner holds the lock, `Meter()` does not open the meter. The Identify count stays the same; `identify:true` forces a new identify.
**Tests:** `UvSweepTests` (Simulated_sweep_measures_every_step_and_switches_the_leds_off, Meter_on_the_other_wavelength_is_refused_unless_forced_and_can_be_set_remotely, Abort_stops_with_the_leds_off, Door_opening_while_lit_stops_the_sweep_instead_of_recording_dark_readings, Door_opening_between_steps_refuses_the_next_step, Refusals_door_process_hdt_and_missing_meter, Meter_wavelength_reply_parsing); `UvOffTimingTests.Meter_status_does_not_open_the_meter_while_a_bench_measurement_holds_it` (CountingSource); Api `DvtTests.Meter_reports_itself_and_takes_a_wavelength`, `The_bench_process_can_hold_the_meter_lock_on_a_lease`, `Sweep_validates_runs_and_reports_in_the_python_json`. All use `ProcessRig` (FakeTimeProvider + simulated hardware) and `SimulatedUvMeterSource(noise:0, seed:1)`.
**Reference (source):** `src/SCureBox.Application/Dvt/UvSweep.cs`, `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`, `tests/SCureBox.Application.Tests/Process/UvSweepTests.cs`, `tests/SCureBox.Api.Tests/DvtTests.cs`

---

### DVT-03 — UV-off-on-door-open timing (DVT-SAF-008 step 2)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/`
**Goal:** Measures, on the machine's clock, how long the UV takes to go dark after the door opens during a cure:
- dark reading → a real UV-only cure program (or a direct UV command) until the StarBright plateau → the operator opens the door → sampling at `hz` until the reading is below 10 % and back at the dark level → tail → alarm watch.
- It records the program end state and the alerts, for the alarm check of the test.
**Depends on:** DVT-01, DVT-02 (shares `UvSweepStartResult`), DVT-07 (IHdtCalibration), Application-Process (`ICureController`: `AnyProcessActive`, `DoorOpenNow()`, `GetState()` [Alerts, AlertDetails, DoorAborted, UiAlerts, UvOn], `SetUv`, `OpenDoor()`; `IRecipeRunner`: `Start(Material)`, `GetStatus()` [State, Message, ErrorCode], `Abort()`), Domain (`Material`, `CureStep`, `ProcessType.Cure/Bleacher`, `Wavelength.Nm450`), Api.
**Files to create:** `src/SCureBox.Application/Dvt/UvOffTiming.cs`, which holds `UvOffTiming`, `UvOffRequest`, `UvOffStatus`, `ProgramEnd`.
**Public contract:**
```csharp
public sealed class UvOffTiming {
  public const double OffFraction = 0.10, StableBandFraction = 0.02, ZeroFraction = 0.005, ZeroFloorMwCm2 = 0.01, ZeroHoldSec = 0.5, InterlockLimitSec = 12.0;
  public UvOffTiming(ICureController hardware, IUvMeterSource meters, IHdtCalibration hdt, DvtBench bench, TimeProvider timeProvider, ILogger<UvOffTiming> log, IRecipeRunner? recipes = null);
  public bool Running { get; }
  public UvSweepStartResult Start(UvOffRequest r);
  public UvOffStatus Status(bool samples = true);
  public string Abort(string? by = null);
}
public sealed record UvOffRequest(int Wavelength = 405 [wavelength], int Intensity = 100 [intensity], double PlateauMaxSec = 30 [plateau_max_s], double StableSec = 2 [stable_s], double OpenTimeoutSec = 30 [open_timeout_s], double TailSec = 3 [tail_s], double Hz = 20 [hz], bool Force = false [force], double AlarmWatchSec = 15 [alarm_watch_s], bool Release = false [release]);
public sealed record ProgramEnd(string State [state], string? Message [message], int? ErrorCode [error_code]);
public sealed record UvOffStatus {  // JSON names
  running, status="IDLE", phase="idle", config, samples, n_samples (omit null), error, aborted, started (unix s), finished, elapsed,
  reading, door_open, meter, meter_wavelength_nm, meter_wavelength_verified, dark_mw_cm2, plateau_mw_cm2, release_at_s, release_ok,
  door_open_at_s, below_10pct_at_s, uv_off_time_s, uv_off_before_door_open, release_to_off_s, residual_mw_cm2, zero_threshold_mw_cm2,
  zero_at_s, uv_zero_time_s, release_to_zero_s, mode ("direct"|"program"), program_end, alerts_before, alerts_after, alert_details,
  door_aborted, ui_alerts (List<string>), interlock_failed, aborted_by }
```
Sample row: `[t_s (3 dp), mW/cm2 (4 dp) | null, door_open (true/false/null), phase]`. Phases: starting, dark, plateau, open_door, decay, tail, alarm_watch, done.
**Behaviour & rules:**
1. `Start` refusals, in order:
   - "a UV-off measurement is already running".
   - "wavelength must be 405 or 450 (got N)".
   - "intensity must be 10-100 % (got N)".
   - `AnyProcessActive`: "a process is running (heating, cooling or UV) - stop it first".
   - "HDT calibration is running - abort it first".
   - recipe state preflight/running/paused: "a program is running - abort it first".
   - `DoorOpenNow() != false`: "the door must be closed at the start (the LEDs are interlocked)".
   - meter open/identify failure: "StarBright not reachable: …".
   - wavelength mismatch without force: code "METER_WAVELENGTH", message "the StarBright is set to X nm but this measurement is at Y nm - set the meter first (or force=1)".
   - `bench.TryAcquire("uv-off")` fails: "the DVT bench is busy ({owner})".
   - Success: config with Hz = clamp(1, 50); status initialised with Mode ("direct" when no recipe runner, else "program") and AlertsBefore = current alerts. Thread "dvt-uv-off". Message "UV-off timing started at Y nm, P %".
2. Dark: sample for 1 s. darkMean = the mean (0 when empty); darkSd = the population SD (0 for fewer than 2).
3. Plateau:
   - Program mode: start Material `{Id="dvt-saf-012-uv-off", Name="DVT-SAF-008 UV off", Steps=[{Step=1, Process = Bleacher if 450 nm else Cure, Time=10, UvIntensity=intensity}]}`. If the start is refused, throw "the program did not start: …". Then poll `GetState().UvOn` every 200 ms for up to 30 s, else throw "the program did not switch the UV on within 30 s ({recipe message})".
   - Direct mode: `SetUv(true, intensity, wl)`; a refusal gives "UV refused: …".
   - Find the plateau with a rolling window of need = max(2, round(StableSec × Hz)) readings. Plateau = the window mean, once the mean > darkMean and max − min ≤ 0.02 × mean, within PlateauMaxSec. Otherwise throw "the StarBright reading did not settle - check the head position and that the LEDs light".
4. Thresholds:
   - zeroLevel = darkMean + max(0.005 × (plateau − darkMean), 3 × darkSd, 0.01).
   - zeroHold = max(1, round(0.5 × Hz)) consecutive samples.
   - offThreshold = darkMean + 0.10 × (plateau − darkMean).
5. open_door phase:
   - Release=true: record `ReleaseAt = now` and call `OpenDoor()` (ReleaseOk = its Ok).
   - Then sample until `door == true` (tOpen), or throw "the door sensor did not report the door open within {OpenTimeoutSec:0} s - open the door while the UV is on".
   - `Track(v)` runs on every sample from here on: the first v ≤ offThreshold sets tBelow. A zero candidate starts at the first v ≤ zeroLevel and resets on any v above; after zeroHold consecutive samples, tZero = the candidate time.
6. decay phase: sample until tZero is set or 20 s pass. If tBelow is still null 12 s (InterlockLimitSec) after the door opened, set InterlockFailed=true and throw "the UV was still above 10 % 12 s after the door opened - the machine did not switch it off; the run switched it off".
7. tail: sample for TailSec; Residual = the mean of the tail readings (4 dp). alarm_watch: sample every 500 ms for AlarmWatchSec (default 15 s; it covers the ~10 s door grace → abort → error 6016).
8. Results:
   - In program mode, ProgramEnd = (state, message, errorCode) of the recipe.
   - AlertsAfter, AlertDetails, DoorAborted, UiAlerts (the keys) come from `GetState()`.
   - UvOffTime = max(0, tBelow − tOpen); UvOffBeforeDoorOpen = tBelow ≤ tOpen; ReleaseToOff = tBelow − tRelease; UvZeroTime = max(0, tZero − tOpen); ReleaseToZero = tZero − tRelease. All rounded to 3 dp.
   - Error when tBelow is null: "the reading did not fall below 10 % of the plateau within 20 s of the door opening". Error when tZero is null: "the reading did not return to zero (<= X mW/cm2) within 20 s of the door opening".
9. Cancellation at any wait returns immediately, and `finally` then runs:
   - Abort the program if it is still preflight/running/paused, `SetUv(false,0,wl)`, dispose the meter, `bench.Release("uv-off")`.
   - Status ABORTED / ERROR / OK; phase "done".
   - `InvalidOperationException` and `UvMeterException` become the error message; other exceptions are logged too.
10. `Abort(by)`: "no UV-off measurement running", or set AbortedBy = by ?? "unknown", cancel, and return "abort requested - LEDs go off".
11. Endpoints:
    - `POST /api/dvt/uv-off?wavelength&intensity&plateau_max&stable&open_timeout&tail&hz&force&alarm_watch&release` → `{ok,message,code,meter_wavelength_nm,meter_wavelength_verified}`.
    - `GET /api/dvt/uv-off?samples=1` → flattened status + ok.
    - `POST /api/dvt/uv-off/abort?by=` (default User-Agent, else "api").
**Configuration:** reads nothing directly. The door grace it measures is the machine's `components.json door_sensor.abort_after_sec` (10 s).
**Acceptance criteria:**
- release=1 with the door opened 0.6 s later: OK, ReleaseOk true, UvOffBeforeDoorOpen true, UvOffTime 0, ReleaseToOff in [0,1), UvZeroTime 0, ReleaseToZero in [0,1.5), ZeroThreshold > Dark, Residual in [0,0.01], DoorOpenAt > ReleaseAt, UV off, tail samples present.
- Operator opens the door with no release: UvOffTime in [9,12] (the software door grace), UvZeroTime ≥ UvOffTime, OK.
- Door open with no supervision tick: ERROR, InterlockFailed, error starts "the UV was still above 10 % 12 s after the door opened", UV off.
- Door never opened (OpenTimeoutSec 5): ERROR "the door sensor did not report the door open…", LEDs off.
- While running, a UvSweep start says "the DVT bench is busy (uv-off)". Abort → ABORTED, bench free.
**Tests:** `UvOffTimingTests` (the 7 facts listed in the source, `ProcessRig` with `Hardware.DoorOpenReading`, step 50 ms); Api `DvtTests.Uv_off_runs_a_real_program_and_reports_how_it_ended`.
**Reference (source):** `src/SCureBox.Application/Dvt/UvOffTiming.cs`, `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`, `tests/SCureBox.Application.Tests/Process/UvOffTimingTests.cs`

---

### DVT-04 — Firmware hang on purpose for the watchdog test (DVT-SAF-010)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/DvtHang.cs`; endpoint + gate middleware in `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`
**Goal:** Puts the firmware into a realistic HUNG state for N seconds. During it:
- no heartbeat is written and every output write blocks (`OutputFreeze`);
- the supervision and the recipe runner are frozen;
- the firmware switches nothing off itself; the separate output watchdog (20 s) must cut.

When the hang ends, the firmware comes back SAFE: the program is failed and all outputs are off. If the watchdog trip record shows a cut during the hang, Err 9017 is raised and latched until the operator acknowledges it.
**Depends on:** Hardware (`OutputFreeze` with `Hang()`, `Recover(Action safeState)`, `Hung`, `Active`; `OutputWatchdog.DefaultTimeoutSec = 20`; `WatchdogTripFile.TryRead(path)` / `ConfiguredPath()` → `/run/scurebox-heartbeat.trip`), Application-Process (`CureController.GetState()`/`StopAll(bool)`, `RecipeRunner.FailFromOutside(string, int)`), Application-Platform/Supervision (`SupervisionState.SetWatchdogTripped(string)`), Domain (`ErrorCodes.WatchdogTripped = 9017`, `ErrorCodes.CureAborted = 7005`, `MachineState`, `DvtHangDto`), Api.
**Files to create:** `src/SCureBox.Application/Dvt/DvtHang.cs`, which holds `IWatchdogTripSource`, `WatchdogTripFileSource`, `DvtHangStart`, `DvtHang`.
**Public contract:**
```csharp
public interface IWatchdogTripSource { (DateTimeOffset At, bool CutOk)? LastTrip(); }
public sealed class WatchdogTripFileSource : IWatchdogTripSource { public WatchdogTripFileSource(string? path); } // null path -> always null
public sealed record DvtHangStart(bool Ok, int Status, string Message, int Sec = 0);
public sealed class DvtHang {
  public const int MinSec = 5, MaxSec = 300, DefaultSec = 60;
  public const double HeartbeatTimeoutSec = OutputWatchdog.DefaultTimeoutSec; // 20
  public const string WatchdogTrippedText = "Firmware stopped responding - the output watchdog switched the heater and UV off. Restart the process to continue.";
  public DvtHang(CureController controller, OutputFreeze freeze, SupervisionState sup, TimeProvider timeProvider, ILogger<DvtHang> log, RecipeRunner? recipes = null, IWatchdogTripSource? trips = null);
  public bool Active { get; }               // => freeze.Active (hung or recovering)
  public DateTimeOffset? Until { get; }
  public MachineState? LastState { get; }
  public bool? LastTripSeen { get; }
  public DvtHangStart Prepare(int sec);
  public void Begin();
  public DvtHangStart Start(int sec);       // Prepare + Begin
  public void End();                        // idempotent
}
```
**Behaviour & rules:**
1. `Prepare(sec)`:
   - sec outside 5..300 → `(false, 400, "sec must be 5-300 (got N)")`.
   - Under the lock: if `freeze.Active` or a hang is pending → `(false, 409, "the firmware is already hung for a DVT test")`.
   - If the state shows neither heating nor UV on → `(false, 409, "nothing is on (heater or UV) - start heating or a UV output first; there is nothing for the watchdog to cut")`.
   - Otherwise capture `LastState = GetState()`, store the pending sec, and return `(true, 200, "the firmware hangs for N s", N)`.
2. `Begin()`:
   - With nothing pending, or when already active, do nothing.
   - Otherwise set `_since = now`, `_until = since + sec`, create a new CTS, and call `freeze.Hang()`. Log a warning.
   - Start thread "dvt-hang": `Wait(sec, ct)` then `End()`.
3. `End()`:
   - Return unless `freeze.Hung` and `_since` is set. Cancel the timer.
   - `freeze.Recover(safeState)`, where safeState does the following:
     - tripped = `LastTrip()` exists and its `At ≥ since − 1 s`; set `LastTripSeen`.
     - `recipes?.FailFromOutside(why, code)`: code 9017 with WatchdogTrippedText if tripped; else code 7005 with "Firmware hang (DVT) - the process was ended, nothing resumes".
     - `controller.StopAll(true)`.
     - If tripped: `sup.SetWatchdogTripped(WatchdogTrippedText + (CutOk ? "" : " (the watchdog reported the cut INCOMPLETE)"))`. This raises 9017, latched until `AckWatchdogTrip` (`POST /api/watchdog/ack`).
     - Each step is wrapped in try/log.
   - Then clear `_until` and `_since`.
4. A trip older than the hang (for example 10 min before) does not count.
5. Endpoint `POST /api/dvt/hang?sec=` (loopback only, else 403 "only the DVT runner on this CureBox may hang the firmware"):
   - A sec that is not an integer → 400 "sec must be a whole number 5-300 (got '…')". An absent sec means 60.
   - A refusal → `ApiJson.Fail(msg, status)`.
   - Success → `{ok:true, sec, heartbeatTimeoutSec:20}`. `Begin()` runs in `Response.OnCompleted`, so the reply goes out before the hang begins.
6. Gate middleware `UseDvtHangGate`: while `hang.Active`, every non-GET/HEAD request under `/api/` answers 409 "the firmware is hung for a DVT test (DVT-SAF-010) until {unix} - no output commands". The exceptions are path prefixes `/api/dvt/meter`, `/api/dvt/bench`, `/api/dvt/remote-confirm`, `/api/dev/picolog`.
7. `GET /api/state` during a hang answers `LastState with { DvtHang = new DvtHangDto(true, until unix seconds) }` (JSON `dvtHang:{active,until}`; omitted when null).
8. `IsLocal(ctx)`: the remote IP is loopback, after mapping an IPv4-mapped IPv6 address to IPv4.
**Configuration:** trip record path from `WatchdogTripFile.ConfiguredPath()` (derived from the heartbeat file path; null = no watchdog).
**Acceptance criteria:**
- Nothing on → 409. sec 4, 301 or "abc" → 400.
- While heating: 200 with sec + heartbeatTimeoutSec 20. State shows dvtHang.active with until in the future and isHeating true (the frozen state). Output POSTs → 409 with "hung" in the message. A second hang → 409. GET picolog status and GET meter → 200.
- A hang ends by itself after sec. Then the heater element is off, all LED levels are 0, IsHeating and UvOn are false, there is no 9017 without a trip record, and the loops do not switch anything back on later.
- A trip recorded during the hang → 9017 with the exact detail text, latched across ticks until acked, and nothing resumes.
- A program hung mid-run ends with recipe state "error" and ErrorCode 9017.
**Tests:** `DvtHangTests` (Refuses_when_nothing_is_on_and_validates_sec, During_the_hang_nothing_is_written_to_the_outputs_and_the_supervision_is_frozen, The_hang_ends_by_itself…, A_watchdog_trip_during_the_hang_raises_9017…, A_trip_from_before_the_hang_is_not_this_hang, A_program_hung_mid_run_ends_as_failed_with_the_code, A_second_hang_is_refused_while_one_is_on; uses a `FakeTrips : IWatchdogTripSource`); Api `DvtHangApiTests.Hang_contract_end_to_end` (a `LoopbackApiFixture` whose startup filter forces RemoteIpAddress = loopback), `DvtLocalOnlyTests.Hang_and_led_checks_are_refused_from_another_host`.
**Reference (source):** `src/SCureBox.Application/Dvt/DvtHang.cs`, `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`, `src/SCureBox.Api/Endpoints/StateEndpoints.cs`, `src/SCureBox.Application/ProcessServiceCollectionExtensions.cs`, `tests/SCureBox.Application.Tests/Process/DvtHangTests.cs`, `tests/SCureBox.Api.Tests/DvtHangApiTests.cs`

---

### DVT-05 — Remote confirmation at the machine (RemoteConfirm)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/RemoteConfirm.cs`; endpoints in `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`
**Goal:** A DVT test asked for from outside the machine (the sCure Cloud DVT tab, through the local DVT runner) must be confirmed by someone at the CureBox before anything turns on. The screen shows Start / Decline. The runner polls the answer. Requests expire, and the asker can withdraw them.
**Depends on:** Native UI (`RemoteConfirmPrompter` subscribes to `Requested`/`Closed` and calls `Resolve`), Api.
**Files to create:** `src/SCureBox.Application/Dvt/RemoteConfirm.cs` — `RemoteConfirm` with nested `Request` and `State`.
**Public contract:**
```csharp
public sealed class RemoteConfirm {
  public sealed record Request(string Id, string Title, string Detail, DateTimeOffset Created, DateTimeOffset Expires);
  public enum State { Pending, Accepted, Declined, Expired, Withdrawn, Unknown }
  public static readonly TimeSpan DefaultTimeout = TimeSpan.FromMinutes(10);
  public static readonly TimeSpan MaxTimeout = TimeSpan.FromMinutes(60);
  // private static readonly TimeSpan Keep = TimeSpan.FromHours(1);
  public RemoteConfirm(TimeProvider time);
  public event Action<Request>? Requested;
  public event Action<string>? Closed;
  public Request Ask(string id, string title, string detail, TimeSpan? timeout = null);
  public State Status(string id);
  public bool Resolve(string id, bool start);
  public void Withdraw(string id);
  public IReadOnlyList<Request> Pending();
}
```
**Behaviour & rules:**
1. `Ask`:
   - A blank id throws `ArgumentException("a request needs an id")`.
   - Wait = timeout if > 0 (capped at 60 min), else 10 min.
   - Under the lock: `Prune()` removes non-pending items whose last change is more than 1 h old. If the id is pending and unexpired, return the same `Request` instance (no new event).
   - Otherwise store `(Request(id, title.Trim(), detail.Trim(), now, now+wait), Pending, now)`.
   - Raise `Requested` outside the lock.
2. `Status(id)`: an unknown id → `Unknown`. A pending request past its expiry becomes `Expired`, and `Closed(id)` is raised outside the lock.
3. `Resolve(id, start)`: only a pending, unexpired request changes. It becomes Accepted (start) or Declined, and the call returns true; otherwise false. A second answer changes nothing.
4. `Withdraw(id)`: Pending → Withdrawn and raise `Closed(id)`. A later Resolve returns false.
5. `Pending()`: pending and unexpired requests, ordered by Created.
6. Endpoints (loopback only; otherwise 403 "only the DVT runner on this CureBox may ask for a confirmation"):
   - `POST /api/dvt/remote-confirm` with JSON body `{id, title, detail, timeoutSec?}`. An empty id → 400 "a confirmation needs an id". Reply `{ok:true,id,state:"pending",expires:<unix s>}`.
   - `GET /api/dvt/remote-confirm/{id}` → `{ok:true,id,state}`, where state is the lowercase enum name.
   - `DELETE /api/dvt/remote-confirm/{id}` → withdraw, then `{ok,id,state}`.
**Configuration:** none.
**Acceptance criteria:** Exactly the behaviours of the five tests below. The timeout cap: `Expires − Created == 60 min` for a 5 h request.
**Tests:** `RemoteConfirmTests` (FakeTimeProvider at 2026-10-12 10:00Z): A_request_waits_for_Start_on_the_screen, Decline_is_an_answer_and_nothing_runs, An_unanswered_request_expires_and_leaves_the_screen (pending at 9 min, expired at 11 min, Closed raised, late Resolve false), A_withdrawn_request_closes_its_dialog_and_ignores_a_late_Start, Asking_again_does_not_open_a_second_dialog_and_the_wait_is_capped.
**Reference (source):** `src/SCureBox.Application/Dvt/RemoteConfirm.cs`, `src/SCureBox.Api/Endpoints/DvtEndpoints.cs`, `tests/SCureBox.Application.Tests/Dvt/RemoteConfirmTests.cs`

---

### DVT-06 — PicoLog TC-08 thermocouple probe (native interop, firmware reader, simulation)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Hdt/`
**Goal:** Gives the firmware a continuous, thread-safe reading of the PicoLog TC-08:
- CH1: the type K thermocouple on the sample or heater body;
- CH2: the reference type K thermocouple in the chamber;
- channel 0: the cold junction, which is the instrument's ambient.

It is used by HDT calibration and the DVT pages. It can release the unit to the DVT bench process and take it back. A deterministic simulation exists for tests and for machines without the driver.
**Depends on:** native `libusbtc08` (Pico, `libusbtc08.so` on the loader path), Api (`/api/dev/picolog/*`), Application-Process (`CureController.CurrentUvPower` for the simulation).
**Files to create:**
- `src/SCureBox.Application/Hdt/UsbTc08Native.cs` — `internal static class UsbTc08Native` (also used by DVT-08 `Tc08Source`)
- `src/SCureBox.Application/Hdt/ITemperatureProbe.cs`
- `src/SCureBox.Application/Hdt/PicologStatusDto.cs`
- `src/SCureBox.Application/Hdt/PicoLogTc08Probe.cs`
- `src/SCureBox.Application/Hdt/SimulatedTc08Probe.cs`
**Public contract:**
```csharp
internal static class UsbTc08Native {   // [DllImport("usbtc08")]; the driver is NOT thread-safe: one thread per handle
  short usb_tc08_open_unit();                                   // >0 handle, 0 none found, <0 failure
  short usb_tc08_set_mains(short handle, short sixtyHertz);     // 0 = 50 Hz rejection
  short usb_tc08_set_channel(short handle, short channel, sbyte tcType); // 'C' cold junction, 'K', 0 = off
  short usb_tc08_get_single(short handle, [Out] float[] temp, ref short overflowFlags, short units); // units 0 = °C; 0 = failure; float[9], [0]=CJ
  short usb_tc08_close_unit(short handle);
  short usb_tc08_get_unit_info2(short handle, StringBuilder buffer, short length, short line); // line 4 = batch and serial
}
public interface ITemperatureProbe : IDisposable { PicologStatusDto Status(); void Release(); void Resume(); bool Released { get; } }
public sealed record PicologStatusDto(bool Connected [connected], bool Ch1Available [ch1Available], double? Temperature [temperature],
  string? DeviceInfo [deviceInfo], string? Error [error], double? Ambient = null [ambient], bool Ch2Available = false [ch2Available], double? Ch2 = null [ch2]);
public sealed class PicoLogTc08Probe : ITemperatureProbe {
  public const double SamplingIntervalSec = 1.0, ReconnectSec = 5.0, StaleSec = 5.0, ValidMinC = -25.0, ValidMaxC = 400.0;
  public const string ReleasedMessage = "released to the DVT bench";
  public PicoLogTc08Probe(TimeProvider timeProvider, ILogger<PicoLogTc08Probe> log); // starts thread "tc08"
}
public sealed class SimulatedTc08Probe : ITemperatureProbe {
  public const double AmbientC = 24.0, GainCPerPct = 0.55, TauSec = 40.0;
  public SimulatedTc08Probe(TimeProvider timeProvider, Func<double> powerSupplier, double noise = 0.15, int? seed = null);
}
```
**Behaviour & rules:**
1. Open sequence (shared with DVT-08):
   - `open_unit`: 0 → "no TC-08 found (unplugged, or in use by PicoLog?)"; < 0 → "TC-08 open failed - replug the USB".
   - Then `set_mains(h,0)`; channel 0 'C', 1 'K', 2 'K'; channels 3..8 set to 0.
   - Info "PicoLog TC-08", or "PicoLog TC-08 S/N {line 4}" when `get_unit_info2(h, sb, 256, 4) > 0` (optional, exceptions ignored).
   - `DllNotFoundException` → error "usbtc08 driver unavailable: …", logged once at Information. Other exceptions → "TC-08 open error: …".
2. The reader thread loop (one thread owns every driver call):
   - If released: close any open handle, set Connected=false with Error=ReleasedMessage, wait 1 s, and loop.
   - If there is no handle: open. On failure set the error and wait 5 s. If the probe was released while opening, loop (it closes on the next pass).
   - Read: `get_single` into float[9]; a return of 0 → IOException "usb_tc08_get_single failed".
   - CH1 = buf[1], CJ = buf[0], CH2 = buf[2].
     - CH1 NaN → connected, error "CH1 reading is NaN (thermocouple disconnected?)".
     - CH1 outside −25..400 → error "CH1 reading {t:0.0}degC out of range".
     - Otherwise store the temperature.
     - The CJ (if finite) is stored, and also refreshes the sample time. CH2 is stored only if finite and inside −25..400, else null.
   - An exception → Connected=false, "communication lost: …", close the handle, retry at once.
   - Wait 1 s between reads. Dispose cancels and joins the thread for up to 5 s, closing the handle.
3. `Status()`:
   - fresh = last sample ≤ 5 s old.
   - Ch1Available = connected && fresh && temperature present. Temperature (2 dp) only when available.
   - Error = null when valid, else the stored error, or "stale data" when connected.
   - Ambient = CJ (2 dp) whenever connected and fresh, even when CH1 is open. Ch2 (2 dp) likewise; Ch2Available = Ch2 is not null.
4. `Release()`/`Resume()` flip a volatile flag and log "PicoLog TC-08 released to the DVT bench" / "PicoLog TC-08 back with the firmware".
5. Simulation:
   - target = 24 + 0.55 × power%; T += (target − T) × dt/40, with dt clamped to 0..10 s and integrated lazily on every `Status()` call.
   - Reading = T ± U(−1,1) × noise (2 dp).
   - DeviceInfo "PicoLog TC-08 (SIMULATED - SCURE_SIM_TC08)".
   - Ambient = 24 ± noise; Ch2Available true, Ch2 = 24.
   - When released: `(false,false,null,info,ReleasedMessage,null)`.
   - A failing power supplier is read as 0.
6. Endpoints:
   - `GET /api/dev/picolog/status` → the DTO.
   - `POST /api/dev/picolog/release`: refused while HDT runs ("HDT calibration is running - abort it first"); else `{ok:true,message:"PicoLog TC-08 released to the DVT bench"}`.
   - `POST /api/dev/picolog/resume` → `{ok:true,message:"PicoLog TC-08 back with the firmware"}`.
7. Difference from the Python reference: `reference/picolog_tc08.py` uses VALID_RANGE_C (−25, 250) and searches lib dirs (`SCURE_TC08_LIB_DIR`, `/opt/picoscope/lib`, `~/pico/root/opt/picoscope/lib`, `/usr/local/lib`). The C# code uses 400 °C (so a 250 °C cutout trip in DVT-SAF-009 is seen with headroom) and plain `DllImport("usbtc08")` with no custom resolver. OPEN QUESTION: whether a NativeLibrary resolver for the extracted-.deb dirs is needed on target images (none exists in the C# code).
**Configuration:** `SCURE_SIM_TC08` (anything but "", "0", "false" → `SimulatedTc08Probe(tp, () => CureController.CurrentUvPower)`, else `PicoLogTc08Probe`). Registered with `TryAddSingleton<ITemperatureProbe>`.
**Acceptance criteria:**
- Simulated at 50 %, noise 0: 24.0 at t0. After 40 s (one 10 s clamped step) the reading is in [30.5, 31.0]. After 100 × 5 s it is in [51.4, 51.5]. Ch1Available is true.
- The simulated Ambient stays 24.0 while CH1 rises (difference in [27.0, 27.5]).
- A missing native library never throws out of the probe; status reports connected=false with the driver error.
**Tests:** `HdtCalibrationTests.Simulated_probe_follows_the_led_power`, `HdtCalibrationTests.The_probe_reports_its_cold_junction_as_ambient`; `DeadProbe` fake (Status → not connected) used by the HDT refusal test.
**Reference (source):** `src/SCureBox.Application/Hdt/UsbTc08Native.cs`, `ITemperatureProbe.cs`, `PicologStatusDto.cs`, `PicoLogTc08Probe.cs`, `SimulatedTc08Probe.cs`, `src/SCureBox.Api/Endpoints/DevEndpoints.cs`, `reference/picolog_tc08.py`

---

### DVT-07 — Material HDT calibration (state machine, thermal model, CSV report)
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Hdt/`; pure math in `src/SCureBox.Domain` `Control/HdtModel.cs`
**Goal:** In Developer Mode, finds the highest calibrated SYSTEM LED power (405 nm) a material takes without its averaged CH1 temperature exceeding the material HDT minus a safety margin. It steps 10 → 90 %; at each level it waits for thermal stability or a timeout. Reaching the HDT stops everything at once. It also estimates the "boost" time (time at boost power from a start temperature up to the lower HDT limit) and produces a CSV report.
**Depends on:** DVT-06 (ITemperatureProbe), Application-Process (`ICureController`: `SetUv(bool,double,Wavelength.Nm405)`, `SetHeaterFan(int)`, `CancelHeaterFanCooldown()`, `LedFactors`, `AnyProcessActive`), Domain (`OpResult`, `HdtModel`), Api (`/api/dev/hdt/*`), Application-Platform (LED calibration store: factors 0..1.5 per zone), Reports (`HdtReportBuilder` consumes `HdtStatusDto` — other area).
**Files to create:**
- `src/SCureBox.Application/Hdt/IHdtCalibration.cs`
- `HdtCalibration.cs`
- `HdtStartRequest.cs`
- `HdtStatusDto.cs`
- `HdtConfigDto.cs`
- `HdtLevelResult.cs`
- `HdtSample.cs`
- `HdtBoost.cs`
- `src/SCureBox.Domain/Control/HdtModel.cs` (if not delivered by Domain)
**Public contract:**
```csharp
public interface IHdtCalibration { bool Running { get; } OpResult Start(HdtStartRequest request); OpResult Abort(); bool Reset(); HdtStatusDto Status(int? samplesFrom = null); string ReportCsv(); }
public sealed class HdtCalibration : IHdtCalibration {
  public const double DefaultSamplingIntervalSec = 1.0, DefaultMovingAverageWindowSec = 10.0, DefaultStabilityBandC = 2.0, DefaultStabilityTimeMin = 5.0,
    DefaultStabilityMaxRateCPerMin = 0.5, DefaultMaxStabilizationTimeMin = 30.0, DefaultSafetyMarginC = 2.0, DefaultNextStepMaxTempDeltaC = 0.0,
    DefaultCooldownMaxWaitMin = 15.0, DefaultBoostPower = 90, DefaultBoostStartTempC = 35.0, HeaterFanReassertSec = 5.0;
  public const int HeaterFanPwmSetting = 100;
  public static readonly IReadOnlyList<int> PowerLevels = { 10, 20, 30, 40, 50, 60, 70, 80, 90 };
  // zones: "back","door","left","right"
  public HdtCalibration(ICureController hardware, ITemperatureProbe tc08, TimeProvider timeProvider, ILogger<HdtCalibration> log);
  public static IReadOnlyDictionary<string, double> ScaledOutputs(double power, IReadOnlyDictionary<string, double> factors); // per zone round(clamp(power*f,0,100),2), f default 1.0
}
public sealed record HdtStartRequest { double? HdtC [hdtC], SafetyMarginC [safetyMarginC], SamplingIntervalSec [samplingIntervalSec], MovingAverageWindowSec [movingAverageWindowSec], StabilityBandC [stabilityBandC], StabilityTimeMin [stabilityTimeMin], StabilityMaxRateCPerMin [stabilityMaxRateCPerMin], MaxStabilizationTimeMin [maxStabilizationTimeMin], NextStepMaxTempDeltaC [nextStepMaxTempDeltaC], CooldownMaxWaitMin [cooldownMaxWaitMin], BoostPower [boostPower], BoostStartTempC [boostStartTempC] }
public sealed record HdtLevelResult { int Power [power]; string Status="NOT_TESTED" [status] (NOT_TESTED|RUNNING|PASS|NOT_CONVERGED|ABORTED|HDT_LIMIT); double? StartTemp [startTemp], StableTemp [stableTemp], MinTemp [minTemp], MaxTemp [maxTemp], TimeToStabilitySec [timeToStabilitySec], DurationSec [durationSec], RateCPerMin [rateCPerMin]; string? StartedAt [startedAt], EndedAt [endedAt]; IReadOnlyDictionary<string,double> Outputs [outputs] }
public sealed record HdtSample { double T [t]; double Raw [raw]; double Avg [avg]; int Power [power]; int Step [step]; [JsonIgnore] string Ts; [JsonIgnore] string State; [JsonIgnore] IReadOnlyDictionary<string,double> Outputs }
public sealed record HdtBoost { double Power [power]; double StartTempC [startTempC]; double? TargetTempC [targetTempC]; double? TimeSec [timeSec]; string? Method [method] (measured|estimated|null); string? Note [note]; double? ModelEqTempC [modelEqTempC]; double? ModelTauSec [modelTauSec] }
public sealed record HdtConfigDto { samplingIntervalSec, movingAverageWindowSec, stabilityBandC, stabilityTimeMin, stabilityMaxRateCPerMin, maxStabilizationTimeMin, hdtSafetyMarginC, nextStepMaxTempDeltaC, powerLevels }
public sealed record HdtStatusDto { state="IDLE", running, finalStatus, message, hdtC, safetyMarginC, currentPower, stepIndex, totalSteps, rawTemp, rateCPerMin, avgTemp, stepElapsedSec, totalElapsedSec, startedAt, endedAt, picolog (PicologStatusDto), factors, outputs, results, recommendedPower, boost, maxMeasuredTemp, heaterFanPwm, config, sampleCount, samples (omitted when null) }
public static class HdtModel {   // SCureBox.Domain.Control
  double? SlopePerMinute(IReadOnlyList<(double t, double v)> window);
  bool IsStable(IReadOnlyList<(double t, double v)> window, double stabilityTimeSec, double bandC, double maxRateCPerMin);
  double EquilibriumAt(IReadOnlyList<(double power, double stableTemp)> levels, double power);
  double? TimeConstant(double startTemp, double stableTemp, IReadOnlyList<(double t, double avg)> trace);
  double? BoostTimeSec(double tau, double tEq, double t0, double limit);
}
```
**Behaviour & rules:**
1. States: IDLE → STARTING_CALIBRATION → [PREPARING_POWER_LEVEL] → TESTING_POWER_LEVEL → WAITING_FOR_STABILITY → STABLE | NOT_CONVERGED, repeated for each of the 9 levels. The run ends in one of:
   - CALIBRATION_COMPLETE, with finalStatus COMPLETED or NOT_CONVERGED (NOT_CONVERGED when every tested level was NOT_CONVERGED);
   - HDT_LIMIT_REACHED (finalStatus HDT_LIMIT_REACHED);
   - ABORTED (ABORTED_BY_USER);
   - SENSOR_ERROR (SENSOR_ERROR).
2. `Start` refusals:
   - Thread alive: "HDT calibration already running".
   - HdtC null: "Invalid material HDT".
   - HdtC outside 30..200: "Invalid material HDT {hdt} (30-200degC)" (invariant culture, e.g. "Invalid material HDT 20 (30-200degC)").
   - `!probe.Status().Ch1Available`: "PicoLog TC-08 CH1 has no valid temperature - " + (error ?? "not connected").
   - `AnyProcessActive` (exceptions ignored): "A cure process is active - stop it before HDT calibration".
   - Success: reset the state and apply the overrides. SafetyMarginC defaults to 2.0; every other parameter falls back to its current value, which is the default after the reset. State STARTING_CALIBRATION, message "Starting calibration", startedAt = local now, Running = true before the thread "hdt-calibration" starts. Returns "HDT calibration started".
3. `Abort()`: cancel and immediately `SetUv(false,0,Nm405)`; returns "Abort requested - LEDs off". `Reset()`: false while the thread is alive, else reset to IDLE ("Idle").
4. `Tick()`, once per sample:
   - Wait samplingIntervalSec (cancel → Abort).
   - Re-assert the heater fan at 100 % when ≥ 5 s have passed since the last time. `HeaterFan(pwm>0)` first calls `CancelHeaterFanCooldown()`, then `SetHeaterFan`; heaterFanPwm = pwm if ok, else 0.
   - Read the probe. A Temperature that is null or not finite → SensorException(error ?? "invalid CH1 temperature").
   - Moving average over the last n = max(1, round(window/interval)) raw values.
   - Update lastRaw/lastAvg/maxMeasured (2 dp).
   - Append an HdtSample: T = seconds since t0 (1 dp), Ts local "yyyy-MM-ddTHH:mm:ss", Power = current, Step = stepIndex, State, Outputs = ScaledOutputs(power, factors).
   - avg ≥ HdtC → HdtLimitException.
5. Run:
   - t0 = now; factors = `LedFactors`; heater fan 100 %.
   - The results list holds every level as NOT_TESTED with its Outputs.
   - 3 seed ticks; baseline = the last avg.
   - For each level i: stepIndex = i, PrepareLevel, TestLevel. Then `Finish("CALIBRATION_COMPLETE", null)`.
6. PrepareLevel:
   - Skipped for i == 0 or when nextStepMaxTempDeltaC ≤ 0 (the default: the LEDs stay on, a direct transition).
   - Otherwise: LEDs off, state PREPARING_POWER_LEVEL, message "Cooling toward {limit:0.0}degC before the {p}% level", where limit = baseline + delta. Tick until avg ≤ limit or cooldownMaxWaitMin passes (a timeout just continues).
7. TestLevel:
   - Result → RUNNING with StartTemp = lastAvg and StartedAt. State TESTING_POWER_LEVEL, message "Applying {p}% calibrated system power".
   - `SetUv(true,p,Nm405)`; a refusal → SensorException "LED command refused: …".
   - State WAITING_FOR_STABILITY, message "Waiting for thermal stabilization".
   - Loop:
     - Tick, then add (t since t0, avg) to the window. Drop points older than needSec + interval, where needSec = stabilityTimeMin × 60.
     - Track min and max.
     - covered = the window spans ≥ needSec AND the step has run ≥ needSec.
     - rate = `SlopePerMinute(window)`.
     - PASS when covered && `IsStable(window, needSec, band, maxRate)`: StableTemp = the window mean, Min/Max of the window, TimeToStability = DurationSec = step seconds (1 dp), Rate (3 dp), EndedAt; state STABLE, message "{p}% stable at {x:0.0}degC".
     - NOT_CONVERGED after maxStabilizationTimeMin × 60 s: Min/Max of the whole step, Duration, EndedAt; message "{p}% did not converge within {N:0} min".
   - `finally` fills in a missing Duration, EndedAt and MaxTemp.
8. Exceptions:
   - Abort: LEDs off, the current step → ABORTED, Finish(ABORTED, ABORTED_BY_USER).
   - HdtLimit: LEDs off, step → HDT_LIMIT, Finish(HDT_LIMIT_REACHED, HDT_LIMIT_REACHED).
   - Sensor: step → ABORTED, Finish(SENSOR_ERROR, SENSOR_ERROR, message).
   - Other: as sensor, with message "internal error: …".
   - A step is marked only while it is RUNNING or NOT_TESTED.
9. Finish:
   - LEDs off, heater fan 0.
   - limit = HdtC − margin. recommendedPower = the highest PASS level with StableTemp ≤ limit.
   - boost = BoostEstimate(limit); an exception gives a note "not available: …".
   - endedAt; totalElapsed; message = given ?? "Calibration finished: {finalStatus}".
10. BoostEstimate (p = boostPower, t0 = boostStartTempC):
    - No limit → note "no HDT limit". limit ≤ t0 → note "lower HDT limit {x:0.0}degC is not above {t0:0}degC".
    - Measured: if level p was tested, take the trace (samples with Step == idx and Power == p, as (T, Avg)). If it has ≥ 2 points and starts ≤ t0 + 0.5:
      - TimeSec = first T with avg ≥ limit minus first T with avg ≥ t0, when both exist and the first is ≥ the second. Method "measured".
      - Else, if the stable temp < limit: Method measured, note "{p}% stabilizes at {x}degC - below the lower HDT limit, never reaches it".
    - Estimated: needs ≥ 2 PASS levels with Stable, Start and TimeToStability > 0, else note "{p}% not tested and too few stabilized levels to estimate".
      - tEq = `EquilibriumAt` (a least-squares line of power vs stable temperature).
      - tau = the mean of `TimeConstant` over those levels. None → note "could not fit a thermal time constant".
      - Method "estimated", ModelEqTempC (1 dp), ModelTauSec (1 dp).
      - tEq ≤ limit → note "model: {p}% would stabilize at ~{tEq}degC, below the lower HDT limit - never reaches it".
      - Else TimeSec = `BoostTimeSec` (1 dp), note "estimated from a first-order model (tau {tau:0}s, {p}% equilibrium ~{tEq:0.0}degC)" + " - the {p}% step started above {t0}degC" (if tested) or " - {p}% was not tested".
11. HdtModel:
    - Slope: least squares with x in minutes from the first t; null for n < 2 or a zero denominator.
    - IsStable: the span ≥ stabilityTimeSec, max − min ≤ band, and (only when maxRate > 0) |slope| ≤ maxRate.
    - TimeConstant: null when the rise is < 1 °C or the trace is empty; else the time from trace[0] to the first avg ≥ start + 0.632 × (stable − start), or null.
    - BoostTimeSec = τ·ln((Teq−T0)/(Teq−TL)), or null when Teq ≤ TL.
12. Status(samplesFrom):
    - stepElapsed is measured from stepT0. totalElapsed is live while running, else the stored value.
    - factors = the run's factors ?? the current `LedFactors`. outputs = ScaledOutputs(currentPower ?? 0).
    - startedAt/endedAt use local format "yyyy-MM-ddTHH:mm:ss.ffffff". totalSteps = 9. picolog = the probe status.
    - samples = the list from index samplesFrom (null when the parameter is absent).
13. CSV (`\n` line endings, comma separated; a cell containing `,`, `"` or `\n` is quoted with `""` escaping; doubles invariant; null → empty):
    - Metadata lines: `# sCure Material HDT Calibration Report`, `# Started,<ts>`, `# Ended,<ts>`, `# Device,<info>,Channel,CH1`, `# Material HDT degC,<hdt>,Safety Margin degC,<m>`, `# Final Status,<final ?? state>`, `# Recommended System LED Power %,<rec>`, `# Max Measured Temp degC,<max>`, then a blank line.
    - `# Per-level results`, then the header `System Power %,Status,Start Temp degC,Stable Temp degC,Min Temp degC,Max Temp degC,Time To Stability s,Duration s,Started,Ended,Back Output %,Door Output %,Left Output %,Right Output %` and one row per level, then a blank line.
    - Sample header `Timestamp,Elapsed Time s,Test Step,Requested System LED Power %,Back LED Factor,Door LED Factor,Left LED Factor,Right LED Factor,Actual Back LED Output %,Actual Door LED Output %,Actual Left LED Output %,Actual Right LED Output %,Raw CH1 Temperature degC,Average Temperature degC,Material HDT degC,HDT Safety Margin degC,Stability Status,Test Status`. Test Step = step + 1 (empty for −1). Test Status = that level's current status.
14. Endpoints:
    - `POST /api/dev/hdt/start` (JSON HdtStartRequest; empty body → defaults) → `{ok,message[,code]}`.
    - `POST /api/dev/hdt/abort` → `{ok:true,message:"Abort requested - LEDs off"}`.
    - `POST /api/dev/hdt/reset` → `{ok, message: null | "Calibration is running"}`.
    - `GET /api/dev/hdt/status?samplesFrom=N`.
    - `GET /api/dev/hdt/report.csv` → text/csv attachment "hdt-calibration.csv" (and it logs "Report exported").
    - `POST /api/dev/led-power` is refused while HDT runs ("HDT calibration is running - abort it first").
15. LED calibration layer (reference `led_calibration.py`; the C# store is in Platform): zones back/door/left/right; factor default 1.0, valid 0.0..1.5, stored 4 dp; physical = round(clamp(power × factor, 0, 100), 2). HDT only uses it through `ScaledOutputs` and `LedFactors`.
**Configuration:** none persistent. The run parameters come from the start request; the defaults are the constants above.
**Acceptance criteria:**
- Simulated run (noise 0, seed 1; StabilityTimeMin 0.5, MaxStabilizationTimeMin 5, MaxRate 0.5, HDT 50):
  - state and finalStatus HDT_LIMIT_REACHED; RecommendedPower 40;
  - results[0] PASS with stable in [29,30]; results[3] PASS; results[4] HDT_LIMIT; results[5] NOT_TESTED;
  - MaxMeasured ≥ 50; Boost.Method "estimated" with TimeSec > 0;
  - SampleCount == Samples.Count; HeaterFanPwm 0 at the end; UV off; EndedAt set; PowerLevels as listed;
  - the CSV starts with "# sCure Material HDT Calibration Report\n" and contains "# Recommended System LED Power %,40\n" and "10,PASS,".
- While running: the heater fan duty is 100 % and the state is WAITING_FOR_STABILITY. Abort → ABORTED / ABORTED_BY_USER, results[0] ABORTED, fan 0, UV off.
- The refusal messages are exactly those in rule 2.
**Tests:** `HdtCalibrationTests` (Simulated_run_reaches_a_recommendation, Heater_fan_is_held_at_full_speed_during_the_run, Start_refusals, plus the probe tests of DVT-06) using `ProcessRig.AdvanceUntil(cond, max, step 1 s)`; Domain `HdtModelTests` (Slope_per_minute_of_a_linear_window, Stability_needs_the_window_the_band_and_the_rate, Equilibrium_line_and_time_constant, Boost_time_formula); `HdtReportBuilderTests` belongs to Reports.
**Reference (source):** `src/SCureBox.Application/Hdt/*.cs` (except the TC-08 files), `src/SCureBox.Domain/Control/HdtModel.cs`, `src/SCureBox.Api/Endpoints/DevEndpoints.cs`, `reference/hdt_calibration.py`, `reference/led_calibration.py`, `tests/SCureBox.Application.Tests/Process/HdtCalibrationTests.cs`, `tests/SCureBox.Domain.Tests/Control/HdtModelTests.cs`

---

### DVT-08 — Bench-process contracts, trace math, TC-08 bench source and the generic BenchRecorder
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/Bench/`
**Goal:** Defines what the separate DVT bench process sees of the firmware (an HTTP-shaped interface), of the TC-08 (opened exclusively for one run) and of the safety net. Also provides the generic recorder that any DVT test script uses: TC-08 CH1/CH2/cold junction + StarBright + firmware state, sampled together at 1..20 Hz on the bench clock, with named marks set by the script and firmware state-change events detected automatically. The recording survives a firmware restart (rows with `fw_alive=false`).
**Depends on:** DVT-01 (DvtBench, IUvMeterSource, MeterIdentity), DVT-06 (UsbTc08Native), DVT-10 (the host wires it in).
**Files to create:**
- `Dvt/Bench/BenchContracts.cs` — `BenchException`, `FirmwareSnapshot`, `BenchReply`, `IFirmwareClient`, `ITc08Session`, `ITc08Source`, `IFirmwareProcess`, `IJournalReader`, `ISafetyNet`, `BenchRequest`
- `Dvt/Bench/BenchRun.cs` — `BenchRunStatus`, `BenchPhase`, `BenchRun`
- `Dvt/Bench/TraceMath.cs` — `TraceMath`
- `Dvt/Bench/Tc08Source.cs` — `Tc08Source`
- `Dvt/Bench/BenchRecorder.cs` — `BenchRecorder`, `RecordRequest`, `RecordStatus`
**Public contract:**
```csharp
namespace SCureBox.Application.Dvt.Bench;
public sealed class BenchException(string message) : Exception;
public sealed record FirmwareSnapshot(bool Alive, bool Heating, bool UvOn, double? ChamberC, bool? ChamberSensorOk, bool? DoorClosed,
  IReadOnlyList<int> Alerts, IReadOnlyDictionary<string,string> AlertDetails, string? RecipeState, string? Version, bool DoorAborted)
  { public static readonly FirmwareSnapshot Dead; }   // all false/null/empty
public sealed record BenchReply(bool Ok, string? Message);
public interface IFirmwareClient {
  FirmwareSnapshot Snapshot(TimeSpan timeout); BenchReply Heat(double targetC); BenchReply Uv(bool on, int intensityPct, int wavelengthNm);
  BenchReply StopAll(); BenchReply RecipeAbort(); BenchReply PicologRelease(); BenchReply PicologResume(); bool PicologReleased();
  BenchReply ClaimBench(string who, double leaseSec); BenchReply ReleaseBench(string who); string? ErrorText(int code);
}
public interface ITc08Session : IDisposable { string Info { get; } (double? Ch1, double? Ch2, double? ColdJunction) Read(); }
public interface ITc08Source { ITc08Session Open(); }
public interface IFirmwareProcess { string UnitName { get; } int? Pid(); void Freeze(int pid); void Thaw(int pid); void Kill(int pid); }  // declared; only the simulation implements it
public interface IJournalReader { IReadOnlyList<string> WatchdogLinesSince(DateTimeOffset since); }                                  // declared; only the simulation implements it
public interface ISafetyNet { string CutNow(); }
public sealed record BenchRequest(string TestId [test_id], double HeatTargetC = 80 [heat_target_c], int UvIntensity = 100 [uv_intensity],
  int UvWavelengthNm = 405 [uv_wavelength_nm], double Hz = 5 [hz], double OperatorTimeoutSec = 180 [operator_timeout_s],
  double CutTimeoutSec = 90 [cut_timeout_s], double CooldownMaxSec = 1200 [cooldown_max_s], double CooldownBelowC = 60 [cooldown_below_c]);
public sealed class BenchRun {
  public static readonly IReadOnlyList<string> Columns = { "t_s","ch1_c","cold_junction_c","meter_mw_cm2","fw_alive","heating","uv_on","chamber_c","chamber_sensor_ok","phase","ch2_c" };
  // mutable public fields: TestId, Running, Status="IDLE", Phase="idle", Prompt, Started, Finished, Elapsed, Error, Aborted, Values, Marks, Notes, Phases, Samples, Config, Tc08, Meter
  public BenchRunStatus Snapshot(bool samples);
}
public sealed record BenchPhase(string Name [name], double FromS [from_s], double? ToS [to_s]);
public sealed record BenchRunStatus { test_id, running, status="IDLE", phase="idle", prompt, started (ISO "O"), finished, elapsed, error, aborted,
  values (Dictionary<string,object?>), marks (Dictionary<string,double>), notes, phases, columns, samples, n_samples (only when samples omitted), last, config, tc08, meter }
public static class TraceMath {
  public const double OpenAboveColdJunctionC = 60, OpenJitterC = 5, OpenWatchSec = 3;
  public static bool ThermocoupleLooksOpen(double? ch1, double? coldJunction, FirmwareSnapshot fw);
  public static bool ReadingsJump(IReadOnlyList<double> readings);
  public static double? Slope(IReadOnlyList<(double T, double V)> pts, double windowSec);
  public static (double T, double V)? Turn(IReadOnlyList<(double T, double V)> pts, double fromT, double dropC);
}
public sealed class Tc08Source : ITc08Source { public ITc08Session Open(); }
public sealed class BenchRecorder {
  public const double MaxSecDefault = 3 * 3600; public const string Owner = "recording";
  public const string MeterOwner = "DVT bench recording"; public const double MeterLeaseSec = 30;
  public BenchRecorder(IFirmwareClient firmware, ITc08Source tc08, IUvMeterSource meters, DvtBench bench, TimeProvider timeProvider, ILogger<BenchRecorder> log);
  public bool Running { get; }
  public BenchReply Start(RecordRequest r); public BenchReply Mark(string name); public BenchReply Stop();
  public RecordStatus Status(bool samples = false, int from = 0);
  public static IEnumerable<string> StateEvents(FirmwareSnapshot? prev, FirmwareSnapshot now);
}
public sealed record RecordRequest(string Label = "" [label], bool Tc08 = true [tc08], bool Meter = false [meter], double Hz = 5 [hz], double MaxSec = BenchRecorder.MaxSecDefault [max_s]);
public sealed record RecordStatus { running, status="IDLE", label, phase="idle", config, started, finished, elapsed, error, tc08, meter,
  clock = "seconds since started, bench clock", t0_unix (ms/1000), marks, events (List<object[]> of [t_s, name]), notes, columns = BenchRun.Columns,
  n_samples, from (omitted when null), samples, last }
```
Sample row (both recorder and runner): `[t_s (3 dp), ch1_c (2 dp)|null, cold_junction_c (2 dp)|null, meter_mw_cm2 (4 dp)|null (runner: always null), fw_alive, heating, uv_on, chamber_c (2 dp)|null, chamber_sensor_ok|null, phase, ch2_c (2 dp)|null]`. `ch2_c` is LAST, so the column indexes the web page uses stay valid.
**Behaviour & rules:**
1. `Tc08Source.Open()`:
   - `DllNotFoundException` → BenchException "usbtc08 driver unavailable: …"; handle 0 → "no TC-08 found (unplugged, or still held by the firmware?)"; < 0 → "TC-08 open failed - replug the USB".
   - Configure exactly as in DVT-06 rule 1 (mains 0; ch0 'C'; ch1 and ch2 'K'; 3..8 off; info "PicoLog TC-08 S/N …").
   - `Session.Read()`: a closed handle → "TC-08 closed". get_single == 0 → "usb_tc08_get_single failed". Returns (buf[1], buf[2], buf[0]), each null when not finite.
   - Dispose closes the unit once.
2. `ThermocoupleLooksOpen` = ch1 and cj present && ch1 − cj > 60 && fw.Alive && !Heating && !UvOn. Checks: (249.3, 24.5, idle) → true; while heating → false; (80, 24.5, idle) → false; cj null → false; a Dead snapshot → false.
3. `ReadingsJump` = count ≥ 2 && max − min > 5.
4. `Slope`:
   - Points with T ≥ last T − window.
   - null when there are < 3 points or their span < 0.6 × window.
   - Otherwise the least-squares slope per second (null when the denominator is 0).
5. `Turn(pts, fromT, drop)`: over points with T ≥ fromT, track the peak (the maximum V). Return the peak once a later V ≤ peak − drop; else null.
6. Recorder `Start` refusals:
   - "a recording is already running ({label})".
   - Neither tc08 nor meter: "nothing to record - ask for tc08=1 and/or meter=1".
   - `bench.TryAcquire("recording")` fails: "the bench is busy ({owner})". The bench is shared with BenchRunner, so only one of them runs at a time.
   - Success: thread "dvt-record", reply "recording started", phase "start".
7. Recorder run:
   - tc08:
     - `fw.PicologRelease()`; a failure → "the firmware did not release the TC-08: …".
     - Poll `PicologReleased()` every 250 ms for up to 10 s.
     - Up to 5 open attempts, 1 s apart; all failing → "TC-08 not usable on the bench: …".
     - Status.Tc08 = Info.
   - meter:
     - `fw.ClaimBench("DVT bench recording", 30)`; a refusal → "the StarBright is in use by the firmware: {msg}".
     - Renew every 10 s (MeterLeaseSec/3); a failed renewal adds a note "the firmware took the meter back: …".
     - Open the meter (failure → "StarBright not usable on the bench: …"). Status.Meter = Identify().
   - Loop period = 1/clamp(hz,1,20) until stop or MaxSec (≤ 0 → 3 h). Each pass:
     - Read the TC-08 (a failure → note "TC-08 read failed: …") and the meter (note "meter read failed: …").
     - `Snapshot(1 s)` (an exception → Dead).
     - If ThermocoupleLooksOpen: CH1 := null, and note once: "CH1 reads X C with the cold junction at Y C and nothing heating - an open thermocouple, recorded as no reading".
     - Append `StateEvents(prev, fw)` as [t, name] and the sample row; the phase column = the last mark name.
   - Reaching the maximum adds the note "recording reached its maximum length and stopped".
   - `finally`, in this order: dispose the meter; `ReleaseBench("DVT bench recording")`; dispose the TC-08; `PicologResume()` if it was released; `bench.Release("recording")`. Status OK / ERROR, phase "done".
8. `Mark(name)`: no recording → "no recording running"; a blank name → "a mark needs a name". Otherwise marks[name] = t, phase = name, reply "{name} at {t:0.000} s". `Stop()` → "stopping" or "no recording running".
9. `StateEvents(prev, now)`:
   - prev null → nothing.
   - Alive changed → "fw_alive" or "fw_dead". If now is dead, stop there.
   - If prev was alive, in this order: heating_on/heating_off, uv_on/uv_off, chamber_sensor_open (now == false) / chamber_sensor_ok, door_closed/door_open (only when now.DoorClosed is not null), door_abort (false → true only).
   - Then "alert_{code}" for each new alert and "alert_{code}_cleared" for each one that is gone.
   - Checks: (a → b) gives `heating_on, uv_on, chamber_sensor_open, door_open, door_abort, alert_9001, alert_9050_cleared`; (a → Dead) gives `fw_dead`; (Dead → a) gives `fw_alive, alert_9050`.
10. `Status(samples, from)`: from is clamped to 0..count. Samples are included only when asked; the From field is set only then.
11. Notes are formatted `"{t:0.0}s {text}"`. Clock = seconds since Started, rounded to 3 dp.
**Configuration:** none.
**Acceptance criteria:**
- A recording with tc08 + meter at 5 Hz:
  - a second start is refused, and a BenchRunner start says "the bench is busy (recording)";
  - the firmware's lock owner is "DVT bench recording" while the TC-08 is released;
  - marks heater_on < heater_off; events heating_on and heating_off each at ≥ mark − 0.3 s;
  - t0_unix = the start time; rows have 11 columns; the CH1 rows under "heater_on" rise with heating true; all rows fw_alive;
  - after the stop: the firmware lock is null, the TC-08 is not released, the bench is free;
  - `Status(true, n−3)` returns 3 rows and From = n−3.
- Meter only, MaxSec 3 → OK with the maximum-length note, Tc08 null, ch1 column null.
- The firmware holding "uv-sweep" → ERROR containing "in use by the firmware" and "uv-sweep". A 2-minute recording keeps a 30 s lease alive and releases it at the end.
**Tests:** `BenchRecorderTests` (Records_tc08_meter_and_firmware_state_with_marks_and_hands_the_tc08_back, Nothing_to_record_is_refused_and_a_dead_meter_ends_the_recording_cleanly, The_meter_is_not_opened_while_the_firmware_uses_it_and_the_lease_is_renewed, A_firmware_bench_lease_runs_out_by_itself, An_open_thermocouple_is_told_from_a_hot_one_by_the_cold_junction_and_the_machine_state, Firmware_state_changes_become_events). They use `SimulatedBenchWorld` (DVT-09) with FakeTimeProvider 2026-09-27 12:00Z and a `Pump` helper that advances 100 ms per step with `Thread.Sleep(1)` (60 s real-time cap). Also `BenchRunnerTests.Trace_math_finds_slopes_and_turns` (0.8 °C/s over 12 s → slope in [0.79, 0.81]; no turn while rising; the turn at the last rising point after a 0.3 °C/s fall; 2 points → null slope).
**Reference (source):** `src/SCureBox.Application/Dvt/Bench/BenchContracts.cs`, `BenchRun.cs`, `TraceMath.cs`, `Tc08Source.cs`, `BenchRecorder.cs`, `tests/SCureBox.Application.Tests/Process/BenchRecorderTests.cs`

---

### DVT-09 — BenchRunner (catalog test DVT-SAF-002, heater thermistor open) and SimulatedBenchWorld
**Project / folder:** `src/SCureBox.Application/SCureBox.Application.csproj` — `Dvt/Bench/`
**Goal:** Runs a whole catalog test from the bench process, with the TC-08 in its own hands and on its own clock. The test checks that pulling the heater thermistor (TEMP_CHAMBER) while heating cuts the heater, raises the alarm, refuses a new heat command, and does not resume by itself after the reconnect. The operator is guided by prompts. Every exit leaves the heater and UV off (through the firmware, else through the watchdog's cut) and gives the TC-08 back. A full simulated machine lets everything run without hardware.
**Depends on:** DVT-08, DVT-01 (DvtBench, IUvMeterSource), DVT-10 (the host).
**Files to create:** `Dvt/Bench/BenchRunner.cs` — `BenchRunner`; `Dvt/Bench/SimulatedBenchWorld.cs` — `SimulatedBenchWorld`.
**Public contract:**
```csharp
public sealed class BenchRunner {
  public const string Saf004 = "DVT-SAF-002";            // NB: constant name Saf004, value DVT-SAF-002
  public static readonly IReadOnlyList<string> Tests = { Saf004 };
  public const double RiseSlopeCPerSec = 0.05, RiseWindowSec = 10, RiseTimeoutSec = 300, TurnDropC = 0.5, FirmwareUpTimeoutSec = 240;
  public const int HeaterSensorAlert = 9010;             // private const HeaterSensorAlertBeforeSplit = 9001 also accepted
  public BenchRunner(IFirmwareClient firmware, ITc08Source tc08, ISafetyNet net, TimeProvider timeProvider, ILogger<BenchRunner> log, DvtBench? bench = null);
  public bool Running { get; }
  public BenchRunStatus Status(bool samples = false);
  public BenchReply Start(BenchRequest req);
  public string Abort(string? by = null);
}
public sealed class SimulatedBenchWorld : IFirmwareClient, ITc08Source, IUvMeterSource, IFirmwareProcess, IJournalReader, ISafetyNet {
  public const double WatchdogSec = 20, SystemdWatchdogSec = 60, RestartSec = 3, RiseCPerSec = 0.8, FallCPerSec = 0.3, AmbientC = 24, UvMwCm2 = 90;
  public SimulatedBenchWorld(TimeProvider tp);
  public string UnitName => "scurebox-ui.service (simulated)";
  public double BodyC { get; } public void SetBody(double c); public Func<double?>? Ch1Override { get; set; }
  public bool HeaterOn { get; } public bool UvOn { get; } public bool SensorOpen { get; } public bool Released { get; } public bool SafetyCutUsed { get; }
  public void SetSensorOpen(bool open); public double ReleaseDelaySec { get; set; } public DvtBench FirmwareBench { get; }
  public IUvMeter OpenMeter();
}
```
**Behaviour & rules:**
1. `Start` refusals:
   - "a bench run is already in progress ({test})".
   - An unknown test → "unknown bench test X - one of DVT-SAF-002".
   - HeatTargetC outside 30..80 → "heat_target_c must be 30-80".
   - Snapshot(3 s) not alive → "the firmware does not answer - the bench starts only from a running machine".
   - RecipeState preflight/running/paused → "a program is running on the machine - stop it first".
   - `bench.TryAcquire("bench run")` fails → "the bench is busy ({owner})".
   - Success: thread "dvt-bench", status RUNNING, phase "starting", reply "DVT-SAF-002 started".
2. `Abort(by)`: "no bench run in progress", or cancel and return "abort requested - outputs go off".
3. Primitives:
   - Period = 1/clamp(Hz,1,20); the clock is seconds since the thread start (3 dp).
   - `SetPhase(name, prompt)` closes the previous phase (ToS) and opens a new `BenchPhase`; it sets Phase and Prompt.
   - `TakeSample(phase)` reads the TC-08 (a failure → note) and `Snapshot(1 s)`, and appends a row with a null meter.
   - `Until(phase, done, timeout, ct, prompt)` samples, then checks done, then the timeout, then waits one period (cancel → internal Aborted).
   - `Rising()`: Slope over 10 s ≥ 0.05 °C/s AND last − first point in the window ≥ 0.5 °C.
   - `StillRising(since)`: the slope over all points since then > 0.05 (needs ≥ 3 points).
4. Prepare (phase "prepare"):
   - The firmware must be alive ("the firmware does not answer").
   - PicologRelease (a failure → "the firmware did not release the TC-08: …"). Poll Released every 250 ms for up to 10 s; when it is still not released, add the note "the firmware did not confirm the TC-08 release within 10 s - trying to open it anyway".
   - 5 open attempts 1 s apart (failure → "TC-08 not usable on the bench: …").
   - Read once: CH1 null → "TC-08 CH1 gives no reading - is the thermocouple on CH1?".
   - If it looks open: read 3 more times, 1 s apart.
     - The readings jump > 5 → BenchException "CH1 reads X C and jumps by J C in 3 s while the TC-08's own terminal block is at Y C and nothing is running - the thermocouple is open or badly seated, not hot. Reseat it on the heater body before the run".
     - Otherwise note "CH1 at X C with nothing running but steady (moved J C in 3 s) - a heater body still hot from an earlier test, not an open probe".
5. EnsureIdleAndCool:
   - Heating or UV on → StopAll and note "outputs were on - stopped".
   - ChamberSensorOk == false → "the heater thermistor (TEMP_CHAMBER) is not reading - reconnect it before the run".
   - If the chamber or the TC-08 body is > CooldownBelowC (60): note "… - waiting for both to fall below 60 C", e.g. "heater body at 119.x C - waiting for both…". Then `Until("cooldown", both ≤ limit or null, CooldownMaxSec)`; a timeout → "the chamber / heater body did not cool below 60 C in 20 min".
6. StartHeatAndWaitRising:
   - `Heat(target)`; a refusal → "the heater did not start: …". Set outputsMayBeOn and mark "heat_on".
   - `Until("heating_wait_rise", Rising, 300 s)`; a timeout → "the heater body did not rise (0.05 C/s over 10 s) within 300 s - is the thermocouple on the heater body?".
7. The DVT-SAF-002 sequence (`RunSaf004`):
   - Prepare → EnsureIdleAndCool → StartHeatAndWaitRising.
   - `Until("prompt_disconnect", ChamberSensorOk == false, OperatorTimeoutSec, prompt "DISCONNECT THE HEATER THERMISTOR (TEMP_CHAMBER) NOW")`. A timeout → "the machine did not see the heater thermistor open within {N:0} s".
   - Mark "disconnect" (t0). Values: `disconnect_timestamp` (local ISO "yyyy-MM-ddTHH:mm:ss.fffK") and `heater_temp_at_disconnect` (the last CH1, 2 dp).
   - `WatchTurn("watch_cut", t0, CutTimeoutSec)` finds `Turn(ch1, t0, 0.5)`. On every sample, collect the alert codes; at the first 9010/9001, mark "alarm". If no alarm yet: `WatchFor("watch_alarm", 5 s)`.
   - Values: `heater_body_drop_observed` (turn found), `heater_off_time` (turn.T − t0, 2 dp, or null), `heater_temp_peak` (turn.V, 2 dp), `alarm_raised`, `error_code` (the sorted codes joined ", ", or ""), `time_to_alarm_s` (2 dp, only when raised). With no turn, add the note "no rise-to-fall turn on the heater body within N s of the disconnection".
   - Alarm text = `ErrorText(active)` + " " + AlertDetails[active], where active = 9001 only if 9001 is present without 9010, else 9010. `alarm_text_instructs_reconnect` = raised && regex `reconnect|re-connect|cable|connector|plug` (case-insensitive). `alarm_text` = the trimmed text.
   - Phase "inhibit": `Heat(target)` again. refused = !Ok; when accepted, add the note "the firmware ACCEPTED a heat command with the thermistor open - stopping it" and StopAll. Then `WatchFor("inhibit_watch", 10 s)`. `heat_start_inhibited` = refused && !StillRising; `heat_command_reply` = the message.
   - `Until("prompt_reconnect", ChamberSensorOk == true, OperatorTimeoutSec, prompt "RECONNECT THE HEATER THERMISTOR NOW")`; a timeout → "the machine did not see the thermistor back within N s". Mark "reconnect".
   - `WatchFor("watch_resume", 20 s)`: resumed if any sample is Heating or StillRising(tBack); alarmCleared once a sample has no 9010/9001. Values `recovery_requires_ack` = !resumed, `alarm_cleared_after_reconnect`, `test_method` = "thermistor disconnected and reconnected by the operator on the bench's prompts; everything else measured by the DVT bench process on the machine's clock (TC-08 CH1 at the heater body, firmware state at 5 Hz)".
8. `finally` Cleanup:
   - Snapshot(3 s); while dead, retry every 1 s for up to 15 s.
   - If alive: StopAll (a failure → note) and RecipeAbort.
   - Else, if outputsMayBeOn: note "firmware not answering with outputs possibly on - watchdog cut: " + `net.CutNow()`.
   - Dispose the TC-08; PicologResume if it was released and the firmware is alive.
   - `bench.Release("bench run")`.
   - Status ABORTED (cancelled) / ERROR / OK; phase "done"; prompt null; close the last phase.
   - BenchExceptions → the error message; others are logged.
9. `FirmwareUpTimeoutSec` (240), `IFirmwareProcess`, `IJournalReader` and the BenchRequest fields `UvIntensity`/`UvWavelengthNm` are defined but not used by the only implemented test. OPEN QUESTION: they are meant for future bench tests (hang/kill tests); keep them in the contract.
10. SimulatedBenchWorld:
    - A lazy `Tick()` on every call. Body += 0.8·dt while the SSR heater is on, else −min(0.3·dt, body − 24). Chamber +0.05·dt while on, else −min(0.02·dt, chamber − 24).
    - Alive and not frozen: sensor open with heat commanded → heater off and alert 9010 added; sensor closed → 9010 removed.
    - Output watchdog: silent (frozen or dead) ≥ 20 s with an output on → both SSRs off and a journal line "[WATCHDOG] TRIPPED - firmware silent for X s: heaters + UV LEDs OFF (verified)".
    - systemd: frozen ≥ 60 s → dead, restart in 3 s. Kill → restart in 3 s. A restart gives pid+1 with all outputs off.
    - Snapshot: Dead when not alive or frozen; else (true, heaterCmd, uvCmd, chamber (null if the sensor is open), !SensorOpen, door closed true, alerts, details {"9010": "Heater temperature sensor (chamber NTC TEMP_CHAMBER) is not reading - the heater is off"}, "idle", "sim", false).
    - Heat: throws BenchException "firmware not answering" when dead; sensor open → (false, "[9010] Heater temperature sensor (chamber NTC TEMP_CHAMBER) is not reading - reconnect the sensor before heating"); else (true, "Heating").
    - Uv/StopAll behave the same way; RecipeAbort → (true, "no program").
    - PicologReleased = released and ≥ ReleaseDelaySec since the release.
    - ClaimBench/ReleaseBench use the `FirmwareBench` lease ("the DVT bench is busy ({owner})").
    - ErrorText(9010) = "Chamber Temperature Sensor Disconnected. Check the chamber thermistor (TEMP_CHAMBER) cable and its connector on the IO board. The alert clears by itself once the sensor reads again".
    - TC-08 Open throws "no TC-08 found (unplugged, or still held by the firmware?)" unless released. Session Info "PicoLog TC-08 (SIMULATED)"; Read = (Ch1Override ?? body (3 dp), chamber (2 dp), 24).
    - Meter: Identify {Transport "simulated", Head "PD300RM-8W SIM", WavelengthNm 405}; power 90 with the UV on, else 0.002.
    - CutNow sets SafetyCutUsed, turns the SSRs off, and returns "manual cut: heaters + UV LEDs OFF (verified)".
**Configuration:** none (`SCURE_SIMULATE` is read by the host, DVT-10).
**Acceptance criteria (simulation, FakeTimeProvider 2026-09-27 12:00Z, 100 ms pump):**
- End to end with the operator acting on the prompts:
  - status OK; the prompt sequence is exactly [DISCONNECT…, RECONNECT…];
  - heater_body_drop_observed true; heater_off_time in [0,0.5]; heater_temp_peak in [28,31];
  - alarm_raised true; error_code "9010"; alarm_text_instructs_reconnect true; heat_start_inhibited true; recovery_requires_ack true; alarm_cleared_after_reconnect true;
  - disconnect_timestamp starts "2026-09-27T"; marks disconnect > heat_on and reconnect > alarm; the phase heating_wait_rise exists;
  - Columns match; > 100 samples; heater off; TC-08 not released; no safety cut.
- Body at 120 °C: the run is not refused. It notes "steady"/"still hot" and "heater body at 1…waiting for both", goes through cooldown, ends OK, and heating_wait_rise starts after more than 150 s.
- A floating CH1 (236.1, 181.0, 230.4, 122.7 repeating) → ERROR containing "jumps by" and "open or badly seated"; the heater never on; the TC-08 returned.
- ReleaseDelaySec 4 → the run still opens the TC-08 (Tc08 "PicoLog TC-08 (SIMULATED)") and reaches heating_wait_rise.
- OperatorTimeoutSec 20 with no operator → ERROR starting "the machine did not see the heater thermistor open within 20 s"; heater off.
- Abort while heating → ABORTED, heater off, TC-08 returned. Abort again → "no bench run in progress".
- Refusals: an unknown test, and heat 90 → "heat_target_c must be 30-80".
**Tests:** `BenchRunnerTests` (all 8 facts named in the source).
**Reference (source):** `src/SCureBox.Application/Dvt/Bench/BenchRunner.cs`, `src/SCureBox.Application/Dvt/Bench/SimulatedBenchWorld.cs`, `tests/SCureBox.Application.Tests/Process/BenchRunnerTests.cs`

---

### DVT-10 — DVT bench host process (HTTP API :3002, firmware HTTP client, watchdog safety net, systemd unit)
**Project / folder:** `src/SCureBox.Api/SCureBox.Api.csproj` — `Bench/`; `deploy/scurebox-dvt-bench.service`
**Goal:** Hosts the bench runner and recorder as their own ASP.NET Core process: `scurebox --dvt-bench`. It is separate from the firmware, so it keeps measuring while the firmware is hung, killed or restarting. It serves `/bench/*` to the DVT web page and reaches the firmware only through its HTTP API on :3001. In simulation it runs against `SimulatedBenchWorld`, with `/bench/sim/*` to play the operator.
**Depends on:** DVT-08, DVT-09, DVT-01, Api (`CommandLine` dispatch of `--dvt-bench`; `ApiJson`, `Query`, `ScureConsoleFormatter`, `CommandLine.ReadAppVersion`), Hardware (the `scurebox --watchdog --cut-now` CLI), Deploy-Ops (install of the unit).
**Files to create:**
- `src/SCureBox.Api/Bench/DvtBenchHost.cs` — `DvtBenchHost`
- `src/SCureBox.Api/Bench/HttpFirmwareClient.cs` — `HttpFirmwareClient`, `WatchdogCutSafetyNet`
- `deploy/scurebox-dvt-bench.service`
**Public contract:**
```csharp
public static class DvtBenchHost {
  public const int DefaultPort = 3002;
  public static int Run(string[] args, TextWriter stderr);   // args after "--dvt-bench"
  public static WebApplication Build(int port, string firmwareUrl, Action<WebApplicationBuilder>? configure = null, bool? simulate = null);
}
public sealed class HttpFirmwareClient : IFirmwareClient { public HttpFirmwareClient(string baseUrl); }
public sealed class WatchdogCutSafetyNet : ISafetyNet { public string CutNow(); }
```
**Behaviour & rules:**
1. `Run`:
   - Parse `--port <int>` (invariant) and `--firmware <url>` (default `http://127.0.0.1:3001`).
   - Anything else → write "usage: scurebox --dvt-bench [--port <n>] [--firmware <url>]" to stderr and return 2.
   - Otherwise `Build(...).Run()` and return 0.
   - `CommandLine` dispatches the first argument `--dvt-bench` to `DvtBenchHost.Run(args[1..], stderr)`.
2. `Build`:
   - `UseUrls("http://*:{port}")`; console logging with `ScureConsoleFormatter` (timestamp "yyyy-MM-dd HH:mm:ss "); CORS allowing any origin, method and header; `TimeProvider.System`.
   - sim = the `simulate` parameter, or else env `SCURE_SIMULATE` not in ("", "0", "false").
   - sim: one `SimulatedBenchWorld` registered as IFirmwareClient, ITc08Source, IUvMeterSource and ISafetyNet. Real: `HttpFirmwareClient(firmwareUrl)`, `Tc08Source`, `StarBrightUsbSource`, `WatchdogCutSafetyNet`.
   - Always: singletons `DvtBench`, `BenchRunner`, `BenchRecorder`; then `configure?.Invoke`.
   - Log a warning "[BENCH] DVT bench {version} on port {port}, firmware at {url}{ (SIMULATED)}".
3. Endpoints (JSON via `ApiJson.Json`, HTTP 200):
   - `GET /bench/status` → `{ok:true, version, simulated, tests:["DVT-SAF-002"], firmware_alive, firmware_version, run: <BenchRunStatus without samples>}` (Snapshot with a 2 s timeout).
   - `POST /bench/run?test=&heat_target=80&uv_intensity=100&uv_wavelength=405&hz=5&operator_timeout=180&cut_timeout=90&cooldown_max=1200&cooldown_below=60` → `{ok,message}`.
   - `GET /bench/run?samples=` (`Query.On`, default "1", so samples are included unless 0/false/off) → BenchRunStatus.
   - `POST /bench/run/abort?by=` (default User-Agent, else "api") → `{ok:true,message}`.
   - `POST /bench/record/start?label=&tc08=1&meter=0&hz=5&max_s=10800` (tc08 uses `OnLoose` with default "1"; meter uses `OnLoose` with default "0") → `{ok,message}`.
   - `POST /bench/record/mark?name=` → `{ok,message}`.
   - `POST /bench/record/stop` → `{ok,message}`.
   - `GET /bench/record?samples=&from=0` → RecordStatus.
   - Sim only:
     - `POST /bench/sim/heat?on=1|0` → Heat(80) or StopAll → `{ok,message}`;
     - `POST /bench/sim/sensor?open=1|0` → `{ok:true,sensor_open}`;
     - `GET /bench/sim` → `{ok:true,body_c,heater_on,uv_on,sensor_open}`.
   - Query semantics: `On` is false only for "0", "false", "off". `OnLoose` is false for "0", "false", "". A malformed number throws `ArgumentException("Invalid {key} '…'")`.
4. HttpFirmwareClient: `HttpClient` with BaseAddress = url (trailing "/" added) and Timeout 10 s.
   - `Snapshot(timeout)`: `GET api/state` with a CTS of `timeout`; any failure → `FirmwareSnapshot.Dead`. Field mapping:

     | Snapshot field | Taken from `/api/state` |
     |---|---|
     | Heating | `isHeating` (true only) |
     | UvOn | `uvOn` |
     | ChamberC | `chamberTemp` (number) |
     | ChamberSensorOk | `sensors.chamber.ok` (bool or null) |
     | DoorClosed | `doorClosed` (bool or null) |
     | Alerts | `alerts` (int array) |
     | AlertDetails | `alertDetails` (string values) |
     | RecipeState | `recipe.state` |
     | Version | `version` |
     | DoorAborted | `doorAborted` |

   - POSTs with no body:

     | Method | Request |
     |---|---|
     | Heat | `api/cure/heat?target={invariant}` |
     | Uv | `api/uv?on=1/0&intensity=&wavelength=` |
     | StopAll | `api/cure/stop?immediate=1` |
     | RecipeAbort | `api/recipe/abort` |
     | PicologRelease | `api/dev/picolog/release` |
     | PicologResume | `api/dev/picolog/resume` |
     | ClaimBench | `api/dvt/bench/claim?who={escaped}&lease_s={invariant}` |
     | ReleaseBench | `api/dvt/bench/release?who=` |

     The reply is `ok` = (JSON `ok` == true) and message = `message` ?? ("ok" | "HTTP {code}"). A body that is not JSON → (false, "HTTP {code}: {first 120 chars}"). A transport error → (false, exception message).
   - `PicologReleased()` = `GET api/dev/picolog/status` with connected false and error containing "released" (case-insensitive); exceptions → false.
   - `ErrorText(code)`: loaded lazily once, under a lock, from `GET config/errors.json`. For each item of `errors[]`, `code` maps to the join of `message`, `description` and the `troubleshooting[]` strings (non-empty ones, space-separated). A failure leaves the map empty, so the result is null.
5. WatchdogCutSafetyNet.CutNow: run `{AppContext.BaseDirectory}/scurebox` (`scurebox.exe` on Windows) with args `--watchdog --cut-now`. Redirect stdout and stderr, read both to the end, `WaitForExit(20000)`, and return the trimmed output. A failed start → IOException "scurebox --watchdog --cut-now did not start".
6. The systemd unit, exactly:
   - `[Unit]`: Description "sCureBox DVT bench - runs DVT catalog tests on the machine with the TC-08 / StarBright, separate from the firmware"; `Documentation=file:///opt/scurebox/docs/01-api-contract.md`; `After=network.target`. It is deliberately NOT bound to scurebox-ui.service / scurebox.service.
   - `[Service]`: `Type=simple`, `User=root`, `WorkingDirectory=/opt/scurebox`, `ExecStart=/opt/scurebox/scurebox --dvt-bench --port 3002 --firmware http://127.0.0.1:3001`, `Environment=SCURE_COMPONENTS=/etc/scurebox/components.json`, `Environment=DOTNET_gcServer=0`, `Restart=always`, `RestartSec=3`.
   - `[Install]`: `WantedBy=multi-user.target`.
   - root is needed for USB access to the TC-08 and the StarBright.
**Configuration:** CLI `--port` (3002), `--firmware` (http://127.0.0.1:3001); env `SCURE_SIMULATE`; `SCURE_COMPONENTS` is set by the unit (not read by the bench code itself; OPEN QUESTION whether anything in the bench path reads it); the app version comes from `CommandLine.ReadAppVersion(AppContext.BaseDirectory)` (the VERSION file).
**Acceptance criteria:**
- Simulated host on TestServer:
  - `/bench/status` gives ok, simulated true, firmware_alive true, tests containing DVT-SAF-002, run.status IDLE.
  - An unknown test → ok false. `test=DVT-SAF-002&heat_target=70` → ok; a second start → ok false.
  - `/bench/run?samples=0` has running true, config.heat_target_c 70, and the keys phase, prompt, values, marks, notes, phases, columns, n_samples, last.
  - Abort → within 30 s status ABORTED, phase done, `/bench/sim` heater_on false.
- Recorder over HTTP: the idle document has the keys running, status, label, phase, clock, t0_unix, marks, events, notes, columns, n_samples, last. Start with tc08=1&meter=1, sim heat on, a mark "heat", then stop → OK; the events contain heating_on; t0_unix is a number; marks has "heat"; a sample row has 11 columns.
- `Build(0, "http://127.0.0.1:1", UseTestServer, simulate:false)` resolves BenchRecorder and BenchRunner without hardware. This is a regression test: 1.0.44 shipped without an IUvMeterSource registration.
**Tests:** `DvtBenchHostTests` (IAsyncLifetime host built with `simulate: true` on TestServer: Status_run_and_abort, Recorder_answers_with_events_and_clock_origin, The_real_bench_process_can_build_its_services_without_hardware).
**Reference (source):** `src/SCureBox.Api/Bench/DvtBenchHost.cs`, `src/SCureBox.Api/Bench/HttpFirmwareClient.cs`, `src/SCureBox.Api/Infrastructure/CommandLine.cs`, `src/SCureBox.Api/Infrastructure/Query.cs`, `deploy/scurebox-dvt-bench.service`, `tests/SCureBox.Api.Tests/DvtBenchHostTests.cs`
