// ============================================================================
// DVT automatic runner.
//
// One "Run the test" button per DVT test. The runner drives the machine over
// its own API, watches /api/state at 1-5 Hz, and writes every value it can
// measure straight into the run - the operator types nothing.
//
// A test stops for the operator only where the catalog asks for something that
// cannot be done over the network (pull a connector, apply a magnet, read a
// clamp meter). Those stops appear as a prompt inside the card, one at a time,
// at the moment they are needed - never as a form to fill in afterwards.
//
// Loaded by dvt-tool.html, which hands it the page's own helpers through
// DVT_AUTO.attach(). Nothing in here touches the page's internals directly.
// ============================================================================

window.DVT_AUTO = (function () {
  'use strict';

  // Shown next to the catalog line in the page. A browser serving a cached dvt-auto.js is the
  // commonest reason a fix appears not to have landed, and this is how you see it at a glance.
  const VERSION = '0.9.131';

  const SCRIPTS = {};                 // test_id -> { kind, minutes, needs, intro, run(c) }
  const STATE = {};                   // test_id -> live runner state
  let H = null;                       // host adapter (dvt-tool.html)

  function attach(host) { H = host; }
  function has(tid) { return !!SCRIPTS[tid]; }
  function script(tid) { return SCRIPTS[tid] || null; }

  // ---------------------------------------------------------------- basics --
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clock = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);
  const r1 = (v) => (v === null ? null : Math.round(v * 10) / 10);
  const r2 = (v) => (v === null ? null : Math.round(v * 100) / 100);
  const r3 = (v) => (v === null ? null : Math.round(v * 1000) / 1000);
  const esc = (s) => String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const he = () => (H && H.lang() === 'he');
  /** Two-language string: L('open the door', 'פתח את הדלת'). */
  const L = (en, hb) => (he() ? hb : en);
  const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;

  // ------------------------------------------------------------ the engine --

  /** What one row of a watch() trace holds - the column header of its CSV. */
  const WATCH_COLUMNS = ['t_s', 'chamber_c', 'heater_pwm_pct', 'heater_on', 'uv_on',
                         'led_right_c', 'led_left_c', 'led_back_c', 'led_door_c', 'tc08_ch1_c', 'alerts', 'tc08_ch2_c',
                         // the chamber fans and the damper (user, 2026-10-01: read the damper position from the fan RPM) -
                         // damper_open is what the machine COMMANDED; the RPM at a given duty is the physical evidence
                         'fan_cooling_rpm', 'fan_cooling_duty', 'fan_heater_rpm', 'damper_open'];

  class Stopped extends Error {
    constructor() { super(L('stopped by the operator', 'נעצר על ידי המפעיל')); this.stopped = true; }
  }

  /**
   * Everything a test script is given. Scripts only ever talk to the machine and
   * to the run through this object, so the engine can stop, log and persist them
   * all the same way.
   */
  class Ctx {
    constructor(tid, test, run, rec) {
      this.tid = tid;
      this.test = test;
      this.run = run;
      this.rec = rec;
      this.variant = run.variant || {};
      this.fields = new Set((test.data_fields || []).map((f) => f.name));
      this.t0 = clock();
      this.timeline = [];             // [sec, text] - what the runner did, in order
      this.traces = {};               // name -> rows (written into the results folder)
      this.filled = [];               // field names filled automatically
      this.asked = [];                // field names the operator was asked for
      this.machine = H.machine();
      this.lastState = null;
    }

    // --- time ---------------------------------------------------------------
    get sec() { return Math.round(clock() - this.t0) / 1000; }
    stopped() { return !!(STATE[this.tid] && STATE[this.tid].stop); }
    check() { if (this.stopped()) throw new Stopped(); }
    async sleep(sec) {
      const end = clock() + sec * 1000;
      while (clock() < end) { this.check(); await sleep(Math.min(250, end - clock())); }
    }

    // --- talking to the machine ---------------------------------------------
    async get(path) {
      this.check();
      const r = await fetch(H.base() + path, { signal: AbortSignal.timeout(15000) });
      return r.json();
    }
    async post(path, timeoutMs) {
      this.check();
      // a diagnostic that runs for `seconds=N` answers only after N s plus its set-up (the 15 s LED test took 18.7 s on
      // the unit, 2026-10-01, and the old fixed 15 s budget threw its PASS away): wait N + 30 s for those
      const m = /[?&]seconds=(\d+)/.exec(path);
      const ms = timeoutMs || (m ? (Number(m[1]) + 30) * 1000 : 15000);
      const r = await fetch(H.base() + path, { method: 'POST', signal: AbortSignal.timeout(ms) });
      return r.json();
    }
    async postJson(path, body) {
      this.check();
      const r = await fetch(H.base() + path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), signal: AbortSignal.timeout(20000),
      });
      return r.json();
    }
    /** POST that never throws - used on the safety paths where "best effort" is the point. */
    async tryPost(path) { try { return await this.post(path); } catch (e) { return { ok: false, message: String(e.message || e) }; } }
    async state() {
      const s = await this.get('/api/state');
      this.lastState = s;
      return s;
    }

    // --- progress -----------------------------------------------------------
    say(en, hb, cls) {
      const text = L(en, hb === undefined ? en : hb);
      const st = STATE[this.tid];
      if (st) { st.line = text; st.cls = cls || ''; st.act = null; st.actAt = 0; st.ackAt = 0; }
      paint(this.tid);
      return text;
    }
    /**
     * An instruction the PERSON must carry out now ("OPEN THE DOOR and keep it open").
     * Unlike say() - which reports what the machine is doing - this is published as the step
     * on the site and in the console: big, amber, with the seconds left while the runner waits.
     * Before this existed (user, 2026-10-29) a timed instruction reached the portal as an
     * ordinary grey line while the big box said "running by itself - nothing to do", so
     * DVT-SAF-008 step 4/6 timed out: nobody was told to open the door.
     */
    act(en, hb, secLeft, opts) {
      const text = L(en, hb === undefined ? en : hb);
      const st = STATE[this.tid];
      const o = opts || {};
      if (st) {
        if (!st.act || st.act.text !== text) { st.actAt = Date.now(); st.ackAt = 0; }   // a new instruction needs its own press
        st.line = text; st.cls = 'act';
        st.act = { text, sec: typeof secLeft === 'number' ? Math.max(0, Math.ceil(secLeft)) : null,
                   stage: this.stageNow || null, ack: o.ack !== false, acked: !!st.ackAt,
                   label: o.label || null };
      }
      paint(this.tid);
      return text;
    }
    /** The person pressed "I did it" for the instruction on screen. */
    acked() {
      const st = STATE[this.tid];
      return !!(st && st.ackAt && st.ackAt >= (st.actAt || 0));
    }
    /** No instruction is on screen any more (the step moved on). */
    actDone() {
      const st = STATE[this.tid];
      if (st) { st.act = null; st.actAt = 0; st.ackAt = 0; }
    }
    /**
     * An instruction that is finished only when BOTH are true: the person pressed "I did it" and
     * (when the machine can see it) the machine agrees. The press alone never stands in for a
     * reading - if they disagree the operator is told which half is missing and the wait goes on.
     * `pred` null = nothing to read, the press is the whole step.
     */
    async doThis(en, hb, pred, sec, failEn, failHb) {
      const limit = sec === undefined ? 120 : sec;
      const t0 = clock();
      let seen = null, seenState = null, ok = false, everSeen = false, pressedOnce = false;
      while ((clock() - t0) / 1000 < limit) {
        this.check();
        const left = limit - (clock() - t0) / 1000;
        ok = true;
        if (pred) { try { seen = await this.state(); } catch (e) { seen = null; } ok = !!(seen && pred(seen)); }
        // look back: the step is done when the machine saw it at ANY moment since the instruction appeared, not only
        // at the moment the press arrives - the press travels through the site for seconds, and a door opened and let
        // go had swung back by then, so "I did it" was not taken (user, 2026-11-12)
        if (ok) { everSeen = true; seenState = seen; }
        // a press is kept for the whole step: the text below changes ("pressed, but..."), which clears the screen's
        // ack - before this a press given before the machine saw the door was lost (user, 2026-11-12)
        const pressed = pressedOnce = pressedOnce || this.acked();
        if (everSeen && pressed) { this.actDone(); return ok ? seen : seenState; }
        if (pressed && !everSeen) this.act(`${en} - pressed, but the machine does not see it yet`, `${hb === undefined ? en : hb} - נלחץ, אבל המכונה עדיין לא רואה את זה`, left);
        else if (everSeen && !pressed) this.act(`${en} - the machine sees it; press "I did it" to go on`, `${hb === undefined ? en : hb} - המכונה רואה את זה; לחץ "ביצעתי" כדי להמשיך`, left);
        else this.act(en, hb, left);
        await sleep(250);
      }
      this.actDone();
      // the machine saw it and only the press is missing: say so - "the machine did not see the door open" was shown
      // while the door sensor read OPEN the whole time (user, 2026-11-12, DVT-SAF-008 step 4 on CureBox-3)
      if (pred && everSeen && !pressedOnce)
        throw new Error(L(`the machine saw it, but nobody pressed "I did it" within ${Math.round(limit)} s - ${en}`,
                          `המכונה ראתה את זה, אבל אף אחד לא לחץ "ביצעתי" תוך ${Math.round(limit)} שניות - ${hb === undefined ? en : hb}`));
      throw new Error(L(failEn || `${en} - it did not happen within ${Math.round(limit)} s`,
                        failHb || `${hb === undefined ? en : hb} - לא בוצע תוך ${Math.round(limit)} שניות`));
    }
    /** A numbered stage of the script: shown to the operator and kept in the record. */
    stage(n, of, en, hb) {
      this.timeline.push([this.sec, L(en, hb === undefined ? en : hb)]);
      this.stageNow = { n, of, text: L(en, hb === undefined ? en : hb) };
      return this.say(`[${n}/${of}] ${en}`, `[${n}/${of}] ${hb === undefined ? en : hb}`);
    }
    note(en, hb) { this.timeline.push([this.sec, L(en, hb === undefined ? en : hb)]); }
    log(kind, en, hb) { H.log(kind, `${this.run.id}: ${L(en, hb === undefined ? en : hb)}`); }

    // --- writing results ----------------------------------------------------
    /** Write a measured value. Silently ignores fields this test does not have. */
    put(field, value) {
      if (!this.fields.has(field) || value === null || value === undefined) return value;
      if (typeof value === 'number' && !isFinite(value)) return null;
      this.rec.values[field] = value;
      if (!this.filled.includes(field)) this.filled.push(field);
      paint(this.tid);
      return value;
    }
    puts(obj) { for (const k of Object.keys(obj)) this.put(k, obj[k]); }
    has(field) { return this.fields.has(field); }
    /** Already answered (variant column or an earlier stage)? Then do not ask again. */
    known(field) {
      const v = this.rec.values[field];
      return v !== undefined && v !== null && v !== '';
    }
    /**
     * Keep a measurement with the run. A watch() trace (rows of scalars) is stored as
     * samples so the page writes it its own CSV in the results folder; anything else
     * (a report, a device record) rides along in the run's JSON.
     */
    trace(name, rows) {
      const isSamples = Array.isArray(rows) && rows.length > 0 && Array.isArray(rows[0]);
      this.traces[name] = isSamples ? { columns: WATCH_COLUMNS, samples: rows } : rows;
      if (this.has('raw_log_attached')) this.put('raw_log_attached', true);
      if (this.has('logged')) this.put('logged', true);
    }
    save() { H.persist(this.run.id, true); }

    // --- waiting ------------------------------------------------------------
    /**
     * Poll /api/state until pred(state) is true.
     * Returns { ok, sec, s } - sec is the time from the call to the first true.
     */
    async until(pred, opts) {
      const o = opts || {};
      const limit = o.sec === undefined ? 60 : o.sec;
      const poll = o.poll === undefined ? 0.3 : o.poll;
      const t = clock();
      let s = null;
      while ((clock() - t) / 1000 < limit) {
        this.check();
        try { s = await this.state(); } catch (e) { s = null; }
        if (s && pred(s)) return { ok: true, sec: Math.round(clock() - t) / 1000, s };
        if (o.tick) o.tick(s, Math.round(clock() - t) / 1000);
        await sleep(poll * 1000);
      }
      return { ok: false, sec: limit, s };
    }

    /**
     * Log the machine for `sec` seconds. Returns the rows it collected.
     * row = [t, chamberTemp, heaterPwm, heaterOut, uvOn, ledTemps..., tc08, alerts]
     * `on(s, t, rows)` may return 'stop' to end the watch early.
     */
    async watch(opts) {
      const o = opts || {};
      const limit = o.sec === undefined ? 60 : o.sec;
      const period = 1000 / (o.hz || 1);
      const withTc = !!o.tc;
      const rows = o.into || [];
      const t = clock();
      let lastSave = clock(), lastDraw = 0;
      while ((clock() - t) / 1000 < limit) {
        this.check();
        const at = Math.round(clock() - t) / 1000;
        let s = null, p = null;
        try {
          if (withTc) { const both = await Promise.all([this.state(), this.get('/api/dev/picolog/status').catch(() => null)]); s = both[0]; p = both[1]; }
          else s = await this.state();
        } catch (e) { /* a dropped poll is not a failed test */ }
        if (s) {
          const lt = s.ledTemps || {};
          rows.push([at, r2(num(s.chamberTemp)), r1(num(s.heaterPwm)), s.heaterOut === true, !!s.uvOn,
            r1(num(lt.right)), r1(num(lt.left)), r1(num(lt.back)), r1(num(lt.door)),   // the machine keys ledTemps by place, not TEMP_*
            withTc ? r2(tcRead(p)) : null, (s.alerts || []).join('|'), withTc ? r2(ch2Read(p)) : null,
            P.rpm(s, 'FAN_COOLING'), num((s.fans || {}).chamber_intake), P.rpm(s, 'FAN_HEATER'),
            s.damperOpen === true ? true : s.damperOpen === false ? false : null]);
          if (o.on && o.on(s, at, rows, p) === 'stop') break;
        }
        if (clock() - lastSave > 30000) { lastSave = clock(); this.save(); }
        if (o.live && clock() - lastDraw > 2000) { lastDraw = clock(); this.drawLive(o.live, rows); }
        await sleep(period);
      }
      return rows;
    }

    /**
     * Show a trace on the page while it is still being recorded: the rows go in as the same auto_<name> record the
     * final c.trace() will write, marked live and NOT persisted (the results folder gets the trace and its picture
     * once, at the end). The first call makes the page create the chart, later ones only redraw it.
     */
    drawLive(name, rows) {
      if (!H.setAuto) return;
      H.setAuto(this.rec, { kind: 'auto_' + name, test: this.tid, at: new Date().toISOString(), machine: this.machine,
                            columns: WATCH_COLUMNS, samples: rows, live: true });
      try {
        if (typeof H.hasTraceCanvas === 'function' && H.hasTraceCanvas(this.tid) && typeof H.drawTraces === 'function') H.drawTraces(this.tid);
        else H.refreshTest(this.tid);
      } catch (e) { /* a page without the chart hooks just shows the trace at the end */ }
    }

    // --- asking the operator (only where the catalog needs a physical act) ---
    /** "Do this, then press Done". Resolves true on Done, false on Skip. */
    ask(en, hb) { return prompt(this.tid, { kind: 'do', text: L(en, hb === undefined ? en : hb) }); }
    /** A yes/no the machine cannot see (visible damage, a fuse, a magnet). */
    async yesno(field, en, hb) {
      if (!this.has(field) || this.known(field)) return this.rec.values[field];
      const v = await prompt(this.tid, { kind: 'yesno', text: L(en, hb === undefined ? en : hb), field });
      if (v === null) return null;
      this.rec.values[field] = v;
      this.asked.push(field);
      this.save();
      paint(this.tid);
      return v;
    }
    /** A yes/no that is not a data field: the raw answer (true / false), null when skipped. */
    confirm(en, hb) { return prompt(this.tid, { kind: 'yesno', text: L(en, hb === undefined ? en : hb), field: null }); }
    /** An instrument reading. `unit` is shown next to the box. */
    async value(field, en, hb, unit) {
      if (!this.has(field) || this.known(field)) return this.rec.values[field];
      const f = (this.test.data_fields || []).find((x) => x.name === field) || {};
      const v = await prompt(this.tid, {
        kind: 'value', text: L(en, hb === undefined ? en : hb), field,
        unit: unit || f.unit || '', type: f.type || 'string', values: f.values || null,
      });
      if (v === null || v === '') return null;
      let out = v;
      if (f.type === 'float') out = Number(v);
      else if (f.type === 'int') out = Math.round(Number(v));
      else if (f.type === 'bool') out = v === 'true' || v === true;
      if (typeof out === 'number' && !isFinite(out)) return null;
      this.rec.values[field] = out;
      this.asked.push(field);
      this.save();
      paint(this.tid);
      return out;
    }
  }

  // --------------------------------------------------------------- prompts --

  function prompt(tid, p) {
    const st = STATE[tid];
    if (!st) return Promise.resolve(null);
    return new Promise((resolve) => {
      st.prompt = Object.assign({}, p, { resolve });
      paint(tid, true);
    });
  }

  /** "I did it" - from the card here or from the site through the runner. */
  function ackAct(tid) {
    const st = STATE[tid];
    if (!st || !st.act) return false;
    st.ackAt = Date.now();
    st.act = Object.assign({}, st.act, { acked: true });
    paint(tid, true);
    return true;
  }

  function answer(tid, value) {
    const st = STATE[tid];
    if (!st || !st.prompt) return;
    const p = st.prompt;
    st.prompt = null;
    p.resolve(value);
    paint(tid, true);
  }

  // ------------------------------------------------- shared measurements P ---

  const P = {
    /** The true chamber temperature for a reference reading: CH2 when plugged in, else CH1 - noted either way. */
    async reference(c) {
      const p = await c.get('/api/dev/picolog/status').catch(() => null);
      const ref = ch2Read(p);
      if (ref !== null) { c.note(`reference ${r2(ref)} C from TC-08 CH2`); return r2(ref); }
      const one = tcRead(p);
      if (one !== null) c.note(`reference ${r2(one)} C from TC-08 CH1 - no thermocouple on CH2`);
      return r2(one);
    },

    /** CH1 of the TC-08 on the machine's USB (the heater-body thermocouple), or null. */
    tc: async (c) => tcRead(await c.get('/api/dev/picolog/status').catch(() => null)),

    /**
     * Tach of one fan, by its name (FAN_HEATER, FAN_LEFT, ...). The machine keys fanRpm by ROLE
     * (led_cooling, chamber_intake, chamber_heating) and puts the per-fan names in fanRpmEach - a
     * read of fanRpm[FAN_HEATER] is null on the unit while the fan spins at 3600 rpm. FAN_HEATER and
     * FAN_COOLING are the only fans of their groups, so the group's reading is that fan's reading
     * exactly, not an average - it is the fallback for a host that reports roles only. The last
     * resort is the old host's shape (fanRpm keyed by fan name).
     */
    rpm(s, fan) {
      // FAN_HEATER and FAN_COOLING are the only fans of their groups, so the group reading IS that fan's -
      // exact, not averaged. The four LED fans share led_cooling, so for them only fanRpmEach counts.
      const role = { FAN_HEATER: 'chamber_heating', FAN_COOLING: 'chamber_intake' }[fan];
      const each = (s && s.fanRpmEach) || {}, byRole = (s && s.fanRpm) || {};
      const v = typeof each[fan] === 'number' ? each[fan] : role && typeof byRole[role] === 'number' ? byRole[role] : null;
      return typeof v === 'number' && isFinite(v) ? v : null;
    },

    /**
     * Is CH1 telling the truth? An open or badly seated thermocouple does not read null - it floats
     * near the top of the driver's valid band (a unit sitting at room temperature was seen reading
     * 249.31 C, which is inside -25..250 and would have been taken for a real near-cutout body).
     * The cold junction is the reference: the instrument's own terminal block is at ambient, so a
     * probe reading far above it with nothing running is broken, not hot.
     * Returns { ok, ch1, ambient, why }.
     */
    async tcCheck(c, s) {
      const p = await c.get('/api/dev/picolog/status').catch(() => null);
      const ch1 = tcRead(p);
      const ambient = p && num(p.ambient) !== null ? num(p.ambient) : null;
      if (ch1 === null)
        return { ok: false, ch1: null, ambient,
                 why: L('CH1 of the TC-08 is not reading - connect the thermocouple to CH1',
                        'ערוץ 1 של ה-TC-08 לא קורא - חבר את התרמוקפל לערוץ 1') };
      const st = s || c.lastState || {};
      const running = !!(st.uvOn || st.isHeating);
      if (!running && ambient !== null && ch1 - ambient > 60) {
        // On a test whose heat comes from outside the machine (catalog: external_heat) a hot body with the
        // machine idle is the normal case, so the level alone cannot condemn the probe. Behaviour can: an
        // open input floats - tens of degrees in seconds - while a real body moves less than a degree.
        if (c.test && c.test.external_heat) {
          const seen = [ch1];
          for (let i = 0; i < 3; i++) {
            await c.sleep(1);
            const again = tcRead(await c.get('/api/dev/picolog/status').catch(() => null));
            if (again !== null) seen.push(again);
          }
          const jitter = Math.max(...seen) - Math.min(...seen);
          if (seen.length < 3 || jitter > 5)
            return { ok: false, ch1, ambient,
                     why: L(`CH1 is floating (${seen.map(r1).join(' / ')} C over 3 s) - an open or badly seated thermocouple, not a hot body. Reseat it at the measurement point before starting.`,
                            `ערוץ 1 צף (${seen.map(r1).join(' / ')} מעלות תוך 3 שניות) - תרמוקפל מנותק או לא יושב טוב, לא גוף חם. הצמד אותו מחדש לנקודת המדידה לפני שמתחילים.`) };
          return { ok: true, ch1, ambient, external: true,
                   why: L(`CH1 is at ${r1(ch1)} C and steady with the machine idle - the heater body is hot from the external supply`,
                          `ערוץ 1 על ${r1(ch1)} מעלות ויציב כשהמכונה במנוחה - גוף ההיטר חם מההזנה החיצונית`) };
        }
        return { ok: false, ch1, ambient,
                 why: L(`CH1 reads ${r1(ch1)} C while the TC-08's own terminal block is at ${r1(ambient)} C and nothing is running - the thermocouple is open or badly seated, not hot. Reseat it at the measurement point before starting.`,
                        `ערוץ 1 קורא ${r1(ch1)} מעלות בזמן שלוח החיבורים של ה-TC-08 עצמו נמצא על ${r1(ambient)} מעלות ושום דבר לא פועל - התרמוקפל מנותק או לא יושב טוב, הוא לא חם. הצמד אותו מחדש לנקודת המדידה לפני שמתחילים.`) };
      }
      return { ok: true, ch1, ambient, why: '' };
    },

    /**
     * The ambient the bench is at. The TC-08 measures it at its own terminal block (the cold
     * junction it needs for every thermocouple reading anyway), so nobody types a room
     * temperature. Without a TC-08 the chamber sensor at rest is the next best thing, and the
     * record says which of the two it was.
     */
    async ambient(c, s) {
      const p = await c.get('/api/dev/picolog/status').catch(() => null);
      // the reference thermocouple on CH2 is the real ambient the test records (user, 2026-10-01)
      const ref = ch2Read(p);
      if (ref !== null) {
        c.note(`ambient ${r2(ref)} C from the reference thermocouple on TC-08 CH2`);
        return r2(ref);
      }
      const cj = p && p.connected && num(p.ambient) !== null ? num(p.ambient) : null;
      if (cj !== null) {
        c.note(`ambient ${r2(cj)} C from the TC-08 cold junction (${p.deviceInfo || 'TC-08'})`);
        return r2(cj);
      }
      const chamber = num((s || c.lastState || {}).chamberTemp);
      if (chamber !== null) c.note(`ambient ${r2(chamber)} C from the chamber sensor at rest - no TC-08 on the machine`);
      return r2(chamber);
    },

    /** Refuse to drive a machine that is already doing something. */
    async idle(c) {
      const s = await c.state();
      // /api/state keeps the LAST program in `recipe` after it ends (aborted, completed, error ...): only a program
      // that is still going counts - an aborted DVT-SAF-008 attempt used to block every other script here for good
      const running = s.recipe && s.recipe.state && ['running', 'paused', 'starting', 'preflight', 'waiting'].includes(String(s.recipe.state).toLowerCase());
      if (s.uvOn || s.isHeating || s.isCooling || s.nitrogenActive || running)
        throw new Error(L('a process is running on the machine - stop it first',
                          'יש תהליך פעיל במכונה - עצור אותו קודם'));
      return s;
    },

    /** Everything off, in the order that is safe even when a call fails. */
    async allOff(c) {
      await c.tryPost('/api/uv?on=0');
      await c.tryPost('/api/recipe/abort');
      await c.tryPost('/api/cure/stop?immediate=1');
      await c.tryPost('/api/chamber/stop');
      await c.tryPost('/api/cure/nitrogen?on=0');
    },

    /**
     * Ride through the machine restarting itself (Err 9006 restarts it 60 s after the alarm - user's rule,
     * 2026-10-01). Waits up to `startWithin` s for the API to go silent; if it does, waits up to 4 min for
     * /api/state to answer again and a few seconds for the firmware to settle. Returns {restarted, at, back}.
     */
    async rideRestart(c, startWithin) {
      const t0 = c.sec;
      let silentAt = null;
      while (c.sec - t0 < startWithin) {
        try { await c.get('/api/system/version'); } catch (e) { silentAt = c.sec; break; }
        c.say('waiting for the machine to restart itself (the 9006 rule)…', 'ממתין שהמכונה תאתחל את עצמה (כלל 9006)…');
        await c.sleep(2);
      }
      if (silentAt === null) { c.note(`no restart within ${startWithin} s`); return { restarted: false }; }
      c.note('machine restarting itself (Err 9006 rule)');
      const back = await c.until(() => true, { sec: 240, poll: 3,
        tick: () => c.say('the machine is restarting - waiting for it to come back…', 'המכונה מאתחלת - ממתין שתחזור…') });
      if (!back.ok) throw new Error(L('the machine did not come back within 4 minutes of restarting', 'המכונה לא חזרה תוך 4 דקות מהאתחול'));
      await c.sleep(10);                                    // let the firmware finish its start-up before commanding it
      c.note(`machine back after ${r1(c.sec - silentAt)} s`);
      return { restarted: true, at: silentAt, back: c.sec };
    },

    /** Alert codes present now that were not present in `before`. */
    fresh(before, s) {
      const had = new Set(before || []);
      return (s && s.alerts ? s.alerts : []).filter((x) => !had.has(x));
    },

    /** The code + text the operator is shown for an alert. */
    detail(s, code) {
      const d = (s && s.alertDetails) || {};
      return d[String(code)] || d[code] || '';
    },

    /** Wait for any alert the machine did not already have. */
    async alarm(c, before, opts) {
      const o = opts || {};
      let codes = [];
      const r = await c.until((s) => (codes = P.fresh(before, s)).length > 0,
        { sec: o.sec === undefined ? 180 : o.sec, poll: o.poll || 0.5, tick: o.tick });
      const code = codes.length ? codes[0] : null;
      return { raised: r.ok, sec: r.sec, code, codes, text: r.ok ? P.detail(r.s, code) : '', s: r.s };
    },

    /** Record alarm_raised / error_code / *_text the same way everywhere. */
    putAlarm(c, a, prefix) {
      const p = prefix || '';
      c.put(p + 'alarm_raised', a.raised);
      if (a.code !== null) c.put(p + 'error_code', String(a.code));
      if (a.text) { c.put(p + 'alarm_text', a.text); c.put('message_text', a.text); }
      return a;
    },

    /** Does the alarm text name this component? Words, not guesses. */
    names(text, words) {
      const t = String(text || '').toLowerCase();
      return words.some((w) => t.includes(String(w).toLowerCase()));
    },

    /**
     * The rise-to-fall turn of a trace: the instant the heater actually went off.
     * `fall` is how far below the peak counts as falling. `minRise` is how far the peak must stand
     * above the lowest point before it: a body that was still cooling from an earlier attempt when
     * the recording started dips first, and that dip is a turn too - one that a real run on the unit
     * recorded as the cut-off (78.9 C at 0 min, with the true trip at 260 C eleven minutes later).
     * With minRise the dip is passed over and the first real climb-then-fall is the one returned.
     */
    turn(rows, col, opts) {
      const o = opts || {};
      const fall = o.fall === undefined ? 0.3 : o.fall;
      const minRise = o.minRise === undefined ? 0 : o.minRise;   // how far the peak must stand above the low before it
      const minFall = o.minFall === undefined ? fall : o.minFall; // how far the trace must drop below the peak to count
      let peak = null, peakAt = null, low = null;
      for (const r of rows) {
        const v = r[col];
        if (v === null || v === undefined) continue;
        if (low === null || v < low) low = v;
        if (peak === null || v > peak) { peak = v; peakAt = r[0]; continue; }
        if (peak - v < fall) continue;
        if (peak - low < minRise) { peak = v; peakAt = r[0]; low = v; continue; }   // a cooling tail, not a trip: start over
        if (peak - v >= minFall) return { turned: true, at: peakAt, peak, fellAt: r[0] };
      }
      return { turned: false, at: peakAt, peak, fellAt: null };
    },

    /** Mean rate of change per minute over the last `sec` seconds of a trace. */
    rate(rows, col, sec) {
      const end = rows.length ? rows[rows.length - 1][0] : 0;
      const win = rows.filter((r) => r[0] >= end - sec && r[col] !== null && r[col] !== undefined);
      if (win.length < 2) return null;
      const dt = (win[win.length - 1][0] - win[0][0]) / 60;
      return dt > 0 ? r3((win[win.length - 1][col] - win[0][col]) / dt) : null;
    },

    maxOf(rows, col) {
      const v = rows.map((r) => r[col]).filter((x) => x !== null && x !== undefined);
      return v.length ? Math.max(...v) : null;
    },
    minOf(rows, col) {
      const v = rows.map((r) => r[col]).filter((x) => x !== null && x !== undefined);
      return v.length ? Math.min(...v) : null;
    },
    /** First row where pred(row) holds - the time it crossed. */
    firstAt(rows, pred) {
      for (const r of rows) if (pred(r)) return r[0];
      return null;
    },

    /**
     * The functional self-check every test ends with (post_test_functional_pass).
     * Nothing is taken on trust: every sensor reads, every fan turns, the heater
     * answers a short command and the LEDs answer a short one, then all off.
     */
    async selfCheck(c, opts) {
      const o = opts || {};
      c.say('functional check: sensors, fans, heater and LEDs…', 'בדיקה פונקציונלית: חיישנים, מאווררים, חימום ולדים…');
      const report = { at: new Date().toISOString() };
      // the step before this one is often "power the unit back up": wait for it to answer instead of
      // failing the whole check on the first refused connection (a DVT-SAF-003 run on the unit did exactly that)
      const up = await c.until(() => true, { sec: 240, poll: 3,
        tick: () => c.say('waiting for the machine to answer before the functional check…', 'ממתין שהמכונה תענה לפני הבדיקה הפונקציונלית…') });
      if (!up.ok) { report.error = 'the machine did not answer within 4 minutes'; report.pass = false; c.trace('functional_check', report);
                    c.put('post_test_functional_pass', false); return report; }
      try {
        await P.allOff(c);
        const s0 = await c.state();
        report.sensors = Object.values(s0.sensors || {}).map((x) => ({ sensor: x.sensor, ok: x.ok }));
        report.sensorsOk = report.sensors.every((x) => x.ok);
        report.chamberTemp = r2(num(s0.chamberTemp));

        const fan = await c.post('/api/diagnostics/fan-test?fan=all').catch(() => null);
        report.fans = fan && fan.fans ? fan.fans : null;
        report.fansOk = !!(fan && String(fan.status || '').toUpperCase() !== 'FAIL');

        if (o.heat !== false) {
          const target = Math.min(80, Math.max(30, Math.round((num(s0.chamberTemp) || 25) + 5)));
          await c.post(`/api/cure/heat?target=${target}`);
          const rise = await c.until((s) => num(s.heaterPwm) > 0 || s.heaterOut === true, { sec: 60, poll: 1 });
          report.heaterResponds = rise.ok;
          await c.tryPost('/api/chamber/stop');
        } else report.heaterResponds = null;

        if (o.led !== false) {
          const led = await c.post('/api/diagnostics/led-test?seconds=15').catch(() => null);
          report.led = led ? { status: led.status, stage: led.stage, message: led.message } : null;
          // the C# firmware answers a passed LED test with status 'OK' (the Python one said 'PASS'): DVT-SAF-017 r1 lost a PASS to this
          report.ledOk = !!(led && ['PASS', 'OK'].includes(String(led.status || '').toUpperCase()));
        } else report.ledOk = null;

        await P.allOff(c);
        const s1 = await c.state();
        report.alertsAfter = s1.alerts || [];
        const parts = [report.sensorsOk, report.fansOk, report.heaterResponds, report.ledOk].filter((x) => x !== null && x !== undefined);
        report.pass = parts.length > 0 && parts.every(Boolean) && report.alertsAfter.length === 0;
      } catch (e) {
        report.error = String(e.message || e);
        report.pass = false;
        if (e.stopped) throw e;
      }
      c.trace('functional_check', report);
      c.put('post_test_functional_pass', report.pass);
      c.put('post_ship_functional_pass', report.pass);
      c.put('pre_ship_functional_pass', report.pass);
      c.put('unit_powers_up', true);
      return report;
    },

    /** Command heat and log it. Returns the trace and the headline numbers. */
    async heatRun(c, opts) {
      const o = opts || {};
      const target = o.target === undefined ? 80 : o.target;
      const s0 = await c.state();
      const start = num(s0.chamberTemp);
      const before = s0.alerts || [];
      const r = await c.post(`/api/cure/heat?target=${target}`);
      const accepted = r.ok !== false;
      c.note(`HEAT ${target} C commanded: ${accepted ? 'accepted' : 'refused - ' + (r.message || '')}`);
      const rows = [];
      let alarmAt = null, alarmCode = null, offAt = null;
      const t = clock();
      await c.watch({
        sec: o.sec === undefined ? 600 : o.sec, hz: o.hz || 1, tc: o.tc !== false, into: rows, live: o.live || 'heat',
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (alarmAt === null && fresh.length) { alarmAt = at; alarmCode = fresh[0]; }
          if (offAt === null && at > 5 && !s.isHeating) offAt = at;
          c.say(`heating · ${mmss(at)} · ${r1(num(s.chamberTemp))} °C${alarmCode ? ' · alarm ' + alarmCode : ''}`,
                `מחמם · ${mmss(at)} · ${r1(num(s.chamberTemp))} °C${alarmCode ? ' · התראה ' + alarmCode : ''}`);
          if (o.stopOn && o.stopOn(s, at, rows)) return 'stop';
          if (o.untilAlarm && alarmAt !== null) return 'stop';
          if (o.untilTarget && num(s.chamberTemp) !== null && num(s.chamberTemp) >= target) return 'stop';
          return undefined;
        },
      });
      const elapsed = Math.round(clock() - t) / 1000;
      if (o.keepHot !== true) await c.tryPost('/api/chamber/stop');
      const s1 = await c.state();
      return {
        accepted, response: r, rows, start, target, elapsed,
        peak: P.maxOf(rows, 1), rise: start === null ? null : r2((P.maxOf(rows, 1) || start) - start),
        bodyPeak: P.maxOf(rows, 9), bodyTurn: P.turn(rows, 9),
        alarmAt, alarmCode, alarmText: alarmCode === null ? '' : P.detail(s1, alarmCode),
        offAt, before,
      };
    },
  };

  /** CH2 of the TC-08: the reference thermocouple in the chamber (sCureBox 1.0.50+), or null. */
  function ch2Read(p) {
    if (!p || !p.connected || p.ch2Available !== true) return null;
    const v = num(p.ch2);
    return v === null || v < -25 || v > 400 ? null : v;
  }

  function tcRead(p) {
    if (!p || !p.connected || p.ch1Available === false) return null;
    const v = num(p.temperature);
    return v === null || v < -25 || v > 400 ? null : v;   // the machine's band (PicoLogTc08Probe.ValidMaxC)
  }

  // ------------------------------------------------------------ the runner --

  async function start(tid) {
    const sc = SCRIPTS[tid];
    if (!sc) return;
    if (!H.folderOk()) { alert(L('Choose the results folder first - every result is written there',
                                 'בחר קודם תיקיית תוצאות - כל תוצאה נכתבת אליה')); return; }
    if (H.busy()) { alert(L('another automatic run is in progress', 'ריצה אוטומטית אחרת בתהליך')); return; }
    const test = H.test(tid);
    const run = H.run(tid);
    const results = H.results();
    const rec = results[run.id] || (results[run.id] = { values: {} });
    if (rec.verdict) return;
    if (sc.needs !== 'none' && !H.connected()) {
      STATE[tid] = { runId: run.id, line: L('Connect to the machine first (Machine field at the top)',
                                            'התחבר קודם למכונה (שדה "מכונה" למעלה)'), cls: 'fail' };
      paint(tid, true);
      return;
    }

    STATE[tid] = { runId: run.id, busy: true, stop: false, line: '', cls: '', prompt: null, started: Date.now() };
    H.autoMap()[tid] = { busy: true, runId: run.id, text: '' };
    const c = new Ctx(tid, test, run, rec);
    STATE[tid].ctx = c;
    H.refreshTest(tid);
    H.log('info', `${run.id}: ${L('automatic run started', 'ריצה אוטומטית התחילה')} (${sc.kind})`);
    H.journal('measurement_start', run.id);

    let status = 'OK', error = '';
    try {
      // A run started while the machine is restarting (its own 9006 restart, an install, a power cycle) must wait
      // for it rather than stop on the first request that times out or fails - "stopped: signal timed out" on the
      // unit was a run started during the machine's restart + boot self-test.
      if (sc.needs !== 'none') {
        const up = await c.until(() => true, { sec: 240, poll: 3,
          tick: () => c.say('waiting for the machine to answer (it may be restarting)…', 'ממתין שהמכונה תענה (ייתכן שהיא מאתחלת)…') });
        if (!up.ok) throw new Error(L('the machine did not answer within 4 minutes', 'המכונה לא ענתה תוך 4 דקות'));
        if (up.s && up.s.uvOn === true) {                    // the boot self-test lights the LEDs for ~15 s
          c.say('the machine is running its start-up self-test - waiting for it to finish…', 'המכונה מריצה את בדיקת האתחול שלה - ממתין שתסתיים…');
          await c.until((s) => s.uvOn !== true, { sec: 90, poll: 2 });
        }
      }
      await sc.run(c);
    } catch (e) {
      status = e && e.stopped ? 'STOPPED' : 'ERROR';
      error = String((e && e.message) || e);
    }
    try { await P.allOff(c); } catch (e) { /* the run is over either way */ }

    rec.autoFields = Array.from(new Set((rec.autoFields || []).concat(c.filled)));
    const at = new Date().toISOString();
    const notes = {};                   // the traces that are not sample rows travel in the summary
    for (const name of Object.keys(c.traces)) {
      const tr = c.traces[name];
      if (tr && tr.samples) H.setAuto(rec, { kind: 'auto_' + name, test: tid, at, machine: c.machine, columns: tr.columns, samples: tr.samples, xy: tr.xy || undefined });
      else notes[name] = tr;
    }
    H.setAuto(rec, {                    // last, so rec.auto is the summary of the whole run
      kind: 'auto_script', test: tid, script: sc.kind, status, error,
      at, machine: c.machine, seconds: c.sec,
      operator: H.operator(), timeline: c.timeline, traces: notes,
      measured: c.filled, asked: c.asked, missing: missing(c),
    });
    H.persist(run.id, true);
    H.journal('measurement', run.id);

    const left = missing(c);
    const done = status === 'OK' && !left.length;
    // The verdict in plain words, from the same evaluator and thresholds the page records with, so the line the
    // operator reads and the badge beside it can never disagree (user, 2026-10-01: "say on the screen it passed").
    let verdict = null, detail = '';
    if (done) {
      try {
        const crit = window.DVT_CRITERIA, cat = window.SCURE_DVT;
        const vals = Object.assign({}, rec.values);
        for (const k of Object.keys(run.variant || {})) if ((test.data_fields || []).some((f) => f.name === k)) vals[k] = run.variant[k];
        if (crit && cat) { const ev = crit.evaluate(test.pass_criteria, vals, cat.thresholds); verdict = ev.verdict; detail = ev.detail || ''; }
      } catch (e) { verdict = null; detail = String(e.message || e); }
    }
    const n = c.filled.length;
    STATE[tid] = {
      runId: run.id, busy: false, status, error,
      line: status !== 'OK' ? L(`stopped: ${error}`, `נעצר: ${error}`)
        : left.length ? L(`finished - waiting for: ${left.join(', ')} (${n} values measured)`,
                          `הסתיים - ממתין ל: ${left.join(', ')} (נמדדו ${n} ערכים)`)
        : verdict === 'PASS' ? L(`the test finished and PASSED - ${n} values measured`, `הבדיקה הסתיימה ועברה בהצלחה - נמדדו ${n} ערכים`)
        : verdict === 'FAIL' ? L(`the test finished - FAILED: ${detail || 'a pass criterion was not met'}`, `הבדיקה הסתיימה - נכשלה: ${detail || 'קריטריון מעבר לא התקיים'}`)
        : verdict === 'BLOCKED' ? L(`the test finished - BLOCKED: ${detail || 'the criteria cannot be evaluated yet'}`, `הבדיקה הסתיימה - חסומה: ${detail || 'אי אפשר עדיין להעריך את הקריטריון'}`)
        : L(`the test finished - ${n} values measured`, `הבדיקה הסתיימה - נמדדו ${n} ערכים`),
      cls: status !== 'OK' ? 'fail' : left.length ? '' : verdict === 'FAIL' ? 'fail' : verdict === 'PASS' ? 'pass' : verdict === 'BLOCKED' ? 'warn' : '',
    };
    H.autoMap()[tid] = { busy: false, runId: run.id, text: STATE[tid].line, cls: STATE[tid].cls };
    H.log(status !== 'OK' || verdict === 'FAIL' ? 'fail' : done ? 'pass' : 'info', `${run.id}: ${STATE[tid].line}`);

    if (done && sc.autoRecord !== false) H.record(tid);
    else H.refreshTest(tid);
  }

  /** Fields the pass criteria need that nobody has answered yet. */
  function missing(c) { return missingFields(c.test, c.rec.values); }
  /** The same question for a run outside a script: which criteria fields are still empty? */
  function missingFields(test, values) {
    const crit = String(test.pass_criteria || '');
    const out = [];
    for (const f of test.data_fields || []) {
      if (!new RegExp(`\\b${f.name}\\b`).test(crit)) continue;
      const v = (values || {})[f.name];
      if (v === undefined || v === null || v === '') out.push(f.name);
    }
    return out;
  }

  function stop(tid) {
    const st = STATE[tid];
    if (!st) return;
    st.stop = true;
    if (st.prompt) answer(tid, null);
    if (st.ctx) P.allOff(st.ctx).catch(() => {});
    paint(tid);
  }

  // ------------------------------------------- reading a finished recording --

  const TRACE = {};                   // test_id -> (rows, put, rec) => message

  /**
   * Fill a run from a measurement that is already in hand, whichever card produced it.
   * A test where the operator drives the hardware (DVT-SAF-009: the heater is bridged by hand,
   * the machine has no command for it) still logs everything through the TC-08, and that log
   * IS the test data - so the values come out of it instead of being typed in afterwards.
   * Returns { filled, message }; filled is empty when the recording does not show what the
   * test needs, and the message says why.
   */
  function fromTrace(test, rec) {
    const tid = test.test_id;
    const fn = TRACE[tid];
    if (!fn || !rec) return { filled: [], message: '' };
    const auto = (rec.autos && rec.autos.tc08_record) || (rec.auto && rec.auto.kind === 'tc08_record' ? rec.auto : null);
    const rows = auto && Array.isArray(auto.samples) ? auto.samples : null;
    if (!rows || rows.length < 5) return { filled: [], message: '' };
    if (rec.verdict) return { filled: [], message: '' };
    const known = new Set((test.data_fields || []).map((f) => f.name));
    const filled = [];
    const put = (field, value) => {
      if (!known.has(field) || value === null || value === undefined) return;
      if (typeof value === 'number' && !isFinite(value)) return;
      rec.values[field] = value;
      if (!filled.includes(field)) filled.push(field);
    };
    let message = '';
    try { message = fn(rows, put, rec) || ''; }
    catch (e) { message = String(e.message || e); }      // whatever it filled before failing is still measured
    if (filled.length) rec.autoFields = Array.from(new Set((rec.autoFields || []).concat(filled)));
    return { filled, message };
  }

  // ------------------------------------------------------------- rendering --

  function counters(tid) {
    const st = STATE[tid];
    const c = st && st.ctx;
    if (!c) return null;
    const total = (H.test(tid).data_fields || []).length;
    return { total, done: Object.keys(c.rec.values || {}).length, auto: c.filled.length, sec: c.sec };
  }

  /** The card: one Start button for the whole test. */
  function card(test, run, locked) {
    const tid = test.test_id;
    const sc = SCRIPTS[tid];
    if (!sc) return '';
    const st = STATE[tid] && STATE[tid].runId === run.id ? STATE[tid] : null;
    const busy = H.busy();
    const n = counters(tid);
    const intro = L(sc.intro[0], sc.intro[1]);
    const kind = { auto: L('fully automatic', 'אוטומטי מלא'), guided: L('automatic, with prompts', 'אוטומטי, עם הנחיות'),
                   instrumented: L('automatic, instrument readings asked for', 'אוטומטי, קריאות מכשיר נדרשות') }[sc.kind] || sc.kind;
    return `<div class="auto-card auto-script">
      <div class="auto-head">
        <span class="badge auto">${esc(kind)}</span>
        ${sc.minutes ? `<span class="auto-est">${L('about', 'כ')} ${sc.minutes} ${L('min', 'דק\'')}</span>` : ''}
        ${n ? `<span class="auto-est">${n.auto}/${n.total} ${L('values measured', 'ערכים נמדדו')} · ${mmss(n.sec)}</span>` : ''}
      </div>
      <div class="auto-note" style="margin:0 0 8px">${esc(intro)}</div>
      <div class="auto-row">
        <button class="btn btn-auto btn-small" data-act="as-run" data-test="${tid}" ${locked || busy ? 'disabled' : ''}>▶ ${L('Run the test', 'הרץ את הבדיקה')}</button>
        ${st && st.busy ? `<button class="btn btn-outline btn-small" data-act="as-stop" data-test="${tid}">■ ${L('Stop', 'עצור')}</button>` : ''}
        <span class="auto-text ${st ? st.cls || '' : ''}" id="as-line-${tid}">${st ? esc(st.line) : ''}</span>
      </div>
      ${st && st.act && st.act.ack && !st.act.acked ? `<div class="auto-prompt"><div class="auto-prompt-text">${esc(st.act.text)}</div>
        <div class="auto-prompt-row"><button class="btn btn-auto btn-small" data-act="as-acted" data-test="${tid}">${esc(st.act.label || L('I did it', 'ביצעתי'))}</button></div></div>` : ''}
      ${st && st.prompt ? promptHtml(tid, st.prompt) : ''}
    </div>`;
  }

  function promptHtml(tid, p) {
    const box = p.kind === 'value'
      ? (p.values && p.values.length
          ? `<select id="as-in-${tid}">${p.values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('')}</select>`
          : `<input id="as-in-${tid}" dir="ltr" ${p.type === 'float' || p.type === 'int' ? 'type="number" step="any"' : 'type="text"'}>`)
      : '';
    const buttons = p.kind === 'yesno'
      ? `<button class="btn btn-auto btn-small" data-act="as-yes" data-test="${tid}">${L('Yes', 'כן')}</button>
         <button class="btn btn-outline btn-small" data-act="as-no" data-test="${tid}">${L('No', 'לא')}</button>`
      : p.kind === 'value'
      ? `<button class="btn btn-auto btn-small" data-act="as-ok" data-test="${tid}">${L('Save', 'שמור')}</button>
         <button class="btn btn-outline btn-small" data-act="as-skip" data-test="${tid}">${L('Skip', 'דלג')}</button>`
      : `<button class="btn btn-auto btn-small" data-act="as-done" data-test="${tid}">${L('Done', 'בוצע')}</button>
         <button class="btn btn-outline btn-small" data-act="as-skip" data-test="${tid}">${L('Skip', 'דלג')}</button>`;
    return `<div class="auto-prompt">
      <div class="auto-prompt-text">${esc(p.text)}</div>
      <div class="auto-prompt-row">${box}${p.unit ? `<span class="unit">[${esc(p.unit)}]</span>` : ''}${buttons}</div>
    </div>`;
  }

  /** The per-step marker: the card at the top is what actually runs. */
  function stepNote() {
    return `<div class="auto-note">${L('This step runs automatically - press "Run the test" above.',
                                        'השלב הזה מתבצע אוטומטית - לחץ "הרץ את הבדיקה" למעלה.')}</div>`;
  }

  /** Cheap repaint: the progress line only, unless the card itself changed. */
  let painting = null;
  function paint(tid, full) {
    if (full) { H.refreshTest(tid); return; }
    if (painting === tid) return;
    painting = tid;
    setTimeout(() => {
      painting = null;
      const st = STATE[tid];
      const el = document.getElementById('as-line-' + tid);
      if (el && st) { el.textContent = st.line; el.className = 'auto-text ' + (st.cls || ''); }
    }, 0);
  }

  // One entry point for every button on the card, so the page needs a single line.
  function click(act, tid) {
    if (act === 'as-run') start(tid);
    else if (act === 'as-stop') stop(tid);
    else if (act === 'as-done') answer(tid, true);
    else if (act === 'as-yes') answer(tid, true);
    else if (act === 'as-no') answer(tid, false);
    else if (act === 'as-skip') answer(tid, null);
    else if (act === 'as-acted') ackAct(tid);
    else if (act === 'as-ok') {
      const el = document.getElementById('as-in-' + tid);
      answer(tid, el ? el.value : null);
    }
  }

  /** A context for the odd API call made outside a run (the page's prepare / finish hooks). */
  function bare() {
    return new Ctx('_bare', { test_id: '_bare', data_fields: [] }, { id: '_bare', variant: {} }, { values: {} });
  }

  /** The sentence above a bench test's checks (the DVT tool shows the same one). */
  const BENCH_INTRO = 'Automatic on the machine: the DVT bench process (port 3002) runs the whole test itself - heats, waits for the heater body to rise, tells you when to pull and when to reconnect the thermistor, times everything on the machine clock and fills every field. The trace and the graph go to the results folder.';

  /**
   * What the DVT tab of sCure Cloud needs to explain a test the way this tool does: why, with what, in which order and
   * what counts as a pass. Plain English text only (the portal has no Hebrew); no data fields or run state.
   */
  // The questions each script asks the operator, in order - GENERATED by DVT/web/build_sim_prompts.cjs (the portal's simulation plays them).
  const SIM_PROMPTS = {"DVT-SAF-018":[{"kind":"do","text":"Selector at 110 V, mains at 230 V, current probe around the heater branch conductor, TC-08 CH1 bonded to the heater body. Press Done when the rig is as the catalog describes."},{"kind":"value","text":"Peak current the clamp meter recorded on the heater branch","field":"heater_branch_peak_current","unit":"A","type":"float"},{"kind":"value","text":"Which fuse opened?","field":"which_fuse_opened","type":"enum","values":["heater_branch_5A","inlet_15A","both","none"]},{"kind":"do","text":"De-energise, isolate and let the unit cool, then open it and inspect."},{"kind":"yesno","text":"Was there smoke or fire?","field":"smoke_or_fire"},{"kind":"yesno","text":"Is the enclosure damaged?","field":"enclosure_damage"},{"kind":"yesno","text":"Does the heater element still have continuity?","field":"heater_element_continuity"},{"kind":"value","text":"Condition of the wiring insulation","field":"wiring_insulation_condition","type":"enum","values":["intact","discoloured","damaged"]},{"kind":"yesno","text":"Take the heater branch fuse out and check it with a meter: did it really blow (open circuit)?","field":"fuse_blown_confirmed"},{"kind":"do","text":"Replace the opened fuse, set the selector correctly and power the unit up again. Press Done when it is running."}],"DVT-SAF-019":[{"kind":"value","text":"Prospective short-circuit current of the supply","field":"prospective_scc","unit":"A","type":"float"},{"kind":"value","text":"PE resistance measured at the inlet","field":"pe_resistance","unit":"ohm","type":"float"},{"kind":"do","text":"Energise the unit, confirm normal standby, then apply the short remotely and capture the current waveform."},{"kind":"value","text":"Peak fault current from the waveform","field":"peak_fault_current","unit":"A","type":"float"},{"kind":"value","text":"Fuse clearing time from the waveform","field":"fuse_clearing_time","unit":"ms","type":"float"},{"kind":"yesno","text":"Did the inlet fuse open?","field":"fuse_opened"},{"kind":"yesno","text":"Is there arc damage?","field":"arc_damage"},{"kind":"yesno","text":"Are the terminals damaged?","field":"terminal_damage"},{"kind":"yesno","text":"Is the inlet filter still functional?","field":"inlet_filter_functional"},{"kind":"value","text":"PE continuity after the event","field":"pe_continuity_post","unit":"ohm","type":"float"},{"kind":"value","text":"Insulation resistance after the event","field":"insulation_resistance_post","unit":"Mohm","type":"float"}],"DVT-SAF-001":[{"kind":"do","text":"Open the circulation fan supply NOW, then press Done. The runner times everything from that press."}],"DVT-SAF-004":[{"kind":"do","text":"Disconnect the RIGHT LED thermistor only (open circuit), then press Done."},{"kind":"do","text":"Reconnect the RIGHT thermistor and acknowledge the alarm on the screen, then press Done - the runner will light the LEDs and ask you to pull it again."},{"kind":"do","text":"LEDs at maximum. Pull the RIGHT thermistor connector NOW, then press Done."},{"kind":"do","text":"Reconnect the RIGHT thermistor and acknowledge the alarm, then press Done."},{"kind":"do","text":"Disconnect the LEFT LED thermistor only (open circuit), then press Done."},{"kind":"do","text":"Reconnect the LEFT thermistor and acknowledge the alarm on the screen, then press Done - the runner will light the LEDs and ask you to pull it again."},{"kind":"do","text":"LEDs at maximum. Pull the LEFT thermistor connector NOW, then press Done."},{"kind":"do","text":"Reconnect the LEFT thermistor and acknowledge the alarm, then press Done."},{"kind":"do","text":"Disconnect the BACK LED thermistor only (open circuit), then press Done."},{"kind":"do","text":"Reconnect the BACK thermistor and acknowledge the alarm on the screen, then press Done - the runner will light the LEDs and ask you to pull it again."},{"kind":"do","text":"LEDs at maximum. Pull the BACK thermistor connector NOW, then press Done."},{"kind":"do","text":"Reconnect the BACK thermistor and acknowledge the alarm, then press Done."},{"kind":"do","text":"Disconnect the DOOR LED thermistor only (open circuit), then press Done."},{"kind":"do","text":"Reconnect the DOOR thermistor and acknowledge the alarm on the screen, then press Done - the runner will light the LEDs and ask you to pull it again."},{"kind":"do","text":"LEDs at maximum. Pull the DOOR thermistor connector NOW, then press Done."},{"kind":"do","text":"Reconnect the DOOR thermistor and acknowledge the alarm, then press Done."}],"DVT-SAF-005":[{"kind":"do","text":"Disconnect the RIGHT LED fan only, then press Done."},{"kind":"do","text":"Reconnect the RIGHT fan, then press Done - the LEDs will go to maximum."},{"kind":"do","text":"Pull the RIGHT fan connector NOW, then press Done."},{"kind":"do","text":"Reconnect the RIGHT fan, then press Done."},{"kind":"do","text":"Disconnect the LEFT LED fan only, then press Done."},{"kind":"do","text":"Reconnect the LEFT fan, then press Done - the LEDs will go to maximum."},{"kind":"do","text":"Pull the LEFT fan connector NOW, then press Done."},{"kind":"do","text":"Reconnect the LEFT fan, then press Done."},{"kind":"do","text":"Disconnect the BACK LED fan only, then press Done."},{"kind":"do","text":"Reconnect the BACK fan, then press Done - the LEDs will go to maximum."},{"kind":"do","text":"Pull the BACK fan connector NOW, then press Done."},{"kind":"do","text":"Reconnect the BACK fan, then press Done."},{"kind":"do","text":"Disconnect the DOOR LED fan only, then press Done."},{"kind":"do","text":"Reconnect the DOOR fan, then press Done - the LEDs will go to maximum."},{"kind":"do","text":"Pull the DOOR fan connector NOW, then press Done."},{"kind":"do","text":"Reconnect the DOOR fan, then press Done."}],"DVT-SAF-006":[{"kind":"do","text":"Disconnect the chamber cooling fan, then press Done."},{"kind":"do","text":"Reconnect the cooling fan and press Done - the runner will heat the chamber and start a cooling cycle, then ask you to disconnect the fan again."},{"kind":"do","text":"Disconnect the cooling fan NOW, then press Done."},{"kind":"do","text":"Reconnect the cooling fan and press Done."}],"DVT-SAF-020":[{"kind":"yesno","text":"Do all 2 of these events appear in the machine's persistent log with a timestamp? (codes: 9001, 9050)","field":"all_logged"}],"DVT-SAF-007":[{"kind":"do","text":"Set the voltage selector to 220 V and feed the unit 110 V at the inlet (the heater gets about a quarter of its power), then press Done."},{"kind":"value","text":"Selector position","field":"selector_position","type":"string"},{"kind":"value","text":"Input voltage (measured at the inlet) - the machine cannot sense it, so you enter it","field":"applied_voltage","unit":"V","type":"float"},{"kind":"value","text":"Heater branch current while heating","field":"heater_branch_current","unit":"A","type":"float"},{"kind":"yesno","text":"Did any fuse open?","field":"fuse_opened"},{"kind":"yesno","text":"Did the thermal cutout trip?","field":"thermal_cutout_tripped"},{"kind":"yesno","text":"Is there visible damage?","field":"visible_damage"},{"kind":"do","text":"Restore the correct selector position for the applied mains, then press Done."}],"DVT-SAF-017":[{"kind":"do","text":"Set the voltage selector to the MIDDLE (between 110 V and 230 V) and the mains input to 220 V, then press Done."},{"kind":"value","text":"Heater branch current with HEAT commanded (expected zero)","field":"heater_branch_current","unit":"A","type":"float"},{"kind":"do","text":"Set the selector to the correct detent for the applied mains, then press Done."}],"DVT-THM-001":[{"kind":"value","text":"Selector position","field":"selector_position","type":"string"}],"DVT-THM-002":[{"kind":"value","text":"LED current at the working point","field":"led_current","unit":"A","type":"float"}],"DVT-THM-003":[{"kind":"value","text":"Peak-to-peak spread across the 16 grid channels at the point of maximum cooling rate","field":"uniformity_pp_during_cooling","unit":"C","type":"float"},{"kind":"value","text":"Grid position of the largest gradient","field":"max_gradient_position","type":"string"}],"DVT-THM-006":[{"kind":"do","text":"Selector at 110 V, mains at 230 V, TC-08 CH1 bonded to the heater body. Power the unit up but do NOT command heat. Press Done."},{"kind":"yesno","text":"Is the selector confirmed and photographed at 110 V?","field":"selector_position_verified"},{"kind":"do","text":"De-energise, isolate and let it cool, then identify which fuse opened."},{"kind":"yesno","text":"Did a fuse open?","field":"fuse_opened"},{"kind":"value","text":"Which fuse opened?","field":"which_fuse_opened","type":"enum","values":["heater_branch_5A","inlet_15A","both","none"]},{"kind":"do","text":"Replace the fuse, set the selector to 230 V, power up, then press Done."}],"DVT-SAF-009":[{"kind":"do","text":"Switch the external heater supply ON now and leave it on - do not interrupt it until the runner says the recording is complete. Fire watch at the bench. Press Done when it is on."},{"kind":"do","text":"the body is climbing again from 194.2 C - the cutout closed; recording complete - switch the external heater supply OFF now, then press Done."}],"DVT-SAF-011":[{"kind":"do","text":"Disconnect the 40-pin flat cable of the CM5 NOW, then press Done. The runner times everything from that press."},{"kind":"yesno","text":"Did the heater SSR switch off?","field":"heater_ssr_switched_off"},{"kind":"do","text":"Reconnect the 40-pin flat cable of the CM5, then press Done."}],"DVT-SAF-012":[{"kind":"do","text":"Darken the room, close and latch the door, hold the meter head flush against the door seam and press Done."},{"kind":"do","text":"Wearing UV eye protection, scan the door seam, hinge line, damper, vents, cable entries and every panel joint with the meter head held flush against the light source. The runner keeps the highest reading - press Done when you have covered everything."},{"kind":"value","text":"Where was the meter when the maximum was read?","field":"leak_location","type":"string"},{"kind":"do","text":"Hold the meter head at the operator position at the front of the machine (eye height, facing the door) and press Done - the runner then averages the meter for 10 s."}],"DVT-SAF-013":[{"kind":"do","text":"Unplug the door switch connector, then press Done."},{"kind":"do","text":"Plug the door switch connector back in, then press Done."}],"DVT-SAF-014":[{"kind":"do","text":"Kill the screen (UI) process only - leave the firmware running. Press Done the moment it is gone."},{"kind":"value","text":"What is on the display now?","field":"display_state","type":"string"},{"kind":"do","text":"Restore the machine to normal operation (restart what you stopped, reconnect, remount read-write), then press Done."}],"DVT-SAF-015":[{"kind":"yesno","text":"Is what the message claims about which fan true for this case? Message: \"LED panel sensor fault - check the thermistor connection\"","field":"claim_is_correct"},{"kind":"value","text":"Airflow at the panel inlet, if an anemometer is fitted (skip if not)","field":"airflow","unit":"m/s","type":"float"},{"kind":"do","text":"Restore normal cooling, then press Done."}],"DVT-SAF-016":[{"kind":"do","text":"With the unit de-energised, open the right panel at led_string_open. Re-energise and press Done."},{"kind":"yesno","text":"Is the right string confirmed open or its driver unpowered on the DMM / clamp?","field":"panel_confirmed_dark"},{"kind":"do","text":"Restore the right connection, acknowledge the alarm, then press Done - the runner will start a cure and ask you to open it again."},{"kind":"do","text":"Open the right connection NOW, then press Done."},{"kind":"do","text":"Restore the right connection and press Done."}],"DVT-GAS-007":[{"kind":"value","text":"N2 flow from the flow meter","field":"n2_flow","unit":"L/min","type":"float"},{"kind":"value","text":"Chamber volume","field":"chamber_volume","unit":"L","type":"float"},{"kind":"value","text":"Analyser reading in air (span check)","field":"o2_reading_air","unit":"%","type":"float"},{"kind":"value","text":"Configured nitrogen purge duration on this machine","field":"program_purge_time_s","unit":"s","type":"float"},{"kind":"do","text":"Chamber closed, both O2 probes in place. Press Done and the runner opens the valve."},{"kind":"do","text":"Press Now the moment the CENTRE probe first reads O2 at or below 4.8 %."},{"kind":"do","text":"Press Now the moment the CORNER probe first reads O2 at or below 4.8 %."},{"kind":"value","text":"Lowest O2 reached during the purge","field":"o2_min_during_purge","unit":"%","type":"float"},{"kind":"do","text":"Press Now the moment the CENTRE probe rises back above 4.8 % (or after 60 minutes, whichever comes first)."},{"kind":"value","text":"O2 at the end of the hold","field":"o2_at_hold_end","unit":"%","type":"float"},{"kind":"value","text":"Longest cure that runs after a purge on this machine (sum of the UV steps)","field":"longest_cure_after_purge_s","unit":"s","type":"float"}],"DVT-GAS-001":[{"kind":"do","text":"Set the nitrogen regulator to about 4 bar (above the 3 bar limit). Keep the nitrogen valve closed. Then press Done."},{"kind":"yesno","text":"On the machine screen, try to switch the nitrogen on. Does it stay off (refused)?","field":"ui_refused"},{"kind":"do","text":"Lower the regulator to the normal working pressure (between 1 and 3 bar) and acknowledge the alarm on the screen if it is shown. Then press Done."},{"kind":"do","text":"Nitrogen is flowing. Raise the regulator to about 4 bar NOW, then press Done."},{"kind":"yesno","text":"Did the flow meter drop to zero?","field":"flow_stopped_on_rise"},{"kind":"do","text":"Lower the regulator back to the normal pressure and acknowledge the alarm on the screen. Then press Done."}],"DVT-GAS-002":[{"kind":"do","text":"Disconnect the nitrogen line (the line pressure must be below 0.5 bar), then press Done."},{"kind":"value","text":"What did the screen say?","field":"message_text","type":"string"}],"DVT-GAS-003":[{"kind":"do","text":"Charge the nitrogen line to about 4 bar (the valve stays closed), then close the shut-off valve at the supply so the line is isolated. Press Done."},{"kind":"yesno","text":"If the pressure dropped: bubble-test every fitting from the inlet to the valve. Did you find a leak?","field":"leak_found"},{"kind":"value","text":"Where does it leak?","field":"leak_location","type":"string"},{"kind":"do","text":"Vent the line and return the supply to the normal working pressure (1 to 3 bar). Press Done."}],"DVT-GAS-004":[{"kind":"value","text":"Chamber O2 at the moment the job reported complete","field":"o2_at_job_complete","unit":"%","type":"float"},{"kind":"do","text":"Press Now the moment the chamber O2 first reaches 19.5 %."},{"kind":"yesno","text":"Was the door released before the chamber O2 reached 19.5 %?","field":"door_released_before_safe"},{"kind":"value","text":"O2 at the moment the door was opened","field":"o2_at_door_opening","unit":"%","type":"float"}],"DVT-GAS-005":[{"kind":"value","text":"Room volume","field":"room_volume","unit":"m3","type":"float"},{"kind":"value","text":"Ventilation state","field":"ventilation_state","type":"string"},{"kind":"value","text":"Reference: O2 at the breathing zone now, before any nitrogen is released","field":"o2_reference","unit":"%","type":"float"},{"kind":"do","text":"Press Now at the moment the breathing-zone O2 reaches its minimum."},{"kind":"value","text":"Minimum O2 in the breathing zone","field":"o2_min_breathing_zone","unit":"%","type":"float"},{"kind":"value","text":"N2 released over the two programs","field":"n2_released","unit":"L","type":"float"},{"kind":"value","text":"O2 sixty minutes after the last purge","field":"o2_after_60min","unit":"%","type":"float"}],"DVT-GAS-006":[{"kind":"do","text":"Block the tube between the nitrogen valve and the chamber (clamp or plug). Keep the supply at the normal working pressure (1 to 3 bar). Press Done."},{"kind":"do","text":"Remove the block and acknowledge the alarm on the screen. Press Done."}],"DVT-NFC-001":[{"kind":"value","text":"Serial printed on the tag of the build head you are about to insert","field":"bh_serial_expected","type":"string"},{"kind":"do","text":"Insert the build head to its stop, close the door, then press Done."},{"kind":"yesno","text":"Does the screen show the build head identity (or the message for a missing / unknown tag)?","field":"operator_shown_identity"},{"kind":"value","text":"What does the screen say?","field":"message_text","type":"string"},{"kind":"do","text":"Remove the build head, then press Done."}],"DVT-ENV-001":[{"kind":"do","text":"Install the data logger and the indicators, record their positions, close the crate and ship. Press Done when the unit is back and unpacked."},{"kind":"value","text":"Route","field":"route","type":"string"},{"kind":"value","text":"Distance","field":"distance_km","unit":"km","type":"float"},{"kind":"value","text":"Transit days","field":"transit_days","unit":"days","type":"float"},{"kind":"yesno","text":"Did the impact indicator trigger?","field":"impact_indicator_triggered"},{"kind":"yesno","text":"Did the tilt indicator trigger?","field":"tilt_indicator_triggered"},{"kind":"yesno","text":"Is the crate damaged?","field":"crate_damage"},{"kind":"yesno","text":"Is any glass broken?","field":"glass_broken"},{"kind":"yesno","text":"Is any glass cracked or chipped?","field":"glass_cracked_or_chipped"},{"kind":"value","text":"How many fasteners are loose?","field":"loose_fasteners","type":"int"},{"kind":"value","text":"How many connectors are dislodged?","field":"connector_dislodged","type":"int"},{"kind":"value","text":"Visible damage (write none if there is none)","field":"visible_damage","type":"string"},{"kind":"value","text":"Peak acceleration, X","field":"peak_g_x","unit":"g","type":"float"},{"kind":"value","text":"Peak acceleration, Y","field":"peak_g_y","unit":"g","type":"float"},{"kind":"value","text":"Peak acceleration, Z","field":"peak_g_z","unit":"g","type":"float"}],"DVT-ELE-001":[{"kind":"value","text":"Test current used","field":"test_current","unit":"A","type":"float"},{"kind":"value","text":"Rating of the upstream protective device","field":"protective_device_rating","unit":"A","type":"float"},{"kind":"do","text":"Measure from the PE pin of the inlet to each listed accessible conductive part in turn, one minute per point."},{"kind":"value","text":"Part with the highest reading","field":"part_name","type":"string"},{"kind":"value","text":"Its measured resistance","field":"measured_resistance","unit":"ohm","type":"float"},{"kind":"value","text":"Where the highest resistance occurred","field":"worst_point","type":"string"},{"kind":"yesno","text":"Is the PE conductor uninterrupted by any switch or fuse?","field":"pe_uninterrupted"}],"DVT-ELE-002":[{"kind":"do","text":"Short L and N together at the inlet and apply 500 Vdc between the shorted L+N and PE for 60 s."},{"kind":"value","text":"Insulation resistance L+N to PE","field":"insulation_resistance_lnpe","unit":"Mohm","type":"float"},{"kind":"value","text":"Ambient temperature","field":"ambient_temp","unit":"C","type":"float"},{"kind":"value","text":"Relative humidity","field":"ambient_rh","unit":"%","type":"float"}],"DVT-ELE-003":[{"kind":"value","text":"Test voltage","field":"test_voltage","unit":"V","type":"float"},{"kind":"value","text":"Waveform","field":"waveform","type":"enum","values":["ac","dc"]},{"kind":"value","text":"Dwell time","field":"dwell_time","unit":"s","type":"float"},{"kind":"value","text":"Trip current setting","field":"trip_current_setting","unit":"mA","type":"float"},{"kind":"value","text":"Clause these derive from","field":"clause_reference","type":"string"},{"kind":"do","text":"Apply between the shorted mains conductors and PE / accessible parts."},{"kind":"yesno","text":"Was there a breakdown?","field":"breakdown"},{"kind":"value","text":"Leakage current at the test voltage","field":"leakage_current_at_voltage","unit":"mA","type":"float"},{"kind":"value","text":"Additional insulation barrier tested","field":"barrier_name","type":"string"},{"kind":"yesno","text":"Did that barrier break down?","field":"barrier_breakdown"},{"kind":"value","text":"Insulation resistance after the hipot","field":"post_hipot_insulation_resistance","unit":"Mohm","type":"float"}],"DVT-ELE-004":[{"kind":"value","text":"Touch current in normal condition, worst polarity","field":"touch_current_normal_max","unit":"mA","type":"float"},{"kind":"value","text":"Touch current with PE open","field":"touch_current_pe_open","unit":"mA","type":"float"},{"kind":"value","text":"Load condition of the worst case","field":"load_condition","type":"enum","values":["idle","heater","cure","heater_and_cure"]},{"kind":"value","text":"Worst-case touch current","field":"touch_current_worst","unit":"mA","type":"float"}],"DVT-ELE-005":[{"kind":"value","text":"Selector position","field":"selector_position","type":"enum","values":["110V","220V"]},{"kind":"value","text":"Voltage measured at the inlet","field":"applied_voltage","unit":"V","type":"float"},{"kind":"value","text":"Input power in standby","field":"input_power_idle","unit":"W","type":"float"},{"kind":"value","text":"Input current, heat only","field":"input_current_heat","unit":"A","type":"float"},{"kind":"value","text":"Input power, heat only","field":"input_power_heat","unit":"W","type":"float"},{"kind":"value","text":"Power factor, heat only","field":"power_factor_heat","type":"float"},{"kind":"value","text":"Input current, cure only","field":"input_current_cure","unit":"A","type":"float"},{"kind":"value","text":"Input power, cure only","field":"input_power_cure","unit":"W","type":"float"},{"kind":"value","text":"Power factor, cure only","field":"power_factor_cure","type":"float"},{"kind":"value","text":"Worst-case input current, everything working","field":"input_current_all","unit":"A","type":"float"},{"kind":"value","text":"Worst-case input power","field":"input_power_all","unit":"W","type":"float"},{"kind":"value","text":"Power factor, everything working","field":"power_factor_all","type":"float"},{"kind":"do","text":"From cold, switch the unit on at least three times at the worst-case phase angle and capture the inrush."},{"kind":"value","text":"How many switch-ons were captured?","field":"inrush_switch_ons","type":"int"},{"kind":"value","text":"Worst peak inrush current","field":"inrush_peak","unit":"A","type":"float"},{"kind":"value","text":"Its duration","field":"inrush_duration","unit":"ms","type":"float"},{"kind":"value","text":"I2t of the worst switch-on","field":"i2t","unit":"A2s","type":"float"},{"kind":"yesno","text":"Is there margin against the inlet fuse rating?","field":"fuse_margin_ok"},{"kind":"yesno","text":"Does it pass a type B 16 A breaker characteristic?","field":"breaker_type_b_ok"},{"kind":"yesno","text":"Does it pass a type C 16 A breaker characteristic?","field":"breaker_type_c_ok"},{"kind":"yesno","text":"Do the whole-machine current and power agree with the rating label?","field":"label_agreement"}]};   // @sim-prompts
  function detailOf(test) {
    const clean = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
    const steps = test.procedure_steps || [];
    const bench = steps.some((s) => s.tool === 'bench');
    const sc = SCRIPTS[test.test_id];
    return {
      purpose: clean(test.purpose),
      rationale: clean(test.sample_rationale),
      safetyPlan: (test.safety_plan || []).map(clean),
      equipment: (test.equipment || []).map((e) => clean(e.label || e.name)),
      preconditions: (test.preconditions || []).map(clean),
      dependencies: (test.dependencies || []).slice(),
      steps: steps.map((s) => clean(s.step)),
      criteria: clean(test.pass_criteria),
      bench,
      kind: sc && sc.kind ? sc.kind : '',
      note: bench ? BENCH_INTRO : sc && sc.intro ? clean(sc.intro[0]) : '',
      prompts: SIM_PROMPTS[test.test_id] || [],
    };
  }

  return { attach, has, script, card, stepNote, click, start, stop, ackAct, fromTrace, bare, missingFields, detailOf, BENCH_INTRO, version: VERSION, SCRIPTS, TRACE, P, L, mmss,
           _host: () => H, _state: (tid) => STATE[tid], _Ctx: Ctx, _tcRead: tcRead };
})();

// ============================================================================
// The test scripts. One per DVT test: what the runner does on the machine and
// which value comes from where. A script only stops for the operator where the
// catalog asks for something no API can do.
// ============================================================================

(function () {
  const A = window.DVT_AUTO, S = A.SCRIPTS, P = A.P;
  const def = (tid, o) => { S[tid] = o; };
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);
  const r1 = (v) => (v === null || v === undefined ? null : Math.round(v * 10) / 10);
  /** The body thermocouple for a log line - a missing reading says so instead of "null" (user, 2026-10-28). */
  const bodyTxt = (v) => (v === null || v === undefined || !isFinite(v) ? 'body: TC-08 CH1 not connected' : `body ${r1(v)} °C`);
  /** The heater as the machine reports it in this sample (user, 2026-10-28: the log must show it). */
  const heatTxt = (s) => (!s ? '' : ` · heater ${s.isHeating || num(s.heaterPwm) > 0 ? 'ON' + (num(s.heaterPwm) !== null ? ' ' + Math.round(num(s.heaterPwm)) + '%' : '') : 'off'}`);
  const r2 = (v) => (v === null || v === undefined ? null : Math.round(v * 100) / 100);
  const stamp = () => new Date().toISOString();
  const mmss_ = A.mmss;
  const H_base = () => A._host().base();
  const H_results = () => A._host().results();

  // Columns of the watch() trace: [t, chamber, heaterPwm, heaterOut, uvOn, R, L, Back, Door, tc08, alerts]
  const C = { T: 0, CHAMBER: 1, PWM: 2, HEATER: 3, UV: 4, R: 5, L: 6, BACK: 7, DOOR: 8, TC: 9, ALERTS: 10, CH2: 11 };

  /**
   * The chamber thermocouple grid (DVT-THM-001 / -003, user 2026-11-09): 2 x 2 x 4, levels Z1 (top) to Z4
   * (bottom), in each level 1 = back left, 2 = front left, 3 = back right, 4 = front right. Both TC-08s sit on
   * the MACHINE's USB; the firmware reports them in /api/dev/picolog/status units[] by serial. The 0031 unit
   * holds the upper eight (CH1-4 = Z1, CH5-8 = Z2), the 114 unit the bottom eight (CH1-4 = Z3, CH5-8 = Z4).
   */
  const GRID_LOGGERS = [{ match: '0031', firstLevel: 1 }, { match: '114', firstLevel: 3 }];
  const GRID_NAMES = [];
  for (let z = 1; z <= 4; z++) for (let q = 1; q <= 4; q++) GRID_NAMES.push(`Z${z}-${q}`);
  const GRID_PLACES = { 1: 'back left', 2: 'front left', 3: 'back right', 4: 'front right' };
  const gridPlace = (name) => { const m = /^Z(\d)-(\d)$/.exec(name || ''); return m ? `level ${m[1]} of 4 from the top, ${GRID_PLACES[m[2]]}` : ''; };

  /** The 16 grid readings in GRID_NAMES order (null = that thermocouple open), or null when a logger is missing. */
  function gridRead(p) {
    const units = p && p.connected && Array.isArray(p.units) ? p.units : [];
    const out = new Array(16).fill(null);
    for (const g of GRID_LOGGERS) {
      const u = units.find((x) => String(x.serial || '').includes(g.match));
      if (!u || !Array.isArray(u.channels)) return null;
      for (let i = 0; i < 8; i++) {
        const v = num(u.channels[i]);
        out[(g.firstLevel - 1) * 4 + i] = v === null || v < -25 || v > 400 ? null : v;
      }
    }
    return out;
  }

  /** Which loggers / thermocouples are missing, in words, or '' when all 16 read. */
  function gridMissing(p) {
    const units = p && p.connected && Array.isArray(p.units) ? p.units : [];
    const lost = GRID_LOGGERS.filter((g) => !units.some((x) => String(x.serial || '').includes(g.match))).map((g) => `TC-08 ${g.match}`);
    if (lost.length) return `${lost.join(' and ')} not seen on the machine's USB`;
    const g = gridRead(p);
    const open = GRID_NAMES.filter((n, i) => g[i] === null);
    return open.length ? `no reading from ${open.join(', ')}` : '';
  }

  /**
   * Spatial uniformity over a window of grid rows ([t, 16 values]): each thermocouple's mean over the window,
   * then the peak-to-peak and the sample standard deviation of those 16 means, and the hottest / coldest place.
   * Means, not single samples, so one noisy second does not set the result. Null when a position has no data.
   */
  function gridUniformity(rows, from, to) {
    const win = rows.filter((r) => r[0] >= from && r[0] <= to);
    const means = GRID_NAMES.map((n, i) => {
      const v = win.map((r) => r[i + 1]).filter((x) => x !== null);
      return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    });
    if (!win.length || means.some((m) => m === null)) return null;
    const hi = Math.max(...means), lo = Math.min(...means);
    const avg = means.reduce((a, b) => a + b, 0) / means.length;
    const sd = Math.sqrt(means.reduce((a, b) => a + (b - avg) ** 2, 0) / (means.length - 1));
    return { pp: hi - lo, sd, mean: avg, means, samples: win.length,
             hottest: GRID_NAMES[means.indexOf(hi)], coldest: GRID_NAMES[means.indexOf(lo)] };
  }
  const PANEL = { right: C.R, left: C.L, back: C.BACK, door: C.DOOR };
  /** A trace row's reference temperature: the CH2 reference thermocouple, else CH1. */
  const refOf = (r) => (r[C.CH2] !== null && r[C.CH2] !== undefined ? r[C.CH2] : r[C.TC]);   // live display only
  /**
   * The reference column of a whole trace: CH2 if it gave even one reading, otherwise CH1. Never mixed row by
   * row - a single CH2 gap would drop in a heater-body value (174 C was recorded as the chamber at 3 min that way).
   */
  const refCol = (rows) => (rows.some((r) => typeof r[C.CH2] === 'number') ? C.CH2 : C.TC);
  /** The value in `col` from the row nearest to `sec` that has one. */
  const nearestAt = (rows, col, sec) => {
    let best = null;
    for (const r of rows) if (typeof r[col] === 'number' && (best === null || Math.abs(r[C.T] - sec) < Math.abs(best[C.T] - sec))) best = r;
    return best ? best[col] : null;
  };

  /** "Press Now the moment X happens" - the tool keeps the time, the operator keeps watching. */
  async function mark(c, en, hb) {
    const ok = await c.ask(en, hb);
    return { ok: ok === true, sec: c.sec };
  }

  /** Hottest of the four LED panels in a trace row set. */
  function hottestPanel(rows) {
    let best = null;
    for (const k of Object.keys(PANEL)) {
      const v = P.maxOf(rows, PANEL[k]);
      if (v !== null && (best === null || v > best.temp)) best = { panel: k, temp: v };
    }
    return best;
  }

  /** The machine's own view of a fan: duty, rpm, expected, health. */
  function fanOf(s, fan) { return ((s && s.fanHealth) || {})[fan] || null; }

  /** A one-step cure program the runner can start over /api/recipe/start. */
  function program(name, steps) {
    return { material: { id: 'dvt-' + name, name: 'DVT ' + name, steps } };
  }

  // ==========================================================================
  // SAF - electrical and heater safety
  // ==========================================================================

  def('DVT-SAF-018', {
    kind: 'instrumented', minutes: 25, autoRecord: false,
    intro: ['The runner commands HEAT to 80 C and logs the chamber and the heater body (TC-08 on the machine) for 10 minutes or until the fuse opens. It reads the temperature rise, the moment the heater body turns from rising to falling - the fuse opening - and the time to it. It asks you only for the clamp-meter current and for what you see when you open the unit.',
            'הרנר מפעיל חימום ל-80 מעלות ורושם את התא ואת גוף ההיטר (TC-08 במכונה) במשך 10 דקות או עד שהנתיך נפתח. הוא מודד את העלייה בטמפרטורה, את הרגע שבו גוף ההיטר עובר מעלייה לירידה - פתיחת הנתיך - ואת הזמן עד אליו. הוא שואל אותך רק את קריאת מלקחי הזרם ומה אתה רואה כשאתה פותח את היחידה.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 5, 'confirm the rig', 'אישור המערך');
      await c.ask('Selector at 110 V, mains at 230 V, current probe around the heater branch conductor, TC-08 CH1 bonded to the heater body. Press Done when the rig is as the catalog describes.',
                  'הבורר על 110 וולט, הרשת על 230 וולט, מלקחי זרם סביב מוליך ענף ההיטר, TC-08 ערוץ 1 מולחם לגוף ההיטר. לחץ "בוצע" כשהמערך מוכן.');

      c.stage(2, 5, 'HEAT to 80 C, logging', 'חימום ל-80 מעלות, רושם');
      const h = await P.heatRun(c, { target: 80, sec: 600, tc: true, hz: 2 });
      c.trace('heat', h.rows);
      c.put('chamber_temp_rise', h.rise);
      if (h.bodyTurn.turned) {
        c.put('time_to_fuse_open', h.bodyTurn.at);
        c.put('fuse_opened', true);
        c.log('info', `heater body turned at ${h.bodyTurn.at} s, peak ${h.bodyTurn.peak} C`,
                      `גוף ההיטר התהפך ב-${h.bodyTurn.at} שניות, שיא ${h.bodyTurn.peak} מעלות`);
      }
      P.putAlarm(c, { raised: h.alarmAt !== null, code: h.alarmCode, text: h.alarmText });

      c.stage(3, 5, 'clamp reading', 'קריאת מלקחיים');
      await c.value('heater_branch_peak_current', 'Peak current the clamp meter recorded on the heater branch',
                    'זרם השיא שמלקחי הזרם רשמו בענף ההיטר');
      if (!c.known('fuse_opened')) await c.yesno('fuse_opened', 'Did a fuse open?', 'האם נתיך נפתח?');
      await c.value('which_fuse_opened', 'Which fuse opened?', 'איזה נתיך נפתח?');
      if (!c.known('time_to_fuse_open'))
        await c.value('time_to_fuse_open', 'Time from energising to the fuse opening', 'הזמן מההפעלה עד פתיחת הנתיך');

      c.stage(4, 5, 'inspection', 'בדיקה ויזואלית');
      await c.ask('De-energise, isolate and let the unit cool, then open it and inspect.',
                  'נתק מהחשמל, בודד, תן ליחידה להתקרר, ואז פתח אותה ובדוק.');
      await c.yesno('smoke_or_fire', 'Was there smoke or fire?', 'האם היה עשן או אש?');
      await c.yesno('enclosure_damage', 'Is the enclosure damaged?', 'האם יש נזק למארז?');
      await c.yesno('heater_element_continuity', 'Does the heater element still have continuity?', 'האם עדיין יש רציפות באלמנט החימום?');
      await c.value('wiring_insulation_condition', 'Condition of the wiring insulation', 'מצב בידוד החיווט');
      // the end of the test: the person confirms with a meter that the fuse really blew (user, 2026-10-25)
      await c.yesno('fuse_blown_confirmed', 'Take the heater branch fuse out and check it with a meter: did it really blow (open circuit)?',
                    'הוצא את נתיך ענף גוף החימום ובדוק אותו במודד: האם הוא באמת נשרף (נתק)?');

      c.stage(5, 5, 'functional check', 'בדיקה פונקציונלית');
      await c.ask('Replace the opened fuse, set the selector correctly and power the unit up again. Press Done when it is running.',
                  'החלף את הנתיך שנפתח, כוון את הבורר נכון והדלק את היחידה מחדש. לחץ "בוצע" כשהיא פועלת.');
      await P.selfCheck(c);
    },
  });

  def('DVT-SAF-019', {
    kind: 'instrumented', minutes: 20, autoRecord: false, needs: 'none',
    intro: ['The unit is on a short-circuit rig for this test, so the runner cannot drive it. It walks the measurements in order, keeps each one with its timestamp, and runs the full functional check on the machine at the end.',
            'היחידה נמצאת על מערך קצר בבדיקה הזו, ולכן הרנר לא יכול להפעיל אותה. הוא מוביל את המדידות לפי הסדר, שומר כל אחת עם חותמת זמן, ומריץ בסוף בדיקה פונקציונלית מלאה על המכונה.'],
    async run(c) {
      c.stage(1, 4, 'supply measurements', 'מדידות הזנה');
      await c.value('prospective_scc', 'Prospective short-circuit current of the supply', 'זרם הקצר הצפוי של ההזנה');
      await c.value('pe_resistance', 'PE resistance measured at the inlet', 'התנגדות ההארקה שנמדדה בכניסה');
      c.stage(2, 4, 'the fault', 'התקלה');
      await c.ask('Energise the unit, confirm normal standby, then apply the short remotely and capture the current waveform.',
                  'הפעל את היחידה, ודא מצב המתנה תקין, ואז הפעל את הקצר מרחוק וקלוט את צורת גל הזרם.');
      await c.value('peak_fault_current', 'Peak fault current from the waveform', 'זרם התקלה המרבי מצורת הגל');
      await c.value('fuse_clearing_time', 'Fuse clearing time from the waveform', 'זמן ניתוק הנתיך מצורת הגל');
      c.stage(3, 4, 'inspection', 'בדיקה ויזואלית');
      await c.yesno('fuse_opened', 'Did the inlet fuse open?', 'האם נתיך הכניסה נפתח?');
      await c.yesno('arc_damage', 'Is there arc damage?', 'האם יש נזק מקשת חשמלית?');
      await c.yesno('terminal_damage', 'Are the terminals damaged?', 'האם יש נזק למהדקים?');
      await c.yesno('inlet_filter_functional', 'Is the inlet filter still functional?', 'האם מסנן הכניסה עדיין תקין?');
      c.stage(4, 4, 'after the event', 'אחרי האירוע');
      await c.value('pe_continuity_post', 'PE continuity after the event', 'רציפות ההארקה אחרי האירוע');
      await c.value('insulation_resistance_post', 'Insulation resistance after the event', 'התנגדות הבידוד אחרי האירוע');
    },
  });

  def('DVT-SAF-001', {
    kind: 'guided', minutes: 25,
    intro: ['The runner heats the chamber, waits until the heater body is rising, then asks you to open the circulation fan supply - the one thing it cannot do over the network. From that instant it measures everything itself: the time to the fan-failure alarm, the instant the heater body turns from rising to falling, the peak, the alarm text and code, and whether the alarm clears on its own after you reconnect.',
            'הרנר מחמם את התא, ממתין עד שגוף ההיטר עולה, ואז מבקש ממך לנתק את הזנת מאוורר הסחרור - הדבר היחיד שהוא לא יכול לעשות ברשת. מהרגע הזה הוא מודד הכול בעצמו: הזמן עד התראת כשל המאוורר, הרגע שבו גוף ההיטר עובר מעלייה לירידה, השיא, נוסח ההתראה והקוד שלה, והאם ההתראה מתנקה מעצמה אחרי שאתה מחבר בחזרה.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 5, 'heating until the body rises', 'מחמם עד שהגוף עולה');
      const s0 = await c.state();
      const before = s0.alerts || [];
      await c.post('/api/cure/heat?target=80');
      const warm = [];
      await c.watch({ sec: 300, hz: 1, tc: true, into: warm,
        on: (s, at) => {
          c.say(`warming · ${r1(num(s.chamberTemp))} °C · ${bodyTxt(P.maxOf(warm, C.TC))}${heatTxt(s)}`,
                `מתחמם · ${r1(num(s.chamberTemp))} °C · גוף ${r1(P.maxOf(warm, C.TC))} °C`);
          const rate = P.rate(warm, C.TC, 60);
          return at > 60 && rate !== null && rate > 2 ? 'stop' : undefined;
        } });
      c.trace('warm_up', warm);

      c.stage(2, 5, 'disconnect the fan', 'נתק את המאוורר');
      const ok = await c.ask('Open the circulation fan supply NOW, then press Done. The runner times everything from that press.',
                             'נתק עכשיו את הזנת מאוורר הסחרור, ואז לחץ "בוצע". הרנר מודד הכול מרגע הלחיצה.');
      if (ok !== true) throw new Error(A.L('the fan was never disconnected', 'המאוורר לא נותק'));
      const t0 = c.sec;
      c.put('disconnect_timestamp', stamp());
      c.put('heater_temp_at_disconnect', r2(await P.tc(c)));

      c.stage(3, 5, 'watching the response', 'צופה בתגובה');
      const rows = [];
      let alarmAt = null, alarmCode = null;
      await c.watch({ sec: 300, hz: 2, tc: true, into: rows,
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (alarmAt === null && fresh.length) { alarmAt = at; alarmCode = fresh[0]; }
          c.say(`after the disconnect · ${at} s${alarmCode ? ' · alarm ' + alarmCode : ''} · ${bodyTxt(rows.length ? rows[rows.length - 1][C.TC] : null)}${heatTxt(s)}`,
                `אחרי הניתוק · ${at} שניות${alarmCode ? ' · התראה ' + alarmCode : ''} · גוף ${r1(rows.length ? rows[rows.length - 1][C.TC] : null)} °C`);
          const turned = P.turn(rows, C.TC);
          return alarmAt !== null && turned.turned && at > alarmAt + 20 ? 'stop' : undefined;
        } });
      c.trace('after_disconnect', rows);
      const turn = P.turn(rows, C.TC);
      const sNow = await c.state();
      c.puts({
        detection_time: alarmAt,
        heater_body_drop_observed: turn.turned,
        heater_off_time: turn.turned ? turn.at : null,
        heater_temp_peak: r2(turn.peak),
      });
      P.putAlarm(c, { raised: alarmAt !== null, code: alarmCode, text: alarmCode === null ? '' : P.detail(sNow, alarmCode) });
      c.put('alarm_identifies_fan', P.names(alarmCode === null ? '' : P.detail(sNow, alarmCode),
        ['fan', 'מאוורר', 'circulation', 'סחרור', 'heater fan', 'FAN_HEATER', 'chamber']));

      c.stage(4, 5, 'reconnect', 'חיבור מחדש');
      await c.tryPost('/api/chamber/stop');
      // the machine sees the fan come back itself (user, 2026-11-12): no "Done" - the step ends when FAN_HEATER turns
      // again. The fan must be commanded to see its tach, so a fan the trip left at 0 % is set to 30 % (the cooldown duty)
      const s4 = await c.state().catch(() => null);
      if (!s4 || !((s4.fanDutyEach || {}).FAN_HEATER > 0)) await c.tryPost('/api/fans/chamber_heating?speed=30');
      const spinning = (s) => (P.rpm(s, 'FAN_HEATER') || 0) >= 300;
      c.act('RECONNECT the circulation fan supply - the machine goes on when it sees the fan turning. Do NOT acknowledge the alarm on the screen',
            'חבר בחזרה את הזנת מאוורר הסחרור - המכונה ממשיכה כשהיא רואה את המאוורר מסתובב. אל תאשר את ההתראה על המסך', 300, { ack: false });
      const back = await c.until(spinning, { sec: 300, poll: 1 });
      c.actDone();
      if (!back.ok) {
        // the tach never came back (a fan that is not driven, or no tach line): fall back to the person's word
        await c.ask('The machine did not see the circulation fan turn. Reconnect its supply, then press Done. Do NOT acknowledge the alarm on the screen.',
                    'המכונה לא ראתה את מאוורר הסחרור מסתובב. חבר בחזרה את ההזנה שלו, ואז לחץ "בוצע". אל תאשר את ההתראה על המסך.');
      }
      c.put('fan_reconnect_seen', back.ok);
      c.note(back.ok ? `the machine saw FAN_HEATER turn again at ${r1(P.rpm(back.s, 'FAN_HEATER'))} RPM` : 'the fan reconnect was confirmed by Done (no tach)');
      const still = await c.until((s) => !(s.alerts || []).includes(alarmCode), { sec: 60, poll: 2 });
      c.put('recovery_requires_ack', !still.ok);

      c.stage(5, 5, 'back to rest', 'חזרה למנוחה');
      await P.allOff(c);
    },
  });

  // DVT-SAF-002 is run by the machine-side DVT bench (catalog tool: bench, port 3002), not from here:
  // the firmware's own clock times the heater-body turn, so there is one path and no second card.

  // The four LED thermistors as the machine names them in /api/state ledTemps and in its alarm text.
  const LED_POSITIONS = [
    { key: 'right', he: 'ימין' }, { key: 'left', he: 'שמאל' }, { key: 'back', he: 'אחור' }, { key: 'door', he: 'דלת' },
  ];
  /** True when the machine reports no reading for that thermistor: ledTemps[key] present but null. */
  const thermistorGone = (s, key) => {
    const lt = (s && s.ledTemps) || {};
    return Object.prototype.hasOwnProperty.call(lt, key) ? lt[key] === null : null;
  };

  def('DVT-SAF-004', {
    kind: 'guided', minutes: 40,
    intro: ['One run walks all four LED thermistors in turn - right, left, back, door. For each one: you disconnect that sensor only, the runner waits for the machine to report it missing (and checks the other three still read), tries to start a cure, which must be refused, and reads the alarm, which must name that sensor. Then you reconnect, the LEDs go to maximum, you pull the same connector again and the StarBright times the LEDs going dark. Before the next sensor the runner waits for the alarm to clear, so one sensor\'s alarm is never credited to the next.',
            'ריצה אחת עוברת על ארבעת תרמיסטורי ה-LED בתורם - ימין, שמאל, אחור, דלת. עבור כל אחד: אתה מנתק רק את החיישן הזה, הרנר ממתין שהמכונה תדווח שהוא חסר (ובודק ששלושת האחרים עדיין קוראים), מנסה להתחיל קיור שחייב להידחות, וקורא את האזעקה שחייבת לזהות את החיישן הזה. אחר כך אתה מחבר בחזרה, הלדים עולים למקסימום, אתה שולף שוב את אותו מחבר וה-StarBright מודד את כיבוי הלדים. לפני החיישן הבא הרנר ממתין שהאזעקה תתנקה, כך שאזעקה של חיישן אחד לא תיזקף לבא אחריו.'],
    async run(c) {
      await P.idle(c);
      const m = await c.get('/api/dvt/meter');
      if (!m.present) throw new Error(m.message || A.L('no StarBright on the machine', 'אין StarBright במכונה'));
      const per = [];                                         // one entry per sensor - the run's record of each
      const n = LED_POSITIONS.length;
      for (let i = 0; i < n; i++) {
        const pos = LED_POSITIONS[i];
        const posL = A.L(pos.key, pos.he);
        const res = { position: pos.key };

        // a clean start for this sensor: no alarm left over from the previous one
        c.stage(i * 3 + 1, n * 3, `${pos.key}: wait for a clean machine`, `${pos.he}: ממתין למכונה נקייה`);
        let clean = await c.until((s) => (s.alerts || []).length === 0 && LED_POSITIONS.every((q) => thermistorGone(s, q.key) !== true), { sec: 60, poll: 1 });
        if (!clean.ok) {
          await c.ask('An alarm is still active from the previous sensor, or a thermistor is still disconnected. Reconnect everything and acknowledge the alarm on the machine\'s screen, then press Done.',
                      'אזעקה מהחיישן הקודם עדיין פעילה, או שתרמיסטור עדיין מנותק. חבר הכול ואשר את האזעקה על מסך המכונה, ואז לחץ "בוצע".');
          clean = await c.until((s) => (s.alerts || []).length === 0 && LED_POSITIONS.every((q) => thermistorGone(s, q.key) !== true), { sec: 60, poll: 1 });
          if (!clean.ok) throw new Error(A.L(`the machine is not clean before the ${pos.key} sensor - an alarm or a missing thermistor remains`,
                                             `המכונה לא נקייה לפני חיישן ה${pos.he} - נשארה אזעקה או תרמיסטור מנותק`));
        }
        const before = (clean.s && clean.s.alerts) || [];

        // disconnect THIS sensor; the machine must see it gone and the other three still there
        await c.ask(`Disconnect the ${pos.key.toUpperCase()} LED thermistor only (open circuit), then press Done.`,
                    `נתק רק את תרמיסטור ה-LED של ה${pos.he} (מעגל פתוח), ואז לחץ "בוצע".`);
        const seen = await c.until((s) => thermistorGone(s, pos.key) === true, { sec: 90, poll: 0.5 });
        res.seen_missing = seen.ok;
        res.others_ok = seen.ok ? LED_POSITIONS.filter((q) => q.key !== pos.key).every((q) => thermistorGone(seen.s, q.key) !== true) : null;

        // a cure must be refused with this sensor out
        c.stage(i * 3 + 2, n * 3, `${pos.key}: a cure must be refused`, `${pos.he}: הקיור חייב להידחות`);
        const r = await c.postJson('/api/recipe/start', program('saf-007-' + pos.key, [{ step: 1, process: 'Cure', time: 1, uvIntensity: 30 }]));
        let started = r.ok === true;
        if (started) { started = (await c.until((s) => s.uvOn === true, { sec: 20, poll: 0.5 })).ok; await P.allOff(c); }
        res.cure_refused = !started;

        // its own alarm, naming this sensor
        const a = await P.alarm(c, before, { sec: 90 });
        res.alarm = a.raised; res.code = a.code === null ? null : String(a.code); res.text = a.text || '';
        res.names_sensor = a.raised && P.names(a.text, [pos.key, pos.he, 'TEMP_' + pos.key.toUpperCase()]);
        c.say(`${pos.key}: ${res.cure_refused ? 'cure refused' : 'CURE STARTED'} · alarm ${res.code || '-'}${res.names_sensor ? ' names it' : ' does NOT name it'}`,
              `${pos.he}: ${res.cure_refused ? 'הקיור נדחה' : 'הקיור התחיל!'} · אזעקה ${res.code || '-'}${res.names_sensor ? ' מזהה אותו' : ' לא מזהה אותו'}`);

        // LED off timing: reconnect, LEDs to maximum, pull the same connector, time the fall on the StarBright
        c.stage(i * 3 + 3, n * 3, `${pos.key}: LED off timing`, `${pos.he}: תזמון כיבוי הלדים`);
        await c.ask(`Reconnect the ${pos.key.toUpperCase()} thermistor and acknowledge the alarm on the screen, then press Done - the runner will light the LEDs and ask you to pull it again.`,
                    `חבר בחזרה את התרמיסטור של ה${pos.he} ואשר את האזעקה על המסך, ואז לחץ "בוצע" - הרנר ידליק את הלדים ויבקש ממך לנתק שוב.`);
        await c.until((s) => thermistorGone(s, pos.key) === false && (s.alerts || []).length === 0, { sec: 60, poll: 1 });
        await c.post('/api/uv?on=1&intensity=100&wavelength=405');
        const lit = await c.until((s) => s.uvOn === true, { sec: 30, poll: 0.5 });
        if (!lit.ok) {
          res.led_off_time = null; res.note = 'the LEDs did not come on for the timing - an alarm may still be active';
        } else {
          await c.sleep(15);
          const plateau = [];
          for (let k = 0; k < 8; k++) { const x = await c.get('/api/dvt/meter').catch(() => null); plateau.push(x ? num(x.reading_mw_cm2) : null); await c.sleep(0.25); }
          const level = Math.max(...plateau.filter((v) => v !== null));
          const pulled = await c.ask(`LEDs at maximum. Pull the ${pos.key.toUpperCase()} thermistor connector NOW, then press Done.`,
                                     `הלדים במקסימום. שלוף עכשיו את מחבר התרמיסטור של ה${pos.he}, ואז לחץ "בוצע".`);
          const t0 = c.sec; const fall = []; let offAt = null;
          while (c.sec - t0 < 30 && pulled === true) {
            const x = await c.get('/api/dvt/meter').catch(() => null);
            const v = x ? num(x.reading_mw_cm2) : null;
            fall.push([r2(c.sec - t0), v]);
            if (v !== null && level > 0 && v < level * 0.1) { offAt = r2(c.sec - t0); break; }
            await c.sleep(0.2);
          }
          res.plateau_mw_cm2 = r2(level); res.led_off_time = offAt; res.fall = fall;
        }
        await P.allOff(c);
        await c.ask(`Reconnect the ${pos.key.toUpperCase()} thermistor and acknowledge the alarm, then press Done.`,
                    `חבר בחזרה את התרמיסטור של ה${pos.he} ואשר את האזעקה, ואז לחץ "בוצע".`);
        per.push(res);
        c.trace('sensor_' + pos.key, res);
      }

      // one verdict for the four: every sensor must have passed on its own
      const all = (k) => per.length === n && per.every((x) => x[k] === true);
      const times = per.map((x) => x.led_off_time);
      c.puts({
        positions_tested: per.map((x) => x.position).join(', '),
        cure_start_inhibited: all('cure_refused'),
        alarm_raised: all('alarm'),
        alarm_identifies_sensor: all('names_sensor'),
        // one field per LED side: the code and the machine's own words for that sensor (user, 2026-10-01)
        ...Object.fromEntries(per.map((x) => ['error_' + x.position, x.code ? `${x.code} - ${x.text || ''}`.trim() : 'no alarm'])),
        led_off_time: times.every((v) => typeof v === 'number') ? Math.max(...times) : null,
      });
      const bad = per.filter((x) => !(x.cure_refused && x.alarm && x.names_sensor));
      c.note(bad.length ? `sensors that did not behave: ${bad.map((x) => x.position).join(', ')}` : 'all four sensors behaved: refused, alarmed, named');
    },
  });

  /** The four LED panels' temperatures from /api/state, as one line - shown live while the LEDs run. */
  function panelsLine(s, lang) {
    const lt = (s && s.ledTemps) || {};
    const he = { right: 'ימין', left: 'שמאל', back: 'אחור', door: 'דלת' };
    return ['right', 'left', 'back', 'door'].map((k) => `${lang === 'he' ? he[k] : k} ${lt[k] === null || lt[k] === undefined ? '—' : r1(lt[k])} °C`).join(' · ');
  }

  def('DVT-SAF-005', {
    kind: 'guided', minutes: 60,
    intro: ['One guided run over the four LED cooling fans - right, left, back, door. For each fan: you disconnect that fan only, the runner tries to start a cure (it must be refused) and reads the alarm (it must name that fan); you reconnect it (the runner acknowledges the alarm on the machine itself); the LEDs go to maximum, you pull the same fan again and the runner times the LEDs going off. Then on to the next fan, by itself. The four panel temperatures are shown live throughout.',
            'ריצה מודרכת אחת על ארבעת מאווררי קירור ה-LED - ימין, שמאל, אחור, דלת. לכל מאוורר: אתה מנתק רק אותו, הרנר מנסה להתחיל קיור (חייב להידחות) וקורא את האזעקה (חייבת לזהות את המאוורר הזה); אתה מחבר בחזרה (הרנר מאשר את האזעקה במכונה בעצמו); הלדים עולים למקסימום, אתה מנתק שוב את אותו מאוורר והרנר מודד מתי הלדים כבים. ואז הוא ממשיך לבד למאוורר הבא. ארבע טמפרטורות הפאנלים מוצגות בזמן אמת לאורך כל הריצה.'],
    async run(c) {
      await P.idle(c);
      c.put('failure_mode', 'disconnected');
      const per = [];
      const rows = [];                                        // one trace for the whole run, drawn live
      const n = LED_POSITIONS.length;
      const clean = (s) => (s.alerts || []).length === 0;
      // sCureBox 1.0.60+: the runner acknowledges the fan alarm itself (POST /api/fans/ack) - the operator only touches
      // fans. The machine keeps the latch of a fan that is driven and still failing, so this never hides a dead fan.
      const release = async (sec) => {
        await c.post('/api/fans/ack').catch(() => null);
        return c.until(clean, { sec: sec || 30, poll: 1 });
      };
      for (let i = 0; i < n; i++) {
        const pos = LED_POSITIONS[i];
        const FAN = 'FAN_' + pos.key.toUpperCase();
        const res = { position: pos.key };

        c.stage(i * 3 + 1, n * 3, `${pos.key} fan: wait for a clean machine`, `מאוורר ${pos.he}: ממתין למכונה נקייה`);
        let ok = await release(30);
        if (!ok.ok) {
          await c.ask('An alarm is still active. Make sure every LED fan is connected, then press Done.',
                      'אזעקה עדיין פעילה. ודא שכל מאווררי ה-LED מחוברים, ואז לחץ "בוצע".');
          ok = await release(60);
          if (!ok.ok) throw new Error(A.L(`an alarm is still active before the ${pos.key} fan`, `אזעקה עדיין פעילה לפני מאוורר ה${pos.he}`));
        }
        const before = (ok.s && ok.s.alerts) || [];

        await c.ask(`Disconnect the ${pos.key.toUpperCase()} LED fan only, then press Done.`,
                    `נתק רק את מאוורר ה-LED של ה${pos.he}, ואז לחץ "בוצע".`);
        const r = await c.postJson('/api/recipe/start', program('saf-008-' + pos.key, [{ step: 1, process: 'Cure', time: 2, uvIntensity: 100 }]));
        let started = r.ok === true;
        if (started) { started = (await c.until((s) => s.uvOn === true, { sec: 25, poll: 0.5 })).ok; await P.allOff(c); }
        res.refused = !started; res.refusal = r.ok === false ? (r.message || '') : '';
        const a = await P.alarm(c, before, { sec: 90 });
        res.alarm = a.raised; res.code = a.code === null ? null : String(a.code); res.text = a.text || res.refusal || '';
        res.names_fan = (a.raised || !!res.refusal) && P.names(res.text, [pos.key, pos.he, FAN]);
        c.say(`${pos.key} fan: ${res.refused ? 'cure refused' : 'CURE STARTED'} · alarm ${res.code || '-'}${res.names_fan ? ' names it' : ' does NOT name it'}`,
              `מאוורר ${pos.he}: ${res.refused ? 'הקיור נדחה' : 'הקיור התחיל!'} · אזעקה ${res.code || '-'}${res.names_fan ? ' מזהה אותו' : ' לא מזהה אותו'}`);

        // the same fan pulled while the LEDs run
        c.stage(i * 3 + 2, n * 3, `${pos.key} fan: pulled with the LEDs on`, `מאוורר ${pos.he}: ניתוק כשהלדים דולקים`);
        await c.ask(`Reconnect the ${pos.key.toUpperCase()} fan, then press Done - the LEDs will go to maximum.`,
                    `חבר בחזרה את מאוורר ה${pos.he}, ואז לחץ "בוצע" - הלדים יעלו למקסימום.`);
        await release(60);
        const uv = await c.post('/api/cure/uv-only?intensity=100&wavelength=405').catch((e) => ({ ok: false, message: String(e.message || e) }));
        const lit = await c.until((s) => s.uvOn === true, { sec: 60, poll: 0.5 });
        if (!lit.ok) {
          // say WHY: the machine's own answer and whatever it is alarming on, instead of a bare "did not light"
          const sNow = await c.state().catch(() => ({}));
          res.led_off_time = null;
          res.note = `LEDs did not light: ${uv && uv.message ? uv.message : 'no refusal message'}; alerts ${(sNow.alerts || []).join(',') || 'none'}`;
          c.note(`${pos.key}: ${res.note}`);
        } else {
          await c.watch({ sec: 30, hz: 1, into: rows, live: 'mid_job',
            on: (s) => c.say(`${pos.key} fan · LEDs at maximum · ${panelsLine(s, 'en')}`, `מאוורר ${pos.he} · לדים במקסימום · ${panelsLine(s, 'he')}`) });
          const pulled = await c.ask(`Pull the ${pos.key.toUpperCase()} fan connector NOW, then press Done.`,
                                     `שלוף עכשיו את מחבר מאוורר ה${pos.he}, ואז לחץ "בוצע".`);
          const t0 = c.sec; let offAt = null;
          await c.watch({ sec: 120, hz: 2, into: rows, live: 'mid_job',
            on: (s) => {
              if (offAt === null && !s.uvOn) offAt = r2(c.sec - t0);
              c.say(`${pos.key} fan pulled · UV ${s.uvOn ? 'on' : 'off'} · ${panelsLine(s, 'en')}`, `מאוורר ${pos.he} נותק · UV ${s.uvOn ? 'דולק' : 'כבוי'} · ${panelsLine(s, 'he')}`);
              return offAt !== null && c.sec - t0 > offAt + 10 ? 'stop' : undefined;
            } });
          res.led_off_time = pulled === true ? offAt : null;
        }
        await P.allOff(c);
        c.stage(i * 3 + 3, n * 3, `${pos.key} fan: restore`, `מאוורר ${pos.he}: החזרה`);
        await c.ask(`Reconnect the ${pos.key.toUpperCase()} fan, then press Done.`,
                    `חבר בחזרה את מאוורר ה${pos.he}, ואז לחץ "בוצע".`);
        await release(30);
        per.push(res);
        c.trace('fan_' + pos.key, res);
      }
      c.trace('saf008', rows);

      const all = (k) => per.length === n && per.every((x) => x[k] === true);
      const times = per.map((x) => x.led_off_time);
      const hot = hottestPanel(rows);
      c.puts({
        positions_tested: per.map((x) => x.position).join(', '),
        job_start_inhibited: all('refused'),
        alarm_raised: all('alarm'),
        alarm_identifies_correct_fan: all('names_fan'),
        ...Object.fromEntries(per.map((x) => ['error_' + x.position, x.code ? `${x.code} - ${x.text}`.trim() : (x.refusal ? `refused - ${x.refusal}` : 'no alarm')])),
        led_off_time_midjob: times.every((v) => typeof v === 'number') ? Math.max(...times) : null,
        max_led_temp: hot ? r2(hot.temp) : null,
      });
    },
  });

  def('DVT-SAF-006', {
    kind: 'guided', minutes: 20,
    intro: ['The runner proves a job cannot start with the chamber cooling fan failed, reads the alarm and checks the text names that fan, then injects the failure during an active cooling cycle and measures the response time and the chamber peak.',
            'הרנר מוכיח שעבודה לא יכולה להתחיל כשמאוורר קירור התא כשל, קורא את ההתראה ובודק שהנוסח מזהה את המאוורר הזה, ואז מזריק את הכשל במהלך מחזור קירור פעיל ומודד את זמן התגובה ואת שיא התא.'],
    async run(c) {
      c.put('failure_mode', 'disconnected');   // disconnection only, no blocked rotor (user, 2026-10-25)
      await P.idle(c);

      c.stage(1, 4, 'disconnect the fan', 'ניתוק המאוורר');
      await c.ask('Disconnect the chamber cooling fan, then press Done.',
                  'נתק את מאוורר קירור התא, ואז לחץ "בוצע".');
      const before = (await c.state()).alerts || [];

      c.stage(2, 4, 'a drying job must not start', 'עבודת ייבוש לא אמורה להתחיל');
      // the machine spin-tests the chamber cooling fan before every DRYING and COOLING step (sCureBox 1.0.63), not
      // before heating or UV - so the job tried here is a drying step; the refusal comes back in this response
      const r = await c.post('/api/cure/dry?target=40').catch((e) => ({ ok: false, message: String(e.message || e) }));
      // inhibited means the machine REFUSED the start. An accepted start is a job that started, whether or not the
      // heater was seen on within 25 s - r1 on the unit (2026-10-01) was accepted in 3 ms and still scored 'inhibited'
      const active = (s) => !!(s.recipe && ['running', 'paused', 'preflight'].includes(String(s.recipe.state || '').toLowerCase()));
      const seen = r.ok === true ? await c.until((s) => active(s) || s.isHeating === true || s.isCooling === true, { sec: 25, poll: 0.5 }) : { ok: false };
      // a refusal of the PROGRAM itself (bad step name, validation) says nothing about the fan: stop as an error
      if (r.ok !== true && !/\[\d{4}\]/.test(String(r.message || '')) && /invalid|could not be converted|validation/i.test(String(r.message || '')))
        throw new Error(A.L(`the machine rejected the test program itself, not because of the fan: ${r.message}`,
                            `המכונה דחתה את תוכנית הבדיקה עצמה, לא בגלל המאוורר: ${r.message}`));
      const started = r.ok === true || seen.ok;
      if (started) await P.allOff(c);
      c.trace('start_attempt', { accepted: r.ok === true, message: r.message || '', seen_running: seen.ok });
      c.put('job_start_inhibited', !started);
      const FAN_WORDS = ['cooling', 'קירור', 'intake', 'FAN_COOLING', 'chamber', 'תא'];
      const a0 = await P.alarm(c, before, { sec: 20 });
      // the refusal message is the alarm when the machine answers it in the start response ("[9003] Chamber cooling
      // fan not spinning: ... (FAN_COOLING) ...") - it need not also stay in the alert list
      const refusal = r.ok === true ? '' : String(r.message || '');
      const code = a0.raised ? a0.code : (/\[(\d{4})\]/.exec(refusal) || [])[1] || (r.code !== undefined ? r.code : null);
      const a = a0.raised ? a0 : { raised: !!refusal && code !== null, code: code === null ? null : Number(code), text: refusal };
      c.trace('start_alarm', { raised: a.raised, code: a.code, text: a.text, refusal });

      c.stage(3, 4, 'the failure during cooling', 'הכשל במהלך קירור');
      await c.ask('Reconnect the cooling fan and press Done - the runner will heat the chamber and start a cooling cycle, then ask you to disconnect the fan again.',
                  'חבר בחזרה את מאוורר הקירור ולחץ "בוצע" - הרנר יחמם את התא ויתחיל מחזור קירור, ואז יבקש ממך לנתק שוב את המאוורר.');
      // 50 C, not 60: the same cooling cycle (50 -> 30) for the fan failure, minutes sooner (user, 2026-10-01)
      await P.heatRun(c, { target: 50, sec: 900, untilTarget: true, tc: false, keepHot: true });
      await c.post('/api/cure/cool?target=30&mode=medium');
      const cooling = await c.until((s) => s.isCooling === true, { sec: 60, poll: 1 });
      if (!cooling.ok) throw new Error(A.L('the cooling cycle never started', 'מחזור הקירור לא התחיל'));
      const before2 = (await c.state()).alerts || [];
      let mid = null;                                         // the first alarm the cooling-stage failure raised
      const failed = await c.ask('Disconnect the cooling fan NOW, then press Done.', 'נתק עכשיו את מאוורר הקירור, ואז לחץ "בוצע".');
      const t0 = c.sec;
      const rows = [];
      let respAt = null;
      await c.watch({ sec: 300, hz: 2, into: rows,
        on: (s, at) => {
          const fresh = P.fresh(before2, s);
          if (mid === null && fresh.length) mid = { code: fresh[0], text: P.detail(s, fresh[0]), at: r2(c.sec - t0) };
          if (respAt === null && (fresh.length || !s.isCooling)) respAt = r2(c.sec - t0);
          c.say(`cooling · ${at} s · ${r1(num(s.chamberTemp))} °C${respAt !== null ? ' · responded at ' + respAt + ' s' : ''}`,
                `מקרר · ${at} שניות · ${r1(num(s.chamberTemp))} °C${respAt !== null ? ' · הגיב ב-' + respAt + ' שניות' : ''}`);
          return respAt !== null && at > 30 ? 'stop' : undefined;
        } });
      c.trace('cooling_failure', rows);
      if (failed === true) c.put('response_time', respAt);
      c.put('max_chamber_temp', r2(P.maxOf(rows, C.CHAMBER)));
      if (mid === null) {
        const a2 = await P.alarm(c, before2, { sec: 20 });
        if (a2.raised) mid = { code: a2.code, text: a2.text, at: null };
      }
      c.trace('cooling_alarm', mid || { code: null });
      // one verdict over both stages: the alarm of either stage counts, and its text must name the cooling fan
      const best = [mid, a.raised ? { code: a.code, text: a.text } : null]
        .filter(Boolean).sort((x, y) => Number(P.names(y.text, FAN_WORDS)) - Number(P.names(x.text, FAN_WORDS)))[0] || null;
      c.puts({
        alarm_raised: !!best,
        error_code: best && best.code !== null ? String(best.code) : null,
        alarm_text: best ? best.text : null,
        alarm_identifies_correct_fan: !!best && P.names(best.text, FAN_WORDS),
      });
      await P.allOff(c);

      c.stage(4, 4, 'restore', 'החזרה למצב תקין');
      await c.ask('Reconnect the cooling fan and press Done.', 'חבר בחזרה את מאוורר הקירור ולחץ "בוצע".');
    },
  });

  def('DVT-SAF-020', {
    kind: 'auto', minutes: 2,
    intro: ['A review with no machine driving: the runner reads the central error registry from the machine, collects every code recorded in DVT-SAF-001 to DVT-SAF-006 on this unit, and checks them itself - each code unique, each one in the registry, each message naming the component and stating what the operator must do.',
            'סקירה בלי הפעלת המכונה: הרנר קורא את מרשם השגיאות המרכזי מהמכונה, אוסף כל קוד שנרשם ב-DVT-SAF-001 עד DVT-SAF-006 ביחידה הזו, ובודק אותם בעצמו - כל קוד ייחודי, כל אחד מופיע במרשם, כל הודעה מזהה את הרכיב ואומרת מה על המפעיל לעשות.'],
    async run(c) {
      c.stage(1, 3, 'read the error registry', 'קריאת מרשם השגיאות');
      let registry = null;
      for (const path of ['/config/errors.json', '/static/config/errors.json']) {
        try { const r = await fetch(H_base() + path, { signal: AbortSignal.timeout(10000) }); if (r.ok) { registry = await r.json(); break; } }
        catch (e) { /* try the next path */ }
      }
      if (!registry) throw new Error(A.L('the machine did not serve config/errors.json', 'המכונה לא הגישה את config/errors.json'));
      const entries = Array.isArray(registry) ? registry : (registry.errors || registry.codes || []);
      const byCode = {};
      for (const e of entries) byCode[String(e.code)] = e;
      c.note(`registry: ${Object.keys(byCode).length} codes`);

      c.stage(2, 3, 'collect the codes recorded in DVT-SAF-001..006', 'איסוף הקודים שנרשמו ב-DVT-SAF-001..006');
      const want = ['DVT-SAF-001', 'DVT-SAF-002', 'DVT-SAF-004', 'DVT-SAF-005', 'DVT-SAF-006'];   // DVT-SAF-003 removed (user, 2026-11-12)
      const seen = [];
      const all = H_results();
      for (const id of Object.keys(all)) {
        const tid = id.split('#')[0];
        if (!want.includes(tid)) continue;
        const v = (all[id] || {}).values || {};
        for (const k of ['error_code', 'open_chain_error_code']) if (v[k]) seen.push({ run: id, test: tid, code: String(v[k]), text: v.alarm_text || v.message_text || '' });
      }
      c.trace('codes_seen', seen);
      if (!seen.length) throw new Error(A.L('no error codes have been recorded in DVT-SAF-001..006 on this unit yet - run those tests first',
                                            'עדיין לא נרשמו קודי שגיאה ב-DVT-SAF-001..006 ביחידה הזו - הרץ קודם את הבדיקות האלה'));

      c.stage(3, 3, 'check them', 'בדיקה');
      const codes = seen.map((x) => x.code);
      const perTest = {};
      for (const x of seen) (perTest[x.test] = perTest[x.test] || new Set()).add(x.code);
      const shared = codes.filter((code, i) => codes.indexOf(code) !== i && seen.find((x, j) => j !== i && x.code === code && x.test !== seen[i].test));
      const missing = codes.filter((code) => !byCode[code]);
      const words = ['fan', 'מאוורר', 'sensor', 'חיישן', 'heater', 'היטר', 'חימום', 'led', 'לד', 'thermistor', 'תרמיסטור', 'door', 'דלת', 'temperature', 'טמפרטורה', 'nitrogen', 'חנקן'];
      const actions = ['check', 'בדוק', 'reconnect', 'חבר', 'replace', 'החלף', 'contact', 'פנה', 'restart', 'הפעל', 'acknowledge', 'אשר', 'service', 'שירות'];
      // registry record: { code, key, message, severity, category, layer, description, troubleshooting: [...] }
      const texts = codes.map((code) => {
        const e = byCode[code] || {};
        const steps = Array.isArray(e.troubleshooting) ? e.troubleshooting : (e.troubleshooting ? [e.troubleshooting] : []);
        return { code, message: [e.message, e.description].filter(Boolean).join(' - '), action: steps.join('; ') };
      });
      c.trace('registry_check', { codes, shared, missing, texts });
      c.puts({
        codes_unique: shared.length === 0,
        codes_registered: missing.length === 0,
        messages_name_component: texts.every((x) => P.names(x.message + ' ' + x.action, words)),
        messages_state_recovery: texts.every((x) => x.action !== '' || P.names(x.message, actions)),
      });
      await c.yesno('all_logged', `Do all ${codes.length} of these events appear in the machine's persistent log with a timestamp? (codes: ${Array.from(new Set(codes)).join(', ')})`,
                    `האם כל ${codes.length} האירועים האלה מופיעים ביומן הקבוע של המכונה עם חותמת זמן? (קודים: ${Array.from(new Set(codes)).join(', ')})`);
    },
  });

  def('DVT-SAF-007', {
    kind: 'instrumented', minutes: 20, autoRecord: false,
    intro: ['Under-powered heating (selector on 220 V, input 110 V): the runner commands HEAT and logs the chamber for 10 minutes or until 80 C - if 80 C is not reached by then the machine must have raised an alarm, and reads out the heat-up time, the plateau it settled at, the time to that plateau, the peak, and the alarm with its code and text. It asks you only for the inlet voltage and the clamp current - and computes the delivered power from them.',
            'חימום בתת-הספק: הרנר מפעיל חימום ורושם את התא במשך 10 דקות או עד 80 מעלות - אם 80 מעלות לא הושגו עד אז המכונה חייבת הייתה להעלות התראה, ומחלץ את זמן החימום, את הרמה היציבה שהגיע אליה, את הזמן אליה, את השיא, ואת ההתראה עם הקוד והנוסח שלה. הוא שואל אותך רק את מתח הכניסה ואת זרם המלקחיים - ומחשב מהם את ההספק שנמסר.'],
    async run(c) {
      c.stage(1, 5, 'the rig', 'המערך');
      await c.ask('Set the voltage selector to 220 V and feed the unit 110 V at the inlet (the heater gets about a quarter of its power), then press Done.',
                  'כוון את בורר המתח ל-220 V והזן את היחידה ב-110 V בכניסה (גוף החימום מקבל בערך רבע מההספק), ואז לחץ "בוצע".');
      await c.value('selector_position', 'Selector position', 'מצב הבורר');
      await c.value('applied_voltage', 'Input voltage (measured at the inlet) - the machine cannot sense it, so you enter it', 'מתח הכניסה (נמדד בכניסה) - המכונה אינה חשה אותו, ולכן מזינים אותו');
      const s0 = await P.idle(c);
      c.put('unit_powers_up', true);
      const before = s0.alerts || [];

      c.stage(2, 5, 'HEAT to the setpoint', 'חימום לנקודת היעד');
      const target = 80;
      c.put('setpoint', target);
      await c.post(`/api/cure/heat?target=${target}`);
      const rows = [];
      let alarmAt = null, alarmCode = null, reachedAt = null;
      await c.watch({ sec: 600, hz: 0.5, tc: true, into: rows,   // 10 minutes: the machine must see it is not heating (user, 2026-10-25)
        on: (s, at) => {
          const t = num(s.chamberTemp);
          if (reachedAt === null && t !== null && t >= target) reachedAt = at;
          const fresh = P.fresh(before, s);
          if (alarmAt === null && fresh.length) { alarmAt = at; alarmCode = fresh[0]; }
          c.say(`heating · ${mmss_(at)} · ${r1(t)} °C${alarmCode ? ' · alarm ' + alarmCode : ''}`,
                `מחמם · ${mmss_(at)} · ${r1(t)} °C${alarmCode ? ' · התראה ' + alarmCode : ''}`);
          return reachedAt !== null ? 'stop' : undefined;
        } });
      c.trace('heat', rows);
      await c.tryPost('/api/chamber/stop');

      c.stage(3, 5, 'the clamp reading', 'קריאת המלקחיים');
      const amps = await c.value('heater_branch_current', 'Heater branch current while heating', 'זרם ענף ההיטר בזמן החימום');
      const volts = c.rec.values.applied_voltage;
      if (num(amps) !== null && num(volts) !== null) c.put('delivered_power', r1(amps * volts));

      c.stage(4, 5, 'reading the trace', 'קורא את העקומה');
      const last20 = rows.filter((r) => r[C.T] >= (rows.length ? rows[rows.length - 1][C.T] : 0) - 1200 && r[C.CHAMBER] !== null);
      const plateau = last20.length ? last20.reduce((a, r) => a + r[C.CHAMBER], 0) / last20.length : null;
      const sNow = await c.state();
      c.puts({
        setpoint_reached: reachedAt !== null,
        heat_up_time: reachedAt === null ? null : r2(reachedAt / 60),
        max_temp_reached: r2(P.maxOf(rows, C.CHAMBER)),
        plateau_temp: r2(plateau),
        time_to_plateau: r2(P.firstAt(rows, (r) => plateau !== null && r[C.CHAMBER] !== null && r[C.CHAMBER] >= plateau - 0.5) / 60),
        time_to_alarm: alarmAt === null ? null : r2(alarmAt / 60),
      });
      const text = alarmCode === null ? '' : P.detail(sNow, alarmCode);
      P.putAlarm(c, { raised: alarmAt !== null, code: alarmCode, text });
      c.put('alarm_identifies_cause', P.names(text, ['selector', 'בורר', 'voltage', 'מתח', 'mains', 'רשת', 'power', 'הספק', 'heating', 'חימום']));

      c.stage(5, 5, 'inspection and functional check', 'בדיקה ויזואלית ופונקציונלית');
      await c.yesno('fuse_opened', 'Did any fuse open?', 'האם נפתח נתיך כלשהו?');
      await c.yesno('thermal_cutout_tripped', 'Did the thermal cutout trip?', 'האם המנתק התרמי פעל?');
      await c.yesno('visible_damage', 'Is there visible damage?', 'האם יש נזק גלוי?');
      await c.ask('Restore the correct selector position for the applied mains, then press Done.',
                  'החזר את הבורר למצב הנכון עבור מתח הרשת, ואז לחץ "בוצע".');
      await P.selfCheck(c);
    },
  });

  def('DVT-SAF-017', {
    kind: 'instrumented', minutes: 25, autoRecord: false,
    intro: ['Selector in the mid detent: the heater gets no power at all. The runner commands HEAT to 80 C and logs the chamber and the heater body until the alarm (up to 12 minutes) - the machine must raise Err 9007 after ten minutes of drive at full output without the chamber rising, switch the heater off, and name both causes: the voltage selector and the heater fuse. It reads out both total rises, the time to the alarm, its text and code.',
            'הבורר במצב האמצעי: ההיטר לא מקבל הספק כלל. הרנר מפעיל חימום ל-80 מעלות ורושם את התא ואת גוף ההיטר עד ההתראה (עד 12 דקות) - המכונה חייבת להעלות שגיאה 9007 אחרי 10 דקות של חימום בהספק מלא בלי עלייה בתא, לכבות את ההיטר, ולציין את שתי הסיבות: בורר המתח ונתיך ההיטר. הוא מחלץ את שתי העליות הכוללות, את הזמן עד ההתראה, את הנוסח והקוד שלה.'],
    async run(c) {
      c.stage(1, 4, 'the rig', 'המערך');
      // nothing to ask: the runner says how the rig must be and records it as set (user, 2026-10-01)
      await c.ask('Set the voltage selector to the MIDDLE (between 110 V and 230 V) and the mains input to 220 V, then press Done.',
                  'העבר את בורר המתח לאמצע (בין 110 V ל-230 V) ואת מתח הכניסה ל-220 V, ואז לחץ "בוצע".');
      c.puts({ selector_position: 'middle (between 110 V and 230 V)', applied_voltage: 220 });
      const s0 = await P.idle(c);
      c.put('unit_powers_up', true);
      const before = s0.alerts || [];
      const start = num(s0.chamberTemp);
      const bodyStart = await P.tc(c);

      c.stage(2, 4, 'HEAT to 80 C', 'חימום ל-80 מעלות');
      c.puts({ setpoint: 80, heat_command_timestamp: stamp() });
      await c.post('/api/cure/heat?target=80');
      const rows = [];
      let alarmAt = null, alarmCode = null;
      await c.watch({ sec: 720, hz: 1, tc: true, into: rows, live: 'heat',   // Err 9007 needs 10 min of full output (1.0.87)
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (alarmAt === null && fresh.length) { alarmAt = at; alarmCode = fresh[0]; }
          c.say(`heating commanded · ${mmss_(at)} · chamber ${r1(num(s.chamberTemp))} °C${alarmCode ? ' · alarm ' + alarmCode : ''}`,
                `חימום מופעל · ${mmss_(at)} · תא ${r1(num(s.chamberTemp))} °C${alarmCode ? ' · התראה ' + alarmCode : ''}`);
          return alarmAt !== null && at > alarmAt + 20 ? 'stop' : undefined;
        } });
      c.trace('heat', rows);

      c.stage(3, 4, 'reading the trace', 'קורא את העקומה');
      const sNow = await c.state();
      const text = alarmCode === null ? '' : P.detail(sNow, alarmCode);
      c.puts({
        chamber_rise: start === null ? null : r2((P.maxOf(rows, C.CHAMBER) || start) - start),
        heater_body_rise: bodyStart === null ? null : r2((P.maxOf(rows, C.TC) || bodyStart) - bodyStart),
        time_to_alarm: alarmAt === null ? null : r2(alarmAt / 60),
        heat_stopped_or_operator_prompted: sNow.isHeating === false || alarmAt !== null,
      });
      P.putAlarm(c, { raised: alarmAt !== null, code: alarmCode, text });
      c.puts({
        alarm_states_no_heating: P.names(text, ['not heating', 'no power', 'לא מתחמם', 'אין הספק', 'heater', 'היטר', 'חימום']),
        alarm_instructs_selector: P.names(text, ['selector', 'בורר', 'voltage selector', 'מתח']),
        alarm_names_fuse: P.names(text, ['fuse', 'נתיך']),
      });
      await c.tryPost('/api/chamber/stop');
      await c.value('heater_branch_current', 'Heater branch current with HEAT commanded (expected zero)',
                    'זרם ענף ההיטר כשהחימום מופעל (הציפייה: אפס)');

      c.stage(4, 4, 'inspection and functional check', 'בדיקה ויזואלית ופונקציונלית');
      // fuse_opened / visible_damage no longer asked - not needed (user, 2026-11-12)
      await c.ask('Set the selector to the correct detent for the applied mains, then press Done.',
                  'העבר את הבורר למצב הנכון עבור מתח הרשת, ואז לחץ "בוצע".');
      await P.selfCheck(c);
    },
  });

  // ==========================================================================
  // THM - thermal characterisation
  // ==========================================================================

  /** Amplitude (half peak-to-peak) and period of the limit cycle in the tail of a trace. */
  function limitCycle(rows, col, fromSec) {
    const v = rows.filter((r) => r[C.T] >= fromSec && r[col] !== null);
    if (v.length < 10) return { amplitude: null, period: null };
    const vals = v.map((r) => r[col]);
    const mean = vals.reduce((a, x) => a + x, 0) / vals.length;
    const amplitude = r2((Math.max(...vals) - Math.min(...vals)) / 2);
    const cross = [];
    for (let i = 1; i < v.length; i++) if ((vals[i - 1] - mean) < 0 && (vals[i] - mean) >= 0) cross.push(v[i][C.T]);
    const period = cross.length >= 2 ? r2((cross[cross.length - 1] - cross[0]) / (cross.length - 1) / 60) : null;
    return { amplitude, period, mean: r2(mean) };
  }

  /** Time (s) the trace first reached `temp` on the way up. */
  function upAt(rows, col, temp) {
    for (const r of rows) if (r[col] !== null && r[col] >= temp) return r[C.T];
    return null;
  }

  /** Time (s) the trace first reached `temp` on the way down. */
  function downAt(rows, col, temp) {
    for (const r of rows) if (r[col] !== null && r[col] <= temp) return r[C.T];
    return null;
  }

  def('DVT-THM-001', {
    kind: 'auto', minutes: 120, autoRecord: false,
    intro: ['A full step response, measured by the machine on itself. The runner records ambient and the start temperature, commands the step to this row\'s setpoint with no ramp, and logs at 1 Hz until it has the heat-up time, the peak and its time, the overshoot, the settling time, the steady-state error, the undershoot and the limit cycle over the last twenty minutes - then keeps logging through the descent. Only the 16-channel uniformity comes from the grid rig, so it asks you for those four values at the end.',
            'תגובת מדרגה מלאה, שהמכונה מודדת על עצמה. הרנר רושם את טמפרטורת הסביבה ואת נקודת ההתחלה, מפעיל את המדרגה לנקודת היעד של השורה הזו בלי ראמפ, ורושם ב-1 הרץ עד שיש לו את זמן החימום, את השיא ואת הזמן אליו, את החריגה, את זמן ההתייצבות, את שגיאת המצב היציב, את התת-חריגה ואת מחזור הגבול של עשרים הדקות האחרונות - ואז ממשיך לרשום גם בירידה. רק האחידות של 16 הערוצים מגיעה ממערך הרשת, ולכן הוא שואל אותך את ארבעת הערכים האלה בסוף.'],
    async run(c) {
      const target = num(c.variant.setpoint) === null ? 60 : Number(c.variant.setpoint);
      const soak = 1800, tail = 1200, band = 0.5;
      c.put('setpoint', target);
      if (c.variant.mains_voltage !== undefined) c.put('mains_voltage', Number(c.variant.mains_voltage));
      const s0 = await P.idle(c);

      c.stage(1, 4, 'ambient and start', 'סביבה והתחלה');
      const start = num(s0.chamberTemp);
      c.puts({ start_temp: r2(start), ambient_temp: await P.ambient(c, s0) });
      if (!c.known('selector_position')) await c.value('selector_position', 'Selector position', 'מצב הבורר');
      if (!c.known('mains_voltage')) await c.value('mains_voltage', 'Mains voltage at the inlet', 'מתח הרשת בכניסה');

      // the 16-point grid is read from the machine (both TC-08s on its USB); a missing logger is said now, not at the end
      const g0 = await c.get('/api/dev/picolog/status').catch(() => null);
      const missing0 = gridMissing(g0);
      if (missing0) c.say(`thermocouple grid: ${missing0} - plug both TC-08s into the machine; uniformity is asked by hand if it stays missing`,
                          `רשת התרמוקפלים: ${missing0} - חבר את שני ה-TC-08 למכונה; אם לא, האחידות תישאל ידנית`);
      else c.note('thermocouple grid: all 16 read from the machine (TC-08 0031 = Z1-Z2, TC-08 114 = Z3-Z4)');

      c.stage(2, 4, `step to ${target} C`, `מדרגה ל-${target} מעלות`);
      await c.post(`/api/cure/heat?target=${target}`);
      const rows = [];
      const grid = [];
      let reachedAt = null, settledFrom = null, settledAt = null;
      await c.watch({ sec: 7200, hz: 1, tc: true, into: rows,
        on: (s, at, _rows, p) => {
          const g = gridRead(p);
          if (g) grid.push([at, ...g.map(r2)]);
          const t = num(s.chamberTemp);
          if (t === null) return undefined;
          if (reachedAt === null && t >= target) reachedAt = at;
          if (Math.abs(t - target) <= band) { if (settledFrom === null) settledFrom = at; if (settledAt === null && at - settledFrom >= 300) settledAt = settledFrom; }
          else settledFrom = null;
          c.say(`step · ${mmss_(at)} · ${r1(t)} / ${target} °C${settledAt !== null ? ' · settled' : ''}`,
                `מדרגה · ${mmss_(at)} · ${r1(t)} / ${target} °C${settledAt !== null ? ' · התייצב' : ''}`);
          return settledAt !== null && at >= settledAt + soak ? 'stop' : undefined;
        } });
      const endOfSoak = rows.length ? rows[rows.length - 1][C.T] : 0;

      c.stage(3, 4, 'descent', 'ירידה');
      await c.tryPost('/api/chamber/stop');
      await c.watch({ sec: tail, hz: 1, tc: true, into: rows,
        on: (s, at, _rows, p) => {
          const g = gridRead(p);
          if (g) grid.push([at, ...g.map(r2)]);
          c.say(`descent · ${mmss_(at)} · ${r1(num(s.chamberTemp))} °C`, `ירידה · ${mmss_(at)} · ${r1(num(s.chamberTemp))} °C`);
        } });
      c.trace('step_response', rows);
      if (grid.length) c.trace('grid', { columns: ['t_s', ...GRID_NAMES.map((n) => n + '_c')], samples: grid });

      c.stage(4, 4, 'reading the trace', 'קורא את העקומה');
      const soakRows = rows.filter((r) => r[C.T] <= endOfSoak);
      const peak = P.maxOf(soakRows, C.CHAMBER);
      const after = reachedAt === null ? [] : soakRows.filter((r) => r[C.T] >= reachedAt && r[C.CHAMBER] !== null);
      const lc = limitCycle(soakRows, C.CHAMBER, Math.max(0, endOfSoak - 1200));
      const tailRows = soakRows.filter((r) => r[C.T] >= endOfSoak - 1200 && r[C.CHAMBER] !== null);
      const mean = tailRows.length ? tailRows.reduce((a, r) => a + r[C.CHAMBER], 0) / tailRows.length : null;
      c.puts({
        heat_up_time: reachedAt === null ? null : r2(reachedAt / 60),
        peak_temp: r2(peak),
        overshoot: peak === null ? null : r2(Math.max(0, peak - target)),
        overshoot_uncompensated: peak === null ? null : r2(Math.max(0, peak - target)),
        time_to_peak: r2(P.firstAt(soakRows, (r) => r[C.CHAMBER] === peak) / 60),
        settling_time: settledAt === null ? null : r2(settledAt / 60),
        steady_state_error: mean === null ? null : r2(mean - target),
        undershoot: after.length ? r2(Math.max(0, target - Math.min(...after.map((r) => r[C.CHAMBER])))) : null,
        limit_cycle_amplitude: lc.amplitude,
        limit_cycle_period: lc.period,
        descent_logged: true,
        descent_linked_run_id: c.run.id,
      });
      // uniformity over the same steady-state window as the steady-state error: the last 20 minutes of the soak
      const u = gridUniformity(grid, Math.max(0, endOfSoak - 1200), endOfSoak);
      if (u) {
        c.puts({ uniformity_pp: r2(u.pp), uniformity_sd: r2(u.sd), hottest_position: u.hottest, coldest_position: u.coldest });
        c.note(`grid over the last 20 min of the soak (${u.samples} samples): mean ${r2(u.mean)} C, ` +
               `hottest ${u.hottest} (${gridPlace(u.hottest)}) ${r2(Math.max(...u.means))} C, ` +
               `coldest ${u.coldest} (${gridPlace(u.coldest)}) ${r2(Math.min(...u.means))} C; ` +
               GRID_NAMES.map((n, i) => `${n} ${r2(u.means[i])}`).join(', '));
        return;
      }
      c.say(`thermocouple grid incomplete at steady state (${gridMissing(await c.get('/api/dev/picolog/status').catch(() => null)) || 'no grid samples in the window'}) - enter the uniformity by hand`,
            'רשת התרמוקפלים לא שלמה במצב היציב - הזן את האחידות ידנית');
      await c.value('uniformity_pp', 'Peak-to-peak spread across the 16 grid channels at steady state', 'הפרש מקסימלי בין 16 ערוצי הרשת במצב יציב');
      await c.value('uniformity_sd', 'Standard deviation across the 16 grid channels', 'סטיית התקן בין 16 ערוצי הרשת');
      await c.value('hottest_position', 'Hottest grid position (Z<level>-<pos>, e.g. Z1-1 = top, back left)', 'המיקום החם ביותר ברשת (Z<קומה>-<מיקום>)');
      await c.value('coldest_position', 'Coldest grid position (Z<level>-<pos>)', 'המיקום הקר ביותר ברשת (Z<קומה>-<מיקום>)');
    },
  });

  def('DVT-THM-007', {
    kind: 'auto', minutes: 45, autoRecord: false,
    intro: ['Chamber Heating Uniformity: the runner records ambient and the start temperature, steps the chamber to 80 C, logs the control sensor and the 16-point grid (both TC-08s on the machine) every second, records the heat-up time, holds 80 C for 5 minutes and computes the uniformity over the hold. 220 V only. Nothing to do once it starts.',
            'אחידות חימום התא: הרנר רושם את טמפרטורת הסביבה ואת נקודת ההתחלה, מעלה את התא ל-80 מעלות, רושם את חיישן הבקרה ואת רשת 16 הנקודות (שני ה-TC-08 על המכונה) כל שנייה, רושם את זמן החימום, מחזיק 80 מעלות 5 דקות ומחשב את האחידות על פני ההחזקה. 220 V בלבד. אין מה לעשות אחרי ההתחלה.'],
    async run(c) {
      const target = num(Number(c.variant.setpoint)) === null ? 80 : Number(c.variant.setpoint);
      const hold = 300, maxHeat = 3600;
      c.put('setpoint', target);
      c.put('mains_voltage', num(Number(c.variant.mains_voltage)) === null ? 220 : Number(c.variant.mains_voltage));
      const s0 = await P.idle(c);

      c.stage(1, 4, 'ambient and grid', 'סביבה ורשת');
      c.puts({ start_temp: r2(num(s0.chamberTemp)), ambient_temp: await P.ambient(c, s0) });
      const g0 = await c.get('/api/dev/picolog/status').catch(() => null);
      const missing0 = gridMissing(g0);
      if (missing0) c.say(`thermocouple grid: ${missing0} - plug both TC-08s into the machine; uniformity is asked by hand if it stays missing`,
                          `רשת התרמוקפלים: ${missing0} - חבר את שני ה-TC-08 למכונה; אם לא, האחידות תישאל ידנית`);
      else c.note('thermocouple grid: all 16 read from the machine (TC-08 0031 = Z1-Z2, TC-08 114 = Z3-Z4)');

      c.stage(2, 4, `heat-up to ${target} C`, `חימום ל-${target} מעלות`);
      await c.post(`/api/cure/heat?target=${target}`);
      const rows = [], grid = [];
      let reachedAt = null;
      await c.watch({ sec: maxHeat + hold, hz: 1, tc: true, into: rows, live: 'heat',
        on: (s, at, _rows, p) => {
          const g = gridRead(p);
          if (g) grid.push([at, ...g.map(r2)]);
          const t = num(s.chamberTemp);
          if (t === null) return undefined;
          if (reachedAt === null && t >= target) {
            reachedAt = at;
            c.stage(3, 4, `hold ${target} C for 5 min`, `החזקה ב-${target} מעלות 5 דקות`);
          }
          if (reachedAt === null) {
            c.say(`heat-up · ${mmss_(at)} · ${r1(t)} / ${target} °C`, `חימום · ${mmss_(at)} · ${r1(t)} / ${target} °C`);
            return at >= maxHeat ? 'stop' : undefined;
          }
          c.say(`hold · ${mmss_(at - reachedAt)} of 05:00 · ${r1(t)} °C`, `החזקה · ${mmss_(at - reachedAt)} מתוך 05:00 · ${r1(t)} °C`);
          return at >= reachedAt + hold ? 'stop' : undefined;
        } });
      await c.tryPost('/api/chamber/stop');
      c.trace('heat_up', rows);
      if (grid.length) c.trace('grid', { columns: ['t_s', ...GRID_NAMES.map((n) => n + '_c')], samples: grid });

      c.stage(4, 4, 'uniformity', 'אחידות');
      c.puts({ reached_setpoint: reachedAt !== null, heat_up_time: reachedAt === null ? null : r2(reachedAt / 60) });
      if (reachedAt === null) {
        c.note(`the chamber did not reach ${target} C in ${maxHeat / 60} min - no hold, no uniformity`);
        return;
      }
      const end = rows.length ? rows[rows.length - 1][C.T] : reachedAt;
      c.put('hold_time', r2((end - reachedAt) / 60));
      const u = gridUniformity(grid, reachedAt, end);
      if (u) {
        c.puts({ uniformity_pp: r2(u.pp), uniformity_sd: r2(u.sd), grid_mean: r2(u.mean), hottest_position: u.hottest, coldest_position: u.coldest });
        c.note(`grid over the ${r1((end - reachedAt) / 60)} min hold (${u.samples} samples): mean ${r2(u.mean)} C, ` +
               `hottest ${u.hottest} (${gridPlace(u.hottest)}) ${r2(Math.max(...u.means))} C, ` +
               `coldest ${u.coldest} (${gridPlace(u.coldest)}) ${r2(Math.min(...u.means))} C; ` +
               GRID_NAMES.map((n, i) => `${n} ${r2(u.means[i])}`).join(', '));
        return;
      }
      c.say(`thermocouple grid incomplete during the hold (${gridMissing(await c.get('/api/dev/picolog/status').catch(() => null)) || 'no grid samples in the hold'}) - enter the uniformity by hand`,
            'רשת התרמוקפלים לא שלמה בזמן ההחזקה - הזן את האחידות ידנית');
      await c.value('uniformity_pp', 'Peak-to-peak spread across the 16 grid channels over the hold', 'הפרש מקסימלי בין 16 ערוצי הרשת בזמן ההחזקה');
      await c.value('uniformity_sd', 'Standard deviation across the 16 grid channels', 'סטיית התקן בין 16 ערוצי הרשת');
      await c.value('hottest_position', 'Hottest grid position (Z<level>-<pos>)', 'המיקום החם ביותר ברשת (Z<קומה>-<מיקום>)');
      await c.value('coldest_position', 'Coldest grid position (Z<level>-<pos>)', 'המיקום הקר ביותר ברשת (Z<קומה>-<מיקום>)');
    },
  });

  def('DVT-THM-002', {
    kind: 'auto', minutes: 40, autoRecord: false,
    intro: ['A 30 minute cure at this row\'s chamber setpoint with the LEDs at the working point. The runner logs all four built-in panel thermistors at 1 Hz, extracts each panel\'s maximum and when it got there, the rate of rise over the final five minutes, and whether any protective trip fired. It computes the junction temperature and its margin from the thermal ladder once you give it the LED current.',
            'קיור של 30 דקות בנקודת היעד של השורה הזו כשהלדים בנקודת העבודה. הרנר רושם את ארבעת התרמיסטורים המובנים ב-1 הרץ, מחלץ את המקסימום של כל פאנל ומתי הגיע אליו, את קצב העלייה בחמש הדקות האחרונות, והאם פעלה הגנה כלשהי. הוא מחשב את טמפרטורת הצומת ואת המרווח שלה מהסולם התרמי ברגע שתיתן לו את זרם הלד.'],
    async run(c) {
      const setpoint = num(c.variant.chamber_setpoint) === null ? 30 : Number(c.variant.chamber_setpoint);
      c.put('chamber_setpoint', setpoint);
      const s0 = await P.idle(c);
      c.put('ambient_temp', await P.ambient(c, s0));
      const before = s0.alerts || [];

      c.stage(1, 3, `cure at ${setpoint} C`, `קיור ב-${setpoint} מעלות`);
      const drive = 100;
      c.put('drive_percent', drive);
      const r = await c.postJson('/api/recipe/start', program('thm-002', [
        { step: 1, process: 'Heating', time: 5, temperature: setpoint },
        { step: 2, process: 'Cure', time: 30, temperature: setpoint, uvIntensity: drive, wavelength: 405 },
      ]));
      if (r.ok === false) throw new Error(r.message || A.L('the machine refused the program', 'המכונה דחתה את התוכנית'));

      c.stage(2, 3, 'logging the panels', 'רושם את הפאנלים');
      const rows = [];
      let tripAt = null, tripTemp = null;
      await c.watch({ sec: 2700, hz: 1, tc: true, into: rows,
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (tripAt === null && (fresh.length || (at > 300 && !s.uvOn))) { tripAt = at; tripTemp = hottestPanel(rows); }
          const hot = hottestPanel(rows);
          c.say(`cure · ${mmss_(at)} · hottest ${hot ? hot.panel + ' ' + r1(hot.temp) + ' °C' : '—'}`,
                `קיור · ${mmss_(at)} · החם ביותר ${hot ? hot.panel + ' ' + r1(hot.temp) + ' °C' : '—'}`);
          return s.recipe && String(s.recipe.state).toLowerCase() === 'idle' && at > 60 ? 'stop' : undefined;
        } });
      c.trace('cure', rows);
      await P.allOff(c);

      c.stage(3, 3, 'reading the trace', 'קורא את העקומה');
      const maxes = {};
      for (const k of Object.keys(PANEL)) maxes[k] = P.maxOf(rows, PANEL[k]);
      const hot = hottestPanel(rows);
      c.puts({
        max_temp_right: r2(maxes.right), max_temp_left: r2(maxes.left),
        max_temp_back: r2(maxes.back), max_temp_door: r2(maxes.door),
        time_to_max: hot ? r2(P.firstAt(rows, (r) => r[PANEL[hot.panel]] === hot.temp) / 60) : null,
        final_dtdt: hot ? P.rate(rows, PANEL[hot.panel], 300) : null,
        protective_trip_occurred: tripAt !== null,
        trip_temp_if_any: tripTemp ? r2(tripTemp.temp) : null,
      });
      const tcMax = P.maxOf(rows, C.TC);
      if (tcMax !== null && hot) c.put('thermistor_error_at_max', r2(hot.temp - tcMax));
      else await c.value('thermistor_error_at_max', 'Bonded thermocouple minus built-in thermistor on the hottest panel, at the maximum',
                         'תרמוקפל מולחם פחות תרמיסטור מובנה בפאנל החם ביותר, בנקודת המקסימום');
      const amps = await c.value('led_current', 'LED current at the working point', 'זרם הלד בנקודת העבודה');
      const rth = 8.0, vf = 3.4;                       // thermal ladder: junction to back face, per the LED datasheet
      if (num(amps) !== null && hot) {
        const tj = hot.temp + amps * vf * rth;
        c.puts({ computed_tj: r2(tj), tj_margin: r2(100 - tj) });
        c.note(`Tj = back face ${r2(hot.temp)} + I*Vf*Rth (${amps} A x ${vf} V x ${rth} C/W)`);
      }
    },
  });

  def('DVT-THM-005', {
    kind: 'auto', minutes: 90,
    intro: ['Drying, measured by the machine on itself, from a cold start. The runner starts Drying to the highest set point drying allows (50 C) and logs the chamber at 1 Hz until it has held that for 15 minutes. From the trace it reads how long the chamber took to reach 30, 40, 50 and 60 C and the highest temperature it reached; the curve is kept so the drying time for any temperature can be read off it. Drying is capped at 50 C, so 60 C is expected to stay empty. Nothing needs to be done by hand - start it with the chamber at room temperature, door closed.',
            'ייבוש שהמכונה מודדת על עצמה, מהתחלה קרה. הרנר מפעיל ייבוש לנקודת ההגדרה הגבוהה ביותר שהייבוש מרשה (50 מעלות) ורושם את התא ב-1 הרץ עד שהוא החזיק אותה 15 דקות. מהעקומה הוא קורא כמה זמן לקח לתא להגיע ל-30, 40, 50 ו-60 מעלות ומהי הטמפרטורה הגבוהה ביותר שהגיע אליה; העקומה נשמרת כדי שאפשר יהיה לקרוא ממנה את זמן הייבוש לכל טמפרטורה. הייבוש מוגבל ל-50 מעלות, ולכן 60 מעלות צפוי להישאר ריק. אין מה לעשות ביד - מתחילים כשהתא בטמפרטורת החדר והדלת סגורה.'],
    async run(c) {
      const target = 50, hold = 900, limit = 7200;          // the highest drying set point; hold it 15 min; give up after 2 h
      c.put('setpoint', target);
      const s0 = await P.idle(c);

      c.stage(1, 3, 'ambient and start', 'סביבה והתחלה');
      const start = num(s0.chamberTemp);
      c.puts({ start_temp: r2(start), ambient_temp: await P.ambient(c, s0) });

      c.stage(2, 3, `drying to ${target} C`, `ייבוש ל-${target} מעלות`);
      await c.post(`/api/cure/dry?target=${target}`);
      const rows = [];
      let reachedAt = null, damperAt = null, damperTemp = null;
      await c.watch({ sec: limit, hz: 1, tc: false, into: rows,
        on: (s, at) => {
          const t = num(s.chamberTemp);
          if (t === null) return undefined;
          if (reachedAt === null && t >= target - 0.5) reachedAt = at;
          if (damperAt === null && s.damperOpen === true) { damperAt = at; damperTemp = t; }
          c.say(`drying · ${mmss_(at)} · ${r1(t)} / ${target} °C${reachedAt !== null ? ' · holding' : ''}`,
                `ייבוש · ${mmss_(at)} · ${r1(t)} / ${target} °C${reachedAt !== null ? ' · מחזיק' : ''}`);
          return reachedAt !== null && at >= reachedAt + hold ? 'stop' : undefined;
        } });
      c.trace('drying', rows);
      await P.allOff(c);

      c.stage(3, 3, 'reading the trace', 'קורא את העקומה');
      // the time to a temperature, from the start of drying; empty when the chamber began above it or never got there
      const minutesTo = (temp) => {
        if (start !== null && start >= temp) return null;
        const sec = upAt(rows, C.CHAMBER, temp);
        return sec === null ? null : r2(sec / 60);
      };
      const peak = P.maxOf(rows, C.CHAMBER);
      c.puts({
        reached_setpoint: reachedAt !== null,
        time_to_30: minutesTo(30), time_to_40: minutesTo(40), time_to_50: minutesTo(50), time_to_60: minutesTo(60),
        max_temp: r2(peak),
        time_to_max: peak === null ? null : r2(P.firstAt(rows, (r) => r[C.CHAMBER] === peak) / 60),
        overshoot: peak === null ? null : r2(Math.max(0, peak - target)),
        damper_opened: damperAt !== null,
        damper_open_temp: r2(damperTemp),
        raw_log_attached: true,
      });
    },
  });

  def('DVT-THM-003', {
    kind: 'auto', minutes: 60,
    intro: ['The runner heats the chamber to 85 C, commands this row\'s cooling mode, and logs the descent to 30 C at 1 Hz. From the trace it reads the 80 to 40 C time, the achieved rate in each ten degree band and the tracking error against the commanded rate, the temperature at which the intake fan saturates, the lowest temperature and the undershoot, and compares the rate the machine reports against the rate it measured. Only the 16-channel spread comes from the grid rig.',
            'הרנר מחמם את התא ל-85 מעלות, מפעיל את מצב הקירור של השורה הזו, ורושם את הירידה ל-30 מעלות ב-1 הרץ. מהעקומה הוא מחלץ את הזמן מ-80 ל-40 מעלות, את הקצב שהושג בכל רצועה של עשר מעלות ואת שגיאת העקיבה מול הקצב המבוקש, את הטמפרטורה שבה מאוורר הכניסה מגיע לרוויה, את הטמפרטורה הנמוכה ביותר ואת התת-חריגה, ומשווה את הקצב שהמכונה מדווחת לקצב שהוא מדד. רק הפער בין 16 הערוצים מגיע ממערך הרשת.'],
    async run(c) {
      const mode = c.variant.cooling_mode || 'medium';
      const wire = mode === 'normal' ? 'medium' : mode;
      const commanded = { fast: 2.5, normal: 1.5, medium: 1.5, slow: 0.4 }[mode] || 1.5;
      c.puts({ cooling_mode: mode, commanded_rate: commanded });
      const s0 = await P.idle(c);
      c.puts({ ambient_temp: await P.ambient(c, s0), ambient_stability: 0 });

      c.stage(1, 3, 'heat to 85 C', 'חימום ל-85 מעלות');
      await c.post('/api/cure/heat?target=80');
      const up = await c.until((s) => num(s.chamberTemp) !== null && num(s.chamberTemp) >= 80, {
        sec: 3600, poll: 5,
        tick: (s) => c.say(`heating · ${r1(s && num(s.chamberTemp))} / 80 °C`, `מחמם · ${r1(s && num(s.chamberTemp))} / 80 °C`),
      });
      if (!up.ok) throw new Error(A.L('the chamber never reached 80 C', 'התא לא הגיע ל-80 מעלות'));
      await c.tryPost('/api/chamber/stop');
      const s1 = await c.state();
      c.put('start_temp', r2(num(s1.chamberTemp)));

      c.stage(2, 3, `cooling - ${mode}`, `מקרר - ${mode}`);
      await c.post(`/api/cure/cool?target=30&mode=${wire}`);
      const entry = await c.until((s) => s.isCooling === true, { sec: 60, poll: 0.5 });
      const sEntry = entry.s || (await c.state());
      c.puts({
        damper_opened: sEntry.damperOpen === true,
        heater_fan_100pct: num((sEntry.fanDutyEach || {}).FAN_HEATER) === 100 || num((sEntry.fans || {}).chamber_heating) === 100,
      });
      const rows = [];
      let satAt = null, reported = [];
      await c.watch({ sec: 5400, hz: 1, tc: false, into: rows,
        on: (s, at) => {
          const t = num(s.chamberTemp);
          if (num(s.coolingRate) !== null) reported.push(Math.abs(s.coolingRate));
          if (satAt === null && num(s.coolingFanPwm) >= 100) satAt = t;
          c.say(`cooling ${mode} · ${mmss_(at)} · ${r1(t)} °C · fan ${s.coolingFanPwm === null ? '—' : s.coolingFanPwm + ' %'}`,
                `מקרר ${mode} · ${mmss_(at)} · ${r1(t)} °C · מאוורר ${s.coolingFanPwm === null ? '—' : s.coolingFanPwm + ' %'}`);
          return t !== null && t <= 30 && at > 60 ? 'stop' : undefined;
        } });
      c.trace('cooldown', rows);
      await c.sleep(120);                                  // the undershoot lives in the two minutes after the target
      const tailRows = [];
      await c.watch({ sec: 120, hz: 1, into: tailRows });
      c.trace('cooldown_tail', tailRows);
      await P.allOff(c);

      c.stage(3, 3, 'reading the trace', 'קורא את העקומה');
      const at = (temp) => downAt(rows, C.CHAMBER, temp);
      const band = (hi, lo) => {
        const a = at(hi), b = at(lo);
        return a === null || b === null || b <= a ? null : r2(10 / ((b - a) / 60));
      };
      const rates = { rate_80_70: band(80, 70), rate_70_60: band(70, 60), rate_60_50: band(60, 50), rate_50_40: band(50, 40) };
      c.puts(rates);
      const errs = Object.values(rates).filter((v) => v !== null).map((v) => Math.abs(v - commanded) / commanded * 100);
      const all = rows.concat(tailRows);
      const low = P.minOf(all, C.CHAMBER);
      const measured = Object.values(rates).filter((v) => v !== null);
      const meanMeasured = measured.length ? measured.reduce((a, x) => a + x, 0) / measured.length : null;
      const meanReported = reported.length ? reported.reduce((a, x) => a + x, 0) / reported.length : null;
      c.puts({
        time_80_to_40: at(80) !== null && at(40) !== null ? r2((at(40) - at(80)) / 60) : null,
        max_tracking_error: errs.length ? r2(Math.max(...errs)) : null,
        pwm_saturation_temp: r2(satAt),
        pwm_saturated: satAt !== null,
        min_temp_reached: r2(low),
        undershoot: low === null ? null : r2(Math.max(0, 30 - low)),
        reported_rate: r2(meanReported),
        reported_vs_measured_error: meanReported !== null && meanMeasured ? r2(Math.abs(meanReported - meanMeasured) / meanMeasured * 100) : null,
      });
      await c.value('uniformity_pp_during_cooling', 'Peak-to-peak spread across the 16 grid channels at the point of maximum cooling rate',
                    'הפרש מקסימלי בין 16 ערוצי הרשת בנקודת קצב הקירור המרבי');
      await c.value('max_gradient_position', 'Grid position of the largest gradient', 'המיקום ברשת עם המפל הגדול ביותר');
    },
  });

  def('DVT-THM-006', {
    kind: 'instrumented', minutes: 30, autoRecord: false,
    intro: ['Over-driven heater on 230 V with the selector at 110 V. The runner first proves nothing is energised before the HEAT command - the heater body must stay flat - then commands HEAT to 80 C and watches the body climb until it turns, which is the fuse opening. It records that turn, its time from the command, the temperature at it, the peak, and what the software reported and when.',
            'היטר בהנעת-יתר על 230 וולט כשהבורר על 110 וולט. הרנר קודם מוכיח ששום דבר לא מופעל לפני פקודת החימום - גוף ההיטר חייב להישאר שטוח - ואז מפעיל חימום ל-80 מעלות וצופה בגוף מטפס עד להיפוך, שהוא פתיחת הנתיך. הוא רושם את ההיפוך, את הזמן שלו מהפקודה, את הטמפרטורה בו, את השיא, ומה התוכנה דיווחה ומתי.'],
    async run(c) {
      c.stage(1, 4, 'the rig', 'המערך');
      await c.ask('Selector at 110 V, mains at 230 V, TC-08 CH1 bonded to the heater body. Power the unit up but do NOT command heat. Press Done.',
                  'הבורר על 110 וולט, הרשת על 230 וולט, TC-08 ערוץ 1 מולחם לגוף ההיטר. הדלק את היחידה אבל אל תפעיל חימום. לחץ "בוצע".');
      await c.yesno('selector_position_verified', 'Is the selector confirmed and photographed at 110 V?', 'האם הבורר אומת וצולם על 110 וולט?');
      await P.idle(c);
      const bodyStart = await P.tc(c);
      c.put('heater_temp_at_start', r2(bodyStart));

      c.stage(2, 4, 'the body must stay flat before HEAT', 'הגוף חייב להישאר שטוח לפני החימום');
      const quiet = [];
      await c.watch({ sec: 180, hz: 1, tc: true, into: quiet,
        on: (s, at) => c.say(`idle · ${at} s · ${bodyTxt(quiet.length ? quiet[quiet.length - 1][C.TC] : null)}${heatTxt(s)}`,
                             `במנוחה · ${at} שניות · גוף ${r1(quiet.length ? quiet[quiet.length - 1][C.TC] : null)} °C`) });
      c.trace('before_heat', quiet);
      const drift = P.rate(quiet, C.TC, 180);
      c.put('body_rising_before_heat', drift !== null && drift > 0.5);

      c.stage(3, 4, 'HEAT to 80 C', 'חימום ל-80 מעלות');
      const before = (await c.state()).alerts || [];
      c.put('heat_command_timestamp', stamp());
      await c.post('/api/cure/heat?target=80');
      const rows = [];
      let alarmAt = null, alarmCode = null;
      await c.watch({ sec: 1200, hz: 4, tc: true, into: rows,
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (alarmAt === null && fresh.length) { alarmAt = at; alarmCode = fresh[0]; }
          c.say(`heating · ${at} s · ${bodyTxt(rows.length ? rows[rows.length - 1][C.TC] : null)}${heatTxt(s)}${alarmCode ? ' · alarm ' + alarmCode : ''}`,
                `מחמם · ${at} שניות · גוף ${r1(rows.length ? rows[rows.length - 1][C.TC] : null)} °C${alarmCode ? ' · התראה ' + alarmCode : ''}`);
          const turn = P.turn(rows, C.TC, { fall: 1.0 });
          return turn.turned && at > turn.at + 60 ? 'stop' : undefined;
        } });
      c.trace('heat', rows);
      await c.tryPost('/api/chamber/stop');
      const turn = P.turn(rows, C.TC, { fall: 1.0 });
      const sNow = await c.state();
      c.puts({
        heater_body_drop_observed: turn.turned,
        heater_off_time: turn.turned ? turn.at : null,
        heater_temp_at_fuse_open: r2(turn.peak),
        heater_temp_peak: r2(P.maxOf(rows, C.TC)),
        manual_abort_used: false,
        software_alarm_raised: alarmAt !== null,
        software_alarm_time: alarmAt !== null && turn.turned ? r2(alarmAt - turn.at) : alarmAt,
      });
      if (alarmCode !== null) c.put('error_code', String(alarmCode));
      c.note(alarmCode === null ? 'the software never alarmed' : `software alarm ${alarmCode}: ${P.detail(sNow, alarmCode)}`);

      c.stage(4, 4, 'inspection and functional check', 'בדיקה ויזואלית ופונקציונלית');
      await c.ask('De-energise, isolate and let it cool, then identify which fuse opened.',
                  'נתק מחשמל, בודד ותן להתקרר, ואז זהה איזה נתיך נפתח.');
      await c.yesno('fuse_opened', 'Did a fuse open?', 'האם נתיך נפתח?');
      await c.value('which_fuse_opened', 'Which fuse opened?', 'איזה נתיך נפתח?');
      await c.ask('Replace the fuse, set the selector to 230 V, power up, then press Done.',
                  'החלף את הנתיך, העבר את הבורר ל-230 וולט, הדלק, ולחץ "בוצע".');
      await P.selfCheck(c);
    },
  });

  def('DVT-THM-004', {
    kind: 'auto', minutes: 45,
    intro: ['Fully automatic. The runner sets the LED cooling fans to this row\'s duty, drives the LEDs to maximum, and logs the four panel thermistors until every panel has settled - rise under 0.1 C per minute over five minutes - or until one reaches the 75 C working limit. It then records the settled temperature of each panel, the hottest one, its margin to the limit, the tach reading at that duty and any alarm the firmware raised.',
            'אוטומטי לחלוטין. הרנר מכוון את מאווררי קירור הלד למחזור העבודה של השורה הזו, מעלה את הלדים למקסימום, ורושם את ארבעת תרמיסטורי הפאנלים עד שכל פאנל התייצב - עלייה מתחת ל-0.1 מעלות לדקה במשך חמש דקות - או עד שאחד מגיע לגבול העבודה של 75 מעלות. אחר כך הוא רושם את הטמפרטורה היציבה של כל פאנל, את החם ביותר, את המרווח שלו לגבול, את קריאת הטכומטר במחזור העבודה הזה וכל התראה שהקושחה העלתה.'],
    async run(c) {
      const duty = num(c.variant.fan_duty) === null ? 100 : Number(c.variant.fan_duty);
      const LIMIT = 75;
      c.put('fan_duty', duty);
      const s0 = await P.idle(c);
      c.puts({ ambient_temp: await P.ambient(c, s0), chamber_temp: r2(num(s0.chamberTemp)) });
      const before = s0.alerts || [];

      c.stage(1, 3, `LED fans at ${duty} %`, `מאווררי הלד על ${duty} אחוז`);
      await c.post('/api/fans/override?fan=led_cooling&on=1');
      await c.post(`/api/fans/led_cooling?speed=${duty}`);
      await c.sleep(20);
      const sFan = await c.state();
      const tach = ['FAN_LEFT', 'FAN_RIGHT', 'FAN_BACK', 'FAN_DOOR'].map((f) => P.rpm(sFan, f)).filter((v) => v !== null);
      c.put('tach_rpm', tach.length ? Math.round(tach.reduce((a, x) => a + x, 0) / tach.length) : null);

      c.stage(2, 3, 'LEDs at maximum until the panels settle', 'לדים במקסימום עד שהפאנלים מתייצבים');
      await c.post('/api/uv?on=1&intensity=100&wavelength=405');
      const rows = [];
      let settledAt = null, limitAt = null, alarmCode = null;
      await c.watch({ sec: 3600, hz: 1, tc: true, into: rows,
        on: (s, at) => {
          const fresh = P.fresh(before, s);
          if (alarmCode === null && fresh.length) alarmCode = fresh[0];
          const hot = hottestPanel(rows);
          if (limitAt === null && hot && hot.temp >= LIMIT) limitAt = at;
          if (settledAt === null && at > 600) {
            const rates = Object.keys(PANEL).map((k) => P.rate(rows, PANEL[k], 300)).filter((v) => v !== null);
            if (rates.length && rates.every((v) => Math.abs(v) < 0.1)) settledAt = at;
          }
          c.say(`fans ${duty} % · ${mmss_(at)} · hottest ${hot ? hot.panel + ' ' + r1(hot.temp) + ' °C' : '—'}${settledAt !== null ? ' · settled' : ''}`,
                `מאווררים ${duty} אחוז · ${mmss_(at)} · החם ביותר ${hot ? hot.panel + ' ' + r1(hot.temp) + ' °C' : '—'}${settledAt !== null ? ' · התייצב' : ''}`);
          return settledAt !== null || limitAt !== null || !s.uvOn && at > 30 ? 'stop' : undefined;
        } });
      c.trace('fan_duty_' + duty, rows);
      await P.allOff(c);
      await c.tryPost('/api/fans/override?fan=led_cooling&on=0');

      c.stage(3, 3, 'reading the trace', 'קורא את העקומה');
      const hot = hottestPanel(rows);
      const sNow = await c.state();
      c.puts({
        settled: settledAt !== null,
        time_to_settle: settledAt === null ? null : r2(settledAt / 60),
        limit_reached: limitAt !== null,
        settled_temp_right: r2(P.maxOf(rows, C.R)), settled_temp_left: r2(P.maxOf(rows, C.L)),
        settled_temp_back: r2(P.maxOf(rows, C.BACK)), settled_temp_door: r2(P.maxOf(rows, C.DOOR)),
        max_settled_temp: hot ? r2(hot.temp) : null,
        hottest_panel: hot ? hot.panel : null,
        margin_to_working_limit: hot ? r2(LIMIT - hot.temp) : null,
        thermistor_hottest_panel: hot ? r2(hot.temp) : null,
        alarm_raised: alarmCode !== null,
      });
      if (alarmCode !== null) { c.put('error_code', String(alarmCode)); c.put('alarm_text', P.detail(sNow, alarmCode)); }
    },
  });

  /**
   * The software temperature limits are never taken away: the heater is driven externally, so the
   * machine's own limits stand untouched for the whole run. Both of the catalog's limit fields are
   * answers to that one fact, and neither is a question for the operator.
   */
  const LIMITS_UNTOUCHED = () => ({
    limits_removed_how: A.L('not removed - the heater was driven externally and the software limits were untouched',
                            'לא הוסרו - ההיטר הונע חיצונית ומגבלות התוכנה נשארו במקומן'),
    limits_restored: true,
    heater_command_percent: 100,
  });

  A.limitsUntouched = LIMITS_UNTOUCHED;         // the trace analyser answers the same fields the same way

  // DVT-SAF-009 runs automatically from the site as well (user, 2026-10-25: "an automatic run that saves the
  // graphs"): the same recording the tc08_record card makes on the page - heater fan on, CH1 + the chamber logged
  // at 1 Hz, the same auto-stop and the same trace reading (A.autoStop / A.TRACE) - stored as the run's
  // tc08_record, so the graph is drawn and its CSV goes up with the result.
  def('DVT-SAF-009', {
    kind: 'guided', minutes: 45, autoRecord: false,
    intro: ['The independent thermal cutout, recorded automatically. You enter the cutout\'s rating and switch the external heater supply on when asked; the runner switches the heater fan on, logs the heater body (TC-08 CH1) and the chamber every second, stops by itself once the cutout has opened and closed again (or 20 minutes after it opened), reads the time to the cut-off, the cut-off and the reset temperatures from the trace and saves the graph with the result.',
            'המנתק התרמי העצמאי, נרשם אוטומטית. אתה מזין את הדירוג של המנתק ומדליק את ההזנה החיצונית של גוף החימום כשמתבקש; הרנר מדליק את מאוורר גוף החימום, רושם את גוף החימום (TC-08 ערוץ 1) ואת התא כל שנייה, עוצר מעצמו כשהמנתק נפתח ונסגר שוב (או 20 דקות אחרי שנפתח), קורא מהגרף את הזמן עד הניתוק, את טמפרטורת הניתוק ואת טמפרטורת הסגירה, ושומר את הגרף עם התוצאה.'],
    async run(c) {
      const DA = window.DVT_AUTO;
      await P.idle(c);
      c.stage(1, 3, 'the cutout rating and the heater fan', 'דירוג המנתק ומאוורר גוף החימום');
      const rated = await c.value('rated_trip_temp', 'Rated trip temperature of the thermal cutout (from its marking / datasheet)',
                                  'טמפרטורת הניתוק הנקובה של המנתק התרמי (מהסימון / גיליון הנתונים)');
      if (num(rated) === null) throw new Error(A.L('the cutout rating is needed for the verdict', 'הדירוג של המנתק נדרש לתוצאה'));
      // the manual abort: above the rating + 10 % the cutout has already failed - stop there, not before it could open
      const ceilingC = Math.round(Math.max(250, num(rated) * 1.1 + 5));
      const prep = await DA.prepare(c.test);
      if (!prep.ok) throw new Error(prep.message);
      c.log('info', prep.message, prep.message);
      const rows = [];
      const sample = async (t0) => {
        const s = await c.state().catch(() => ({}));
        const body = await P.tc(c).catch(() => null);
        rows.push([r2(c.sec - t0), r2(body), r2(num(s.chamberTemp)), s.isHeating === true, (s.alerts || []).join('|'), s.isHeating === true, num(s.heaterPwm)]);
        return body;
      };
      const t0 = c.sec;
      for (let i = 0; i < 20; i++) { await sample(t0); await c.sleep(1); }   // the baseline before the heater

      c.stage(2, 3, 'heater on from the external supply - recording', 'גוף החימום מוזן מההזנה החיצונית - רושם');
      await c.ask('Switch the external heater supply ON now and leave it on - do not interrupt it until the runner says the recording is complete. Fire watch at the bench. Press Done when it is on.',
                  'הדלק עכשיו את ההזנה החיצונית של גוף החימום והשאר אותה דלוקה - אל תפסיק עד שהרנר אומר שהרישום הושלם. צופה אש ליד העמדה. לחץ "בוצע" כשהיא דלוקה.');
      const fake = { autos: { tc08_record: { kind: 'tc08_record', samples: rows } } };
      let stopWhy = '', ceiling = false;
      while (c.sec - t0 < 90 * 60) {
        const body = await sample(t0);
        const st = DA.autoStop(c.test, fake);
        c.say(`recording · ${mmss_(c.sec - t0)} · ${bodyTxt(body)}${fake.marks && fake.marks.trip_s ? ' · cut-off at ' + mmss_(fake.marks.trip_s) : ''}`,
              `רושם · ${mmss_(c.sec - t0)} · גוף ${r1(body)} °C${fake.marks && fake.marks.trip_s ? ' · ניתוק ב-' + mmss_(fake.marks.trip_s) : ''}`);
        if (rows.length % 10 === 0) c.drawLive('tc08', rows);
        if (st.stop) { stopWhy = st.why; break; }
        if (body !== null && body >= ceilingC && !(fake.marks && fake.marks.trip_s)) { ceiling = true; break; }
        await c.sleep(1);
      }
      if (ceiling) {
        await c.ask(`The heater body passed ${ceilingC} C and the cutout has NOT opened. Cut the supply at the contactor NOW, then press Done.`,
                    `גוף החימום עבר ${ceilingC} מעלות והמנתק לא נפתח. נתק עכשיו את ההזנה במגען, ואז לחץ "בוצע".`);
        c.note(`manual abort at the ${ceilingC} C ceiling: the cutout did not open - a FAIL of the cutout`);
      } else {
        await c.ask(`${stopWhy || A.L('recording complete', 'הרישום הושלם')} - switch the external heater supply OFF now, then press Done.`,
                    `${stopWhy || 'הרישום הושלם'} - כבה עכשיו את ההזנה החיצונית של גוף החימום, ואז לחץ "בוצע".`);
      }
      await DA.finish(c.test);

      c.stage(3, 3, 'reading the trace', 'קורא את הגרף');
      A._host().setAuto(c.rec, { kind: 'tc08_record', test: c.tid, at: new Date().toISOString(), machine: c.machine, status: 'DONE',
                         columns: ['t_s', 'ch1_c', 'machine_chamber_c', 'machine_heating', 'alerts', 'heater_commanded', 'heater_pwm_pct'], samples: rows });
      const why = A.TRACE['DVT-SAF-009'](rows, (k, v) => c.put(k, v), c.rec);
      if (typeof why === 'string' && why) { c.note(why); c.log('warn', why, why); }
      if (stopWhy) c.log('info', stopWhy, stopWhy);
      c.save();
    },
  });

  /**
   * Did the firmware really stop? The API runs in the firmware process, so a frozen or killed firmware stops
   * answering. Pressing Done proves nothing: a run where nobody stopped anything used to wait on as if the
   * watchdog had failed, when the heartbeat was alive and the watchdog rightly had nothing to cut.
   */
  async function firmwareWentSilent(c, sec) {
    const end = c.sec + sec;                    // the runner's own clock (virtual in the test harness)
    while (c.sec < end) {
      try { await c.get('/api/system/version'); } catch (e) { return true; }
      await c.sleep(1);
    }
    return false;
  }
  const NOT_STOPPED = [
    'the firmware is still answering - the heartbeat was NOT stopped, so the watchdog has nothing to cut. Freeze or kill the firmware process on the unit (e.g. sudo systemctl kill -s SIGSTOP scurebox-ui), then run again',
    'התוכנה עדיין עונה - פעימת הלב לא נעצרה, ולכן לשומר אין מה לנתק. הקפא או הרוג את תהליך התוכנה במכונה (למשל sudo systemctl kill -s SIGSTOP scurebox-ui), ואז הרץ שוב'];

  def('DVT-SAF-010', {
    kind: 'auto', minutes: 25, autoRecord: false,
    intro: ['The second line of defence. The runner heats at full output and puts the UV at maximum, then makes the firmware hang on purpose: its heartbeat and every output write freeze, and it switches nothing off itself. The separate output watchdog must then cut the heater and the UV - the runner proves it on the StarBright (UV below 10 %) and on the heater-body thermocouple (rise turning to fall), and checks that nothing comes back by itself after the hang and that an alarm asks for a restart.',
            'קו ההגנה השני. הרנר מחמם בהספק מלא ומעלה את ה-UV למקסימום, ואז תוקע את התוכנה בכוונה: הפעימה וכל כתיבה ליציאות קופאות, והיא לא מכבה כלום בעצמה. שומר היציאות הנפרד חייב אז לנתק את החימום ואת ה-UV - הרנר מוכיח את זה ב-StarBright (UV מתחת ל-10%) ובתרמוקפל גוף החימום (עלייה שהופכת לירידה), ובודק ששום דבר לא חוזר לבד אחרי התקיעה ושהתראה מבקשת הפעלה מחדש.'],
    async run(c) {
      await P.idle(c);
      const m = await c.get('/api/dvt/meter').catch(() => ({ present: false }));
      if (!m.present) throw new Error(A.L('connect the StarBright to the machine - the UV cut is proven on it', 'חבר את ה-StarBright למכונה - ניתוק ה-UV מוכח עליו'));
      const before = (await c.state()).alerts || [];

      c.stage(1, 3, 'heater rising, UV at maximum', 'החימום עולה, UV במקסימום');
      await c.post('/api/cure/heat?target=80');
      const warm = [];
      await c.watch({ sec: 300, hz: 1, tc: true, into: warm,
        on: (s, at) => { c.say(`warming · ${bodyTxt(warm.length ? warm[warm.length - 1][C.TC] : null)}${heatTxt(s)}`,
                               `מתחמם · גוף ${r1(warm.length ? warm[warm.length - 1][C.TC] : null)} °C`);
                         const rate = P.rate(warm, C.TC, 60);
                         return at > 60 && rate !== null && rate > 2 ? 'stop' : undefined; } });
      await c.post('/api/uv?on=1&intensity=100&wavelength=405');
      await c.sleep(20);
      const plateau = [];
      for (let i = 0; i < 10; i++) { const x = await c.get('/api/dvt/meter').catch(() => null); plateau.push(x ? num(x.reading_mw_cm2) : null); await c.sleep(0.2); }
      const level = Math.max(...plateau.filter((v) => v !== null));
      if (!(level > 0.5)) throw new Error(A.L('the StarBright sees no UV - check the head position', 'ה-StarBright לא רואה UV - בדוק את מיקום הראש'));
      c.put('uv_plateau', r2(level));

      c.stage(2, 3, 'the firmware hangs: the watchdog must cut', 'התוכנה נתקעת: השומר חייב לנתק');
      // the heater controller pulses the element: hang it while it is driving FULL output, or there may be nothing to cut
      await c.until((s) => num(s.heaterPwm) >= 99, { sec: 60, poll: 0.5 });
      const HANG = 240;                                       // the heater-body turn may take up to 200 s (user, 2026-10-25)
      const h = await c.postJson(`/api/dvt/hang?sec=${HANG}`, {});
      if (h.ok === false) throw new Error(h.message || A.L('the machine refused the hang command', 'המכונה דחתה את פקודת התקיעה'));
      if (num(h.heartbeatTimeoutSec) !== null) c.put('watchdog_timeout_s', num(h.heartbeatTimeoutSec));
      const t0 = c.sec;
      const rows = [];
      let uvOff = null;
      const fall = [];
      // the StarBright fast (5 Hz), the TC-08 at 2 Hz, until both have proven the cut or the hang is over
      while (c.sec - t0 < HANG) {
        const x = await c.get('/api/dvt/meter').catch(() => null);
        const v = x ? num(x.reading_mw_cm2) : null;
        fall.push([r2(c.sec - t0), v]);
        if (uvOff === null && v !== null && v < level * 0.1) uvOff = r2(c.sec - t0);
        if (fall.length % 2 === 0) {
          const body = await P.tc(c).catch(() => null);
          rows.push([r2(c.sec - t0), null, null, null, null, null, null, null, null, r2(body), '', null]);
        }
        const turn = P.turn(rows, C.TC);
        c.say(`hung · ${Math.round(c.sec - t0)} s · UV ${uvOff === null ? 'still on' : 'off at ' + uvOff + ' s'} · heater ${turn.turned ? 'off at ' + turn.at + ' s' : bodyTxt(rows.length ? rows[rows.length - 1][C.TC] : null)}`,
              `תקוע · ${Math.round(c.sec - t0)} שניות · UV ${uvOff === null ? 'עדיין דולק' : 'כבה ב-' + uvOff + ' שניות'} · חימום ${turn.turned ? 'כבה ב-' + turn.at + ' שניות' : 'גוף ' + r1(rows.length ? rows[rows.length - 1][C.TC] : null) + ' °C'}`);
        if (uvOff !== null && turn.turned) break;
        await c.sleep(0.2);
      }
      c.trace('hang_uv', { plateau_mw_cm2: r2(level), samples: fall });
      c.trace('hang_heater', rows);
      const turn = P.turn(rows, C.TC);
      c.puts({ uv_drop_observed: uvOff !== null, uv_off_time: uvOff, heater_body_drop_observed: turn.turned, heater_off_time: turn.turned ? turn.at : null });

      c.stage(3, 3, 'after the hang: nothing restarts by itself', 'אחרי התקיעה: שום דבר לא חוזר לבד');
      while (c.sec - t0 < HANG + 5) await c.sleep(1);          // the hang is over
      const watch = [];
      await c.watch({ sec: 120, hz: 1, tc: true, into: watch,
        on: (s, at) => c.say(`watching for an automatic restart · ${at} s`, `צופה בהפעלה אוטומטית מחדש · ${at} שניות`) });
      c.trace('no_auto_restart', watch);
      c.put('auto_restart_prevented', !watch.some((r) => r[C.HEATER] === true || r[C.UV] === true));
      const a = await P.alarm(c, before, { sec: 10 });
      P.putAlarm(c, a);
      c.put('logged', a.raised);
      await P.allOff(c);
    },
  });

  def('DVT-SAF-011', {
    kind: 'guided', minutes: 30,
    intro: ['One run. The runner switches heating on and waits until the heater body is clearly rising, then asks you to disconnect the CM5\'s 40-pin flat cable - from that press it times the heater body turning from rising to falling on the thermocouple, and asks whether the heater SSR switched off. Then you reconnect the cable; once the machine answers again it watches for two and a half minutes that heating and UV do not resume by themselves and the heater body keeps falling.',
            'ריצה אחת. הרנר מדליק חימום וממתין עד שגוף ההיטר עולה בבירור, ואז מבקש ממך לנתק את כבל הפלט 40 פין של ה-CM5 - מרגע הלחיצה הוא מודד בתרמוקפל מתי גוף ההיטר עובר מעלייה לירידה, ושואל האם ה-SSR של ההיטר כבה. אחר כך אתה מחבר בחזרה את הכבל; ברגע שהמכונה עונה שוב הוא צופה שתי דקות וחצי שהחימום וה-UV לא מתחדשים מעצמם ושגוף ההיטר ממשיך לרדת.'],
    async run(c) {
      await P.idle(c);
      const cfgBefore = await c.get('/api/system/version').catch(() => null);

      c.stage(1, 5, 'heating until the body rises', 'מחמם עד שהגוף עולה');
      const r = await c.post('/api/cure/heat?target=50');
      if (r.ok === false) throw new Error(r.message || A.L('the machine refused to heat', 'המכונה סירבה לחמם'));
      const warm = [];
      await c.watch({ sec: 300, hz: 1, tc: true, into: warm, live: 'warm_up',
        on: (s, at) => {
          c.say(`warming · ${r1(num(s.chamberTemp))} °C · ${bodyTxt(P.maxOf(warm, C.TC))}${heatTxt(s)}`,
                `מתחמם · ${r1(num(s.chamberTemp))} °C · גוף ${r1(P.maxOf(warm, C.TC))} °C`);
          const rate = P.rate(warm, C.TC, 60);
          return at > 60 && rate !== null && rate > 2 ? 'stop' : undefined;
        } });
      c.trace('warm_up', warm);

      c.stage(2, 5, 'disconnect the CM5 cable', 'נתק את כבל ה-CM5');
      const pulled = await c.ask('Disconnect the 40-pin flat cable of the CM5 NOW, then press Done. The runner times everything from that press.',
                                 'נתק עכשיו את כבל הפלט 40 פין של ה-CM5, ואז לחץ "בוצע". הרנר מודד הכול מרגע הלחיצה.');
      if (pulled !== true) throw new Error(A.L('the cable was never disconnected', 'הכבל לא נותק'));
      const rows = [];
      // the TC-08 is on the CM5's USB, so CH1 keeps logging as long as the firmware answers; dropped polls are skipped
      // 10 min (was 4): on the unit the heater body takes at least 5 min to turn after the cable is pulled (user, 2026-11-12);
      // the watch still ends 30 s after the body has clearly turned
      await c.watch({ sec: 600, hz: 1, tc: true, into: rows, live: 'cable_out',
        on: (s, at) => {
          const turned = P.turn(rows, C.TC);
          c.say(`cable out · ${at} s · ${bodyTxt(rows.length ? rows[rows.length - 1][C.TC] : null)}${heatTxt(s)}${turned.turned ? ' · body falling since ' + turned.at + ' s' : ''}`,
                `כבל מנותק · ${at} שניות · גוף ${r1(rows.length ? rows[rows.length - 1][C.TC] : null)} °C${turned.turned ? ' · הגוף יורד מ-' + turned.at + ' שניות' : ''}`);
          return turned.turned && at > turned.at + 30 ? 'stop' : undefined;
        } });
      c.trace('cable_out', rows);
      const turn = P.turn(rows, C.TC);
      c.puts({ heater_off_time: turn.turned ? turn.at : null, heater_temp_peak: r2(turn.peak) });

      c.stage(3, 5, 'the heater SSR', 'ה-SSR של ההיטר');
      await c.yesno('heater_ssr_switched_off', 'Did the heater SSR switch off?', 'האם ה-SSR של ההיטר כבה?');

      c.stage(4, 5, 'reconnect - nothing may resume', 'חיבור מחדש - שום דבר לא מתחדש');
      await c.ask('Reconnect the 40-pin flat cable of the CM5, then press Done.', 'חבר בחזרה את כבל הפלט 40 פין של ה-CM5, ואז לחץ "בוצע".');
      c.say('waiting for the machine to answer again…', 'ממתין שהמכונה תענה שוב…');
      const back = await c.until(() => true, { sec: 300, poll: 3 });
      if (!back.ok) throw new Error(A.L('the machine never answered after the cable was reconnected', 'המכונה לא ענתה אחרי חיבור הכבל'));
      const after = [];
      await c.watch({ sec: 150, hz: 1, tc: true, into: after, live: 'after_reconnect',
        on: (s, at) => c.say(`after the reconnect · ${at} s · heat ${s.isHeating ? 'on' : 'off'} · UV ${s.uvOn ? 'on' : 'off'}`,
                             `אחרי החיבור · ${at} שניות · חימום ${s.isHeating ? 'דולק' : 'כבוי'} · UV ${s.uvOn ? 'דולק' : 'כבוי'}`) });
      c.trace('after_reconnect', after);
      const body = P.rate(after, C.TC, 120);
      c.puts({
        auto_resume_heat: after.some((x) => x[C.HEATER] === true || x[C.PWM] > 0),
        auto_resume_uv: after.some((x) => x[C.UV] === true),
        heater_body_stays_falling: body === null ? null : body <= 0,
      });

      c.stage(5, 5, 'the record survived', 'הרישום שרד');
      const cfgAfter = await c.get('/api/system/version').catch(() => null);
      c.put('config_intact', !!cfgAfter && (!cfgBefore || cfgBefore.appVersion === cfgAfter.appVersion));
      c.put('log_intact', !!(await c.get('/api/state').catch(() => null)));
      await P.allOff(c);
    },
  });

  // ------------------------------------------------------------------------------------------------ DVT-SAF-008 --
  // Door interlock - UV inhibited with the door open. The four steps of the catalog (steps 5 door status and 6 alarm removed, user 2026-11-12), which
  // the DVT tool runs one card at a time (door_open_cure, uv_off_timing, door_lock_check, door_magnet_defeat), run
  // here as one script so the CureBox's runner can do them from sCure Cloud, one after the other, the person at the
  // machine only doing what a hand has to do (open, pull, hold a magnet, close). 405 nm only; the StarBright on the
  // machine's USB gives every irradiance number. The UV is always switched off again, whatever happens.
  def('DVT-SAF-008', {
    kind: 'guided', minutes: 40,
    intro: ['Four parts, one after the other, 405 nm only, with the StarBright on the machine. (1) The door is released and you open it: the runner reads the dark level, then tries a 405 nm program and a direct UV command - both must be refused and the meter must see no UV. (2) With the door closed, a real cure runs at 100 % until the StarBright is stable; you open the door and the meter times the UV going off. (3) A cure at 30 % with the door closed: you pull the door for 10 s - it must stay locked. (4) The door is released, you hold it open and put the magnet to the door sensor for 10 s - the sensor must not be fooled. Wear UV eye protection near the door.',
            'ארבעה חלקים ברצף, 405 ננומטר בלבד, עם ה-StarBright שבמכונה. (1) הדלת משתחררת ואתה פותח אותה: הרנר קורא את רמת החושך, ואז מנסה תוכנית 405 ופקודת UV ישירה - שתיהן חייבות להידחות והמד לא רואה UV. (2) עם דלת סגורה רצה תוכנית אמיתית ב-100% עד שה-StarBright יציב; אתה פותח את הדלת והמד מתזמן את כיבוי ה-UV. (3) תוכנית ב-30% עם דלת סגורה: אתה מושך את הדלת 10 שניות - היא חייבת להישאר נעולה. (4) הדלת משתחררת, אתה מחזיק אותה פתוחה ומקרב מגנט לחיישן הדלת 10 שניות - החיישן אסור שיתבלבל. עטה הגנת עיניים מ-UV ליד הדלת.'],
    async run(c) {
      const THRESHOLD = 0.5;                                  // mW/cm2 above the dark reading = UV seen (the catalog's field note)
      const closed = (s) => s.doorClosed === true;
      const open = (s) => s.doorClosed === false;
      const meter = async () => {
        const m = await c.get('/api/dvt/meter').catch(() => ({ present: false }));
        if (!m.present) throw new Error(m.message || A.L('no StarBright on the machine - every irradiance of this test comes from it', 'אין StarBright במכונה - כל ערך הקרינה בבדיקה הזו מגיע ממנו'));
        return m;
      };
      const readMeter = async () => { const m = await c.get('/api/dvt/meter').catch(() => null); return m && m.present ? num(m.reading_mw_cm2) : null; };
      // every waiting prompt is an instruction to the person: doThis() publishes it as the step and
      // needs BOTH the press ("I did it") and the machine's own reading before the script goes on
      const wait = async (pred, sec, say, failEn, failHb) =>
        say ? c.doThis(say[0], say[1], pred, sec, failEn, failHb)
            : (async () => { const r = await c.until(pred, { sec, poll: 0.25 }); if (!r.ok) throw new Error(A.L(failEn, failHb)); return r.s; })();
      const door = async (what, en, hb) => { c.act(en, hb, 60); await c.tryPost('/api/door/open'); return wait(what, 60, [en, hb], 'the machine did not see the door change - nothing was done', 'המכונה לא ראתה את הדלת משתנה - לא בוצע דבר'); };

      await P.idle(c);
      const m0 = await meter();
      if (m0.wavelength_nm !== 405) {
        const w = await c.post('/api/dvt/meter/wavelength?nm=405');
        if (w.ok === false) throw new Error(w.message || A.L('the meter did not take 405 nm', 'המד לא קיבל 405 ננומטר'));
      }

      // ---- 1/4 the door open: dark level, then both ways of starting UV must be refused and nothing seen
      c.stage(1, 4, 'door open - a cure must not start', 'דלת פתוחה - אסור שתוכנית תתחיל');
      await door(open, 'OPEN THE DOOR NOW - the lock has been released', 'פתח את הדלת עכשיו - הנעילה שוחררה');
      c.say('door open - reading the dark level', 'הדלת פתוחה - קורא את רמת החושך');
      const trace1 = [];                                       // [t_s, mW/cm2, phase, door_open, uv_on]
      const t1 = c.sec;
      const sample1 = async (phase) => {
        const [v, s] = await Promise.all([readMeter(), c.state()]);
        trace1.push([r2(c.sec - t1), v, phase, open(s), s.uvOn === true]);
        await c.sleep(0.15);
        return { v, s };
      };
      const darkEnd = c.sec + 2;
      while (c.sec < darkEnd) await sample1('dark');
      const darkVals = trace1.filter((r) => r[2] === 'dark' && r[1] !== null).map((r) => r[1]);
      if (!darkVals.length) throw new Error(A.L('the StarBright gave no reading', 'ה-StarBright לא נתן קריאה'));
      if (trace1.some((r) => r[2] === 'dark' && !r[3])) throw new Error(A.L('the door closed during the dark reading - repeat the step', 'הדלת נסגרה בזמן קריאת החושך - חזור על השלב'));
      const dark = Math.max(...darkVals);

      c.say('trying to start a 405 nm cure and a direct UV command with the door open', 'מנסה להתחיל תוכנית 405 ופקודת UV ישירה כשהדלת פתוחה');
      const material = { id: 'dvt-saf-012', name: 'DVT-SAF-008 door interlock', steps: [{ step: 1, process: 'Cure', time: 1, uvIntensity: 30 }] };
      const rRecipe = await c.postJson('/api/recipe/start', { material }).catch((e) => ({ ok: false, message: String(e.message || e) }));
      let recipeOk = rRecipe.ok === true, recipeStop = null;
      if (recipeOk) {                                         // "started" can still be stopped by the program's own pre-flight a moment later (6015)
        const until = c.sec + 3;
        while (c.sec < until) {
          const rs = await c.get('/api/recipe/status').catch(() => ({}));
          if (String(rs.state).toLowerCase() === 'error') { recipeStop = { state: rs.state, message: rs.message, code: rs.errorCode }; break; }
          await c.sleep(0.3);
        }
        if (recipeStop) recipeOk = false;
      }
      trace1.push([r2(c.sec - t1), null, 'recipe_start:' + (rRecipe.ok ? (recipeStop ? `stopped by the machine (${recipeStop.code} ${recipeStop.message})` : 'accepted') : 'refused'), null, null]);
      const rUv = await c.post('/api/uv?on=1&intensity=30&wavelength=405').catch((e) => ({ ok: false, message: String(e.message || e) }));
      const uvOk = rUv.ok === true;
      trace1.push([r2(c.sec - t1), null, 'uv_command:' + (uvOk ? 'accepted' : 'refused'), null, null]);
      let peak = dark, uvOnSeen = false, doorStayed = true;
      const watchEnd = c.sec + 5;
      while (c.sec < watchEnd) {
        const { v, s } = await sample1('watch');
        if (v !== null) peak = Math.max(peak, v);
        if (s.uvOn) uvOnSeen = true;
        if (!open(s)) doorStayed = false;
        if (v !== null && v - dark > THRESHOLD) break;        // UV seen: off at once, the step has failed
      }
      await P.allOff(c);
      if (!doorStayed) throw new Error(A.L('the door closed during the attempt - repeat the step', 'הדלת נסגרה בזמן הניסיון - חזור על השלב'));
      const uvDetected = peak - dark > THRESHOLD;
      c.puts({
        door_open_detected: true, cure_start_refused: !recipeOk, uv_command_refused: !uvOk, uv_detected: uvDetected,
        uv_peak_above_dark: Math.round(Math.max(0, peak - dark) * 1e4) / 1e4,
        cure_start_inhibited: !recipeOk && !uvOk && !uvDetected && !uvOnSeen,
      });
      c.trace('door_open_cure', { columns: ['t_s', 'irradiance_mw_cm2', 'phase', 'door_open', 'uv_on'], samples: trace1 });
      c.note(`step 1: dark ${r2(dark)}, peak ${r2(peak)} mW/cm2, recipe ${recipeOk ? 'ACCEPTED' : 'refused'}, UV command ${uvOk ? 'ACCEPTED' : 'refused'}`);
      c.save();

      // ---- 2/4 UV-off timing: a real cure at 100 %, the door opened, the meter times the UV going off
      c.stage(2, 4, 'UV off when the door opens', 'כיבוי UV בפתיחת הדלת');
      await wait(closed, 300, ['CLOSE and latch the door to continue (part 2 runs a real cure)', 'סגור ונעל את הדלת כדי להמשיך (חלק 2 מריץ תוכנית אמיתית)'],
                 'the door was not closed within 5 minutes', 'הדלת לא נסגרה תוך 5 דקות');
      const started = await c.post('/api/dvt/uv-off?wavelength=405&intensity=100');
      if (started.ok === false) throw new Error(started.message || A.L('the machine refused to start the UV-off timing', 'המכונה סירבה להתחיל את תזמון כיבוי ה-UV'));
      let uo, aborted = false;
      do {
        await c.sleep(0.4);
        if (c.stopped() && !aborted) { aborted = true; await c.tryPost('/api/dvt/uv-off/abort'); }
        uo = await c.get('/api/dvt/uv-off?samples=0');
        // the machine times the UV from the door sensor itself: no press here, it would add nothing
        // and the measurement is the point - but the instruction is still THE step on screen
        if (uo.phase === 'open_door') c.act('OPEN THE DOOR NOW', 'פתח את הדלת עכשיו', null, { ack: false });
        else c.say(uo.phase === 'plateau' ? `waiting for the UV to settle (${r2(num(uo.reading))} mW/cm2) - do not touch the door yet` : `${uo.phase} · ${r2(num(uo.reading))} mW/cm2`,
                   uo.phase === 'plateau' ? `ממתין שה-UV יתייצב (${r2(num(uo.reading))}) - אל תיגע בדלת עדיין` : `${uo.phase} · ${r2(num(uo.reading))}`);
      } while (uo.running);
      uo = await c.get('/api/dvt/uv-off');
      if (uo.status !== 'OK') throw new Error(uo.error || uo.status);
      c.puts({ uv_off_time: uo.uv_off_time_s, uv_zero_time: uo.uv_zero_time_s, residual_irradiance: uo.residual_mw_cm2 });
      c.trace('uv_off_timing', { columns: ['t_s', 'irradiance_mw_cm2', 'door_open', 'phase'], samples: uo.samples || [] });
      c.note(`step 2: UV off ${uo.uv_off_time_s} s after the door opened, zero at ${uo.uv_zero_time_s} s, residual ${uo.residual_mw_cm2} mW/cm2`);
      c.save();

      // ---- 3/4 the lock: a cure at 30 % with the door closed, the door pulled for 10 s
      c.stage(3, 4, 'the lock holds against a pull', 'הנעילה מחזיקה מול משיכה');
      await wait(closed, 300, ['CLOSE and latch the door to continue', 'סגור ונעל את הדלת כדי להמשיך'], 'the door was not closed within 5 minutes', 'הדלת לא נסגרה תוך 5 דקות');
      const lockMaterial = { id: 'dvt-saf-012-lock', name: 'DVT-SAF-008 lock check', steps: [{ step: 1, process: 'Cure', time: 1, uvIntensity: 30 }] };
      const rLock = await c.postJson('/api/recipe/start', { material: lockMaterial });
      if (rLock.ok === false) throw new Error(rLock.message || A.L('the program did not start', 'התוכנית לא התחילה'));
      c.say('starting the cure at 30 %', 'מתחיל תוכנית ב-30%');
      const lit = await c.until((s) => s.uvOn === true, { sec: 30, poll: 0.3 });
      if (!lit.ok) throw new Error(A.L('the UV never came on', 'ה-UV לא נדלק'));
      const lockRows = [];
      let pulledOpen = false;
      // the ten seconds are counted from the moment the person says they are pulling: before this
      // (user, 2026-10-30) the window ran whether or not anybody had a hand on the door
      await c.doThis('PULL the door firmly and keep pulling, then press "I am pulling"',
                     'משוך את הדלת בחוזקה והמשך למשוך, ואז לחץ "אני מושך"', null, 300,
                     'nobody confirmed the pull within 5 minutes', 'אף אחד לא אישר משיכה תוך 5 דקות');
      const lockEnd = c.sec + 10;
      while (c.sec < lockEnd) {
        const s = await c.state();
        lockRows.push([r2(c.sec), open(s), s.uvOn === true, 'pull']);
        if (open(s)) { pulledOpen = true; break; }
        c.act(`KEEP PULLING - ${Math.ceil(lockEnd - c.sec)} s`, `המשך למשוך - ${Math.ceil(lockEnd - c.sec)} שניות`, lockEnd - c.sec, { ack: false });
        await c.sleep(0.2);
      }
      c.actDone();
      const rsLock = await c.get('/api/recipe/status').catch(() => ({}));
      const sLock = await c.state();
      await P.allOff(c);
      c.put('lock_engaged', !pulledOpen);
      c.trace('door_lock_check', { columns: ['t_s', 'door_open', 'uv_on', 'phase'], samples: lockRows });
      c.note(`step 3: the door ${pulledOpen ? 'OPENED under the pull' : 'held'}; program ${rsLock.state || '?'}`);
      c.save();

      // ---- 4/4 the magnet: the door held open, the magnet on the door sensor for 10 s
      c.stage(4, 4, 'a magnet must not fool the door sensor', 'מגנט אסור שיטעה את חיישן הדלת');
      await c.tryPost('/api/door/open');
      await wait(open, 120, ['OPEN THE DOOR and keep it open', 'פתח את הדלת והחזק אותה פתוחה'], 'the machine did not see the door open', 'המכונה לא ראתה את הדלת נפתחת');
      const magRows = [];
      let fooled = false;
      await c.doThis('HOLD THE MAGNET against the door sensor from outside, keep the door open, then press "I am holding it"',
                     'החזק את המגנט מול חיישן הדלת מבחוץ, השאר את הדלת פתוחה, ואז לחץ "אני מחזיק"', null, 300,
                     'nobody confirmed the magnet within 5 minutes', 'אף אחד לא אישר את המגנט תוך 5 דקות');
      const magEnd = c.sec + 10;
      while (c.sec < magEnd) {
        const s = await c.state();
        magRows.push([r2(c.sec), open(s), s.uvOn === true, 'magnet']);
        if (closed(s)) fooled = true;
        c.act(`KEEP THE MAGNET on the sensor, door open - ${Math.ceil(magEnd - c.sec)} s${fooled ? ' · the machine reads CLOSED' : ''}`,
              `השאר את המגנט על החיישן, הדלת פתוחה - ${Math.ceil(magEnd - c.sec)} שניות${fooled ? ' · המכונה קוראת "סגורה"' : ''}`,
              magEnd - c.sec, { ack: false });
        await c.sleep(0.2);
      }
      c.actDone();
      if (fooled) {                                            // a door that fell shut also reads closed: the person says which it was
        const heldOpen = await c.confirm(
          A.L('The machine read the door CLOSED while you held the magnet. Was the door still held OPEN by you the whole time? (Yes = the magnet fooled the sensor; No = the door fell shut - the step must be repeated)',
                    'המכונה קראה "דלת סגורה" כשהחזקת את המגנט. האם החזקת את הדלת פתוחה כל הזמן? (כן = המגנט הטעה את החיישן; לא = הדלת נסגרה - צריך לחזור על השלב)'));
        if (heldOpen !== true) throw new Error(A.L('the door fell shut during the magnet step - repeat it', 'הדלת נסגרה בשלב המגנט - חזור עליו'));
      }
      c.put('defeat_by_magnet_possible', fooled);
      c.trace('door_magnet_defeat', { columns: ['t_s', 'door_open', 'uv_on', 'phase'], samples: magRows });
      c.note(`step 4: the sensor was ${fooled ? 'FOOLED' : 'not fooled'} by the magnet`);
      c.save();

      // steps 5 (door status) and 6 (alarm) were removed from the test (user, 2026-11-12)
      await P.allOff(c);
    },
  });

  def('DVT-SAF-012', {
    kind: 'instrumented', minutes: 30,
    intro: ['405 nm only, and every number comes from the StarBright on the machine\'s USB - nothing is typed in. The runner sets the meter to 405 nm, reads the dark room with the LEDs off, drives the LEDs to maximum at 405 nm and samples the meter continuously while you scan the enclosure with the meter head; the meter head is held flush against each possible light source, and the highest reading of the scan is the maximum. It then averages the meter at the operator position and computes the permitted daily exposure from that level against the UV-A eye limit of IEC 62471 / EN 62471 clause 4.3.5: 1 mW/cm2 for exposures over 1000 s, 1000 mJ/cm2 below that.',
            '405 ננומטר בלבד, וכל מספר מגיע מה-StarBright שמחובר ל-USB של המכונה - שום דבר לא מוקלד. הרנר מכוון את המד ל-405 ננומטר, קורא את החדר החשוך כשהלדים כבויים, מעלה את הלדים למקסימום ב-405 ננומטר ודוגם את המד ברציפות בזמן שאתה סורק את המארז עם ראש המד; ראש המד מוצמד לכל מקור אור אפשרי, והקריאה הגבוהה ביותר בסריקה היא המקסימום. אחר כך הוא ממצע את המד בעמדת המפעיל ומחשב מהרמה הזו את משך החשיפה היומי המותר לפי מגבלת UV-A לעין בתקן IEC 62471 / EN 62471 סעיף 4.3.5: 1 mW/cm2 לחשיפה מעל 1000 שניות, 1000 mJ/cm2 מתחת לזה.'],
    async run(c) {
      await P.idle(c);
      const m = await c.get('/api/dvt/meter').catch(() => ({ present: false }));
      if (!m.present) throw new Error(m.message || A.L('no StarBright on the machine - every value of this test comes from it', 'אין StarBright במכונה - כל ערך בבדיקה הזו מגיע ממנו'));
      const w = await c.post('/api/dvt/meter/wavelength?nm=405');
      if (w.ok === false) throw new Error(w.message || A.L('the meter refused 405 nm', 'המד סירב ל-405 ננומטר'));
      const read = async () => { const x = await c.get('/api/dvt/meter').catch(() => null); return x ? num(x.reading_mw_cm2) : null; };
      const samples = [];                                   // [t s, mW/cm2, phase] - one meter caller at a time, never in parallel
      const t0 = c.sec;
      // sample the meter until `done` resolves (the operator pressed Done) or `sec` runs out; returns that phase's readings
      const sampleWhile = async (phase, done, sec, show) => {
        let finished = false;
        if (done) done.then(() => { finished = true; });
        const got = [];
        const start = c.sec;
        while (!finished && (sec === undefined || c.sec - start < sec)) {
          const v = await read();
          samples.push([r2(c.sec - t0), v, phase]);
          if (v !== null) got.push(v);
          if (show) show(v, got);
          await c.sleep(0.25);
        }
        return got;
      };

      c.stage(1, 4, 'dark room, LEDs off', 'חדר חשוך, לדים כבויים');
      await c.ask('Darken the room, close and latch the door, hold the meter head flush against the door seam and press Done.',
                  'החשך את החדר, סגור ונעל את הדלת, הצמד את ראש המד לתפר הדלת ולחץ "בוצע".');
      const dark = await sampleWhile('dark', null, 5);
      const darkLevel = dark.length ? Math.max(...dark) : 0;
      c.note(`dark-room reading at 405 nm: ${r2(darkLevel)} mW/cm2 (${dark.length} samples)`);

      c.stage(2, 4, 'LEDs at maximum, 405 nm - scan the enclosure', 'לדים במקסימום, 405 ננומטר - סרוק את המארז');
      await c.post('/api/uv?on=1&intensity=100&wavelength=405');
      const lit = await c.until((s) => s.uvOn === true, { sec: 60, poll: 1 });
      if (!lit.ok) { await P.allOff(c); throw new Error(A.L('the LEDs never came on', 'הלדים לא נדלקו')); }
      let peakAt = null;
      const scanDone = c.ask('Wearing UV eye protection, scan the door seam, hinge line, damper, vents, cable entries and every panel joint with the meter head held flush against the light source. The runner keeps the highest reading - press Done when you have covered everything.',
                             'עם משקפי מגן ל-UV, סרוק עם ראש המד את תפר הדלת, קו הצירים, הדמפר, הפתחים, כניסות הכבלים וכל חיבור פאנל כשראש המד צמוד למקור האור. הרנר שומר את הקריאה הגבוהה ביותר - לחץ "בוצע" כשכיסית הכל.');
      const scan = await sampleWhile('scan', scanDone, 1800, (v, got) => {
        const mx = got.length ? Math.max(...got) : null;
        if (v !== null && v === mx) peakAt = r2(c.sec - t0);
        c.put('max_irradiance_10cm', mx === null ? null : r2(mx));
        c.say(`scanning at 405 nm · now ${v === null ? '-' : r2(v)} mW/cm2 · max ${mx === null ? '-' : r2(mx)} mW/cm2`,
              `סורק ב-405 ננומטר · עכשיו ${v === null ? '-' : r2(v)} mW/cm2 · מקסימום ${mx === null ? '-' : r2(mx)} mW/cm2`);
      });
      await scanDone;
      const peak = scan.length ? r2(Math.max(...scan)) : null;
      c.put('max_irradiance_10cm', peak);
      if (peakAt !== null) c.note(`maximum ${peak} mW/cm2 at t = ${peakAt} s of the meter trace`);
      await c.value('leak_location', 'Where was the meter when the maximum was read?', 'היכן היה המד כשנקרא המקסימום?');

      c.stage(3, 4, 'operator position', 'עמדת המפעיל');
      await c.ask('Hold the meter head at the operator position at the front of the machine (eye height, facing the door) and press Done - the runner then averages the meter for 10 s.',
                  'החזק את ראש המד בעמדת המפעיל בחזית המכונה (בגובה העיניים, מול הדלת) ולחץ "בוצע" - הרנר ממצע את המד במשך 10 שניות.');
      const front = await sampleWhile('operator', null, 10, (v) => c.say(`operator position · ${v === null ? '-' : r2(v)} mW/cm2`, `עמדת המפעיל · ${v === null ? '-' : r2(v)} mW/cm2`));
      const frontLevel = front.length ? r2(front.reduce((a, b) => a + b, 0) / front.length) : null;
      c.put('irradiance_operator_position', frontLevel);
      await P.allOff(c);
      c.trace('uv_meter_405', { wavelength_nm: 405, dark_mw_cm2: r2(darkLevel), columns: ['t_s', 'mw_cm2', 'phase'], samples });

      c.stage(4, 4, 'permitted exposure', 'חשיפה מותרת');
      const level = frontLevel !== null ? frontLevel : peak;
      // IEC 62471:2006 / EN 62471:2008 clause 4.3.5, UV-A hazard exposure limit for the eye:
      // E <= 1 mW/cm2 (10 W/m2) for t > 1000 s - a full day; above it E x t <= 1000 mJ/cm2 (10 kJ/m2)
      const STD = 'IEC 62471:2006 / EN 62471:2008 cl. 4.3.5 - UV-A eye limit: 1 mW/cm2 for t > 1000 s, 1000 mJ/cm2 for t <= 1000 s';
      c.put('exposure_limit_standard', STD);
      if (level !== null) {
        const hours = level <= 1 ? 10000 : r2(1000 / level / 3600);
        c.put('permitted_exposure_hours', hours);
        c.note(level <= 1
          ? `permitted exposure: ${level} mW/cm2 <= 1 mW/cm2, the continuous UV-A limit - no daily limit (${STD})`
          : `permitted exposure = 1000 mJ/cm2 / ${level} mW/cm2 = ${r2(1000 / level)} s (${STD})`);
      }
    },
  });

  def('DVT-SAF-013', {
    kind: 'guided', minutes: 15,
    intro: ['The door switch connector unplugged: the runner turns the LEDs on and then the heating, and checks that neither turns on (the heating is watched for 200 seconds). It also records any alarm the machine raises.',
            'מחבר מתג הדלת מנותק: הרנר מדליק את הלדים ואז את החימום, ובודק שאף אחד מהם לא נדלק (החימום נבדק במשך 200 שניות). הוא רושם גם כל התראה שהמכונה מעלה.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 3, 'unplug the door switch', 'ניתוק מתג הדלת');
      await c.ask('Unplug the door switch connector, then press Done.', 'נתק את מחבר מתג הדלת, ואז לחץ "בוצע".');
      const before = (await c.state()).alerts || [];

      c.stage(2, 3, 'the LEDs and the heating must stay off', 'הלדים והחימום חייבים להישאר כבויים');
      await c.tryPost('/api/uv?on=1&intensity=30&wavelength=405');
      const uvRan = (await c.until((s) => s.uvOn === true, { sec: 15, poll: 0.5 })).ok;
      await P.allOff(c);
      await c.tryPost('/api/cure/heat?target=60');
      const heatRan = (await c.until((s) => s.isHeating === true && num(s.heaterPwm) > 0, { sec: 200, poll: 1 })).ok;   // 200 s: the heating must stay off the whole time (user, 2026-10-25)
      await c.tryPost('/api/chamber/stop');
      await P.allOff(c);
      c.puts({ open_chain_cure_inhibited: !uvRan, open_chain_heat_inhibited: !heatRan });
      const a = await P.alarm(c, before, { sec: 30 });
      c.puts({ open_chain_alarm: a.raised, open_chain_error_code: a.code === null ? null : String(a.code) });

      c.stage(3, 3, 'plug it back in', 'חיבור בחזרה');
      await c.ask('Plug the door switch connector back in, then press Done.', 'חבר בחזרה את מחבר מתג הדלת, ואז לחץ "בוצע".');
    },
  });

  def('DVT-SAF-014', {
    kind: 'guided', minutes: 25,
    intro: ['One part of the software stack fails and the outputs are watched, not the log: the StarBright for the UV, the heater-body thermocouple for the heat. Screen killed: the cure must carry on and the screen come back. Storage read-only: the machine must keep answering and raise an alarm. I2C bus lost: the UV must be gone within 25 s and the heater body turn within 200 s. Then nothing may come back by itself.',
            'חלק אחד במחסנית התוכנה נכשל והיציאות נצפות, לא היומן: ה-StarBright עבור ה-UV ותרמוקפל גוף החימום עבור החימום. מסך שנהרג: הקיור חייב להמשיך והמסך לחזור. אחסון לקריאה בלבד: המכונה חייבת להמשיך לענות ולהעלות התראה. אפיק I2C שאבד: ה-UV חייב להיעלם תוך 25 שניות וגוף החימום לעבור לירידה תוך 200 שניות. אחר כך שום דבר לא חוזר לבד.'],
    async run(c) {
      const kase = String(c.variant.case || 'ui_kill');
      c.put('failure_mode', kase);
      await P.idle(c);
      const m = await c.get('/api/dvt/meter').catch(() => ({ present: false }));
      if (!m.present) throw new Error(A.L('connect the StarBright to the machine - the UV is read on it', 'חבר את ה-StarBright למכונה - ה-UV נקרא עליו'));
      const before = (await c.state()).alerts || [];
      const meter = async () => { const x = await c.get('/api/dvt/meter').catch(() => null); return x ? num(x.reading_mw_cm2) : null; };

      c.stage(1, 3, 'a heated cure under way', 'קיור עם חימום בעיצומו');
      const r = await c.postJson('/api/recipe/start', program('saf-014', [
        { step: 1, process: 'Cure', time: 20, temperature: 60, uvIntensity: 50, wavelength: 405 }]));
      if (r.ok === false) throw new Error(r.message || A.L('the machine refused the cure', 'המכונה דחתה את הקיור'));
      const lit = await c.until((s) => s.uvOn === true, { sec: 600, poll: 2 });
      if (!lit.ok) throw new Error(A.L('the UV never came on', 'ה-UV לא נדלק'));
      await c.sleep(20);
      const plateau = [];
      for (let i = 0; i < 10; i++) { plateau.push(await meter()); await c.sleep(0.2); }
      const level = Math.max(...plateau.filter((v) => v !== null));
      c.put('uv_plateau', r2(level));

      c.stage(2, 3, `the failure - ${kase}`, `הכשל - ${kase}`);
      const what = {
        ui_kill: ['Kill the screen (UI) process only - leave the firmware running. Press Done the moment it is gone.', 'הרוג רק את תהליך המסך (UI) - השאר את התוכנה רצה. לחץ "בוצע" ברגע שהוא נעלם.'],
        storage_loss: ['Force the filesystem read-only now (e.g. remount the data partition ro). Press Done the moment it is applied.', 'הפוך עכשיו את מערכת הקבצים לקריאה בלבד (למשל remount של מחיצת הנתונים ל-ro). לחץ "בוצע" ברגע שזה בוצע.'],
        i2c_loss: ['Interrupt the I2C bus to the IO board now (pull the I2C link / short SDA). Press Done the moment it is cut.', 'נתק עכשיו את אפיק ה-I2C ללוח ה-IO (נתק את חיבור ה-I2C / קצר את SDA). לחץ "בוצע" ברגע שהוא נותק.'],
      }[kase] || ['Apply the failure now, then press Done.', 'הפעל עכשיו את הכשל, ואז לחץ "בוצע".'];
      await c.ask(what[0], what[1]);
      const t0 = c.sec;
      const rows = [];
      const fall = [];
      let uvOff = null, answered = true, uvLow = false;
      const span = kase === 'i2c_loss' ? 240 : 60;
      while (c.sec - t0 < span) {
        const v = await meter();
        fall.push([r2(c.sec - t0), v]);
        if (v !== null && v < level * 0.1) { uvLow = true; if (uvOff === null) uvOff = r2(c.sec - t0); }
        if (fall.length % 2 === 0) {
          const s = await c.state().catch(() => null);
          if (!s) answered = false;
          const body = await P.tc(c).catch(() => null);
          rows.push([r2(c.sec - t0), s ? num(s.chamberTemp) : null, s ? num(s.heaterPwm) : null, s ? s.isHeating === true : null, s ? s.uvOn === true : null,
                     null, null, null, null, r2(body), s ? (s.alerts || []).join('|') : '', null]);
        }
        const turn = P.turn(rows, C.TC);
        c.say(`after the failure · ${Math.round(c.sec - t0)} s · UV ${uvOff === null ? 'on' : 'off at ' + uvOff + ' s'} · heater ${turn.turned ? 'off at ' + turn.at + ' s' : 'on'}`,
              `אחרי הכשל · ${Math.round(c.sec - t0)} שניות · UV ${uvOff === null ? 'דולק' : 'כבה ב-' + uvOff + ' שניות'} · חימום ${turn.turned ? 'כבה ב-' + turn.at + ' שניות' : 'דולק'}`);
        if (kase === 'i2c_loss' && uvOff !== null && turn.turned) break;
        await c.sleep(0.2);
      }
      c.trace('failure_uv', { plateau_mw_cm2: r2(level), samples: fall });
      c.trace('failure_heater', rows);
      const turn = P.turn(rows, C.TC);
      c.puts({ uv_off_time: uvOff, heater_off_time: turn.turned ? turn.at : null });
      const a = await P.alarm(c, before, { sec: 15 });
      P.putAlarm(c, a);
      let ok = false;
      if (kase === 'ui_kill') {
        c.put('process_continued', !uvLow && !turn.turned);
        const back = await c.yesno('screen_back', 'Did the screen come back (restarted by itself, or you started it) showing the running cure?',
                                   'האם המסך חזר (עלה מעצמו, או שהפעלת אותו) ומציג את הקיור שרץ?');
        ok = !uvLow && !turn.turned && back === true;
      } else if (kase === 'storage_loss') {
        ok = answered && a.raised;
      } else {
        ok = uvOff !== null && uvOff <= 25 && turn.turned && turn.at <= 200;
      }
      c.put('case_ok', ok);
      await c.value('display_state', 'What is on the display now?', 'מה מוצג כעת על המסך?');

      c.stage(3, 3, 'restore: nothing comes back by itself', 'החזרה: שום דבר לא חוזר לבד');
      await P.allOff(c);
      await c.ask('Restore the machine to normal operation (restart what you stopped, reconnect, remount read-write), then press Done.',
                  'החזר את המכונה לפעולה תקינה (הפעל מחדש את מה שעצרת, חבר מחדש, remount לכתיבה), ואז לחץ "בוצע".');
      const watch = [];
      await c.watch({ sec: 60, hz: 1, tc: true, into: watch,
        on: (s, at) => c.say(`watching for an automatic restart · ${at} s`, `צופה בהפעלה אוטומטית מחדש · ${at} שניות`) });
      c.trace('after_restore', watch);
      c.put('auto_resume', watch.some((r) => r[C.HEATER] === true || r[C.UV] === true));
    },
  });

  def('DVT-SAF-015', {
    kind: 'auto', minutes: 70,
    intro: ['Degraded LED cooling, applied over the API. The runner records the healthy baseline for this side, then steps the fan duty down 75, 50, 25 % and holds each step until the panel settles, watching for the first alarm. It records the level and the temperature at which it fired, the alarm text and code, the tach reading at that moment, how far the panel rose after the protection acted, and whether any other panel alarmed. Only case C, a blocked air path, needs your hands.',
            'קירור לד מדורדר, מופעל דרך ה-API. הרנר רושם את קו הבסיס התקין של הצד הזה, ואז מוריד את מחזור העבודה של המאוורר ל-75, 50 ו-25 אחוז ומחזיק כל שלב עד שהפאנל מתייצב, בזמן שהוא ממתין להתראה הראשונה. הוא רושם את הרמה והטמפרטורה שבהן היא פעלה, את נוסח ההתראה והקוד, את קריאת הטכומטר באותו רגע, כמה הפאנל עוד עלה אחרי שההגנה פעלה, והאם פאנל אחר התריע. רק מקרה C, חסימת נתיב אוויר, דורש את הידיים שלך.'],
    async run(c) {
      const kase = String(c.variant.case || 'A_hottest');
      // Cases B name their side (B_right ...); cases A and C say "hottest", which is not a side but an
      // instruction - the side is whichever panel the baseline shows running hottest, read from the machine.
      const named = String(c.variant.side || kase.split('_')[1] || '').toLowerCase();
      let side = PANEL[named] ? named : null;
      const blocked = kase.indexOf('C') === 0;
      c.put('case', c.variant.case || null);
      const s0 = await P.idle(c);
      const before = s0.alerts || [];

      c.stage(1, 4, 'healthy baseline', 'קו בסיס תקין');
      await c.post('/api/uv?on=1&intensity=100&wavelength=405');
      const base = [];
      const shown = () => (side ? PANEL[side] : (hottestPanel(base) ? PANEL[hottestPanel(base).panel] : C.R));
      await c.watch({ sec: 600, hz: 1, into: base,
        on: (s, at) => { const k = shown();
                         c.say(`baseline · ${mmss_(at)} · ${r1(base.length ? base[base.length - 1][k] : null)} °C`,
                               `קו בסיס · ${mmss_(at)} · ${r1(base.length ? base[base.length - 1][k] : null)} °C`);
                         const rate = P.rate(base, k, 120);   // steady: at most 1 C in 2 minutes (user, 2026-10-25)
                         return at > 300 && rate !== null && Math.abs(rate) <= 0.5 ? 'stop' : undefined; } });
      c.trace('baseline', base);
      if (!side) {
        const hot = hottestPanel(base);
        if (!hot) throw new Error(A.L('no panel thermistor gave a reading during the baseline', 'אף תרמיסטור פאנל לא נתן קריאה בקו הבסיס'));
        side = hot.panel;
        c.note(`hottest side in the baseline: ${side} (${r1(hot.temp)} C)`);
      }
      c.put('side', side);
      const col = PANEL[side];
      const fanName = 'FAN_' + side.toUpperCase();
      const sBase = await c.state();
      c.puts({ baseline_temp: r2(P.maxOf(base, col)), baseline_tach: P.rpm(sBase, fanName) });

      c.stage(2, 4, 'degrade it in steps', 'הדרדרות בשלבים');
      // the settled temperature of every step, for the final duty-versus-temperature graph (user, 2026-10-25)
      const settled = (list, k) => { const end = list.length ? list[list.length - 1][C.T] : 0;
                                     const tail = list.filter((r) => r[C.T] >= end - 60 && num(r[k]) !== null);
                                     return tail.length ? r2(tail.reduce((a, r) => a + r[k], 0) / tail.length) : null; };
      const curve = [[100, settled(base, col), P.rpm(sBase, fanName)]];
      const steps = blocked ? ['operator 75 %', 'operator 50 %', 'operator 25 %'] : [75, 50, 25];
      const rows = [];
      let alarmAt = null, alarmCode = null, levelAtAlarm = null, tempAtAlarm = null, tachAtAlarm = null;
      await c.post('/api/fans/override?fan=led_cooling&on=1');
      for (const step of steps) {
        if (alarmAt !== null) break;
        if (blocked) await c.ask(`Obstruct the shared air path to ${Number(String(step).replace(/\D/g, ''))} % of normal, then press Done.`,
                                 `חסום את נתיב האוויר המשותף ל-${Number(String(step).replace(/\D/g, ''))} אחוז מהרגיל, ואז לחץ "בוצע".`);
        else await c.post(`/api/fans/led_cooling?speed=${step}`);
        const t0 = c.sec;
        await c.watch({ sec: 900, hz: 1, into: rows,
          on: (s, at) => {
            const fresh = P.fresh(before, s);
            if (alarmAt === null && fresh.length) {
              alarmAt = c.sec; alarmCode = fresh[0]; levelAtAlarm = String(step);
              tempAtAlarm = rows.length ? rows[rows.length - 1][col] : null;
              tachAtAlarm = P.rpm(s, fanName);
            }
            c.say(`${step} % · ${mmss_(at)} · ${r1(rows.length ? rows[rows.length - 1][col] : null)} °C${alarmCode ? ' · alarm ' + alarmCode : ''}`,
                  `${step} אחוז · ${mmss_(at)} · ${r1(rows.length ? rows[rows.length - 1][col] : null)} °C${alarmCode ? ' · התראה ' + alarmCode : ''}`);
            if (alarmAt !== null) return 'stop';
            const rate = P.rate(rows, col, 120);
            return at > 300 && rate !== null && Math.abs(rate) <= 0.5 ? 'stop' : undefined;
          } });
        const sStep = await c.state();
        c.puts({ degradation_level: String(step), settled_panel_temp: r2(P.maxOf(rows, col)), tach_reading: P.rpm(sStep, fanName) });
        curve.push([Number(String(step).replace(/\D/g, '')), settled(rows.filter((r) => r[C.T] >= t0 - (rows.length ? 0 : 0)), col), P.rpm(sStep, fanName)]);
      }
      c.trace('degradation', rows);
      c.trace('duty_vs_temp', { columns: ['fan_duty_pct', 'panel_temp_c', 'tach_rpm'], samples: curve,
                                xy: { x: 'fan_duty_pct', y: 'panel_temp_c', xLabel: blocked ? 'air path open (%)' : 'LED fan duty (%)', yLabel: side + ' panel (°C)' } });

      c.stage(3, 4, 'after the protection acts', 'אחרי שההגנה פעלה');
      const after = [];
      await c.watch({ sec: 600, hz: 1, into: after,
        on: (s, at) => c.say(`after the alarm · ${mmss_(at)} · ${r1(after.length ? after[after.length - 1][col] : null)} °C`,
                             `אחרי ההתראה · ${mmss_(at)} · ${r1(after.length ? after[after.length - 1][col] : null)} °C`) });
      c.trace('after_alarm', after);
      await P.allOff(c);
      await c.tryPost('/api/fans/override?fan=led_cooling&on=0');

      c.stage(4, 4, 'reading the alarm', 'קריאת ההתראה');
      const sNow = await c.state();
      const text = alarmCode === null ? '' : P.detail(sNow, alarmCode);
      const peakAfter = P.maxOf(after, col);
      c.puts({
        level_at_alarm: levelAtAlarm, temp_at_alarm: r2(tempAtAlarm), time_to_alarm: alarmAt,
        tach_at_alarm: tachAtAlarm, alarm_raised: alarmCode !== null,
        peak_temp_after_shutdown: r2(peakAfter),
        post_shutdown_overshoot: tempAtAlarm === null || peakAfter === null ? null : r2(Math.max(0, peakAfter - tempAtAlarm)),
        alarm_identifies_correct_side: P.names(text, [side, 'FAN_' + side.toUpperCase()]),
        message_names_specific_fan: /fan\s+\w+|FAN_[A-Z]+|מאוורר\s+\S+/.test(text),
        message_states_ambiguity: P.names(text, ['or ', 'either', 'one of', 'או ', 'אחד מ']),
        false_alarm_on_other_sides: (sNow.alerts || []).filter((x) => x !== alarmCode).length > 0,
      });
      if (alarmCode !== null) { c.put('error_code', String(alarmCode)); c.put('alarm_text', text); }
      const base2 = num(c.rec.values.baseline_tach);
      if (tachAtAlarm !== null && base2 !== null) c.put('tach_within_normal_band', Math.abs(tachAtAlarm - base2) / base2 <= 0.2);
      await c.yesno('claim_is_correct', `Is what the message claims about which fan true for this case? Message: "${text}"`,
                    `האם מה שההודעה טוענת לגבי המאוורר נכון למקרה הזה? ההודעה: "${text}"`);
      if (c.has('airflow')) await c.value('airflow', 'Airflow at the panel inlet, if an anemometer is fitted (skip if not)',
                                          'זרימת האוויר בכניסת הפאנל, אם מותקן אנמומטר (דלג אם לא)');
      await c.ask('Restore normal cooling, then press Done.', 'החזר קירור תקין, ואז לחץ "בוצע".');
      const cleared = await c.until((s) => !(s.alerts || []).includes(alarmCode), { sec: 60, poll: 2 });
      c.put('recovery_requires_ack', !cleared.ok);
    },
  });

  def('DVT-SAF-016', {
    kind: 'guided', minutes: 40,
    intro: ['With one LED panel open, the runner switches the machine\'s panel-must-warm check on for the left and right panels (this test only) and lights the LEDs, times the alarm from that command, reads the text and code, and checks that it names the right panel and tells the operator to check the LED. It then proves a job will not start, restores the panel, starts a cure and asks you to open the same connection with the LEDs on, timing that alarm too.',
            'כשפאנל לד אחד מנותק, הרנר מפעיל את בדיקת הלדים כדי שהלדים יידלקו, מודד את הזמן להתראה מאותה פקודה, קורא את הנוסח והקוד, ובודק שהיא מזהה את הפאנל הנכון ומנחה את המפעיל לבדוק את הלד. אחר כך הוא מוכיח שעבודה לא תתחיל, מחזיר את הפאנל, מתחיל קיור ומבקש ממך לפתוח את אותו חיבור כשהלדים דולקים, ומודד גם את ההתראה הזו.'],
    async run(c) {
      const panel = String(c.variant.panel || 'right');
      const point = String(c.variant.disconnect_point || 'led_string_open');
      c.puts({ panel: c.variant.panel || null, disconnect_point: c.variant.disconnect_point || null });

      // the 'panel must warm while lit' check (Err 9004 / 9005) for all four panels, switched on for this test only
      // (user, 2026-10-25) - the machine keeps it off in normal operation and forgets the override on a restart
      const lc = await c.postJson('/api/dvt/led-checks?on=1', {}).catch((e) => ({ ok: false, message: String(e.message || e) }));
      if (lc.ok === false) throw new Error(lc.message || A.L('the machine could not switch the LED panel checks on - update its software (1.0.111+)',
                                                             'המכונה לא הצליחה להפעיל את בדיקות לוחות הלדים - עדכן את התוכנה שלה (1.0.111 ומעלה)'));
      try {
      c.stage(1, 4, 'open the panel', 'נתק את הפאנל');
      await c.ask(`With the unit de-energised, open the ${panel} panel at ${point}. Re-energise and press Done.`,
                  `כשהיחידה מנותקת מחשמל, נתק את פאנל ${panel} בנקודה ${point}. הדלק מחדש ולחץ "בוצע".`);
      await c.yesno('panel_confirmed_dark', `Is the ${panel} string confirmed open or its driver unpowered on the DMM / clamp?`,
                    `האם אומת שמחרוזת ${panel} פתוחה או שהדרייבר שלה ללא הזנה, במולטימטר או במלקחיים?`);
      const s0 = await P.idle(c);
      const before = s0.alerts || [];

      c.stage(2, 4, 'switch the LEDs on', 'הדלקת הלדים');
      // the check needs 90 s of light before it judges a panel: the LEDs stay on up to 150 s, not a 30 s self-test
      const test = null;
      await c.post('/api/cure/uv-only?intensity=100&wavelength=405');
      const a = await P.alarm(c, before, { sec: 150,
        tick: (s, at) => c.say(`LEDs on · ${at} s - the panel check judges after 90 s`, `לדים דולקים · ${at} שניות - בדיקת הלוחות שופטת אחרי 90 שניות`) });
      await P.allOff(c);
      const text = a.text || '';
      c.puts({ alarm_raised: a.raised, time_to_alarm: a.raised ? a.sec : null });
      if (a.code !== null) c.put('error_code', String(a.code));
      c.put('alarm_text', text);
      c.puts({
        alarm_identifies_correct_panel: P.names(text, [panel, 'LED_' + panel.toUpperCase(), 'TEMP_' + panel.toUpperCase()]),
        alarm_action_says_check_led: P.names(text, ['check', 'בדוק', 'led', 'לד', 'panel', 'פאנל']),
        false_alarm_on_other_panels: (a.codes || []).length > 1,
      });
      if (test) c.trace('led_test', test);

      c.stage(3, 4, 'a job must not start', 'העבודה לא אמורה להתחיל');
      const r = await c.postJson('/api/recipe/start', program('saf-020', [{ step: 1, process: 'Cure', time: 2, uvIntensity: 100 }]));
      let started = r.ok === true && (await c.until((s) => s.uvOn === true, { sec: 25, poll: 0.5 })).ok;
      await P.allOff(c);
      c.put('job_start_inhibited', !started);

      c.stage(4, 4, 'the same break mid-job', 'אותו ניתוק באמצע התהליך');
      await c.ask(`Restore the ${panel} connection, acknowledge the alarm, then press Done - the runner will start a cure and ask you to open it again.`,
                  `החזר את החיבור של ${panel}, אשר את ההתראה, ולחץ "בוצע" - הרנר יתחיל קיור ויבקש ממך לנתק שוב.`);
      const before2 = (await c.state()).alerts || [];
      await c.post('/api/cure/uv-only?intensity=100&wavelength=405');
      const lit = await c.until((s) => s.uvOn === true, { sec: 60, poll: 0.5 });
      if (lit.ok) {
        await c.sleep(30);
        await c.ask(`Open the ${panel} connection NOW, then press Done.`, `נתק עכשיו את החיבור של ${panel}, ואז לחץ "בוצע".`);
        const t1 = c.sec;
        const a2 = await P.alarm(c, before2, { sec: 180, tick: (s, at) => c.say(`mid-job · ${at} s`, `אמצע תהליך · ${at} שניות`) });
        const sNow = await c.state();
        c.puts({ midjob_alarm_raised: a2.raised, midjob_time_to_alarm: a2.raised ? a2.sec : null, midjob_job_stopped: sNow.uvOn === false });
      }
      await P.allOff(c);
      await c.ask(`Restore the ${panel} connection and press Done.`, `החזר את החיבור של ${panel} ולחץ "בוצע".`);
      const cleared = await c.until((s) => (s.alerts || []).length === 0, { sec: 60, poll: 2 });
      c.put('recovery_requires_ack', !cleared.ok);
      const post = await c.post('/api/diagnostics/led-test?seconds=30&wavelength=405').catch(() => null);
      c.put('post_test_panel_functional', !!(post && ['PASS', 'OK'].includes(String(post.status || '').toUpperCase())));
      if (post) c.trace('led_test_after', post);
      } finally {
        await c.tryPost('/api/dvt/led-checks?on=0');      // back to the machine's normal setting
      }
    },
  });

  // ==========================================================================
  // GAS - nitrogen
  // ==========================================================================

  def('DVT-GAS-007', {
    kind: 'instrumented', minutes: 90, autoRecord: false,
    intro: ['The runner reads the line pressure, the damper and the extraction from the machine, opens the valve itself and keeps the clock. The O2 analyser is not on the network, so it asks you to press Now at the two moments that matter - the centre probe and the corner probe first reaching 4.8 % - and works out the times, the purge duration, the hold above 95 % and the margin from its own clock.',
            'הרנר קורא את לחץ הקו, את המדף ואת השאיבה מהמכונה, פותח את השסתום בעצמו ומנהל את השעון. מנתח החמצן לא ברשת, ולכן הוא מבקש ממך ללחוץ "עכשיו" בשני הרגעים שחשובים - כשגשוש המרכז וגשוש הפינה מגיעים לראשונה ל-4.8 אחוז - ומחשב את הזמנים, את משך השטיפה, את זמן ההחזקה מעל 95 אחוז ואת המרווח מהשעון שלו.'],
    async run(c) {
      c.put('case', c.variant.case || null);
      const s0 = await P.idle(c);
      c.stage(1, 4, 'the supply and the chamber', 'ההזנה והתא');
      c.puts({
        n2_pressure: r2(num((s0.n2Pressure || {}).bar) === null ? num(s0.n2LinePressure) : num(s0.n2Pressure.bar)),
        chamber_temp: r2(num(s0.chamberTemp)),
        nitrogen_mode_enabled: true,
      });
      if (!c.known('n2_pressure')) await c.value('n2_pressure', 'N2 regulator pressure', 'לחץ וסת החנקן');
      await c.value('n2_flow', 'N2 flow from the flow meter', 'ספיקת החנקן ממד הספיקה');
      await c.value('chamber_volume', 'Chamber volume', 'נפח התא');
      await c.value('o2_reading_air', 'Analyser reading in air (span check)', 'קריאת המנתח באוויר (בדיקת טווח)');
      await c.value('program_purge_time_s', 'Configured nitrogen purge duration on this machine', 'משך שטיפת החנקן המוגדר במכונה הזו');

      c.stage(2, 4, 'purge', 'שטיפה');
      await c.ask('Chamber closed, both O2 probes in place. Press Done and the runner opens the valve.',
                  'התא סגור, שני גששי החמצן במקום. לחץ "בוצע" והרנר יפתח את השסתום.');
      c.put('purge_start_timestamp', stamp());
      const t0 = c.sec;
      await c.post('/api/cure/nitrogen?on=1');
      const sOpen = await c.state();
      c.puts({ damper_closed: sOpen.damperOpen === false, extraction_off: sOpen.ventOn === false && sOpen.bofaOn === false });
      const centre = await mark(c, 'Press Now the moment the CENTRE probe first reads O2 at or below 4.8 %.',
                                  'לחץ "עכשיו" ברגע שגשוש המרכז מגיע לראשונה לחמצן של 4.8 אחוז או פחות.');
      const corner = await mark(c, 'Press Now the moment the CORNER probe first reads O2 at or below 4.8 %.',
                                  'לחץ "עכשיו" ברגע שגשוש הפינה מגיע לראשונה לחמצן של 4.8 אחוז או פחות.');
      c.puts({
        n2_95_reached: centre.ok,
        time_to_95_n2: centre.ok ? r2(centre.sec - t0) : null,
        time_to_95_n2_corner: corner.ok ? r2(corner.sec - t0) : null,
      });
      c.say('purging 60 s past the 95 % point…', 'ממשיך לשטוף 60 שניות אחרי נקודת 95 האחוז…');
      await c.sleep(60);
      await c.value('o2_min_during_purge', 'Lowest O2 reached during the purge', 'החמצן הנמוך ביותר שהושג בשטיפה');
      const purgeEnd = c.sec;
      await c.post('/api/cure/nitrogen?on=0');
      const closed = await c.until((s) => s.nitrogenActive === false, { sec: 30, poll: 0.5 });
      c.puts({ purge_duration: r2(purgeEnd - t0), valve_closed_confirmed: closed.ok, hold_start_timestamp: stamp() });

      c.stage(3, 4, 'hold', 'החזקה');
      const holdFrom = c.sec;
      const rise = await mark(c, 'Press Now the moment the CENTRE probe rises back above 4.8 % (or after 60 minutes, whichever comes first).',
                                 'לחץ "עכשיו" ברגע שגשוש המרכז עולה חזרה מעל 4.8 אחוז (או אחרי 60 דקות, המוקדם מביניהם).');
      const hold = r2(rise.sec - holdFrom);
      c.put('hold_time_above_95', hold);
      const o2End = await c.value('o2_at_hold_end', 'O2 at the end of the hold', 'החמצן בסוף ההחזקה');
      const o2Min = num(c.rec.values.o2_min_during_purge);
      if (num(o2End) !== null && o2Min !== null && hold > 0) c.put('o2_rise_rate', r2((o2End - o2Min) / (hold / 60)));

      c.stage(4, 4, 'consumption and margin', 'צריכה ומרווח');
      const flow = num(c.rec.values.n2_flow), dur = num(c.rec.values.purge_duration), prog = num(c.rec.values.program_purge_time_s);
      const t95 = num(c.rec.values.time_to_95_n2);
      if (flow !== null && dur !== null) c.put('n2_consumed_l', r2(flow * dur / 60));
      if (prog !== null && t95 !== null && t95 > 0) c.put('purge_time_margin', r2(prog / t95));
      const longest = await c.value('longest_cure_after_purge_s', 'Longest cure that runs after a purge on this machine (sum of the UV steps)',
                                    'הקיור הארוך ביותר שרץ אחרי שטיפה במכונה הזו (סכום שלבי ה-UV)');
      if (num(longest) !== null && hold !== null) c.put('hold_covers_cure', hold >= longest);
      await P.allOff(c);
    },
  });

  def('DVT-GAS-001', {
    kind: 'guided', minutes: 30,
    intro: ['Nitrogen over-pressure interlock. You set the regulator; the runner reads the line pressure from the machine, tries to open the nitrogen above 3 bar (it must stay closed), opens it at the normal pressure, and times the valve closing when you raise the pressure while it flows. It records the alarm each time and asks you only what it cannot see: the screen button and the flow meter.',
            'הגנת לחץ-יתר בחנקן. אתה מכוון את הווסת; הרנר קורא את לחץ הקו מהמכונה, מנסה לפתוח את החנקן מעל 3 בר (הוא חייב להישאר סגור), פותח אותו בלחץ הרגיל, ומודד את סגירת השסתום כשאתה מעלה את הלחץ בזמן שהוא זורם. הוא רושם את ההתראה בכל פעם ושואל אותך רק את מה שהוא לא רואה: הלחצן במסך ומד הזרימה.'],
    async run(c) {
      const bar = (s) => num(s && s.n2Pressure ? s.n2Pressure.bar : s && s.n2LinePressure);
      const pressureWords = ['pressure', 'לחץ', 'bar', 'בר'];
      const open = async () => {
        await c.tryPost('/api/cure/nitrogen?on=1');
        return (await c.until((s) => s.nitrogenActive === true, { sec: 10, poll: 0.5 })).ok;
      };

      c.stage(1, 5, 'about 4 bar, valve closed', 'כ-4 בר, שסתום סגור');
      await P.idle(c);
      await c.ask('Set the nitrogen regulator to about 4 bar (above the 3 bar limit). Keep the nitrogen valve closed. Then press Done.',
                  'כוון את ווסת החנקן לכ-4 בר (מעל הגבול של 3 בר). השאר את שסתום החנקן סגור. ואז לחץ "בוצע".');
      const s1 = await c.state();
      const before = s1.alerts || [];
      if (bar(s1) !== null) c.put('applied_pressure_high', r2(bar(s1)));
      else await c.value('applied_pressure_high', 'Line pressure on the regulator gauge', 'לחץ הקו במד של הווסת');

      c.stage(2, 5, 'it must refuse to open', 'הוא חייב לסרב להיפתח');
      const opened = await open();
      await c.tryPost('/api/cure/nitrogen?on=0');
      c.put('n2_refused_at_high_pressure', !opened);
      await c.yesno('ui_refused', 'On the machine screen, try to switch the nitrogen on. Does it stay off (refused)?',
                    'במסך המכונה, נסה להפעיל את החנקן. האם הוא נשאר כבוי (מסרב)?');
      const a1 = await P.alarm(c, before, { sec: 30 });
      c.puts({ alarm_raised_high: a1.raised, error_code: a1.code === null ? null : String(a1.code), alarm_text: a1.text || null,
               alarm_names_pressure: P.names(a1.text, pressureWords) });

      c.stage(3, 5, 'normal pressure: it must open', 'לחץ רגיל: הוא חייב להיפתח');
      await c.ask('Lower the regulator to the normal working pressure (between 1 and 3 bar) and acknowledge the alarm on the screen if it is shown. Then press Done.',
                  'הורד את הווסת ללחץ העבודה הרגיל (בין 1 ל-3 בר) ואשר את ההתראה במסך אם היא מוצגת. ואז לחץ "בוצע".');
      const s3 = await c.state();
      if (bar(s3) !== null) c.put('normal_pressure', r2(bar(s3)));
      else await c.value('normal_pressure', 'Line pressure on the regulator gauge', 'לחץ הקו במד של הווסת');
      c.put('n2_opened_at_normal', await open());

      c.stage(4, 5, 'raise the pressure while it flows', 'העלאת הלחץ בזמן זרימה');
      const before2 = (await c.state()).alerts || [];
      await c.ask('Nitrogen is flowing. Raise the regulator to about 4 bar NOW, then press Done.',
                  'החנקן זורם. העלה את הווסת לכ-4 בר עכשיו, ואז לחץ "בוצע".');
      const closed = await c.until((s) => s.nitrogenActive === false, { sec: 30, poll: 0.2 });
      c.puts({ valve_closed_on_rise: closed.ok, close_time: closed.ok ? r2(closed.sec) : null });
      await c.yesno('flow_stopped_on_rise', 'Did the flow meter drop to zero?', 'האם מד הזרימה ירד לאפס?');
      const a2 = await P.alarm(c, before2, { sec: 30 });
      c.put('alarm_raised_on_rise', a2.raised);
      if (a2.text && !c.known('alarm_text')) c.put('alarm_text', a2.text);
      await c.tryPost('/api/cure/nitrogen?on=0');

      c.stage(5, 5, 'back to normal', 'חזרה לרגיל');
      await c.ask('Lower the regulator back to the normal pressure and acknowledge the alarm on the screen. Then press Done.',
                  'הורד את הווסת בחזרה ללחץ הרגיל ואשר את ההתראה במסך. ואז לחץ "בוצע".');
      c.put('n2_works_after', await open());
      await c.tryPost('/api/cure/nitrogen?on=0');
    },
  });

  def('DVT-GAS-002', {
    kind: 'guided', minutes: 35,
    intro: ['Four ways to lose the nitrogen supply, one per row. The runner does the machine side itself: it tries to enable nitrogen mode, reads back what the screen shows for the line pressure, tries to start a nitrogen program, and watches for the loss to be detected and for what the job then does. You only set the supply state the row calls for.',
            'ארבע דרכים לאבד את הזנת החנקן, אחת לכל שורה. הרנר עושה את צד המכונה בעצמו: מנסה לאפשר מצב חנקן, קורא מה המסך מראה על לחץ הקו, מנסה להתחיל תוכנית חנקן, וצופה בזיהוי האובדן ובמה שהעבודה עושה אז. אתה רק מגדיר את מצב ההזנה שהשורה דורשת.'],
    async run(c) {
      const kase = String(c.variant.case || 'A_no_supply_enable');
      c.put('case', c.variant.case || null);
      await P.idle(c);

      if (kase.indexOf('A') === 0) {
        c.stage(1, 2, 'below 0.5 bar: turning nitrogen on must be refused', 'מתחת ל-0.5 בר: הפעלת חנקן חייבת להידחות');
        await c.ask('Disconnect the nitrogen line (the line pressure must be below 0.5 bar), then press Done.',
                    'נתק את קו החנקן (לחץ הקו חייב להיות מתחת ל-0.5 בר), ואז לחץ "בוצע".');
        c.put('supply_state', 'line disconnected (below 0.5 bar)');
        const before = (await c.state()).alerts || [];
        const r = await c.post('/api/cure/nitrogen?on=1');
        if (r && r.ok === false && r.message) c.put('message_text', String(r.message));   // the refusal says why: no nitrogen supply
        const on = await c.until((s) => s.nitrogenActive === true, { sec: 20, poll: 0.5 });
        c.put('enable_refused', r.ok === false || !on.ok);
        const s = await c.state();
        const p = s.n2Pressure || {};
        c.put('pressure_display', p.bar === null || p.bar === undefined ? String(p.volts === undefined ? '—' : p.volts + ' V') : p.bar + ' bar');
        const a = await P.alarm(c, before, { sec: 30 });
        P.putAlarm(c, a);
        c.puts({ detected_and_handled: c.rec.values.enable_refused === true, cure_ran_in_air: false });
      } else if (kase.indexOf('B') === 0) {
        c.stage(1, 2, 'low pressure: the pre-cure check must refuse', 'לחץ נמוך: בדיקת הקדם-קיור חייבת לדחות');
        await c.ask('Set the supply to about 0.3 bar (below the 0.5 bar minimum), then press Done.',
                    'כוון את ההזנה לכ-0.3 בר (מתחת למינימום של 0.5 בר), ואז לחץ "בוצע".');
        c.put('supply_state', 'about 0.3 bar');
        const before = (await c.state()).alerts || [];
        const r = await c.postJson('/api/recipe/start', program('gas-003b', [
          { step: 1, process: 'Nitrogen', time: 2 }, { step: 2, process: 'Cure', time: 2, uvIntensity: 30 }]));
        const ran = r.ok === true && (await c.until((s) => s.nitrogenActive === true || s.uvOn === true, { sec: 25, poll: 0.5 })).ok;
        await P.allOff(c);
        c.put('precure_refused', !ran);
        const a = await P.alarm(c, before, { sec: 30 });
        P.putAlarm(c, a);
        c.puts({ detected_and_handled: !ran, cure_ran_in_air: ran });
      } else {
        const mid = kase.indexOf('C') === 0;
        c.stage(1, 2, mid ? 'supply closed mid-purge' : 'supply closed mid-cure', mid ? 'ההזנה נסגרת באמצע השטיפה' : 'ההזנה נסגרת באמצע הקיור');
        c.put('supply_state', mid ? 'closed 30 s into the purge' : 'closed during the cure');
        const before = (await c.state()).alerts || [];
        const r = await c.postJson('/api/recipe/start', program('gas-003cd', [
          { step: 1, process: 'Nitrogen', time: 3 }, { step: 2, process: 'Cure', time: 10, uvIntensity: 50, wavelength: 405 }]));
        if (r.ok === false) throw new Error(r.message || A.L('the machine refused the program', 'המכונה דחתה את התוכנית'));
        const wait = mid ? (await c.until((s) => s.nitrogenActive === true, { sec: 120, poll: 1 }))
                         : (await c.until((s) => s.uvOn === true, { sec: 600, poll: 2 }));
        if (!wait.ok) throw new Error(A.L('the program never reached the step under test', 'התוכנית לא הגיעה לשלב הנבדק'));
        if (mid) await c.sleep(30);
        await c.ask('Close the nitrogen supply NOW, then press Done.', 'סגור עכשיו את הזנת החנקן, ואז לחץ "בוצע".');
        const t0 = c.sec;
        const rows = [];
        let detectedAt = null;
        await c.watch({ sec: 600, hz: 1, into: rows,
          on: (s, at) => {
            if (detectedAt === null && P.fresh(before, s).length) detectedAt = r2(c.sec - t0);
            c.say(`after the loss · ${at} s${detectedAt !== null ? ' · detected at ' + detectedAt + ' s' : ''}`,
                  `אחרי האובדן · ${at} שניות${detectedAt !== null ? ' · זוהה ב-' + detectedAt + ' שניות' : ''}`);
            return detectedAt !== null && at > detectedAt + 60 ? 'stop' : undefined;
          } });
        c.trace('loss', rows);
        const sNow = await c.state();
        const rs = await c.get('/api/recipe/status').catch(() => null);
        const st = rs ? String(rs.state || '').toLowerCase() : '';
        c.puts({
          loss_detected: detectedAt !== null, detection_time: detectedAt,
          job_handling: st.indexOf('error') >= 0 || st.indexOf('abort') >= 0 ? 'abort' : st.indexOf('pause') >= 0 ? 'prompt' : 'continue',
        });
        const a = await P.alarm(c, before, { sec: 5 });
        P.putAlarm(c, a);
        await c.value('o2_at_end_of_cure', 'O2 at the end of the cure step', 'החמצן בסוף שלב הקיור');
        const o2 = num(c.rec.values.o2_at_end_of_cure);
        c.puts({
          cure_ran_in_air: o2 !== null ? o2 > 4.8 && sNow.uvOn === false && st.indexOf('error') < 0 : null,
          detected_and_handled: detectedAt !== null && (st.indexOf('error') >= 0 || st.indexOf('abort') >= 0 || st.indexOf('pause') >= 0),
        });
        await P.allOff(c);
      }

      c.stage(2, 2, 'was the operator told?', 'האם נאמר למפעיל?');
      const text = c.rec.values.alarm_text || c.rec.values.message_text || '';
      c.puts({
        alarm_names_n2_line: P.names(text, ['nitrogen', 'חנקן', 'N2', 'line', 'קו', 'supply', 'הזנה']),
        operator_told_n2_line: P.names(text, ['nitrogen', 'חנקן', 'N2']),
      });
      if (!c.known('message_text')) await c.value('message_text', 'What did the screen say?', 'מה כתב המסך?');
    },
  });

  def('DVT-GAS-003', {
    kind: 'guided', minutes: 750, autoRecord: false,
    intro: ['Nitrogen leak-down. You charge the line to about 4 bar and isolate it; the machine keeps the valve closed and the runner logs the line pressure it reads once a minute for 12 hours, then works out the drop and the drop per hour.',
            'בדיקת דליפה בחנקן. אתה טוען את הקו לכ-4 בר ומבודד אותו; המכונה משאירה את השסתום סגור והרנר רושם את לחץ הקו שהיא קוראת פעם בדקה במשך 12 שעות, ואז מחשב את הירידה ואת הירידה לשעה.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 3, 'charge and isolate', 'טעינה ובידוד');
      await c.ask('Charge the nitrogen line to about 4 bar (the valve stays closed), then close the shut-off valve at the supply so the line is isolated. Press Done.',
                  'טען את קו החנקן לכ-4 בר (השסתום נשאר סגור), ואז סגור את ברז הסגירה בהזנה כך שהקו מבודד. לחץ "בוצע".');
      const p0 = n2bar(await c.state());
      if (p0 === null) throw new Error(A.L('the machine does not read the N2 line pressure - the leak-down needs it', 'המכונה לא קוראת את לחץ קו החנקן - בדיקת הדליפה צריכה אותו'));
      c.put('start_pressure', r2(p0));

      c.stage(2, 3, '12 hours of logging', '12 שעות רישום');
      const rows = [];
      const t0 = c.sec;
      let last = p0;
      while (c.sec - t0 < 12 * 3600) {
        const s = await c.state().catch(() => null);
        const b = n2bar(s);
        if (b !== null) last = b;
        rows.push([r2(c.sec - t0), b]);
        const h = (c.sec - t0) / 3600;
        c.say(`leak-down · ${h.toFixed(1)} / 12 h · ${r2(last)} bar (drop ${r2(p0 - last)} bar)`,
              `בדיקת דליפה · ${h.toFixed(1)} / 12 שעות · ${r2(last)} בר (ירידה ${r2(p0 - last)} בר)`);
        await c.sleep(60);
      }
      c.trace('leak_down', { columns: ['t_s', 'n2_bar'], samples: rows });
      const hours = r2((c.sec - t0) / 3600);
      c.puts({ end_pressure: r2(last), pressure_drop: r2(p0 - last), drop_per_hour: hours ? r2((p0 - last) / hours) : null, hours_logged: hours });

      c.stage(3, 3, 'where does it leak?', 'היכן הדליפה?');
      const leaked = await c.yesno('leak_found', 'If the pressure dropped: bubble-test every fitting from the inlet to the valve. Did you find a leak?',
                                   'אם הלחץ ירד: בדוק בבועות כל מחבר מהכניסה עד השסתום. האם מצאת דליפה?');
      if (leaked === true) await c.value('leak_location', 'Where does it leak?', 'היכן זה דולף?');
      await c.ask('Vent the line and return the supply to the normal working pressure (1 to 3 bar). Press Done.',
                  'שחרר את הלחץ מהקו והחזר את ההזנה ללחץ העבודה הרגיל (1 עד 3 בר). לחץ "בוצע".');
    },
  });

  def('DVT-GAS-004', {
    kind: 'instrumented', minutes: 40, autoRecord: false,
    intro: ['A nitrogen program with no vent step must be refused - the runner submits exactly that and records the refusal and its code. It then runs the full program with the vent and keeps the clock while you watch the analyser, so the time from the end of the cure to safe O2 comes from its clock and not from your stopwatch.',
            'תוכנית חנקן בלי שלב אוורור חייבת להידחות - הרנר מגיש בדיוק את זה ורושם את הסירוב ואת הקוד שלו. אחר כך הוא מריץ את התוכנית המלאה עם האוורור ומנהל את השעון בזמן שאתה צופה במנתח, כך שהזמן מסוף הקיור עד חמצן בטוח מגיע מהשעון שלו ולא משעון העצר שלך.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 3, 'a program without a vent must be refused', 'תוכנית בלי אוורור חייבת להידחות');
      const before = (await c.state()).alerts || [];
      const r = await c.postJson('/api/recipe/start', program('gas-005-novent', [
        { step: 1, process: 'Nitrogen', time: 2 }, { step: 2, process: 'Cure', time: 3, uvIntensity: 30, wavelength: 405 }]));
      const ran = r.ok === true && (await c.until((s) => s.nitrogenActive === true || s.uvOn === true, { sec: 25, poll: 0.5 })).ok;
      await P.allOff(c);
      c.put('program_without_vent_refused', !ran);
      const a = await P.alarm(c, before, { sec: 20 });
      if (a.code !== null) c.put('error_code', String(a.code));
      else if (r.code) c.put('error_code', String(r.code));
      c.note(`refusal: ${r.message || '(none)'}`);

      c.stage(2, 3, 'the full program', 'התוכנית המלאה');
      const r2ok = await c.postJson('/api/recipe/start', program('gas-005', [
        { step: 1, process: 'Nitrogen', time: 2 },
        { step: 2, process: 'Cure', time: 5, uvIntensity: 50, wavelength: 405 },
        { step: 3, process: 'Cooling', time: 10, temperature: 30 }]));
      if (r2ok.ok === false) throw new Error(r2ok.message || A.L('the machine refused the vented program', 'המכונה דחתה את התוכנית עם האוורור'));
      const cureEnd = await c.until((s) => s.uvOn === false && s.recipe && String(s.recipe.state).toLowerCase() !== 'idle',
        { sec: 3600, poll: 2, tick: (s, at) => c.say(`program · ${mmss_(at)}`, `תוכנית · ${mmss_(at)}`) });
      const tCureEnd = c.sec;
      const done = await c.until((s) => !s.recipe || String(s.recipe.state).toLowerCase() === 'idle', { sec: 3600, poll: 2 });

      c.stage(3, 3, 'venting', 'אוורור');
      await c.value('o2_at_job_complete', 'Chamber O2 at the moment the job reported complete', 'החמצן בתא ברגע שהעבודה דיווחה על סיום');
      const safe = await mark(c, 'Press Now the moment the chamber O2 first reaches 19.5 %.',
                                 'לחץ "עכשיו" ברגע שהחמצן בתא מגיע לראשונה ל-19.5 אחוז.');
      c.put('time_to_o2_safe', safe.ok ? r2(safe.sec - tCureEnd) : null);
      await c.yesno('door_released_before_safe', 'Was the door released before the chamber O2 reached 19.5 %?',
                    'האם הדלת שוחררה לפני שהחמצן בתא הגיע ל-19.5 אחוז?');
      await c.value('o2_at_door_opening', 'O2 at the moment the door was opened', 'החמצן ברגע שהדלת נפתחה');
      await P.allOff(c);
    },
  });

  def('DVT-GAS-005', {
    kind: 'instrumented', minutes: 90, autoRecord: false,
    intro: ['Room depletion. The runner runs the longest nitrogen program the software allows twice back to back and keeps the clock from the first purge, so the time of the minimum is measured against its clock. The analyser readings are yours.',
            'דלדול חמצן בחדר. הרנר מריץ את תוכנית החנקן הארוכה ביותר שהתוכנה מאפשרת פעמיים ברצף ומנהל את השעון מהשטיפה הראשונה, כך שזמן המינימום נמדד מול השעון שלו. קריאות המנתח הן שלך.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 3, 'the room', 'החדר');
      await c.value('room_volume', 'Room volume', 'נפח החדר');
      await c.value('ventilation_state', 'Ventilation state', 'מצב האוורור');
      // the room's own O2 before any nitrogen, as the reference the drop is measured from (user, 2026-10-25)
      await c.value('o2_reference', 'Reference: O2 at the breathing zone now, before any nitrogen is released',
                    'ייחוס: החמצן באזור הנשימה עכשיו, לפני שמשתחרר חנקן כלשהו');

      c.stage(2, 3, 'two maximum purges back to back', 'שתי שטיפות מקסימליות ברצף');
      const t0 = c.sec;
      for (let i = 0; i < 2; i++) {
        const r = await c.postJson('/api/recipe/start', program('gas-006', [
          { step: 1, process: 'Nitrogen', time: 5 }, { step: 2, process: 'Nitrogen', time: 5 }]));
        if (r.ok === false) throw new Error(r.message || A.L('the machine refused the purge program', 'המכונה דחתה את תוכנית השטיפה'));
        await c.until((s) => !s.recipe || String(s.recipe.state).toLowerCase() === 'idle',
          { sec: 3600, poll: 3, tick: (s, at) => c.say(`purge ${i + 1}/2 · ${mmss_(at)}`, `שטיפה ${i + 1}/2 · ${mmss_(at)}`) });
      }
      const lastPurge = c.sec;

      c.stage(3, 3, 'the breathing zone', 'אזור הנשימה');
      const min = await mark(c, 'Press Now at the moment the breathing-zone O2 reaches its minimum.',
                                'לחץ "עכשיו" ברגע שהחמצן באזור הנשימה מגיע למינימום שלו.');
      c.put('time_of_min', min.ok ? r2((min.sec - t0) / 60) : null);
      await c.value('o2_min_breathing_zone', 'Minimum O2 in the breathing zone', 'החמצן המינימלי באזור הנשימה');
      const ref = num(c.rec.values.o2_reference), low = num(c.rec.values.o2_min_breathing_zone);
      if (ref !== null && low !== null) c.put('o2_drop', r2(ref - low));
      await c.value('n2_released', 'N2 released over the two programs', 'כמות החנקן ששוחררה בשתי התוכניות');
      c.say('waiting 60 minutes from the last purge…', 'ממתין 60 דקות מהשטיפה האחרונה…');
      while (c.sec - lastPurge < 3600) { c.say(`waiting · ${mmss_(c.sec - lastPurge)} / 60:00`, `ממתין · ${mmss_(c.sec - lastPurge)} / 60:00`); await c.sleep(10); }
      await c.value('o2_after_60min', 'O2 sixty minutes after the last purge', 'החמצן שישים דקות אחרי השטיפה האחרונה');
    },
  });

  // ==========================================================================
  // NFC, transport and the electrical bench
  // ==========================================================================

  const n2bar = (s) => num(s && s.n2Pressure ? s.n2Pressure.bar : s && s.n2LinePressure);

  def('DVT-GAS-006', {
    kind: 'guided', minutes: 20,
    intro: ['Nitrogen that does not reach the chamber. You block the tube after the valve; the runner opens the nitrogen and watches the machine notice that the line pressure did not drop - the alarm, how long it took, and that the valve was closed. Then you remove the block and it opens again to record the normal pressure drop with no alarm.',
            'חנקן שלא מגיע לתא. אתה חוסם את הצינור אחרי השסתום; הרנר פותח את החנקן וצופה במכונה מזהה שלחץ הקו לא ירד - ההתראה, כמה זמן זה לקח, ושהשסתום נסגר. אחר כך אתה מסיר את החסימה והוא פותח שוב כדי לרשום את ירידת הלחץ הרגילה בלי התראה.'],
    async run(c) {
      await P.idle(c);
      c.stage(1, 3, 'block the path', 'חסימת המסלול');
      await c.ask('Block the tube between the nitrogen valve and the chamber (clamp or plug). Keep the supply at the normal working pressure (1 to 3 bar). Press Done.',
                  'חסום את הצינור בין שסתום החנקן לתא (מלחציים או פקק). השאר את ההזנה בלחץ העבודה הרגיל (1 עד 3 בר). לחץ "בוצע".');
      const s1 = await c.state();
      const before = s1.alerts || [];
      if (n2bar(s1) !== null) c.put('pressure_before', r2(n2bar(s1)));

      c.stage(2, 3, 'open: the machine must notice', 'פתיחה: המכונה חייבת לזהות');
      await c.tryPost('/api/cure/nitrogen?on=1');
      const a = await P.alarm(c, before, { sec: 30, poll: 0.2 });
      const sA = await c.state();
      c.puts({ blocked_alarm_raised: a.raised, detection_time: a.raised ? r2(a.sec) : null,
               error_code: a.code === null ? null : String(a.code), alarm_text: a.text || null,
               alarm_names_n2: P.names(a.text, ['nitrogen', 'חנקן', 'N2', 'flow', 'זרימה']),
               valve_closed_after_alarm: sA.nitrogenActive === false });
      await c.tryPost('/api/cure/nitrogen?on=0');

      c.stage(3, 3, 'path open: no alarm', 'מסלול פתוח: בלי התראה');
      await c.ask('Remove the block and acknowledge the alarm on the screen. Press Done.',
                  'הסר את החסימה ואשר את ההתראה במסך. לחץ "בוצע".');
      const s3 = await c.state();
      const before3 = s3.alerts || [];
      const p0 = n2bar(s3);
      await c.tryPost('/api/cure/nitrogen?on=1');
      await c.sleep(5);
      const p5 = n2bar(await c.state());
      if (p0 !== null && p5 !== null) c.put('normal_drop_bar', r2(p0 - p5));
      const a3 = await P.alarm(c, before3, { sec: 15 });
      c.put('normal_no_alarm', !a3.raised);
      await c.tryPost('/api/cure/nitrogen?on=0');
    },
  });

  def('DVT-NFC-001', {
    kind: 'guided', minutes: 12,
    intro: ['The runner watches the reader itself. You seat the build head; from that press it polls the NFC reader until a tag appears, takes the detection time and the serial it reports, then starts a print step to see whether that serial is bound or the start is refused with a reason, and finally watches the identity clear when you take the build head out.',
            'הרנר צופה בקורא בעצמו. אתה מכניס את ראש הבנייה; מרגע הלחיצה הוא דוגם את קורא ה-NFC עד שמופיע תג, לוקח את זמן הזיהוי ואת המספר הסידורי שהוא מדווח, אחר כך מתחיל שלב הדפסה כדי לראות האם המספר נקשר או שההתחלה נדחית עם סיבה, ולבסוף צופה בזיהוי מתנקה כשאתה מוציא את ראש הבנייה.'],
    async run(c) {
      const kase = String(c.variant.case || 'A_registered_bh');
      c.put('case', c.variant.case || null);
      await P.idle(c);
      c.stage(1, 4, 'the build head', 'ראש הבנייה');
      await c.value('bh_serial_expected', 'Serial printed on the tag of the build head you are about to insert',
                    'המספר הסידורי המודפס על התג של ראש הבנייה שאתה עומד להכניס');
      if (kase.indexOf('E') === 0) await c.value('seating_offset_mm', 'Measured seating offset', 'סטיית ההושבה שנמדדה');
      else c.put('seating_offset_mm', 0);

      c.stage(2, 4, 'insert it', 'הכנס אותו');
      const before = (await c.state()).alerts || [];
      await c.ask('Insert the build head to its stop, close the door, then press Done.',
                  'הכנס את ראש הבנייה עד הסוף, סגור את הדלת, ולחץ "בוצע".');
      const t0 = c.sec;
      let tag = null;
      while (c.sec - t0 < 60) {
        const n = await c.get('/api/nfc').catch(() => null);
        const s = await c.state();
        const serial = (n && n.reader && n.reader.serial) || (s.nfcReader && s.nfcReader.serial) || null;
        c.say(`waiting for a tag · ${r2(c.sec - t0)} s`, `ממתין לתג · ${r2(c.sec - t0)} שניות`);
        if (serial) { tag = { serial, at: r2(c.sec - t0), reader: n && n.reader }; break; }
        await c.sleep(0.5);
      }
      c.puts({ tag_read: !!tag, detection_time: tag ? tag.at : null, bh_serial_read: tag ? String(tag.serial) : null });
      if (tag) c.trace('nfc', tag);
      const a = await P.alarm(c, before, { sec: 15 });
      if (a.code !== null) c.put('error_code', String(a.code));
      if (a.text) c.put('message_text', a.text);
      await c.yesno('operator_shown_identity', 'Does the screen show the build head identity (or the message for a missing / unknown tag)?',
                    'האם המסך מציג את זהות ראש הבנייה (או את ההודעה לתג חסר או לא מוכר)?');
      if (!c.known('message_text')) await c.value('message_text', 'What does the screen say?', 'מה כתוב על המסך?');

      c.stage(3, 4, 'a print step', 'שלב הדפסה');
      const r = await c.postJson('/api/recipe/start', program('nfc-001', [{ step: 1, process: 'Cure', time: 1, uvIntensity: 30 }]));
      const started = r.ok === true && (await c.until((s) => s.uvOn === true, { sec: 20, poll: 0.5 })).ok;
      await P.allOff(c);
      c.puts({ bound_to_print: started && !!tag, start_refused_with_reason: !started && !!(r.message || r.code) });
      if (!started) c.note(`start refused: ${r.message || r.code || '(no reason given)'}`);

      c.stage(4, 4, 'remove it', 'הוצא אותו');
      await c.ask('Remove the build head, then press Done.', 'הוצא את ראש הבנייה, ואז לחץ "בוצע".');
      const cleared = await c.until((s) => !(s.nfcReader && s.nfcReader.serial), { sec: 60, poll: 1 });
      c.put('identity_cleared_on_removal', cleared.ok);
      const expected = c.rec.values.bh_serial_expected;
      const read = c.rec.values.bh_serial_read;
      const wants = { A: !!read && read === expected, B: !!read && read === expected, C: !read, D: !!read && read !== expected,
                      E: true, F: !c.rec.values.bound_to_print };
      const key = kase.charAt(0).toUpperCase();
      c.put('response_correct', wants[key] === undefined ? null : wants[key]);
      if (!c.known('response_correct'))
        await c.yesno('response_correct', 'Did the system respond as this case requires?', 'האם המערכת הגיבה כפי שהמקרה הזה דורש?');
    },
  });

  def('DVT-ENV-001', {
    kind: 'guided', minutes: 30, autoRecord: false,
    intro: ['The shipment happens away from the tool. What the runner does is the two ends: the full functional acceptance before the crate is closed and the same one after it is opened, both measured on the machine, so the comparison is like for like. The route, the indicators and the inspection are yours.',
            'המשלוח קורה הרחק מהכלי. מה שהרנר עושה הוא שני הקצוות: בדיקת הקבלה הפונקציונלית המלאה לפני סגירת הארגז ואותה בדיקה אחרי הפתיחה, שתיהן נמדדות על המכונה, כך שההשוואה היא בין שווים. המסלול, המחוונים והבדיקה הוויזואלית הם שלך.'],
    async run(c) {
      c.stage(1, 3, 'before the crate is closed', 'לפני סגירת הארגז');
      const pre = await P.selfCheck(c);
      c.trace('pre_ship', pre);
      c.put('pre_ship_functional_pass', pre.pass);
      await c.ask('Install the data logger and the indicators, record their positions, close the crate and ship. Press Done when the unit is back and unpacked.',
                  'התקן את הרשם ואת המחוונים, רשום את מיקומם, סגור את הארגז ושלח. לחץ "בוצע" כשהיחידה חזרה ונפרקה.');

      c.stage(2, 3, 'the crate and the unit', 'הארגז והיחידה');
      await c.value('route', 'Route', 'מסלול');
      await c.value('distance_km', 'Distance', 'מרחק');
      await c.value('transit_days', 'Transit days', 'ימי מעבר');
      await c.yesno('impact_indicator_triggered', 'Did the impact indicator trigger?', 'האם מחוון המכה הופעל?');
      await c.yesno('tilt_indicator_triggered', 'Did the tilt indicator trigger?', 'האם מחוון ההטיה הופעל?');
      await c.yesno('crate_damage', 'Is the crate damaged?', 'האם הארגז ניזוק?');
      await c.yesno('glass_broken', 'Is any glass broken?', 'האם זכוכית כלשהי שבורה?');
      await c.yesno('glass_cracked_or_chipped', 'Is any glass cracked or chipped?', 'האם זכוכית כלשהי סדוקה או פגומה?');
      await c.value('loose_fasteners', 'How many fasteners are loose?', 'כמה מחברים רופפים?');
      await c.value('connector_dislodged', 'How many connectors are dislodged?', 'כמה מחברים יצאו ממקומם?');
      await c.value('visible_damage', 'Visible damage (write none if there is none)', 'נזק גלוי (כתוב "אין" אם אין)');
      await c.value('peak_g_x', 'Peak acceleration, X', 'תאוצת שיא, ציר X');
      await c.value('peak_g_y', 'Peak acceleration, Y', 'תאוצת שיא, ציר Y');
      await c.value('peak_g_z', 'Peak acceleration, Z', 'תאוצת שיא, ציר Z');

      c.stage(3, 3, 'after the shipment', 'אחרי המשלוח');
      const post = await P.selfCheck(c);
      c.trace('post_ship', post);
      c.put('post_ship_functional_pass', post.pass);
      const diffs = [];
      for (const k of ['sensorsOk', 'fansOk', 'heaterResponds', 'ledOk'])
        if (pre[k] !== post[k]) diffs.push(`${k}: ${pre[k]} -> ${post[k]}`);
      c.put('deviations_from_baseline', diffs.length ? diffs.join('; ') : 'none');
    },
  });

  const eleIntro = ['The unit sits on a safety-test bench for this test, so the runner does not drive it. It walks the measurements in the catalog order and keeps each one with its timestamp, so nothing is written down twice or out of order.',
                    'היחידה נמצאת על שולחן בדיקות בטיחות בבדיקה הזו, ולכן הרנר לא מפעיל אותה. הוא מוביל את המדידות לפי סדר הקטלוג ושומר כל אחת עם חותמת זמן, כך ששום דבר לא נרשם פעמיים או מחוץ לסדר.'];

  def('DVT-ELE-001', {
    kind: 'instrumented', minutes: 20, needs: 'none', autoRecord: false, intro: eleIntro,
    async run(c) {
      await c.value('test_current', 'Test current used', 'זרם הבדיקה שהופעל');
      await c.value('protective_device_rating', 'Rating of the upstream protective device', 'דירוג התקן ההגנה במעלה הזרם');
      await c.ask('Measure from the PE pin of the inlet to each listed accessible conductive part in turn, one minute per point.',
                  'מדוד מפין ההארקה של הכניסה לכל חלק מוליך נגיש ברשימה בתורו, דקה לכל נקודה.');
      await c.value('part_name', 'Part with the highest reading', 'החלק עם הקריאה הגבוהה ביותר');
      const r = await c.value('measured_resistance', 'Its measured resistance', 'ההתנגדות שנמדדה בו');
      if (num(r) !== null) c.put('max_resistance', r);
      await c.value('worst_point', 'Where the highest resistance occurred', 'היכן הייתה ההתנגדות הגבוהה ביותר');
      await c.yesno('pe_uninterrupted', 'Is the PE conductor uninterrupted by any switch or fuse?',
                    'האם מוליך ההארקה אינו מנותק על ידי מתג או נתיך כלשהו?');
    },
  });

  def('DVT-ELE-002', {
    kind: 'instrumented', minutes: 10, needs: 'none', autoRecord: false, intro: eleIntro,
    async run(c) {
      await c.ask('Short L and N together at the inlet and apply 500 Vdc between the shorted L+N and PE for 60 s.',
                  'קצר בין L ל-N בכניסה והפעל 500 וולט DC בין L+N המקוצרים לבין ההארקה למשך 60 שניות.');
      await c.value('insulation_resistance_lnpe', 'Insulation resistance L+N to PE', 'התנגדות הבידוד בין L+N להארקה');
      await c.value('ambient_temp', 'Ambient temperature', 'טמפרטורת הסביבה');
      await c.value('ambient_rh', 'Relative humidity', 'לחות יחסית');
    },
  });

  def('DVT-ELE-003', {
    kind: 'instrumented', minutes: 30, needs: 'none', autoRecord: false, intro: eleIntro,
    async run(c) {
      await c.value('test_voltage', 'Test voltage', 'מתח הבדיקה');
      await c.value('waveform', 'Waveform', 'צורת הגל');
      await c.value('dwell_time', 'Dwell time', 'זמן ההחזקה');
      await c.value('trip_current_setting', 'Trip current setting', 'הגדרת זרם הניתוק');
      await c.value('clause_reference', 'Clause these derive from', 'הסעיף שממנו אלה נגזרים');
      await c.ask('Apply between the shorted mains conductors and PE / accessible parts.',
                  'הפעל בין מוליכי הרשת המקוצרים לבין ההארקה והחלקים הנגישים.');
      await c.yesno('breakdown', 'Was there a breakdown?', 'האם היה כשל בידוד?');
      await c.value('leakage_current_at_voltage', 'Leakage current at the test voltage', 'זרם הדליפה במתח הבדיקה');
      await c.value('barrier_name', 'Additional insulation barrier tested', 'מחסום הבידוד הנוסף שנבדק');
      await c.yesno('barrier_breakdown', 'Did that barrier break down?', 'האם המחסום הזה כשל?');
      await c.value('post_hipot_insulation_resistance', 'Insulation resistance after the hipot', 'התנגדות הבידוד אחרי בדיקת המתח הגבוה');
    },
  });

  def('DVT-ELE-004', {
    kind: 'instrumented', minutes: 20, needs: 'none', autoRecord: false, intro: eleIntro,
    async run(c) {
      await c.value('touch_current_normal_max', 'Touch current in normal condition, worst polarity', 'זרם המגע במצב תקין, בקוטביות הגרועה');
      await c.value('touch_current_pe_open', 'Touch current with PE open', 'זרם המגע כשההארקה מנותקת');
      await c.value('load_condition', 'Load condition of the worst case', 'מצב העומס במקרה הגרוע');
      const a = num(c.rec.values.touch_current_normal_max), b = num(c.rec.values.touch_current_pe_open);
      if (a !== null && b !== null) c.put('touch_current_worst', Math.max(a, b));
      else await c.value('touch_current_worst', 'Worst-case touch current', 'זרם המגע במקרה הגרוע');
    },
  });

  def('DVT-ELE-005', {
    kind: 'instrumented', minutes: 45, autoRecord: false,
    intro: ['The runner puts the machine into each operating mode for you - idle, heat only, cure only, and everything at once - and waits for it to be genuinely in that mode before asking for the power-analyser reading, so each number belongs to the mode it is labelled with. Inrush is captured on your analyser.',
            'הרנר מכניס עבורך את המכונה לכל מצב עבודה - מנוחה, חימום בלבד, קיור בלבד, והכול יחד - וממתין שהיא באמת תהיה במצב הזה לפני שהוא מבקש את קריאת מנתח ההספק, כך שכל מספר שייך למצב שהוא מתויג בו. זרם ההתנעה נקלט במנתח שלך.'],
    async run(c) {
      if (c.variant.mains_voltage !== undefined) c.put('mains_voltage', Number(c.variant.mains_voltage));
      await c.value('selector_position', 'Selector position', 'מצב הבורר');
      await c.value('applied_voltage', 'Voltage measured at the inlet', 'המתח שנמדד בכניסה');
      await P.idle(c);

      c.stage(1, 5, 'idle', 'מנוחה');
      await c.sleep(30);
      await c.value('input_power_idle', 'Input power in standby', 'הספק הכניסה במצב המתנה');

      c.stage(2, 5, 'heat only', 'חימום בלבד');
      await c.post('/api/cure/heat?target=80');
      const full = await c.until((s) => num(s.heaterPwm) >= 90, { sec: 600, poll: 2,
        tick: (s, at) => c.say(`waiting for full heater output · ${at} s · ${r1(s && num(s.heaterPwm))} %`,
                               `ממתין למוצא היטר מלא · ${at} שניות · ${r1(s && num(s.heaterPwm))} אחוז`) });
      if (!full.ok) c.note('the heater never reached 90 % output - the reading below is at the output it did reach');
      await c.value('input_current_heat', 'Input current, heat only', 'זרם הכניסה, חימום בלבד');
      await c.value('input_power_heat', 'Input power, heat only', 'הספק הכניסה, חימום בלבד');
      await c.value('power_factor_heat', 'Power factor, heat only', 'מקדם ההספק, חימום בלבד');
      await c.tryPost('/api/chamber/stop');

      c.stage(3, 5, 'cure only', 'קיור בלבד');
      c.say('letting the chamber fall back to ambient…', 'ממתין שהתא יחזור לטמפרטורת הסביבה…');
      await c.post('/api/cure/cool?target=30&mode=fast');
      await c.until((s) => num(s.chamberTemp) !== null && num(s.chamberTemp) <= 32, { sec: 3600, poll: 5,
        tick: (s, at) => c.say(`cooling · ${r1(s && num(s.chamberTemp))} °C`, `מתקרר · ${r1(s && num(s.chamberTemp))} °C`) });
      await c.tryPost('/api/cure/stop?immediate=1');
      await c.post('/api/cure/uv-only?intensity=100&wavelength=405');
      await c.until((s) => s.uvOn === true, { sec: 120, poll: 1 });
      await c.sleep(30);
      await c.value('input_current_cure', 'Input current, cure only', 'זרם הכניסה, קיור בלבד');
      await c.value('input_power_cure', 'Input power, cure only', 'הספק הכניסה, קיור בלבד');
      await c.value('power_factor_cure', 'Power factor, cure only', 'מקדם ההספק, קיור בלבד');

      c.stage(4, 5, 'everything at once', 'הכול יחד');
      await c.post('/api/cure/heat?target=80');
      await c.until((s) => s.uvOn === true && num(s.heaterPwm) >= 90, { sec: 900, poll: 2,
        tick: (s, at) => c.say(`waiting for heater and LEDs together · ${at} s`, `ממתין להיטר ולדים יחד · ${at} שניות`) });
      await c.value('input_current_all', 'Worst-case input current, everything working', 'זרם הכניסה הגרוע ביותר, הכול פועל');
      await c.value('input_power_all', 'Worst-case input power', 'הספק הכניסה הגרוע ביותר');
      await c.value('power_factor_all', 'Power factor, everything working', 'מקדם ההספק, הכול פועל');
      await P.allOff(c);

      c.stage(5, 5, 'inrush and the label', 'זרם התנעה והתווית');
      await c.ask('From cold, switch the unit on at least three times at the worst-case phase angle and capture the inrush.',
                  'ממצב קר, הדלק את היחידה לפחות שלוש פעמים בזווית הפאזה הגרועה ביותר וקלוט את זרם ההתנעה.');
      await c.value('inrush_switch_ons', 'How many switch-ons were captured?', 'כמה הדלקות נקלטו?');
      await c.value('inrush_peak', 'Worst peak inrush current', 'זרם ההתנעה המרבי הגרוע ביותר');
      await c.value('inrush_duration', 'Its duration', 'משך הזמן שלו');
      await c.value('i2t', 'I2t of the worst switch-on', 'ה-I2t של ההדלקה הגרועה ביותר');
      await c.yesno('fuse_margin_ok', 'Is there margin against the inlet fuse rating?', 'האם יש מרווח מול דירוג נתיך הכניסה?');
      await c.yesno('breaker_type_b_ok', 'Does it pass a type B 16 A breaker characteristic?', 'האם זה עובר מאפיין מפסק טיפוס B של 16 אמפר?');
      await c.yesno('breaker_type_c_ok', 'Does it pass a type C 16 A breaker characteristic?', 'האם זה עובר מאפיין מפסק טיפוס C של 16 אמפר?');
      await c.yesno('label_agreement', 'Do the whole-machine current and power agree with the rating label?',
                    'האם הזרם וההספק של המכונה כולה תואמים לתווית הדירוג?');
    },
  });
})();

// ============================================================================
// Reading a finished TC-08 recording. The operator drives the heater in hardware
// for these rows - the machine has no command for it - so the log the TC-08 wrote
// is the only record of what happened, and every number the test asks for that the
// log actually determines is taken from it rather than typed in afterwards.
// ============================================================================

(function () {
  const A = window.DVT_AUTO, P = A.P;
  const r2 = (v) => (v === null || v === undefined ? null : Math.round(v * 100) / 100);
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);

  // tc08_record row: [t_s, ch1_c, machine_chamber_c, machine_heating, alerts, heater_commanded, heater_pwm_pct]
  const T = 0, CH1 = 1, CHAMBER = 2, HEATING = 3, ALERTS = 4, CMD = 5, PWM = 6;

  /**
   * What the machine's own protection did while the temperature ran away.
   * With the heater driven externally the machine cannot stop the heat - but if it was
   * commanding heat of its own, the instant its drive goes low while the trace keeps
   * climbing is the protection acting, and that is worth having on the record.
   */
  function protection(rows) {
    const wasCommanding = rows.some((r) => r[CMD] === true || num(r[PWM]) > 0);
    if (!wasCommanding) return { commanded: false };
    const on = rows.find((r) => r[CMD] === true || num(r[PWM]) > 0);
    const off = rows.find((r) => r[T] > on[T] && r[CMD] !== true && !(num(r[PWM]) > 0));
    if (!off) return { commanded: true, cutOff: false, onAt: on[T] };
    const after = rows.filter((r) => r[T] > off[T]);
    return {
      commanded: true, cutOff: true, onAt: on[T], offAt: off[T],
      sec: r2(off[T] - on[T]),
      bodyAtCutOff: num(off[CH1]), chamberAtCutOff: num(off[CHAMBER]),
      keptRising: after.length > 3 && P.maxOf(after, CH1) - (num(off[CH1]) || 0) >= 1.0,
    };
  }

  /** The instant the trace started climbing: the lowest point before the peak. */
  function riseOnset(rows, col, peakAt) {
    let best = null;
    for (const r of rows) {
      if (r[T] > peakAt) break;
      const v = num(r[col]);
      if (v === null) continue;
      if (best === null || v <= best.v) best = { v, at: r[T] };
    }
    return best;
  }

  /** The first alert code that appears after `fromSec` (the codes ride along in each row). */
  function firstAlert(rows, fromSec) {
    const base = new Set(String((rows[0] || [])[ALERTS] || '').split('|').filter(Boolean));
    for (const r of rows) {
      if (r[T] < fromSec) continue;
      const codes = String(r[ALERTS] || '').split('|').filter(Boolean).filter((c) => !base.has(c));
      if (codes.length) return { at: r[T], code: codes[0] };
    }
    return null;
  }

  A.TRACE['DVT-SAF-009'] = function (rows, put, rec) {
    const turn = P.turn(rows, CH1, { fall: 1.5, minRise: 3, minFall: 20 });   // a cutout trip is a real climb, never a dip
    if (!turn.turned)
      return A.L('the CH1 trace never turned from rising to falling - nothing in this recording shows the cutout opening',
                 'עקומת CH1 לא עברה מעלייה לירידה - שום דבר ברישום הזה לא מראה את המנתק נפתח');

    // The heater is bridged by hand, so the machine's own heating flag stays false all the way
    // through: the clock for this test starts where the trace itself starts climbing.
    const onset = riseOnset(rows, CH1, turn.at);
    const tripAt = turn.at;
    const after = rows.filter((r) => r[T] >= tripAt);
    const atTrip = rows.find((r) => r[T] >= tripAt) || [];
    const chamberPeak = P.maxOf(after, CHAMBER);
    const chamberAtTrip = num(atTrip[CHAMBER]);

    put('cutout_trip_temp', r2(turn.peak));
    put('chamber_temp_at_trip', r2(chamberAtTrip));
    if (onset) put('time_to_trip', r2((tripAt - onset.at) / 60));
    put('graph_attached', true);                           // drawn from the stored samples by the page (drawTc08)
    rec.marks = { onset_s: onset ? onset.at : null, trip_s: tripAt, reset_s: null };
    if (chamberPeak !== null) {
      const peakAt = P.firstAt(after, (r) => num(r[CHAMBER]) === chamberPeak);
      put('chamber_time_to_peak', r2(peakAt === null ? null : peakAt - tripAt));
      if (chamberAtTrip !== null) put('chamber_overshoot_after_trip', r2(Math.max(0, chamberPeak - chamberAtTrip)));
      // the five minutes that follow the peak, not the tail of however long the recording ran on for
      if (peakAt !== null) {
        const win = after.filter((r) => r[T] >= peakAt && r[T] <= peakAt + 300 && num(r[CHAMBER]) !== null);
        if (win.length >= 2) {
          const dt = (win[win.length - 1][T] - win[0][T]) / 60;
          if (dt > 0) put('chamber_cooling_rate_after_trip', r2((win[win.length - 1][CHAMBER] - win[0][CHAMBER]) / dt));
        }
      }
    }

    // A cutout that closes again lets the bridged heater back on: the body starts climbing a second time.
    const falling = after.filter((r) => num(r[CH1]) !== null);
    const low = P.minOf(falling, CH1);
    if (low !== null) {
      const lowAt = P.firstAt(falling, (r) => num(r[CH1]) === low);
      const later = falling.filter((r) => r[T] > lowAt);
      const rose = later.length > 3 && P.maxOf(later, CH1) - low >= 2.0;
      put('self_resetting', rose);
      if (rose) { put('reset_temp', r2(low)); rec.marks.reset_s = lowAt; }
    }

    const alarm = rows.length && rows[0].length > ALERTS ? firstAlert(rows, onset ? onset.at : 0) : null;
    if (rows.length && rows[0].length > ALERTS) {
      put('alarm_raised', alarm !== null);
      if (alarm) {
        put('error_code', String(alarm.code));
        put('time_to_alarm', r2(Math.max(0, alarm.at - tripAt) / 60));
      }
    }

    // DVT-SAF-009's safety plan puts the operator's abort at 250 C on the body: a turn well below it
    // is the cutout doing its job, and a trace that reached it is a run the operator had to stop.
    const CEILING_C = 250;
    put('manual_abort_used', turn.peak !== null && turn.peak >= CEILING_C - 5);
    // A heater body cannot fall while its element is still delivering heat, so the fall after the
    // turn is the proof that power was removed - the same evidence this campaign uses everywhere else.
    const justAfter = after.filter((r) => r[T] <= tripAt + 120 && num(r[CH1]) !== null);
    const fell = justAfter.length >= 2 && turn.peak !== null ? turn.peak - P.minOf(justAfter, CH1) : null;
    put('heater_power_removed', fell !== null && fell >= 5);
    const untouched = A.limitsUntouched();
    Object.keys(untouched).forEach((k) => put(k, untouched[k]));

    // The machine's own response to a temperature it cannot stop - free evidence from the same run
    const prot = protection(rows);
    if (prot.commanded && prot.cutOff) {
      put('heater_off_at_alarm', alarm !== null && Math.abs(prot.offAt - alarm.at) <= 5);
      put('heater_off_delay', r2(alarm ? Math.max(0, prot.offAt - alarm.at) : null));
      put('heater_off_time', prot.sec);
      put('heater_body_drop_observed', turn.turned);
      // The cutout closing again makes heat available: if the machine's own drive stayed off through
      // that, something held it off and an acknowledgement is required. If the drive DID come back we
      // cannot tell whether the operator acknowledged an alarm on the screen first, so that case is
      // left to them rather than recorded as a failure they may not have.
      const backOn = rows.some((r) => r[T] > prot.offAt && (r[CMD] === true || num(r[PWM]) > 0));
      if (rec.values.self_resetting === true && !backOn) put('resume_requires_ack', true);
    }
    rec.protection = prot;

    // The three numbers this test exists for, first and on their own: when it tripped, at what
    // temperature, and where it closed again. Everything else the trace gives is recorded but secondary.
    const trip = r2(turn.peak);
    const mins = onset ? r2((tripAt - onset.at) / 60) : null;
    const reset = rec.values.reset_temp;
    const headEn = `CUT-OFF at ${trip} C` + (mins !== null ? ` after ${mins} min of heating` : '') +
      (reset !== undefined && reset !== null ? `, closed again at ${reset} C` : ', did not close again within the recording');
    const headHe = `ניתוק ב-${trip} מעלות` + (mins !== null ? ` אחרי ${mins} דקות חימום` : '') +
      (reset !== undefined && reset !== null ? `, נסגר שוב ב-${reset} מעלות` : ', לא נסגר שוב בתוך הרישום');

    const en = `${headEn}. Read from the recording: the cutout opened at ${r2(turn.peak)} C` +
      (onset ? `, ${r2((tripAt - onset.at) / 60)} min after the body started rising` : '') +
      (prot.commanded
        ? (prot.cutOff
            ? `. The machine was commanding heat and took its own drive off at ${r2(prot.bodyAtCutOff)} C` +
              (prot.keptRising ? ', while the body kept climbing - the protection acted and the heat was external' : '')
            : '. The machine was commanding heat and never took its drive off - that is a finding')
        : '. The machine was not commanding heat, so nothing here tests its heater cut-off');
    const hb = `${headHe}. נקרא מהרישום: המנתק נפתח ב-${r2(turn.peak)} מעלות` +
      (onset ? `, ${r2((tripAt - onset.at) / 60)} דקות אחרי שגוף ההיטר התחיל לעלות` : '') +
      (prot.commanded
        ? (prot.cutOff
            ? `. המכונה פקדה חימום והורידה את הפקודה שלה ב-${r2(prot.bodyAtCutOff)} מעלות` +
              (prot.keptRising ? ', בזמן שהגוף המשיך לטפס - ההגנה פעלה והחום היה חיצוני' : '')
            : '. המכונה פקדה חימום ומעולם לא הורידה את הפקודה - זה ממצא')
        : '. המכונה לא פקדה חימום, ולכן שום דבר כאן לא בודק את כיבוי ההיטר שלה');
    return A.L(en, hb);
  };
})();

// ============================================================================
// What a recording needs of the machine before it starts, and what to release
// afterwards. DVT-SAF-009 heats from an external supply the machine knows nothing
// about, so the machine will not run the heater fan on its own - and an element
// driven with no airflow is a different failure from the one under test.
// ============================================================================

(function () {
  const A = window.DVT_AUTO, P = A.P, L = A.L;
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);

  const NEEDS_HEATER_FAN = ['DVT-SAF-009'];
  const FAN = 'FAN_HEATER';

  /** Called by the page before a TC-08 recording starts. Returns { ok, message }. */
  A.prepare = async function (test) {
    const tid = test && test.test_id;
    const c = A.bare();

    // Every firmware start runs a 15 s LED self-test at 405 nm. It is an internal call, so nothing
    // appears in the machine log and the only sign of it is the UV being on with nothing commanding
    // it. A recording started in that window carries the self-test in its trace as a real UV event.
    try {
      const s = await c.state();
      if (s.uvOn === true)
        return { ok: false, message: L('the machine has UV on - if it has just restarted this is its start-up self-test (about 15 s). Wait for it to finish and start again.',
                                       'ה-UV דולק במכונה - אם היא בדיוק עלתה מחדש זו בדיקת האתחול העצמית שלה (כ-15 שניות). המתן שתסתיים והתחל שוב.') };
    } catch (e) {
      return { ok: false, message: L('the machine did not answer', 'המכונה לא ענתה') };
    }

    if (!NEEDS_HEATER_FAN.includes(tid)) return { ok: true, message: '' };

    // DVT-SAF-009 ends and records itself; the cutout's rating is the one value the verdict needs that no
    // trace can supply, so it has to be in before the recording starts, not remembered afterwards.
    try {
      const run = A._host().run(tid);
      const rec = (A._host().results() || {})[run.id] || {};
      const rated = rec.values && rec.values.rated_trip_temp;
      if (rated === undefined || rated === null || rated === '')
        return { ok: false, message: L('enter the cutout’s rated trip temperature (step 1) before starting - the test records its own verdict at the end and needs it',
                                       'הזן קודם את טמפרטורת הניתוק הנקובה של המנתק (שלב 1) - הבדיקה רושמת את התוצאה שלה בעצמה בסוף וצריכה אותה') };
    } catch (e) { /* no run in hand (a bare page): nothing to gate on */ }
    try {
      await c.post('/api/fans/override?fan=chamber_heating&on=1');
      await c.post('/api/fans/chamber_heating?speed=100');
      const spun = await c.until((s) => P.rpm(s, FAN) > 0, { sec: 20, poll: 1 });
      if (!spun.ok)
        return { ok: false, message: L('the heater fan is not turning - the element must not be driven without airflow',
                                       'מאוורר ההיטר לא מסתובב - אסור להניע את האלמנט בלי זרימת אוויר') };
      const rpm = P.rpm(spun.s, FAN);
      return { ok: true, message: L(`heater fan on, ${rpm} rpm`, `מאוורר ההיטר פועל, ${rpm} סל"ד`) };
    } catch (e) {
      return { ok: false, message: String(e.message || e) };
    }
  };

  /** Called by the page after the recording stops: give the fan back to the machine. */
  A.finish = async function (test) {
    const tid = test && test.test_id;
    if (!NEEDS_HEATER_FAN.includes(tid)) return;
    try { await A.bare().post('/api/fans/override?fan=chamber_heating&on=0'); } catch (e) { /* the run is over either way */ }
  };
})();

// ============================================================================
// A recording that ends by itself. The operator drives the heater and walks away;
// the page watches the stored samples every second and stops the recording when
// the trace holds what the test needs, then reads it and records the verdict -
// "the test finished" is written by the tool, not by somebody pressing Stop.
// ============================================================================

(function () {
  const A = window.DVT_AUTO, P = A.P, L = A.L;
  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);
  const r1 = (v) => (v === null || v === undefined ? null : Math.round(v * 10) / 10);
  const T = 0, CH1 = 1;

  function tc08Rows(rec) {
    const a = rec && ((rec.autos && rec.autos.tc08_record) || (rec.auto && rec.auto.kind === 'tc08_record' ? rec.auto : null));
    return a && Array.isArray(a.samples) ? a.samples : null;
  }

  /** Per test: given the rows so far, is the recording complete? Returns { stop, why } - pure, no I/O. */
  const AUTO_STOP = {
    'DVT-SAF-009'(rows, rec) {
      // stop as soon as the trace holds all three numbers: the trip and then the body climbing again (the
      // cutout closed). The old ten-minute wait after the trip fed chamber fields the test no longer has.
      const turn = P.turn(rows, CH1, { fall: 1.5, minRise: 3, minFall: 20 });
      // the graph's marks follow the live trace, so lines from an earlier reading never sit on a new run
      const before = rows.filter((r) => r[T] <= (turn.turned ? turn.at : Infinity) && num(r[CH1]) !== null);
      const lowB = P.minOf(before, CH1);
      const onset = lowB === null ? null : P.firstAt(before, (r) => num(r[CH1]) === lowB);
      if (rec) rec.marks = { onset_s: onset, trip_s: turn.turned ? turn.at : null, reset_s: null };
      if (!turn.turned) return { stop: false, why: '' };
      const since = rows[rows.length - 1][T] - turn.at;
      const after = rows.filter((r) => r[T] > turn.at && num(r[CH1]) !== null);
      const low = P.minOf(after, CH1);
      if (low !== null) {
        const lowAt = P.firstAt(after, (r) => num(r[CH1]) === low);
        const later = after.filter((r) => r[T] > lowAt);
        // a real second climb: 2 C above the low and held for 20 s, not one noisy sample
        if (later.length > 3 && P.maxOf(later, CH1) - low >= 2.0 && later[later.length - 1][T] - lowAt >= 20) {
          if (rec) rec.marks.reset_s = lowAt;
          return { stop: true, why: L(`the body is climbing again from ${r1(low)} C - the cutout closed; recording complete`,
                                      `הגוף מטפס שוב מ-${r1(low)} מעלות - המנתק נסגר; הרישום הושלם`) };
        }
      }
      if (since >= 1200) return { stop: true, why: L('20 minutes after the cut-off with no reset - recording complete', '20 דקות אחרי הניתוק בלי סגירה מחדש - הרישום הושלם') };
      return { stop: false, why: '' };
    },
  };

  A.autoStop = function (test, rec) {
    const fn = test && AUTO_STOP[test.test_id];
    const rows = tc08Rows(rec);
    if (!fn || !rows || rows.length < 10 || (rec && rec.verdict)) return { stop: false, why: '' };
    try { return fn(rows, rec); } catch (e) { return { stop: false, why: String(e.message || e) }; }
  };

  /** After fromTrace: did the recording give the test everything its verdict needs? { ok, message } - pure. */
  A.completed = function (test, rec) {
    if (!test || !rec || !AUTO_STOP[test.test_id]) return { ok: false, message: '' };
    const left = A.missingFields(test, rec.values || {});
    const v = rec.values || {};
    if (left.length)
      return { ok: false, message: L(`the test finished but ${left.join(', ')} could not be read - fill it in and record`,
                                     `הבדיקה הסתיימה אבל לא ניתן היה לקרוא ${left.join(', ')} - השלם ורשום`) };
    const numbers = `${L('CUT-OFF at ', 'ניתוק ב-')}${v.cutout_trip_temp} °C ${L('after', 'אחרי')} ${v.time_to_trip} ${L('min', 'דקות')}` +
      (v.reset_temp !== undefined && v.reset_temp !== null ? `, ${L('closed again at ', 'נסגר שוב ב-')}${v.reset_temp} °C` : '');
    // "finished successfully" is only true when the criteria say so: the page's own evaluator and thresholds
    // give the verdict here, so the sentence the operator reads and the verdict the run records cannot differ
    let verdict = null, detail = '';
    try {
      const crit = window.DVT_CRITERIA, cat = window.SCURE_DVT;
      if (crit && cat) { const ev = crit.evaluate(test.pass_criteria, v, cat.thresholds); verdict = ev.verdict; detail = ev.detail || ''; }
    } catch (e) { verdict = null; detail = String(e.message || e); }
    if (verdict === 'PASS')
      return { ok: true, verdict, detail, message: L(`the test finished on its own and PASSED - ${numbers}`, `הבדיקה הסתיימה מעצמה בהצלחה - ${numbers}`) };
    if (verdict === 'FAIL')
      return { ok: true, verdict, detail, message: L(`the test finished on its own and FAILED - ${numbers}${detail ? ' (' + detail + ')' : ''}`,
                                                    `הבדיקה הסתיימה מעצמה ונכשלה - ${numbers}${detail ? ' (' + detail + ')' : ''}`) };
    return { ok: true, verdict, detail, message: L(`the test finished on its own - ${numbers}`, `הבדיקה הסתיימה מעצמה - ${numbers}`) };
  };
})();
