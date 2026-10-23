// The page's cloud sync (lifted out of dvt-tool.html) against a fake portal: what a recorded run looks like
// when it reaches Code.gs, that the raw sweep goes up with it, and that a failed upload loses nothing.
// Driven by DVT/tests/test_dvt_web.py.
const fs = require('fs'), vm = require('vm'), path = require('path'), assert = require('assert');
const WEB = __dirname;
const html = fs.readFileSync(path.join(WEB, 'dvt-tool.html'), 'utf8').replace(/\r\n/g, '\n');
const start = html.indexOf('// ---------- sCure Cloud:');
const end = html.indexOf('\nasync function journal(', start);
if (start < 0 || end < 0) { console.error('the sCure Cloud section was not found in dvt-tool.html'); process.exit(2); }
const src = html.slice(start, end);

const posted = [];                     // every body the page sent to the portal
let refuse = false;                    // make the portal reject the next uploads
const sandbox = {
  console, Date, JSON, Math, Object, Set, Array, String, Number, Promise, TextEncoder,
  setTimeout: () => 0, clearTimeout: () => {}, alert: () => {},
  AbortSignal: { timeout: () => undefined },
  btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
  $: () => null,                                       // no DOM in this harness: renderCloud returns early
  log: () => {}, save: () => {},
  t: (k) => (...a) => `${k}:${a.join(',')}`,
  state: { operator: 'Amitai', unit: 'DVT-01', cloud: { url: '', key: '' }, results: {} },
  runInfo: (id) => { const [tid, unit, variant, rep] = id.split('|'); return { tid, unit, variant, rep: Number(rep) }; },
  runPath: (id) => { const [, , vl, rep] = id.split('|'); return { dir: [], stem: `${vl}_r${rep}` }; },
  sweepCsv: () => 't_s,irradiance_mw_cm2\n0,0\n1,1.8\n',
  // the catalog the page publishes: two tests, one with two variants (variantLabel = the page's k=v join)
  CAT: { catalog_version: '0.24', phases: [{ id: 1, name: 'Electrical safety', gate: 'All ELE tests PASS', tests: ['DVT-ELE-001', 'DVT-ELE-005'] }] },
  TESTS: { 'DVT-ELE-001': { title: 'Protective earth', units: ['DVT-01'], variants: [{}], repetitions: 1, duration_est_min: 90, safety_critical: null },
           'DVT-ELE-005': { title: 'Rated input current', units: ['DVT-01'], variants: [{ mains_voltage: 100 }, { mains_voltage: 230 }], repetitions: 2, safety_critical: true } },
  DVT_AUTO: { has: (tid) => tid === 'DVT-ELE-001', detailOf: (t) => ({ purpose: 'why ' + t.title, steps: (t.procedure_steps || []).map((x) => x.step), bench: (t.procedure_steps || []).some((x) => x.tool === 'bench') }) },
  variantLabel: (v) => Object.entries(v).map(([k, x]) => `${k}=${x}`).join(','),
  isTrace: () => false,                                // the graph path needs a canvas; covered by trace-check
  tracePng: async () => { throw new Error('not used here'); },
  fetch: async (url, opts) => {
    const body = JSON.parse(opts.body);
    posted.push({ url, body, type: opts.headers['Content-Type'] });
    if (refuse) return { ok: false, status: 500, json: async () => null };
    const reply = body.kind === 'dvt_machines' ? { ok: true, machines: ['CureBox-1', 'Demo-CureBox'] } : { ok: true };
    return { ok: true, status: 200, json: async () => reply };
  },
};
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const S = sandbox.state;
const CLOUD = () => vm.runInContext('CLOUD', sandbox);   // const in the page's scope: not a sandbox global

(async () => {
  // 1. without a URL + key nothing is queued and nothing is sent
  sandbox.cloudQueue('SAF-016|DVT-01|wavelength=450|1');
  await sandbox.cloudSyncNow();
  assert.strictEqual(posted.length, 0, 'an unconfigured cloud must stay silent');

  // 2. a recorded run reaches the portal as one dvt_run, with its values and the operator who signed it
  S.cloud = { url: 'https://script.google.com/macros/s/X/exec', key: 'dk' };
  const id = 'SAF-016|DVT-01|wavelength=450|1';
  S.results[id] = { values: { max_irradiance_10cm: 1.8, leak_location: 'hinge' }, verdict: 'PASS', by: 'Amitai',
                    at: '2026-10-12T05:00:00Z', note: 'leak at the hinge' };
  sandbox.cloudQueue(id);
  await sandbox.cloudSyncNow();
  // the catalog goes first, once: every phase and test with the runs it owes, so the portal lists untouched tests too
  assert.strictEqual(posted.length, 2);
  const cat = posted[0].body;
  assert.strictEqual(cat.kind, 'dvt_catalog');
  assert.strictEqual(cat.catalog.version, '0.24');
  assert.deepStrictEqual(cat.catalog.phases[0].tests, ['DVT-ELE-001', 'DVT-ELE-005']);
  assert.deepStrictEqual(cat.catalog.tests['DVT-ELE-001'].runs, ['|1']);
  assert.deepStrictEqual(cat.catalog.tests['DVT-ELE-005'].runs, ['mains_voltage=100|1', 'mains_voltage=100|2', 'mains_voltage=230|1', 'mains_voltage=230|2']);
  assert.strictEqual(cat.catalog.tests['DVT-ELE-001'].auto, true);
  assert.strictEqual(cat.catalog.tests['DVT-ELE-005'].safety, true);
  assert.strictEqual(cat.catalog.tests['DVT-ELE-001'].d.purpose, 'why Protective earth', "Sync all publishes each test's description too");
  posted.shift();
  assert.strictEqual(posted.length, 1);
  assert.strictEqual(posted[0].url, S.cloud.url);
  assert.ok(posted[0].type.startsWith('text/plain'), 'text/plain keeps the browser from sending a CORS preflight');
  assert.deepStrictEqual(posted[0].body, { kind: 'dvt_run', unit: 'DVT-01', testId: 'SAF-016', variant: 'wavelength=450',
    rep: 1, runId: id, verdict: 'PASS', operator: 'Amitai', startedAt: '2026-10-12T05:00:00Z',
    note: 'leak at the hinge', machine: '', values: { max_irradiance_10cm: 1.8, leak_location: 'hinge' }, machineKey: 'dk' });

  // 3. the raw samples of an automatic measurement go up next to the run
  posted.length = 0;
  S.results[id].autos = { uv_sweep: { kind: 'uv_sweep', at: '2026-10-12T05:01:02.500Z', samples: [[0, 0], [1, 1.8]] } };
  sandbox.cloudQueue(id);
  await sandbox.cloudSyncNow();
  assert.strictEqual(posted.length, 2);
  const file = posted[1].body;
  assert.strictEqual(file.kind, 'dvt_file');
  assert.strictEqual(file.fileKind, 'uv_sweep');                       // the sheet's "kind" column, not the routing kind
  assert.strictEqual(file.runId, id);
  assert.strictEqual(file.fileName, 'wavelength=450_r1_uv_sweep_20261012T050102.csv');   // same name the results folder uses
  assert.strictEqual(Buffer.from(file.contentBase64, 'base64').toString('utf8'), 't_s,irradiance_mw_cm2\n0,0\n1,1.8\n');

  // 4. a portal that refuses keeps the run queued - the folder is the record, the cloud never loses one
  posted.length = 0;
  refuse = true;
  sandbox.cloudQueue(id);
  await sandbox.cloudSyncNow();
  assert.strictEqual(CLOUD().queue.size, 1, 'a failed upload must stay queued');
  assert.ok(CLOUD().error, 'the bar must say the portal was not reached');
  refuse = false;
  await sandbox.cloudSyncNow();
  assert.strictEqual(CLOUD().queue.size, 0);
  assert.strictEqual(CLOUD().error, '');

  // 5. the CureBox list comes from the portal, and assigning the unit re-files its runs under that CureBox
  posted.length = 0;
  await sandbox.cloudLoadMachines();
  assert.deepStrictEqual([...CLOUD().machines], ['CureBox-1', 'Demo-CureBox']);
  assert.strictEqual(posted[0].body.kind, 'dvt_machines');
  posted.length = 0;
  sandbox.cloudSetMachine('CureBox-1');
  while (CLOUD().busy) await new Promise((r) => setImmediate(r));
  const refiled = posted.find((x) => x.body.kind === 'dvt_run');
  assert.ok(refiled, "assigning a CureBox must re-send the unit's runs");
  assert.strictEqual(refiled.body.machine, 'CureBox-1');
  assert.strictEqual(S.cloud.machines['DVT-01'], 'CureBox-1');           // remembered per DVT unit
  S.unit = 'DVT-02';
  assert.strictEqual(sandbox.cloudRunBody(id).machine, 'CureBox-1');      // a run keeps ITS unit's CureBox, not the selected unit's

  console.log('dvt-tool.html cloud sync: all checks passed');
})().catch((e) => { console.error(e); process.exit(1); });
