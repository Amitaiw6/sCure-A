// Browser test of an upload test split into cases:  node cloud/google/test_upload_cases.cjs
// DVT-OPT-003 at two LED intensities (catalog 0.86, user 2026-11-18: "a second upload option for the uv uniformity file. one
// is 100 percent intensity and one is 60"). Checks: one Upload button per intensity, each labelled; a scan uploaded before the
// split (no case) shows as the 100 % one; the form names the intensity and sends the case; once both are in, both show their
// scan date with their own "View uniformity", and the test is complete.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const now = Math.floor(Date.now() / 1000);
const CATALOG = {
  version: '0.86', updated: 5,
  phases: [{ id: 3, name: 'Performance', gate: 'Data complete', tests: ['DVT-OPT-003'] }],
  tests: {
    'DVT-OPT-003': { title: 'UV uniformity — UV Uniformity Jig workbook', group: 'OPT', upload: true, safety: false, auto: false, minutes: 180, units: ['U1'],
                     runs: ['intensity=100|1', 'intensity=60|1'] },
  },
};
const STUB = `
window.__calls = [];
// a scan uploaded before the split: recorded without a case
const rec = (variant, date, file) => ({ unit: 'U1', testId: 'DVT-OPT-003', variant, rep: 1, runId: 'DVT-OPT-003|U1|' + variant + '|1', verdict: 'PASS',
  operator: 'Amit', startedAt: date + 'T12:00:00Z', recordedAt: ${now}, note: '', machine: 'CureBox-1', values: { test_date: date, workbook_file: file, workbook_uploaded: true },
  files: [{ name: file, kind: 'workbook', size: 10, id: 'w-' + variant }, { name: 'r.csv', kind: 'uv_readings', size: 10, id: 'c-' + variant }] });
window.__runs = [rec('', '2026-11-15', 'old.csv')];
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMe: () => ({ email: '', name: '', role: 'service', roleLabel: 'Service', via: 'password', canService: true, canAdmin: false }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: ${now}, state: {}, runs: [], errors: [] }],
    portalDvt: () => ({ runs: window.__runs, fileUrl: 'https://example.test/exec', catalog: ${JSON.stringify(CATALOG)}, requests: [], units: [],
      build: (typeof PORTAL_BUILD !== 'undefined' ? PORTAL_BUILD : ''), runners: [{ machine: 'CureBox-1', lastSeen: ${now}, online: true, version: '0.9.159', unit: 'U1', readiness: null }] }),
    portalDvtDetail: () => ({ updated: 5, tests: {} }),
    portalDvtWait: () => ({ ver: 1 }),
    portalDvtUpload: (tok, unit, testId, date, fileName, content, who, csv, machine, variant) => {
      window.__calls.push({ unit, testId, date, fileName, who, machine, variant });
      window.__runs = window.__runs.filter(r => r.variant !== variant).concat([rec(variant, date, fileName)]);
      return { ok: true, runId: testId + '|' + unit + '|' + variant + '|1' };
    },
  };
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); ok(h(...args)); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();`;

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ID100 = 'DVT-OPT-003|U1|intensity=100|1', ID60 = 'DVT-OPT-003|U1|intensity=60|1';

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });
  const page = await browser.newPage();
  await page.emulate({ viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148' });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.evaluateOnNewDocument(STUB);
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, .subtab', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.tap('#go'); }
  await page.waitForSelector('.subtab', { timeout: 10000 });
  await sleep(300);
  await page.tap('[data-view="dvt"]');
  await page.waitForSelector('[data-dvt-test="DVT-OPT-003"]', { timeout: 8000 });
  await sleep(300);

  const row = () => page.evaluate(() => document.querySelector('[data-dvt-test="DVT-OPT-003"]').textContent.replace(/\s+/g, ' '));
  let t = await row();
  check(/100 % intensity:/.test(t) && /60 % intensity:/.test(t), 'the test shows both intensities: ' + t.slice(0, 160));
  check(/scan of 2026-11-15/.test(t), 'the scan uploaded before the split shows as the 100 % one');
  check(!!(await page.$(`[data-dvt-uvmap="DVT-OPT-003|U1||1"]`)), 'its heatmap is still offered');
  const b60 = await page.$eval(`[data-dvt-upload="${ID60}"]`, b => ({ t: b.textContent.trim(), h: Math.round(b.getBoundingClientRect().height) }));
  check(/Upload scan file/.test(b60.t) && b60.h >= 44, 'the 60 % one has its own thumb-sized Upload button: ' + JSON.stringify(b60));
  check(/Replace/.test(await page.$eval(`[data-dvt-upload="${ID100}"]`, b => b.textContent)), 'the 100 % one offers Replace');
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'nothing scrolls sideways at 390 px');

  await page.tap(`[data-dvt-upload="${ID60}"]`);
  await page.waitForSelector('[data-dvt-upload-form]', { timeout: 3000 });
  const f = await page.evaluate(() => ({ v: document.querySelector('[data-dvt-upload-form]').dataset.variant,
                                         txt: document.querySelector('[data-dvt-upload-form]').textContent.replace(/\s+/g, ' ') }));
  check(f.v === 'intensity=60' && /Scan at 60 % intensity/.test(f.txt), 'the form is for the 60 % scan and says so: ' + f.txt.slice(0, 120));

  const tmp = path.join(require('os').tmpdir(), 'scan60.csv');
  require('fs').writeFileSync(tmp, 'utc,x_idx,y_idx,z_idx,direction,reading\n2026-11-18T10:00:00Z,1,1,1,UP,48.9\n');
  await (await page.$('#up-file')).uploadFile(tmp);
  await page.$eval('#up-date', i => { i.value = '2026-11-18'; });
  await page.$eval('#up-who', i => { i.value = 'Amit'; });
  await page.tap('#up-go');
  await page.waitForFunction(() => !document.querySelector('[data-dvt-upload-form]'), { timeout: 5000 });
  await sleep(300);
  const c = (await page.evaluate(() => window.__calls))[0];
  check(c && c.variant === 'intensity=60' && c.fileName === 'scan60.csv' && c.date === '2026-11-18', 'the site gets the 60 % case with the file: ' + JSON.stringify(c));

  t = await row();
  check(/scan of 2026-11-15/.test(t) && /scan of 2026-11-18/.test(t), 'both scans are shown, each with its date: ' + t.slice(0, 200));
  check(!!(await page.$(`[data-dvt-uvmap="${ID60}"]`)), 'the 60 % scan has its own "View uniformity"');
  check(/2\/2/.test(t), 'the test counts both runs as recorded (2/2)');
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
