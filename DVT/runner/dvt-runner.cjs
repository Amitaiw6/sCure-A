#!/usr/bin/env node
// sCure DVT runner - runs on the CureBox, next to the firmware (user, 2026-10-12).
//
//   sCure Cloud DVT tab --(Run)--> request queue --(dvt_next)--> this runner
//   this runner --(POST 127.0.0.1:3001/api/dvt/remote-confirm)--> Start / Decline on the machine's screen
//   Start --> the SAME dvt-auto.js script the DVT tool runs, through the machine's own API (its safety layer stays in
//   charge) --> values, verdict and raw samples back to the portal (dvt_run / dvt_file), the request marked done.
//
// Nothing runs until someone AT the machine presses Start. A step that needs a person (open the door, pull a sensor,
// read a meter) is asked on the site, in the request's row, and the answer comes back here.
//
//     node DVT/runner/dvt-runner.cjs [config.json]        (default: ./dvt-runner.json next to this file)
//
// config: { "portalUrl": ".../exec", "key": "<DVT key>", "machine": "CureBox-1", "unit": "UUT-01",
//           "machineApi": "http://127.0.0.1:3001", "pollSec": 10, "confirmTimeoutSec": 600, "promptTimeoutMin": 60 }
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');

const WEB = path.join(__dirname, '..', 'web');
// the repo keeps VERSION two levels up (sCure-A/VERSION); an installed runner keeps it next to its web/ folder
const VERSION = (() => {
  for (const p of [path.join(__dirname, '..', 'VERSION'), path.join(__dirname, '..', '..', 'VERSION')])
    try { return fs.readFileSync(p, 'utf8').trim(); } catch (e) { /* next */ }
  return 'dev';
})();
const DONE_VERDICTS = ['PASS', 'FAIL', 'BLOCKED', 'WAIVED'];

/** The page's catalog, criteria and test engine in a sandbox - the very files dvt-tool.html loads. */
function loadEngine(fetchImpl) {
  const html = fs.readFileSync(path.join(WEB, 'dvt-tool.html'), 'utf8').replace(/\r\n/g, '\n');
  const lift = (re, what) => { const m = html.match(re); if (!m) throw new Error(`${what} not found in dvt-tool.html`); return m[0]; };
  const box = { pending: '' };
  const sb = {
    window: {}, console, Date, Math, JSON, Promise, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    performance: { now: () => Date.now() }, AbortSignal, URL, TextEncoder, Buffer,
    fetch: (...a) => fetchImpl(...a),
    alert: (m) => console.log('[engine]', m),
    // a value answer reaches the engine the way the page hands it over: the run card's input box
    document: { getElementById: (id) => (String(id).startsWith('as-in-') ? { value: box.pending } : null) },
  };
  vm.createContext(sb);
  for (const f of ['dvt-catalog.js', 'dvt-criteria.js', 'dvt-auto.js']) vm.runInContext(fs.readFileSync(path.join(WEB, f), 'utf8'), sb, { filename: f });
  vm.runInContext(lift(/\nfunction variantLabel\(v\)[^\n]*\n/, 'variantLabel'), sb);
  vm.runInContext(lift(/\nfunction csvCell\(v\) \{[\s\S]*?\n\}\n/, 'csvCell'), sb);
  vm.runInContext(lift(/\nconst csvText = [^\n]*\n/, 'csvText').replace('const csvText', 'var csvText'), sb);
  vm.runInContext(lift(/\nfunction sweepCsv\(auto\) \{[\s\S]*?\n\}\n/, 'sweepCsv'), sb);
  return { A: sb.window.DVT_AUTO, CAT: sb.window.SCURE_DVT, CRIT: sb.window.DVT_CRITERIA, variantLabel: sb.variantLabel, sweepCsv: sb.sweepCsv, box };
}

function createRunner(cfg, deps = {}) {
  const fetchImpl = deps.fetch || fetch;
  const sleep = deps.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const log = deps.log || ((...a) => console.log(new Date().toISOString(), ...a));
  const E = deps.engine || loadEngine(fetchImpl);
  const { A, CAT, CRIT } = E;
  const api = String(cfg.machineApi || 'http://127.0.0.1:3001').replace(/\/+$/, '');
  const resultsFile = cfg.resultsFile || path.join(__dirname, 'results.json');
  let results = {};
  try { results = JSON.parse(fs.readFileSync(resultsFile, 'utf8')); } catch (e) { results = {}; }
  const saveResults = () => { try { fs.writeFileSync(resultsFile, JSON.stringify(results)); } catch (e) { log('results file not written:', e.message); } };
  let current = null;                                    // { tid, run }
  const isBenchTest = (t) => ((t && t.procedure_steps) || []).some((s) => s.tool === 'bench');   // run by the DVT bench process (port 3002)
  const benchUrl = String(cfg.benchApi || String(cfg.machineApi || 'http://127.0.0.1:3001').replace(/:(\d+)\/?$/, ':3002')).replace(/\/+$/, '');

  /**
   * What a missing instrument or a busy machine means for the person: the sentence to show, and 'blocked' (the run could not
   * begin - nothing was measured, nothing to judge) instead of 'failed'. null = an ordinary failure, shown as it is.
   */
  function blockedReason(message) {
    const m = String(message || '');
    if (/no (Ophir )?StarBright|StarBright on (the machine|USB)/i.test(m)) return "Connect the StarBright sensor to the machine's USB and switch it on";
    if (/no TC-08|TC-08 (not found|not usable)|plug the TC-08|CH1 (gives no|is not) reading|no valid reading on CH1/i.test(m)) return "Connect the TC-08 to the machine's USB, with its thermocouple on CH1";
    if (/a process is running on the machine|program is running|outputs are on|is heating|UV is on/i.test(m)) return 'Stop the process that is running on the machine first';
    if (/DVT bench is not running/i.test(m)) return 'The DVT bench service is not running on the machine (port 3002)';
    return null;
  }

  /** Does this test need the StarBright (its equipment list or its script says so), and is one plugged in? null = fine. */
  async function missingInstrument(tid, test) {
    const eq = ((test && test.equipment) || []).map((e) => `${e.name || ''} ${e.label || ''}`).join(' ');
    const sc = A.SCRIPTS && A.SCRIPTS[tid];
    const needsMeter = /starbright|ophir/i.test(eq) || (sc && sc.run && /dvt\/meter|starbright/i.test(String(sc.run)));
    if (!needsMeter) return null;
    const m = await machine('GET', '/api/dvt/meter').catch(() => null);
    if (m && m.present) return null;
    return blockedReason((m && m.message) || 'no StarBright on the machine');
  }

  /** Evaluate the current run's values against the test's pass criteria and record the verdict. */
  function recordVerdict(tid) {
    const test = CAT.tests[tid], run = current.run, rec = results[run.id] || (results[run.id] = { values: {} });
    const vals = { ...(rec.values || {}) };
    for (const [k, v] of Object.entries(run.variant || {})) if ((test.data_fields || []).some((f) => f.name === k)) vals[k] = v;
    let ev;
    try { ev = CRIT.evaluate(test.pass_criteria, vals, CAT.thresholds); } catch (e) { ev = { verdict: 'BLOCKED', detail: e.message }; }
    Object.assign(rec, { verdict: ev.verdict, detail: ev.detail, by: 'sCure Cloud (started at the machine)', at: new Date().toISOString(), catalog: CAT.catalog_version });
    saveResults();
  }

  /** One call to the portal. Apps Script sometimes answers with an HTML error page (a busy or timed-out execution):
   *  that is retried with a growing pause; only a JSON refusal ({ok:false}) is final. */
  async function portal(body, tries = 4) {
    for (let i = 1; ; i++) {
      let text = '', status = 0;
      try {
        const r = await fetchImpl(cfg.portalUrl, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' },
          body: JSON.stringify({ ...body, machineKey: cfg.key }) });
        status = r.status;
        text = typeof r.text === 'function' ? await r.text() : JSON.stringify(await r.json());
        const out = JSON.parse(text);
        if (!out || out.ok === false) throw Object.assign(new Error((out && out.message) || `portal HTTP ${status}`), { final: true });
        return out;
      } catch (e) {
        if (e.final || i >= tries) {
          if (e.final) throw e;
          const title = (/<title>([^<]*)<\/title>/i.exec(text) || [])[1];
          throw new Error(`portal not usable after ${tries} tries (${title ? 'HTML page: ' + title.trim() : e.message}${status ? ', HTTP ' + status : ''})`);
        }
        await sleep(2000 * i);
      }
    }
  }
  async function machine(method, p, body) {
    const r = await fetchImpl(api + p, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    return r.json();
  }
  const update = (id, extra) => portal({ kind: 'dvt_update', machine: cfg.machine, id, ...extra });

  /** The catalog as the portal lays it out (same shape the DVT tool publishes). */
  function catalogBody() {
    const tests = {};
    for (const [tid, t] of Object.entries(CAT.tests)) {
      const reps = Number(t.repetitions) || 1;
      tests[tid] = { title: t.title, safety: !!t.safety_critical, auto: !!A.has(tid) || isBenchTest(t), minutes: t.duration_est_min || null, units: t.units || [],
                     d: A.detailOf ? A.detailOf(t) : undefined,
                     runs: (t.variants || [{}]).flatMap((v) => Array.from({ length: reps }, (_, r) => `${E.variantLabel(v)}|${r + 1}`)) };
    }
    return { kind: 'dvt_catalog', catalog: { version: CAT.catalog_version,
      phases: CAT.phases.map((ph) => ({ id: ph.id, name: ph.name, gate: ph.gate || '', tests: ph.tests })), tests } };
  }

  function owedRuns(tid, unit) {
    const t = CAT.tests[tid];
    if (!t || !(t.units || []).includes(unit)) return [];
    const reps = Number(t.repetitions) || 1, out = [];
    (t.variants || [{}]).forEach((v) => { for (let r = 1; r <= reps; r++) out.push({ id: `${tid}|${unit}|${E.variantLabel(v)}|${r}`, variant: v, rep: r }); });
    return out;
  }

  // the host the engine drives - the same contract dvt-tool.html fulfils (DVT_AUTO.attach)
  A.attach({
    base: () => api, lang: () => 'en', connected: () => true, machine: () => `${cfg.machine} (DVT runner ${VERSION})`,
    folderOk: () => true, operator: () => 'sCure Cloud (started at the machine)',
    test: (tid) => CAT.tests[tid], run: () => current.run, results: () => results,
    log: (kind, msg) => log(`[${kind}]`, msg), persist: () => saveResults(), journal: () => {}, refreshTest: () => {},
    record: (tid) => recordVerdict(tid),
    setAuto: (rec, auto) => { (rec.autos = rec.autos || {})[auto.kind] = auto; rec.auto = auto; },
    drawTraces: () => {}, hasTraceCanvas: () => false, autoMap: () => ({}), busy: () => false,
  });

  async function publishRun(runId) {
    const rec = results[runId] || {};
    const [tid, unit, variant, rep] = runId.split('|');
    await portal({ kind: 'dvt_run', unit, testId: tid, variant: variant || '', rep: Number(rep) || 1, runId, verdict: rec.verdict || '',
                   operator: rec.by || '', startedAt: rec.at || new Date().toISOString(), note: rec.note || '', machine: cfg.machine, values: rec.values || {} });
    const stem = `${variant ? variant.replace(/[^\w.=-]+/g, '_') + '_' : ''}r${rep}`;
    for (const a of Object.values(rec.autos || {})) {
      if (!a.samples || !a.samples.length || !a.at || a.live) continue;
      const name = `${stem}_${a.kind}_${a.at.replace(/[-:]/g, '').replace(/\..*$/, '')}.csv`;
      await portal({ kind: 'dvt_file', unit, runId, fileKind: a.kind, fileName: name, mimeType: 'text/csv',
                     contentBase64: Buffer.from(E.sweepCsv(a), 'utf8').toString('base64') });
    }
  }

  /** Ask the person at the machine; true only on Start. A cancel from the site withdraws the dialog. */
  async function confirmAtMachine(req, test) {
    const cid = `cloud-${req.id}`;
    const timeoutSec = Number(cfg.confirmTimeoutSec) || 600;
    const asked = await machine('POST', '/api/dvt/remote-confirm', { id: cid, timeoutSec,
      title: `${req.testId} - ${test.title}`, detail: `Unit ${req.unit} · requested from sCure Cloud for ${cfg.machine}` });
    if (!asked || asked.ok === false) throw new Error(`the machine did not take the confirmation: ${asked && asked.message}`);
    await update(req.id, { status: 'waiting', line: `waiting for Start on the ${cfg.machine} screen (${Math.round(timeoutSec / 60)} min)` });
    for (let i = 0; ; i++) {
      const woke = await wake.wait(1000);
      const st = (await machine('GET', `/api/dvt/remote-confirm/${encodeURIComponent(cid)}`)).state;
      if (st === 'accepted') return { start: true };
      if (st === 'declined') return { start: false, status: 'cancelled', line: 'declined at the machine' };
      if (st === 'expired') return { start: false, status: 'failed', line: `nobody pressed Start within ${Math.round(timeoutSec / 60)} min` };
      if (st !== 'pending') return { start: false, status: 'failed', line: `the confirmation was lost (${st}) - the machine may have restarted` };
      if (i % 2 === 1 || woke === 'wake') {                // every ~2 s, or at once when the portal commanded: still waiting, did the site cancel?
        const u = await update(req.id, { status: 'waiting' });
        if (u.cancel) { await machine('DELETE', `/api/dvt/remote-confirm/${encodeURIComponent(cid)}`); return { start: false, status: 'cancelled', line: 'cancelled from the site before Start' }; }
      }
    }
  }

  /** Relay the engine's prompts to the site and its answers back while a run is going. */
  async function pumpRun(req, tid, running) {
    let finished = false, cancelled = false, promptSince = 0, lastPrompt = null;
    running.then(() => { finished = true; }, () => { finished = true; });
    while (!finished) {
      await wake.wait(1000);
      if (finished) break;
      const st = A._state(tid) || {};
      const p = st.prompt ? { kind: st.prompt.kind, text: st.prompt.text, field: st.prompt.field || null, unit: st.prompt.unit || '',
                              type: st.prompt.type || null, values: st.prompt.values || null } : null;
      if (p && (!lastPrompt || lastPrompt.text !== p.text)) { promptSince = Date.now(); log(`[ask] ${req.testId}: ${p.text}`); }
      lastPrompt = p;
      let u;
      try { u = await update(req.id, { status: 'running', line: st.line || 'running', prompt: p }); } catch (e) { log('portal not reached:', e.message); continue; }
      if (u.cancel && !cancelled) { cancelled = true; log(`[stop] ${req.testId}: cancelled from the site`); A.stop(tid); }
      if (u.hasAnswer && st.prompt) answer(tid, st.prompt.kind, u.answer);
      else if (p && Date.now() - promptSince > (Number(cfg.promptTimeoutMin) || 60) * 60000) { log(`[ask] ${req.testId}: no answer in time - skipped`); A.click('as-skip', tid); }
    }
    return cancelled;
  }

  function answer(tid, kind, v) {
    if (v === null || v === undefined) A.click('as-skip', tid);
    else if (kind === 'value') { E.box.pending = String(v); A.click('as-ok', tid); }
    else if (kind === 'yesno') A.click(v === false ? 'as-no' : 'as-yes', tid);
    else A.click(v === false ? 'as-skip' : 'as-done', tid);
  }

  // ---------------------------------------------------------------- bench tests (the DVT bench process on this machine)
  async function benchCall(method, p) {
    const r = await fetchImpl(benchUrl + p, { method });
    if (r.status === 404) throw new Error('the DVT bench is not running on this machine (port 3002)');
    return r.json();
  }

  const TC_MIN_C = -25, TC_MAX_C = 400, TC_OPEN_MARGIN_C = 60;   // as dvt-tool.html: the machine's valid CH1 range, and "hot with nothing running"

  /**
   * What a bench test would refuse on, read here on the machine and shown on the test's card in the portal BEFORE anyone asks
   * for a run (the DVT tool shows the same rows: machine, bench service, thermocouple, heater thermistor, idle).
   * Returns { <testId>: { ready, rows: { machine, svc, tc08, chamber, idle } } } - every row { ok: true|false|'warn'|null, text }.
   */
  async function readiness() {
    const ids = Object.keys(CAT.tests).filter((tid) => isBenchTest(CAT.tests[tid]));
    if (!ids.length) return null;
    const get = (p) => machine('GET', p).catch(() => null);
    const [st, pico] = await Promise.all([get('/api/state'), get('/api/dev/picolog/status')]);
    const bs = await benchCall('GET', '/bench/status').catch(() => null);
    const running = !!(st && (st.uvOn || st.isHeating || st.isCooling || st.nitrogenActive || (st.recipe && st.recipe.state && !['idle', 'completed', 'stopped', 'aborted'].includes(st.recipe.state))));
    const temp = pico && pico.connected && pico.ch1Available && typeof pico.temperature === 'number' ? pico.temperature : null;
    const ambient = pico && typeof pico.ambient === 'number' ? pico.ambient : null;
    const hot = temp !== null && ambient !== null && temp - ambient > TC_OPEN_MARGIN_C && !running;
    const tc = temp !== null && temp >= TC_MIN_C && temp <= TC_MAX_C;
    const chamber = st && st.sensors && st.sensors.chamber ? st.sensors.chamber.ok === true : null;
    const out = {};
    for (const tid of ids) {
      const svc = !!(bs && bs.ok && bs.tests && bs.tests.includes(tid));
      const rows = {
        machine: { ok: !!st, text: st ? `v${cfg.firmware || ''}`.replace(/^v$/, 'connected') : 'the machine software does not answer' },
        svc: { ok: svc, text: svc ? `sCureBox ${bs.version}${bs.run && bs.run.running ? ' · busy with ' + bs.run.test_id : ''}`
                                  : bs && bs.ok ? `the bench on this machine does not know ${tid}` : 'the DVT bench is not running on this machine (port 3002)' },
        tc08: { ok: !pico || !pico.connected ? false : tc ? (hot ? 'warn' : true) : false,
                text: !pico || !pico.connected ? 'plug the TC-08 into the machine\'s USB' : tc ? `${temp.toFixed(1)} °C${hot ? ' · hot with nothing running - a body still hot from an earlier test is fine' : ''}` : 'no valid reading on CH1 - connect the thermocouple to CH1' },
        chamber: { ok: chamber, text: chamber === null ? '' : chamber ? (st && typeof st.chamberTemp === 'number' ? `${st.chamberTemp.toFixed(1)} °C` : 'ok') : 'the heater thermistor is disconnected - reconnect it (the run starts with it connected; the bench tells you when to pull it)' },
        idle: { ok: st ? !running : null, text: !st ? '' : running ? 'a process is running on the machine - stop it first' : 'nothing running' },
      };
      out[tid] = { ready: !!st && svc && tc && chamber === true && !running && !(bs && bs.run && bs.run.running), rows };
    }
    return out;
  }

  /** A bench test's runs, one after the other: the bench does everything, the person at the machine only plugs / unplugs. */
  async function runBench(req, tid, test, runs) {
    const written = [];
    let lastLine = '';
    for (const run of runs) {
      current = { tid, run };
      const rec = results[run.id] = { values: {} };
      let st = null, cancelled = false, refused = '';
      try {
        const bs = await benchCall('GET', '/bench/status');
        if (!bs.tests || !bs.tests.includes(tid)) throw new Error(`the bench on this machine does not know ${tid}`);
        if (bs.run && bs.run.running) throw new Error(`the bench is busy with ${bs.run.test_id}`);
        const start = await benchCall('POST', `/bench/run?test=${encodeURIComponent(tid)}`);
        if (!start.ok) throw new Error(start.message || 'refused');
        log(`[request ${req.id}] bench: ${start.message || 'started'}`);
        for (let i = 0; ; i++) {
          const woke = await wake.wait(1000);
          st = await benchCall('GET', '/bench/run?samples=0');
          if (!st.running) break;
          if (i % 2 === 0 || woke === 'wake') {               // the portal every ~2 s, or at once when it commanded
            const last = st.last || [];
            lastLine = `${st.phase} · ${A.mmss ? A.mmss(st.elapsed) : Math.round(st.elapsed) + ' s'}${typeof last[1] === 'number' ? ' · body ' + last[1].toFixed(1) + ' °C' : ''}${typeof last[7] === 'number' ? ' · chamber ' + last[7].toFixed(1) + ' °C' : ''}${st.prompt ? ' - ' + st.prompt : ''}`;
            let u = {};
            try { u = await update(req.id, { status: 'running', line: lastLine }); } catch (e) { log('portal not reached:', e.message); }
            if (u.cancel && !cancelled) { cancelled = true; log(`[stop] ${tid}: cancelled from the site`); await benchCall('POST', '/bench/run/abort?by=site').catch(() => {}); }
          }
        }
        st = await benchCall('GET', '/bench/run');
      } catch (e) {
        refused = e.message;
      }
      if (st) {
        const known = new Set((test.data_fields || []).map((f) => f.name));
        const measured = st.status === 'OK' || !!(st.marks && st.marks.disconnect);   // a run that never reached the disconnect fills nothing
        const values = {};
        if (measured) {
          for (const [k, v] of Object.entries(st.values || {})) if (known.has(k) && v !== null && v !== undefined) values[k] = v;
          if (known.has('raw_log_attached') && st.samples && st.samples.length) values.raw_log_attached = true;
        }
        Object.assign(rec.values, values);
        rec.autoFields = Object.keys(values);
        rec.auto = { kind: 'bench', status: st.status, error: st.error, at: new Date().toISOString(), machine: cfg.machine, test_id: st.test_id, config: st.config,
                     marks: st.marks, phases: st.phases, notes: st.notes, extra: st.values, tc08: st.tc08, columns: st.columns, samples: st.samples };
        rec.autos = { bench: rec.auto };
        if (st.status === 'OK' && !cancelled) recordVerdict(tid);   // only a finished run gets a verdict; a refused or aborted one stays open
        saveResults();
      }
      written.push(run.id);
      if (st || !refused) { try { await publishRun(run.id); } catch (e) { log('upload failed (kept in results.json):', e.message); } }
      if (cancelled) return update(req.id, { status: 'cancelled', line: 'stopped from the site - the bench aborted the run', runIds: written });
      if (refused) { const why = blockedReason(refused); return update(req.id, { status: why ? 'blocked' : 'failed', line: why || `did not start: ${refused}`, runIds: written.filter((id) => id !== run.id) }); }
      if (st && st.status !== 'OK') return update(req.id, { status: 'failed', line: `the bench ended "${st.status}"${st.error ? ': ' + st.error : ''} - ${Object.keys(rec.values).length} value(s) kept, no verdict`, runIds: written });
    }
    const vs = written.map((id) => (results[id] || {}).verdict).filter(Boolean);
    const verdict = vs.includes('FAIL') ? 'FAIL' : vs.includes('BLOCKED') ? 'BLOCKED' : vs.length === written.length && vs.every((v) => v === 'PASS') ? 'PASS' : '';
    return update(req.id, { status: 'done', verdict, runIds: written, line: verdict ? `${tid} ${verdict}` : 'finished' });
  }

  async function handle(req) {
    const stopListening = watchCommands();
    try { return await handleRequest(req); } finally { stopListening(); }
  }

  async function handleRequest(req) {
    const tid = req.testId, test = CAT.tests[tid];
    log(`[request ${req.id}] ${tid} on ${req.unit}`);
    if (!test) return update(req.id, { status: 'failed', line: `${tid} is not in catalog ${CAT.catalog_version}` });
    // this CureBox IS one unit: a request for another (a stale page) must not record results under a unit that is not here
    if (cfg.unit && req.unit !== cfg.unit) return update(req.id, { status: 'failed', line: `${cfg.machine} is unit ${cfg.unit} - the request was for ${req.unit}; nothing was started` });
    if (!A.has(tid) && !isBenchTest(test)) return update(req.id, { status: 'failed', line: 'no automatic script for this test - run it from the DVT tool' });
    const runs = owedRuns(tid, req.unit).filter((r) => !DONE_VERDICTS.includes((results[r.id] || {}).verdict));
    if (!runs.length) return update(req.id, { status: 'done', line: `every run of ${tid} on ${req.unit} is already recorded` });
    const s = await machine('GET', '/api/state');
    if (s && (s.isRunning || s.isHeating || s.uvOn || s.isCooling)) return update(req.id, { status: 'failed', line: 'the machine is busy with a process - nothing was started' });
    // an instrument that is not plugged in: say so now, not after someone pressed Start at the machine
    const missing = await missingInstrument(tid, test).catch(() => null);
    if (missing) { log(`[request ${req.id}] ${missing}`); return update(req.id, { status: 'blocked', line: missing }); }
    if (isBenchTest(test) && !A.has(tid)) {
      const rd = await readiness().catch(() => null);
      const red = rd && rd[tid] && !rd[tid].ready ? Object.values(rd[tid].rows).find((r) => r && r.ok === false) : null;
      if (red) { const why = blockedReason(red.text) || red.text; log(`[request ${req.id}] ${why}`); return update(req.id, { status: 'blocked', line: why }); }
    }
    const ok = await confirmAtMachine(req, test);
    if (!ok.start) { log(`[request ${req.id}] ${ok.line}`); return update(req.id, { status: ok.status, line: ok.line }); }
    log(`[request ${req.id}] START pressed at the machine - running ${runs.length} run(s)`);
    if (isBenchTest(test) && !A.has(tid)) return runBench(req, tid, test, runs);
    const written = [];
    for (const run of runs) {
      current = { tid, run };
      results[run.id] = results[run.id] || { values: {} };
      const going = A.start(tid);
      const cancelled = await pumpRun(req, tid, going);
      await going.catch(() => {});
      written.push(run.id);
      try { await publishRun(run.id); } catch (e) { log('upload failed (kept in results.json):', e.message); }
      if (cancelled) return update(req.id, { status: 'cancelled', line: 'stopped from the site - the machine turned everything off', runIds: written });
    }
    const vs = written.map((id) => (results[id] || {}).verdict).filter(Boolean);
    const verdict = vs.includes('FAIL') ? 'FAIL' : vs.includes('BLOCKED') ? 'BLOCKED' : vs.length === written.length && vs.every((v) => v === 'PASS') ? 'PASS' : '';
    const st = A._state(tid) || {};
    if (st.status && st.status !== 'OK') {                    // the script stopped (an instrument missing, a failed step): that is not "done"
      const why = blockedReason(st.error);
      return update(req.id, { status: why ? 'blocked' : 'failed', line: why || st.line || `stopped: ${st.error}`, runIds: written });
    }
    return update(req.id, { status: 'done', verdict, runIds: written, line: st.line || (verdict || 'finished') });
  }

  async function hello() {
    await portal({ kind: 'dvt_runner_hello', machine: cfg.machine, version: VERSION, unit: cfg.unit });
    await portal(catalogBody());
  }

  // ---- waking up: while a request is handled a long poll tells at once when the portal commanded something (a cancel, an answer)
  let wakeResolve = null;
  const wake = {
    fire() { if (wakeResolve) { const r = wakeResolve; wakeResolve = null; r('wake'); } },
    wait(ms) { return Promise.race([sleep(ms).then(() => 'timeout'), new Promise((res) => { wakeResolve = res; })]); },
  };
  /** Start listening; returns the function that stops it. The held request outlives the stop by up to cfg.eventsHoldSec. */
  function watchCommands() {
    let since = '', stop = false;
    (async () => {
      while (!stop) {
        try {
          const r = await portal({ kind: 'dvt_events', machine: cfg.machine, since, wait: Number(cfg.eventsHoldSec) || 15 }, 1);
          if (stop) break;
          if (since !== '' && String(r.ver) !== since) wake.fire();
          since = String(r.ver);
        } catch (e) { await sleep(3000); }
        await sleep(50);
      }
    })();
    return () => { stop = true; };
  }

  let lastWatch = 0, lastReadyAt = 0, lastPollMs = 0;                     // the portal says in its reply when somebody is looking at the DVT tab
  /** Seconds to wait before the next poll: fast (cfg.fastPollSec, 1.5) while the portal is watched, else cfg.pollSec (10). */
  function nextDelaySec() {
    return Date.now() - lastWatch < 60000 ? (Number(cfg.fastPollSec) || 1.5) : (Number(cfg.pollSec) || 10);
  }

  /** One poll: take the next request of this CureBox and run it. Returns true when there was one. */
  async function tick() {
    let ready = null;
    if (Date.now() - lastReadyAt > 8000) {                  // the checks are read and sent every ~8 s, not with every fast poll
      try { ready = await readiness(); lastReadyAt = Date.now(); } catch (e) { log('readiness not read:', e.message); }
    }
    const t0 = Date.now();
    const next = await portal({ kind: 'dvt_next', machine: cfg.machine, readiness: ready, wait: cfg.holdSec === undefined ? 20 : Number(cfg.holdSec) });
    lastPollMs = Date.now() - t0;
    if (next.watch) lastWatch = Date.now();
    if (!next.request) return false;
    try { await handle(next.request); }
    catch (e) { log(`[request ${next.request.id}] error:`, e.message); await update(next.request.id, { status: 'failed', line: `runner error: ${e.message}` }).catch(() => {}); }
    return true;
  }

  async function loop() {
    let lastHello = 0;
    for (;;) {
      try {
        if (Date.now() - lastHello > 10 * 60000) { await hello(); lastHello = Date.now(); log(`[runner ${VERSION}] online for ${cfg.machine}, unit ${cfg.unit}`); }
        // a poll the server held open (it came back after seconds, empty) is asked again at once; one that came back straight away
        // (an older portal that does not hold) is paced as before
        if (!(await tick())) await sleep((lastPollMs > 3000 ? 0.2 : nextDelaySec()) * 1000);
      } catch (e) {
        log('portal not reached:', e.message);
        await sleep(30000);
      }
    }
  }

  return { tick, handle, hello, loop, catalogBody, owedRuns, readiness, nextDelaySec, results: () => results };
}

module.exports = { createRunner, loadEngine };

if (require.main === module) {
  const file = process.argv[2] || path.join(__dirname, 'dvt-runner.json');
  const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
  for (const k of ['portalUrl', 'key', 'machine', 'unit']) if (!cfg[k]) { console.error(`${file}: "${k}" is missing`); process.exit(2); }
  createRunner(cfg).loop();
}
