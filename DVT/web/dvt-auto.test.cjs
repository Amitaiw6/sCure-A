// Runs every script in dvt-auto.js against a simulated machine, on a virtual clock,
// with the operator prompts answered automatically. Driven by DVT/tests/test_dvt_web.py:
//
//     node DVT/web/dvt-auto.test.js            # prints one JSON result per test id
//
// The point is not to prove the numbers are right - only the machine can do that - but
// that every script runs to the end, drives the API it thinks it drives, fills values,
// and always leaves the machine off.

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const WEB = __dirname;
const CATALOG = JSON.parse(fs.readFileSync(path.join(WEB, 'dvt-catalog.js'), 'utf8')
  .replace(/^[\s\S]*?window\.SCURE_DVT = /, '').replace(/;\s*$/, ''));

// ---------------------------------------------------------------- the clock --
// setTimeout advances the virtual clock by the delay it was asked for and runs on the
// next tick, so a script that sleeps ten minutes finishes in milliseconds.
let vt = 0;
function makeTimer(sandbox) {
  sandbox.setTimeout = (fn, ms) => { vt += (ms || 0); return setImmediate(fn); };
  sandbox.clearTimeout = (h) => clearImmediate(h);
  sandbox.setInterval = () => 0;
  sandbox.clearInterval = () => {};
  sandbox.queueMicrotask = queueMicrotask;
  sandbox.performance = { now: () => vt };
  sandbox.Date = Date;
  sandbox.AbortSignal = { timeout: () => undefined };
}

// -------------------------------------------------------- the fake machine --
class Machine {
  constructor() {
    this.calls = [];
    this.chamber = 22;
    this.body = 22;                 // the TC-08 CH1 thermocouple
    this.panels = { right: 24, left: 24, back: 24, door: 24 };   // keyed by place exactly as the unit's ledTemps
    this.openThermistor = null;      // an LED thermistor the simulated operator has pulled
    this.openFan = null;             // an LED cooling fan the simulated operator has pulled (right/left/back/door)
    this.heating = false; this.cooling = false; this.uvOn = false; this.n2 = false;
    this.drying = false; this.damperOpened = false;     // Drying: slower than Heating, the damper opens 1.5 C below the set point
    this.uvIntensity = 0; this.target = null; this.alerts = []; this.recipe = null;
    this.doorClosed = true; this.tick = 0; this.ledFanDuty = 100;
    this.openThermocouple = false;        // an unseated probe floats near the top of the valid band
    // the door, as the person at DVT-SAF-008 handles it: every lock release (POST /api/door/open) is followed by what the
    // script asked for - open (1), open and held open (2), open then closed (3), a hold that does not move it (4)
    this.doorReleases = 0; this.closeInPolls = null; this.uvOffPolls = 0; this.uvOffDone = false;
    // SCURE_DOOR_FAULT: accept = the machine STARTS UV with the door open; magnet = the sensor reads closed while the magnet is held;
    // pull = the lock gives way when the door is pulled
    this.doorFault = process.env.SCURE_DOOR_FAULT || '';
    this.lockPolls = 0;
  }
  advance() {
    this.tick++;
    if (this.extHeat) {                                   // the cutout opens at 262 C and closes again at 198 C
      if (!this.cutOpen) { this.body += 3; if (this.body >= 262) this.cutOpen = true; }
      else { this.body -= 2; if (this.body <= 198) this.cutOpen = false; }
      this.chamber += 0.1;
    }
    if (this.hangUntil && vt >= this.hangFrom + 20000) { this.heating = false; this.uvOn = false; }   // the watchdog cut
    if (this.hangUntil && vt >= this.hangUntil) { this.hangUntil = null; this.alerts = [9060]; }       // after the hang: the restart alarm
    if (this.heating && this.drying) {
      this.chamber = Math.min(this.target + 1.2, this.chamber + 0.7); this.body += 2;
      if (this.chamber >= this.target - 1.5) this.damperOpened = true;
    }
    else if (this.heating) { this.chamber += 2.5; this.body += 6; }
    else if (this.cooling) { this.chamber = Math.max(21, this.chamber - 3); this.body = Math.max(22, this.body - 5); }
    else { this.chamber = Math.max(21, this.chamber - 0.4); this.body = Math.max(22, this.body - 1.2); }
    if (!this.heating) { this.drying = false; this.damperOpened = false; }
    for (const k of Object.keys(this.panels))
      this.panels[k] = this.uvOn ? Math.min(62, this.panels[k] + 1.1) : Math.max(24, this.panels[k] - 0.8);
    // a pulled LED thermistor: the machine sees it gone, refuses UV and raises an alarm that names the place
    if (this.openThermistor) { this.uvOn = false; if (!this.alerts.includes(9004)) this.alerts = [9004]; }
    // a pulled LED fan: no tach, the LEDs go off and an alarm names that fan
    if (this.openFan) { this.uvOn = false; if (!this.alerts.includes(9002)) this.alerts = [9002]; }
    // the machine protects itself: an alert after a while under heat, and the heater goes off
    if (this.heating && this.chamber > 95) { this.heating = false; this.alerts = [9001]; }
    if (this.uvOn && this.tick > 400) { this.uvOn = false; this.alerts = [9050]; }
    if (this.recipe && this.tick % 120 === 0) this.recipe = null;
  }
  state() {
    this.advance();
    if (this.doorClosed === false && this.closeInPolls !== null && --this.closeInPolls <= 0) { this.doorClosed = true; this.closeInPolls = null; }
    if (this.doorFault === 'pull' && this.doorReleases === 1 && this.uvOn && this.recipe && this.doorClosed && ++this.lockPolls > 4) this.doorClosed = false;   // pulled open under UV
    return {
      chamberTemp: Math.round(this.chamber * 100) / 100, targetTemp: this.target,
      doorClosed: this.doorClosed, isHeating: this.heating, isCooling: this.cooling,
      coolingRate: this.cooling ? 1.4 : null, coolingFanPwm: this.cooling ? 100 : 0,
      uvOn: this.uvOn, uvIntensity: this.uvIntensity, uvWavelength: 405,
      heaterPwm: this.heating ? 100 : 0, heaterOut: this.heating,
      ventOn: false, bofaOn: false, damperOpen: this.cooling || this.damperOpened, nitrogenActive: this.n2,
      n2Pressure: { volts: 2.9, mpa: 0.6, bar: 6.0, on: true, saturated: false, mode: 'analog_voltage', setPointMPa: 0.6 },
      ledTemps: Object.assign({}, this.panels, this.openThermistor ? { [this.openThermistor]: null } : {}),
      fans: { led_cooling: this.ledFanDuty, chamber_intake: 60, chamber_heating: this.heating ? 100 : 0 },
      fanDutyEach: { FAN_HEATER: this.heating ? 100 : (this.heaterFanDuty || 0), FAN_COOLING: this.cooling ? 100 : 0 },
      // exactly the unit's shape (sCureBox 1.0.4x): fanRpm is keyed by ROLE, fanRpmEach by fan - a script
      // that reads fanRpm.FAN_HEATER gets undefined here, as it does on the machine
      fanRpm: { led_cooling: 3500, chamber_intake: this.cooling ? 4700 : 0, chamber_heating: this.heating || this.heaterFanOn || this.heaterFanDuty > 0 ? 3500 : 0 },
      fanRpmEach: Object.assign({ FAN_LEFT: 3500, FAN_RIGHT: 3500, FAN_BACK: 3500, FAN_DOOR: 3500, FAN_HEATER: this.heating || (!process.env.SCURE_NO_TACH && (this.heaterFanOn || this.heaterFanDuty > 0)) ? 3500 : 0, FAN_COOLING: this.cooling ? 4700 : 0 },
                                this.openFan ? { ['FAN_' + this.openFan.toUpperCase()]: 0 } : {}),
      fanHealth: {}, ledHealth: {}, sensors: { TEMP_CHAMBER: { sensor: 'TEMP_CHAMBER', ok: true, openSec: null, critical: false } },
      alerts: this.alerts.slice(), alertDetails: { 9004: `LED thermistor not reading: ${this.openThermistor || 'right'} panel - check the sensor connection`,
                                                   9001: 'Chamber circulation fan FAN_HEATER stopped - check the fan and acknowledge',
                                                   9002: `LED cooling fan FAN_${String(this.openFan || 'right').toUpperCase()} stopped (${this.openFan || 'right'} fan) - check the fan connection`,
                                                   9050: 'LED panel sensor fault - check the thermistor connection' },
      nfcReader: this.tick > 3 ? { detected: true, serial: 'BH-0001' } : { detected: false, serial: null },
      recipe: this.recipe, hwSource: 'simulation', counters: {}, cloudSync: {},
    };
  }
  handle(url, method, body) {
    const p = url.replace(/^https?:\/\/[^/]+/, '');
    this.calls.push(`${method} ${p}`);
    if (this.hangUntil && (p.startsWith('/api/dvt/meter') || p.startsWith('/api/dev/picolog'))) this.advance();   // time passes for the instruments while the firmware hangs
    if (p.startsWith('/api/state')) return this.state();
    if (p.startsWith('/api/dev/picolog/status'))
      return { connected: true, ch1Available: true,
               temperature: this.openThermocouple ? 249.31 : Math.round(this.body * 100) / 100,
               ambient: 21.7, deviceInfo: 'PicoLog TC-08 S/N SIM', error: null,   // channel 0: the cold junction
               ch2Available: true, ch2: Math.round(this.chamber * 100) / 100,     // CH2: the reference thermocouple in the chamber
               // the chamber grid: two TC-08s x 8 (0031 = Z1-Z2, 114 = Z3-Z4); the top runs warmer, the front cooler,
               // by fixed offsets - Z1-3 (top, back right) is the hottest (+1.05 C) and Z4-2 (bottom, front left)
               // the coldest (-1.35 C), a 2.4 C spread
               units: ['A0031/338', 'AO114/209'].map((serial, u) => ({ serial, coldJunction: 21.7,
                 channels: Array.from({ length: 8 }, (_, i) => {
                   const level = u * 2 + Math.floor(i / 4) + 1, pos = (i % 4) + 1;
                   const off = 0.6 * (2.5 - level) + (pos === 3 ? 0.15 : 0) + (pos % 2 === 0 ? -0.45 : 0);
                   return Math.round((this.chamber + off) * 100) / 100;
                 }) })) };
    if (p.startsWith('/api/dvt/meter/wavelength')) return { ok: true };
    if (p.startsWith('/api/dvt/meter'))
      return { present: true, head: 'StarBright SIM', wavelength_nm: 405, reading_mw_cm2: this.uvOn && !this.openThermistor ? 12.5 : 0.01 };   // the LEDs go dark the moment a thermistor is pulled
    if (p.startsWith('/api/dvt/led-checks')) return { ok: true, enabled: /on=1/.test(p), panels: ['LED_LEFT', 'LED_RIGHT', 'LED_BACK', 'LED_DOOR'] };
    if (p.startsWith('/api/dvt/hang')) {                  // DVT-SAF-010: the firmware hangs; the output watchdog cuts after 20 s
      const sec = Number((/sec=(\d+)/.exec(p) || [])[1] || 60);
      this.hangFrom = vt; this.hangUntil = vt + sec * 1000;
      return { ok: true, sec, heartbeatTimeoutSec: 20 };
    }
    if (p.startsWith('/api/system/version')) return { appVersion: '1.0.35', gitCommit: 'sim' };
    if (p.startsWith('/api/nfc')) return { ok: true, enabled: true, reader: { detected: true, serial: 'BH-0001' } };
    if (p.startsWith('/api/recipe/status')) return { state: this.recipe ? 'running' : 'idle' };
    if (p.startsWith('/api/door/open')) {
      this.doorReleases++;
      if (this.doorReleases === 1) { this.doorClosed = false; this.closeInPolls = Infinity; }   // step 1: the person opens it and keeps it open
      else if (this.doorReleases === 2) { this.doorClosed = false; this.closeInPolls = this.doorFault === 'magnet' ? 5 : 70; }      // step 4: held open through the magnet, then closed
      else if (this.doorReleases === 3) { this.doorClosed = false; this.closeInPolls = 6; }       // step 5: opened, then closed again
      return { ok: true };                                                                         // 4th: a hold - nothing moves
    }
    if (p.startsWith('/api/dvt/uv-off/abort')) return { ok: true };
    if (p.startsWith('/api/dvt/uv-off')) {
      if (method === 'POST') { this.uvOffPolls = 0; this.uvOffDone = false; this.uvOn = true; return { ok: true, message: 'uv-off timing started' }; }
      if (/samples=0/.test(p)) {
        this.uvOffPolls++;
        if (this.uvOffPolls === 3) { this.doorClosed = false; this.uvOn = false; }
        const running = this.uvOffPolls < 6;
        if (!running) { this.uvOffDone = true; this.closeInPolls = 3; }
        return { running, phase: this.uvOffPolls < 3 ? 'plateau' : 'open_door', reading: this.uvOffPolls < 3 ? 12.5 : 0.01, plateau_mw_cm2: 12.5 };
      }
      return { status: 'OK', running: false, uv_off_time_s: 0.4, uv_zero_time_s: 0.9, residual_mw_cm2: 0.02, plateau_mw_cm2: 12.5, dark_mw_cm2: 0.01,
               samples: [[0, 12.5, false, 'plateau'], [1, 12.5, true, 'open_door'], [1.4, 0.01, true, 'off']], alerts_before: [], alerts_after: [6016],
               ui_alerts: ['critical', 'warning', 'at'],   // as the unit sends it: the UI's alert-count keys, not codes
               program_end: { state: 'error', error_code: '6016' }, door_aborted: true };
    }
    if (p.startsWith('/api/recipe/start') && this.doorClosed === false && this.doorFault === 'accept') { this.recipe = { state: 'running' }; this.uvOn = true; return { ok: true }; }
    if (p.startsWith('/api/recipe/start') && this.doorClosed === false) return { ok: false, message: '[6015] door open - job start refused' };
    if (p.startsWith('/api/uv') && /on=1/.test(p) && this.doorClosed === false && this.doorFault === 'accept') { this.uvOn = true; return { ok: true }; }
    if (p.startsWith('/api/uv') && /on=1/.test(p) && this.doorClosed === false) return { ok: false, message: 'door open - UV refused' };
    if (p.startsWith('/api/recipe/start')) {
      const steps = (() => { try { const b = JSON.parse(body || '{}'); return (b.material || b).steps || []; } catch (e) { return []; } })();
      const bad = steps.find((st) => !['Heating', 'Drying', 'Cure', 'Cooling', 'Bleacher', 'Nitrogen'].includes(st.process));
      if (bad) return { ok: false, message: `Invalid material: The JSON value could not be converted to SCureBox.Domain.Models.ProcessType. Path: $.steps[${steps.indexOf(bad)}].process` };
    }
    if (p.startsWith('/api/recipe/start')) { if (this.openThermistor) return { ok: false, message: 'LED thermistor missing' }; if (this.openFan) return { ok: false, message: `LED cooling fan ${this.openFan} not turning` }; this.recipe = { state: 'running' }; this.heating = true; this.uvOn = true; this.uvIntensity = 50; return { ok: true }; }
    if (p.startsWith('/api/recipe/abort')) { this.recipe = null; this.heating = false; this.uvOn = false; return { ok: true }; }
    if (p.startsWith('/api/cure/dry') && this.coolingFanOut) return { ok: false, message: '[9003] Chamber cooling fan not spinning: Chamber cooling fan (FAN_COOLING): 0 RPM - job start refused' };
    if (p.startsWith('/api/cure/dry')) { this.heating = true; this.drying = true; this.target = Number(/target=([\d.]+)/.exec(p)?.[1]) || 50; return { ok: true }; }
    if (p.startsWith('/api/cure/heat')) { this.heating = true; this.target = 80; return { ok: true }; }
    if (p.startsWith('/api/cure/cool')) { this.cooling = true; this.heating = false; return { ok: true }; }
    if (p.startsWith('/api/cure/uv-only')) { if (this.openFan || this.alerts.length) return { ok: false, message: 'refused: alarm active' }; this.uvOn = true; this.uvIntensity = 100; return { ok: true }; }
    if (p.startsWith('/api/cure/nitrogen')) { this.n2 = /on=1/.test(p); return { ok: true }; }
    if (p.startsWith('/api/cure/stop') && this.doorReleases === 1 && this.closeInPolls === Infinity) this.closeInPolls = 3;   // step 1 is over: the person closes the door
    if (p.startsWith('/api/cure/stop')) { this.heating = this.cooling = this.uvOn = this.n2 = false; this.recipe = null; return { ok: true }; }
    if (p.startsWith('/api/chamber/stop')) { this.heating = false; return { ok: true }; }
    if (p.startsWith('/api/uv')) { this.uvOn = /on=1/.test(p) && !this.openThermistor; this.uvIntensity = this.uvOn ? 100 : 0; return { ok: true }; }
    if (p.startsWith('/api/fans/override')) { if (/fan=chamber_heating/.test(p)) this.heaterFanOn = /on=1/.test(p); return { ok: true }; }
    if (p.startsWith('/api/fans/ack')) { this.acks = (this.acks || 0) + 1; if (!this.openFan) this.alerts = this.alerts.filter((a) => a !== 9002 && a !== 9003); return { ok: true, message: 'Fan alarm acknowledged' }; }
    if (p.startsWith('/api/fans/chamber_heating')) { const m = /speed=(\d+)/.exec(p); this.heaterFanDuty = m ? Number(m[1]) : 0; return { ok: true }; }
    if (p.startsWith('/api/fans/')) { const m = /speed=(\d+)/.exec(p); if (m) this.ledFanDuty = Number(m[1]); return { ok: true }; }
    if (p.startsWith('/api/diagnostics/fan-test')) return { ok: true, status: 'PASS', fans: {} };
    if (p.startsWith('/api/diagnostics/led-test')) return { ok: true, status: 'OK', stage: 'heating', message: null };   // what sCureBox 1.0.6x answers for a pass
    if (p.startsWith('/api/cure-history')) return { runs: [{ id: 'r1', status: 'aborted' }] };
    if (p.startsWith('/config/errors.json'))       // the shape the machine really serves
      return { _meta: { version: '3.0.1' }, errors: [
        { code: 9001, key: 'FAN_HEATER_STOPPED', message: 'Chamber circulation fan stopped',
          description: 'FAN_HEATER reports no rotation while the heater is on', troubleshooting: ['Check the fan connector', 'Acknowledge the alarm'] },
        { code: 9050, key: 'LED_SENSOR_FAULT', message: 'LED thermistor fault',
          description: 'The right LED panel thermistor is open circuit', troubleshooting: ['Check the sensor connection', 'Replace the thermistor'] }] };
    return { ok: true };
  }
}

// -------------------------------------------------------------- the harness --
function load(machine) {
  const sandbox = { window: {}, console };
  makeTimer(sandbox);
  sandbox.document = { getElementById: () => null };
  sandbox.alert = () => {};
  sandbox.fetch = async (url, opts) => {
    if (machine.onPoll) machine.onPoll();                 // the person at the machine, doing and confirming
    if (machine.frozenUntil && vt < machine.frozenUntil) throw new Error('fetch failed');   // a frozen firmware does not answer
    const body = machine.handle(String(url), (opts && opts.method) || 'GET', opts && opts.body);
    return { ok: true, json: async () => body };
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-catalog.js'), 'utf8'), sandbox);    // SCURE_DVT: thresholds
  vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-criteria.js'), 'utf8'), sandbox);   // DVT_CRITERIA: the page's evaluator
  vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-auto.js'), 'utf8'), sandbox);
  return sandbox.window.DVT_AUTO;
}

async function runOne(tid) {
  vt = 0;
  const machine = new Machine();
  const A = load(machine);
  const test = CATALOG.tests[tid];
  const run = { id: tid + '#1', variant: (test.variants && test.variants[0]) || {}, rep: 1 };
  // DVT-SAF-020 reviews what the earlier tests recorded, so the harness gives it something to review
  const results = {
    'DVT-SAF-001#1': { values: { error_code: '9001', alarm_text: 'Chamber circulation fan FAN_HEATER stopped' } },
    'DVT-SAF-004#1': { values: { error_code: '9050', alarm_text: 'LED thermistor fault on the right panel' } },
    'DVT-SAF-009#1': { values: { rated_trip_temp: 250 } },   // the cutout rating the operator enters first
  };
  const logs = [];
  A.attach({
    base: () => 'http://sim:3001', lang: () => 'en', connected: () => true, machine: () => 'sim',
    folderOk: () => true, operator: () => 'harness',
    test: () => test, run: () => run, results: () => results,
    log: (kind, msg) => logs.push(`${kind}: ${msg}`),
    persist: () => {}, journal: () => {}, refreshTest: () => {}, record: () => { results[run.id].verdict = 'RECORDED'; },
    setAuto: (rec, auto) => { (rec.autos = rec.autos || {})[auto.kind] = auto; rec.auto = auto; },
    autoMap: () => ({}), busy: () => false,
  });

  // answer every prompt the moment it appears, the way an operator who does as asked would
  let answered = 0;
  const asked = [];             // what the operator is asked, in order: the portal's simulation plays the same questions
  let pressed = 0, latePolls = 0;
  // the press rides on the machine poll (virtual time: a real-time timer would never run during a wait)
  machine.onPoll = () => {
    const st = A._state(tid);
    // SCURE_NO_PRESS: the operator never presses "I did it" on an instruction containing this text
    if (st && st.act && process.env.SCURE_NO_PRESS && st.act.text.includes(process.env.SCURE_NO_PRESS)) return;
    // SCURE_LATE_PRESS: the press for that instruction arrives SCURE_LATE_POLLS polls late (through the site), when the door
    // the person opened has already swung back
    if (st && st.act && process.env.SCURE_LATE_PRESS && st.act.text.includes(process.env.SCURE_LATE_PRESS)) {
      latePolls = (latePolls || 0) + 1;
      if (latePolls < Number(process.env.SCURE_LATE_POLLS || 100)) return;
    }
    if (st && st.act && st.act.ack && !st.act.acked) { pressed++; A.ackAct(tid); }
  };
  const pump = setInterval(() => {
    const st = A._state(tid);
    machine.onPoll();
    if (!st || !st.prompt) return;
    answered++;
    { const q = st.prompt; asked.push({ kind: q.kind, text: q.text, ...(q.field ? { field: q.field } : {}), ...(q.unit ? { unit: q.unit } : {}), ...(q.type && q.kind === 'value' ? { type: q.type } : {}), ...(q.values ? { values: q.values } : {}) }); }
    const pull = /(Disconnect|Pull) the (RIGHT|LEFT|BACK|DOOR)/.exec(st.prompt.text);
    if (pull) { if (/\bfan\b/i.test(st.prompt.text)) machine.openFan = pull[2].toLowerCase(); else machine.openThermistor = pull[2].toLowerCase(); }
    if (/Reconnect|acknowledge the alarm/.test(st.prompt.text)) {
      machine.openThermistor = null;
      if (/ fan/i.test(st.prompt.text)) machine.openFan = null;           // a fan alarm stays until the runner acknowledges it
      else machine.alerts = [];
    }
    // the simulated operator really does freeze the firmware when asked: its API goes silent for 30 s
    if (/stop the heartbeat|kill the control process/i.test(st.prompt.text)) machine.frozenUntil = vt + 30000;
    if (/Switch the external heater supply ON/.test(st.prompt.text)) machine.extHeat = true;            // DVT-SAF-009: the heater fed from outside
    if (/switch the external heater supply OFF|Cut the supply at the contactor/.test(st.prompt.text)) machine.extHeat = false;
    if (/Disconnect the (chamber )?cooling fan/.test(st.prompt.text)) machine.coolingFanOut = true;
    if (/Reconnect the cooling fan/.test(st.prompt.text)) machine.coolingFanOut = false;
    A.click(st.prompt.kind === 'yesno' ? 'as-yes' : st.prompt.kind === 'value' ? 'as-skip' : 'as-done', tid);
  }, 1);

  const started = Date.now();
  await A.start(tid);
  clearInterval(pump);
  const rec = results[run.id] || {};
  const auto = rec.auto || {};
  return {
    test: tid, status: auto.status, error: auto.error || '', line: (A._state(tid) || {}).line, cls: (A._state(tid) || {}).cls, valuesSeen: process.env.SCURE_DUMP ? rec.values : undefined,
    tracesSeen: process.env.SCURE_DUMP ? auto.traces : undefined, timeline: process.env.SCURE_DUMP ? (A._state(tid) || {}).timeline : undefined, logsSeen: process.env.SCURE_DUMP ? logs.slice(-6) : undefined, samplesSeen: process.env.SCURE_DUMP && auto.samples ? [auto.samples.length, auto.samples[30], auto.samples[auto.samples.length - 1]] : undefined,
    values: Object.keys(rec.values || {}).length, measured: (auto.measured || []).length,
    prompts: answered, pressed, asked: process.env.SCURE_SIM_PROMPTS ? asked : undefined, calls: machine.calls.length,
    traces: Object.keys(rec.autos || {}).filter((k) => (rec.autos[k].samples || []).length).length,
    left_on: machine.uvOn || machine.heating || machine.cooling || machine.n2,
    virtual_minutes: Math.round(vt / 60000), wall_ms: Date.now() - started,
  };
}

(async () => {
  const only = process.argv.slice(2);
  const A = load(new Machine());
  const ids = (only.length ? only : Object.keys(A.SCRIPTS)).filter((t) => A.SCRIPTS[t]);
  const out = [];
  for (const tid of ids) {
    try { out.push(await runOne(tid)); }
    catch (e) { out.push({ test: tid, status: 'THREW', error: String(e && e.stack || e) }); }
  }
  process.stdout.write(JSON.stringify(out, null, 1));
})();
