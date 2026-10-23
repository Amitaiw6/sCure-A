// The DVT runner's orchestration against a fake portal, a fake firmware and a fake engine: nothing runs before Start
// at the machine, Decline / expiry / a cancel stop it, a busy machine or a manual test is refused, and a prompt is
// relayed to the site and its answer back.   node DVT/runner/runner.test.cjs   (driven by DVT/tests/test_dvt_web.py)
'use strict';
const assert = require('assert'), path = require('path'), os = require('os'), fs = require('fs');
const { createRunner } = require('./dvt-runner.cjs');

function world(opts = {}) {
  const portalCalls = [], machineCalls = [];
  let confirmStates = (opts.confirm || ['pending', 'accepted']).slice();
  let answerQueue = (opts.answers || []).slice();
  let cancelAfter = opts.cancelAfter === undefined ? -1 : opts.cancelAfter;   // cancel on the Nth dvt_update
  let updates = 0;
  let started = 0, stopped = 0, clicks = [];
  const tests = {
    'DVT-ELE-001': { title: 'Protective earth bonding continuity', units: ['UUT-01'], variants: [{}], repetitions: 1, data_fields: [], pass_criteria: 'ok',
      equipment: opts.needsMeter ? [{ name: 'Ophir StarBright power meter' }] : [] },
    'DVT-OPT-001': { title: 'UV linearity', units: ['UUT-01'], variants: [{}], repetitions: 1, data_fields: [], pass_criteria: 'ok' },
    'DVT-SAF-004': { title: 'Heater temperature sensor disconnected', units: ['UUT-01'], variants: [{}], repetitions: 1,
      data_fields: [{ name: 'heater_off_time' }, { name: 'raw_log_attached' }], pass_criteria: 'heater_off_time <= 80',
      procedure_steps: [{ step: 'Automatic on the machine - press Start.', tool: 'bench' }, { step: 'Record the alarm text' }] },
  };
  const eventCalls = [];
  const benchPolls = (opts.benchPolls || 2);        // how many "running" answers the bench gives before it finishes
  let benchPolled = 0, benchAborted = 0;
  let H = null, state = {}, resolveRun = null, endRun = null;
  const A = {
    version: 'test', SCRIPTS: { 'DVT-ELE-001': {} },
    has: (tid) => tid === 'DVT-ELE-001',
    detailOf: (t) => ({ purpose: 'why ' + t.title, steps: (t.procedure_steps || []).map((x) => x.step), criteria: t.pass_criteria, bench: (t.procedure_steps || []).some((x) => x.tool === 'bench') }),
    mmss: (n) => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}`,
    attach: (h) => { H = h; },
    _state: (tid) => state[tid],
    start: (tid) => { started++; const run = H.run(tid); const rec = H.results()[run.id];
      state[tid] = { line: 'measuring the bond', prompt: opts.prompt ? { kind: 'do', text: 'Clip the probe to the PE stud, then press Done' } : null };
      if (opts.stopError) { state[tid] = { line: 'stopped: ' + opts.stopError, status: 'ERROR', error: opts.stopError }; return Promise.resolve(); }   // the script stopped before measuring
      return new Promise((res) => {
        endRun = () => { resolveRun = null; endRun = null; res(); };              // a stopped run ends without a verdict
        resolveRun = () => { rec.values.r_mohm = 42; state[tid] = { line: 'the test finished and PASSED' }; H.record(tid); endRun(); };
        if (!opts.prompt && !opts.longRun) resolveRun(); }); },
    stop: () => { stopped++; if (endRun) { state['DVT-ELE-001'] = { line: 'stopped' }; endRun(); } },
    click: (act, tid) => { clicks.push(act); if (resolveRun && (act === 'as-done' || act === 'as-skip')) resolveRun(); },
  };
  const engine = { A, CAT: { catalog_version: '0.24', thresholds: {}, tests, phases: [{ id: 1, name: 'Electrical safety', gate: '', tests: Object.keys(tests) }] },
    CRIT: { evaluate: (crit, vals) => vals.heater_off_time !== undefined ? { verdict: vals.heater_off_time <= 80 ? 'PASS' : 'FAIL', detail: '' }
                                                                       : { verdict: vals.r_mohm !== undefined ? 'PASS' : 'BLOCKED', detail: '' } },
    variantLabel: (v) => Object.entries(v).map(([k, x]) => `${k}=${x}`).join(','), sweepCsv: () => 't_s\n0\n', box: { pending: '' } };
  const reply = (obj) => ({ status: 200, json: async () => obj });
  const fetchImpl = async (url, o = {}) => {
    const body = o.body ? JSON.parse(o.body) : null;
    if (url === 'https://portal/exec') {
      portalCalls.push(body);
      if (body.kind === 'dvt_events') { eventCalls.push(body); return reply({ ok: true, ver: opts.commandAt !== undefined && eventCalls.length > opts.commandAt ? 2 : 1 }); }
      if (body.kind === 'dvt_next') return reply({ ok: true, watch: !!opts.watch, request: opts.noRequest ? null : { id: 7, unit: opts.unit || 'UUT-01', testId: opts.testId || 'DVT-ELE-001' } });
      if (body.kind === 'dvt_update') {
        updates++;
        const out = { ok: true, cancel: cancelAfter >= 0 && updates > cancelAfter };
        if (body.prompt && answerQueue.length) { out.hasAnswer = true; out.answer = answerQueue.shift(); }
        return reply(out);
      }
      return reply({ ok: true });
    }
    if (url.startsWith('http://127.0.0.1:3002')) {               // the DVT bench process
      const b = url.replace('http://127.0.0.1:3002', '');
      machineCalls.push(`${o.method || 'GET'} ${b} (bench)`);
      if (opts.benchMissing) return { status: 404, json: async () => ({}) };
      if (b === '/bench/status') return reply({ ok: true, tests: ['DVT-SAF-004'], version: '1.0.91', run: { running: false } });
      if (b.startsWith('/bench/run?test=') && o.method === 'POST') return reply(opts.benchRefuses ? { ok: false, message: 'TEMP_CHAMBER is not reading' } : { ok: true, message: 'bench started' });
      if (b === '/bench/run/abort?by=site') { benchAborted++; return reply({ ok: true }); }
      if (b === '/bench/run?samples=0') { benchPolled++; return reply(benchPolled <= benchPolls && !benchAborted
        ? { running: true, phase: 'heating', elapsed: 75, prompt: 'DISCONNECT the heater thermistor now', last: [75, 61.5, 0, 0, 0, 0, 0, 30.2] } : { running: false }); }
      if (b === '/bench/run') return reply(opts.benchStatus === 'ABORTED'
        ? { status: 'ABORTED', error: 'aborted by the page', marks: {}, samples: [[0, 40, 0, 0, 0, 0, 0, 22]], columns: ['t_s', 'body'], values: {} }
        : { status: 'OK', marks: { heat_on: 1, disconnect: 30 }, columns: ['t_s', 'body'], samples: [[0, 40], [1, 41]], test_id: 'DVT-SAF-004',
            values: { heater_off_time: opts.heaterOff || 51.6, not_a_field: 1 }, phases: [{ name: 'done' }], notes: [] });
    }
    const p = url.replace('http://127.0.0.1:3001', '');
    machineCalls.push(`${o.method || 'GET'} ${p}`);
    if (p === '/api/dvt/meter') return reply(opts.noMeter ? { present: false, message: 'no Ophir StarBright on USB - plug the meter into the machine and switch it on' } : { present: true, reading_mw_cm2: 0.01 });
    if (p === '/api/dev/picolog/status') return reply(opts.noTc08 ? { connected: false } : { connected: true, ch1Available: true, temperature: 30.5, ambient: 22 });
    if (p === '/api/state' && opts.bench) return reply({ isRunning: false, uvOn: false, isHeating: false, isCooling: false, chamberTemp: 22.8, sensors: { chamber: { ok: !opts.chamberOpen } } });
    if (p === '/api/state') return reply(opts.busy ? { isRunning: true } : { isRunning: false, uvOn: false, isHeating: false });
    if (p === '/api/dvt/remote-confirm' && o.method === 'POST') return reply({ ok: true, id: body.id, state: 'pending', _title: body.title });
    if (p.startsWith('/api/dvt/remote-confirm/') && o.method === 'GET') return reply({ ok: true, state: confirmStates.length > 1 ? confirmStates.shift() : confirmStates[0] });
    if (p.startsWith('/api/dvt/remote-confirm/') && o.method === 'DELETE') return reply({ ok: true, state: 'withdrawn' });
    return reply({ ok: true });
  };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dvt-runner-'));
  const runner = createRunner({ portalUrl: 'https://portal/exec', key: 'dk', machine: 'CureBox-1', unit: 'UUT-01',
    machineApi: 'http://127.0.0.1:3001', resultsFile: path.join(dir, 'results.json'), confirmTimeoutSec: 600 },
    { fetch: fetchImpl, engine, log: () => {}, sleep: () => new Promise((r) => setImmediate(r)) });
  return { runner, portalCalls, machineCalls, eventCalls, get started() { return started; }, get stopped() { return stopped; }, get benchAborted() { return benchAborted; }, clicks,
           finalUpdate: () => portalCalls.filter((c) => c.kind === 'dvt_update').pop() };
}

(async () => {
  // 1. Start at the machine -> the run happens, its prompt goes to the site and the answer comes back, results go up
  let w = world({ prompt: true, answers: [true] });
  assert.strictEqual(await w.runner.tick(), true);
  assert.ok(w.machineCalls.includes('POST /api/dvt/remote-confirm'), 'the machine is asked first');
  assert.ok(w.machineCalls.indexOf('POST /api/dvt/remote-confirm') < w.machineCalls.length, 'confirm before anything');
  const waiting = w.portalCalls.find((c) => c.kind === 'dvt_update' && c.status === 'waiting');
  assert.ok(waiting && /waiting for Start on the CureBox-1 screen/.test(waiting.line));
  const asked = w.portalCalls.find((c) => c.kind === 'dvt_update' && c.prompt);
  assert.strictEqual(asked.prompt.text, 'Clip the probe to the PE stud, then press Done');
  assert.ok(w.clicks.includes('as-done'), 'the answer from the site reaches the engine');
  const run = w.portalCalls.find((c) => c.kind === 'dvt_run');
  assert.deepStrictEqual([run.runId, run.machine, run.verdict, run.values.r_mohm], ['DVT-ELE-001|UUT-01||1', 'CureBox-1', 'PASS', 42]);
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().verdict, w.finalUpdate().runIds[0]], ['done', 'PASS', 'DVT-ELE-001|UUT-01||1']);
  assert.strictEqual(w.started, 1);

  // 2. Decline at the machine -> nothing runs
  w = world({ confirm: ['pending', 'declined'] });
  await w.runner.tick();
  assert.strictEqual(w.started, 0, 'a declined request must never start the engine');
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().line], ['cancelled', 'declined at the machine']);

  // 3. nobody answers -> expired, nothing runs
  w = world({ confirm: ['pending', 'expired'] });
  await w.runner.tick();
  assert.strictEqual(w.started, 0);
  assert.strictEqual(w.finalUpdate().status, 'failed');
  assert.ok(/nobody pressed Start/.test(w.finalUpdate().line));

  // 4. the site cancels while the machine still asks -> the dialog is withdrawn, nothing runs
  w = world({ confirm: ['pending'], cancelAfter: 1 });
  await w.runner.tick();
  assert.strictEqual(w.started, 0);
  assert.ok(w.machineCalls.some((c) => c.startsWith('DELETE /api/dvt/remote-confirm/')), 'the dialog on the screen is withdrawn');
  assert.strictEqual(w.finalUpdate().status, 'cancelled');

  // 5. the site cancels a running test -> the engine is stopped (it turns everything off), the run is still reported
  w = world({ longRun: true, cancelAfter: 2 });
  await w.runner.tick();
  assert.strictEqual(w.started, 1);
  assert.strictEqual(w.stopped, 1, 'the engine must be stopped');
  assert.strictEqual(w.finalUpdate().status, 'cancelled');

  // 6. a machine busy with a process -> refused before any dialog
  w = world({ busy: true });
  await w.runner.tick();
  assert.ok(!w.machineCalls.includes('POST /api/dvt/remote-confirm'));
  assert.strictEqual(w.started, 0);
  assert.ok(/busy/.test(w.finalUpdate().line));

  // 7. a test with no automatic script -> refused, with where to run it
  w = world({ testId: 'DVT-OPT-001' });
  await w.runner.tick();
  assert.ok(!w.machineCalls.includes('POST /api/dvt/remote-confirm'));
  assert.ok(/run it from the DVT tool/.test(w.finalUpdate().line));

  // 7b. a request for another unit than this CureBox's -> refused before any dialog
  w = world({ unit: 'UUT-02' });
  await w.runner.tick();
  assert.ok(!w.machineCalls.includes('POST /api/dvt/remote-confirm'));
  assert.strictEqual(w.started, 0);
  assert.ok(/CureBox-1 is unit UUT-01/.test(w.finalUpdate().line), w.finalUpdate().line);

  // 8. no request -> the runner just waits; hello announces it and publishes the catalog
  w = world({ noRequest: true });
  assert.strictEqual(await w.runner.tick(), false);
  await w.runner.hello();
  assert.ok(w.portalCalls.some((c) => c.kind === 'dvt_runner_hello' && c.machine === 'CureBox-1' && c.unit === 'UUT-01'));
  const cat = w.portalCalls.find((c) => c.kind === 'dvt_catalog');
  assert.strictEqual(cat.catalog.tests['DVT-ELE-001'].auto, true);
  assert.strictEqual(cat.catalog.tests['DVT-OPT-001'].auto, false);
  assert.ok(w.portalCalls.every((c) => c.machineKey === 'dk'), 'every portal call carries the DVT key');

  // 9. the catalog carries each test's detail (purpose, steps, criteria) and a bench test is runnable from the site
  assert.strictEqual(cat.catalog.tests['DVT-ELE-001'].d.purpose, 'why Protective earth bonding continuity');
  assert.deepStrictEqual(cat.catalog.tests['DVT-SAF-004'].d.steps, ['Automatic on the machine - press Start.', 'Record the alarm text']);
  assert.strictEqual(cat.catalog.tests['DVT-SAF-004'].d.bench, true);
  assert.strictEqual(cat.catalog.tests['DVT-SAF-004'].auto, true, 'a bench test is run by the DVT bench process');

  // 10. readiness: every row of the card, read on the machine, sent with the poll
  w = world({ noRequest: true, bench: true });
  let rd = await w.runner.readiness();
  assert.strictEqual(rd['DVT-SAF-004'].ready, true);
  assert.deepStrictEqual(Object.keys(rd['DVT-SAF-004'].rows), ['machine', 'svc', 'tc08', 'chamber', 'idle']);
  assert.ok(/sCureBox 1.0.91/.test(rd['DVT-SAF-004'].rows.svc.text) && /30.5 °C/.test(rd['DVT-SAF-004'].rows.tc08.text));
  await w.runner.tick();
  assert.strictEqual(w.portalCalls.find((c) => c.kind === 'dvt_next').readiness['DVT-SAF-004'].ready, true, 'readiness goes up with every poll');
  w = world({ noRequest: true, bench: true, noTc08: true });
  rd = await w.runner.readiness();
  assert.deepStrictEqual([rd['DVT-SAF-004'].ready, rd['DVT-SAF-004'].rows.tc08.ok], [false, false]);
  assert.ok(/plug the TC-08/.test(rd['DVT-SAF-004'].rows.tc08.text));
  w = world({ noRequest: true, bench: true, chamberOpen: true });
  rd = await w.runner.readiness();
  assert.strictEqual(rd['DVT-SAF-004'].rows.chamber.ok, false);
  assert.ok(/thermistor is disconnected/.test(rd['DVT-SAF-004'].rows.chamber.text));
  w = world({ noRequest: true, bench: true, benchMissing: true });
  rd = await w.runner.readiness();
  assert.deepStrictEqual([rd['DVT-SAF-004'].ready, rd['DVT-SAF-004'].rows.svc.ok], [false, false]);
  assert.ok(/port 3002/.test(rd['DVT-SAF-004'].rows.svc.text));

  // 11. a bench test: Start at the machine -> the bench runs it, values, verdict and trace go up
  w = world({ testId: 'DVT-SAF-004', bench: true, benchPolls: 5 });
  await w.runner.tick();
  assert.ok(w.machineCalls.indexOf('POST /api/dvt/remote-confirm') >= 0, 'confirmation at the machine first');
  assert.ok(w.machineCalls.some((c) => c.startsWith('POST /bench/run?test=DVT-SAF-004')), 'the bench is started');
  const brun = w.portalCalls.find((c) => c.kind === 'dvt_run');
  assert.deepStrictEqual([brun.runId, brun.verdict, brun.values.heater_off_time, brun.values.raw_log_attached, brun.values.not_a_field], ['DVT-SAF-004|UUT-01||1', 'PASS', 51.6, true, undefined]);
  const bfile = w.portalCalls.find((c) => c.kind === 'dvt_file');
  assert.ok(bfile && bfile.fileKind === 'bench' && /\.csv$/.test(bfile.fileName), 'the trace is uploaded');
  const live = w.portalCalls.find((c) => c.kind === 'dvt_update' && /heating/.test(c.line || ''));
  assert.ok(live && /DISCONNECT the heater thermistor now/.test(live.line) && /body 61.5/.test(live.line), 'the bench\'s prompt reaches the site: ' + (live && live.line));
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().verdict], ['done', 'PASS']);

  // 11b. a failing value -> FAIL is recorded as measured
  w = world({ testId: 'DVT-SAF-004', bench: true, heaterOff: 95 });
  await w.runner.tick();
  assert.strictEqual(w.portalCalls.find((c) => c.kind === 'dvt_run').verdict, 'FAIL');

  // 12. the bench refuses (thermistor not reading) -> nothing recorded, the reason goes to the site
  w = world({ testId: 'DVT-SAF-004', bench: true, benchRefuses: true });
  await w.runner.tick();
  assert.ok(!w.portalCalls.some((c) => c.kind === 'dvt_run'), 'a refused run records nothing');
  assert.strictEqual(w.finalUpdate().status, 'failed');
  assert.ok(/did not start: TEMP_CHAMBER is not reading/.test(w.finalUpdate().line), w.finalUpdate().line);

  // 12b. no bench service on the machine -> a clear message
  w = world({ testId: 'DVT-SAF-004', bench: true, benchMissing: true });
  await w.runner.tick();
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().line], ['blocked', 'The DVT bench service is not running on the machine (port 3002)']);

  // 13. the bench ends without finishing -> the values it has are kept, no verdict
  w = world({ testId: 'DVT-SAF-004', bench: true, benchStatus: 'ABORTED' });
  await w.runner.tick();
  const arun = w.portalCalls.find((c) => c.kind === 'dvt_run');
  assert.strictEqual(arun.verdict, '', 'an unfinished run has no verdict');
  assert.strictEqual(w.finalUpdate().status, 'failed');
  assert.ok(/ABORTED/.test(w.finalUpdate().line));

  // 14. the site cancels a running bench test -> the bench is told to abort, nothing is judged
  w = world({ testId: 'DVT-SAF-004', bench: true, benchPolls: 40, cancelAfter: 2 });
  await w.runner.tick();
  assert.ok(w.benchAborted >= 1, 'the bench is aborted');
  assert.strictEqual(w.finalUpdate().status, 'cancelled');
  assert.ok(!w.portalCalls.some((c) => c.kind === 'dvt_run' && c.verdict), 'a cancelled run is not judged');

  // 15. an instrument that is not plugged in is said in words BEFORE anyone is asked for Start, and is not "done"
  w = world({ needsMeter: true, noMeter: true });
  await w.runner.tick();
  assert.ok(!w.machineCalls.includes('POST /api/dvt/remote-confirm'), 'no Start dialog for a run that cannot begin');
  assert.strictEqual(w.started, 0);
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().line], ['blocked', "Connect the StarBright sensor to the machine's USB and switch it on"]);
  w = world({ needsMeter: true });                     // with the meter plugged in the run goes on as usual
  await w.runner.tick();
  assert.strictEqual(w.started, 1);
  assert.strictEqual(w.finalUpdate().status, 'done');

  // 16. a script that stops because the meter went away mid-way ends "blocked" with the sentence, not "done: stopped: ..."
  w = world({ stopError: 'no Ophir StarBright on USB - plug the meter into the machine and switch it on' });
  await w.runner.tick();
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().line], ['blocked', "Connect the StarBright sensor to the machine's USB and switch it on"]);
  w = world({ stopError: 'the door closed during the attempt - repeat the step' });     // any other stop is a failure, in its own words
  await w.runner.tick();
  assert.strictEqual(w.finalUpdate().status, 'failed');
  assert.strictEqual(w.finalUpdate().line, 'stopped: the door closed during the attempt - repeat the step');

  // 17. a bench test with the TC-08 unplugged: blocked, the TC-08 named, no Start dialog
  w = world({ testId: 'DVT-SAF-004', bench: true, noTc08: true });
  await w.runner.tick();
  assert.ok(!w.machineCalls.includes('POST /api/dvt/remote-confirm'));
  assert.deepStrictEqual([w.finalUpdate().status, w.finalUpdate().line], ['blocked', "Connect the TC-08 to the machine's USB, with its thermocouple on CH1"]);

  // 18. the poll pace: every 10 s while nobody watches the portal, every 1.5 s while the portal says somebody does
  w = world({ noRequest: true });
  await w.runner.tick();
  assert.strictEqual(w.runner.nextDelaySec(), 10);
  w = world({ noRequest: true, watch: true });
  await w.runner.tick();
  assert.strictEqual(w.runner.nextDelaySec(), 1.5);

  // 19. readiness is read and sent every ~8 s, not with every fast poll
  w = world({ noRequest: true, bench: true, watch: true });
  await w.runner.tick();
  await w.runner.tick();
  await w.runner.tick();
  const polls = w.portalCalls.filter((c) => c.kind === 'dvt_next');
  assert.deepStrictEqual(polls.map((c) => !!c.readiness), [true, false, false]);

  // 20. while a request is handled the runner listens for commands from the portal (a cancel / an answer wakes it at once)
  w = world({ longRun: true, cancelAfter: 2, commandAt: 1 });
  await w.runner.tick();
  assert.ok(w.eventCalls.length >= 1, 'it listened');
  assert.deepStrictEqual([w.eventCalls[0].machine, w.eventCalls[0].since], ['CureBox-1', '']);
  assert.ok(w.eventCalls.every((c) => c.wait > 0), 'each listen is a held request');
  assert.strictEqual(w.finalUpdate().status, 'cancelled');
  const callsAtEnd = w.eventCalls.length;
  await new Promise((r) => setTimeout(r, 120));
  assert.ok(w.eventCalls.length <= callsAtEnd + 1, 'it stops listening when the request is over');

  // 21. the poll is a long poll: the server is asked to hold it, and a poll it held is repeated at once
  w = world({ noRequest: true });
  await w.runner.tick();
  assert.ok(w.portalCalls.find((c) => c.kind === 'dvt_next').wait > 0, 'dvt_next asks the server to hold the call');

  console.log('dvt-runner: all checks passed');
})().catch((e) => { console.error(e); process.exit(1); });
