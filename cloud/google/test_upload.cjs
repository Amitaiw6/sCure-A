// Browser test of an UPLOAD test on the DVT tab:  node cloud/google/test_upload.cjs
// DVT-OPT-003 (user, 2026-11-15): the UV Uniformity Jig runs on its own; the DVT records it by an upload of the jig's final
// workbook with the date of the scan, and the upload is the PASS. Checks: no Run / Approve on such a test, the Upload form
// (date, file, name when signed in with the shared password), the workbook's Readings sheet turned into the readings CSV,
// the call the site gets, a refusal shown in the form, and - once recorded - "View uniformity" (the heatmap) and Replace.
// The Excel reader (SheetJS, loaded from a CDN on the real site) is stubbed: the test runs offline.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const now = Math.floor(Date.now() / 1000);
const CATALOG = {
  version: '0.79', updated: 5,
  phases: [{ id: 3, name: 'Performance', gate: 'Data complete', tests: ['DVT-OPT-003', 'T-1'] }],
  tests: {
    'DVT-OPT-003': { title: 'UV uniformity — UV Uniformity Jig workbook', group: 'OPT', upload: true, safety: false, auto: false, minutes: 180, units: ['U1'], runs: ['|1'] },
    'T-1': { title: 'Something automatic', safety: false, auto: true, minutes: 10, units: ['U1'], runs: ['|1'] },
  },
};
const STUB = `
window.__calls = [];
window.__runs = [];
window.__refuseNext = false;
window.google = { script: { run: {} } };
// SheetJS stand-in: a workbook with the jig's Readings sheet - two rows with readings, one still empty
window.XLSX = { read: () => ({ SheetNames: ['Readings', 'README'], Sheets: { Readings: 'R', README: 'X' } }),
  utils: { sheet_to_json: () => [['ID', 'Phase', 'X idx', 'Y idx', 'Z idx', 'X mm', 'Y mm', 'Z mm', 'Y steps', 'Z steps', 'Direction', 'Method', 'Servo deg', 'Reading'],
                                [1, 'AUTO', 1, 1, 1, 0, 0, 0, 0, 0, 'FRONT', 'SERVO', 180, 106.5],
                                [2, 'AUTO', 1, 1, 1, 0, 0, 0, 0, 0, 'up', 'SERVO', 90, 81.5],
                                [3, 'AUTO', 1, 1, 1, 0, 0, 0, 0, 0, 'BACK', 'SERVO', 0, null]] } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMe: () => ({ email: '', name: '', role: 'service', roleLabel: 'Service', via: 'password', canService: true, canAdmin: false }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: ${now}, state: {}, runs: [], errors: [] }],
    portalDvt: () => ({ runs: window.__runs, fileUrl: 'https://example.test/exec', catalog: ${JSON.stringify(CATALOG)}, requests: [], units: [],
      build: (typeof PORTAL_BUILD !== 'undefined' ? PORTAL_BUILD : ''), runners: [{ machine: 'CureBox-1', lastSeen: ${now}, online: true, version: '0.9.149', unit: 'U1', readiness: null }] }),
    portalDvtDetail: () => ({ updated: 5, tests: {} }),
    portalDvtWait: () => ({ ver: 1 }),
    portalDvtUpload: (tok, unit, testId, date, fileName, content, who, csv, machine) => {
      window.__calls.push({ unit, testId, date, fileName, content, who, csv, machine });
      if (window.__refuseNext) { window.__refuseNext = false; return { ok: false, message: 'fill in the date of the scan' }; }
      window.__runs = [{ unit, testId, variant: '', rep: 1, runId: testId + '|' + unit + '||1', verdict: 'PASS', operator: who, startedAt: date + 'T12:00:00Z',
        recordedAt: ${now}, note: '', machine, values: { test_date: date, workbook_file: fileName, workbook_uploaded: true },
        files: [{ name: fileName, kind: 'workbook', size: 10, id: 'w1' }, { name: 'uv_scan-readings.csv', kind: 'uv_readings', size: 10, id: 'c1' }] }];
      return { ok: true, runId: testId + '|' + unit + '||1' };
    },
  };
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); ok(h(...args)); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();`;

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

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

  check(!(await page.$('[data-dvt-run-test="DVT-OPT-003"]')) && !(await page.$('[data-dvt-approve="DVT-OPT-003"]')), 'an upload test has no Run and no Approve button');
  const up = await page.$eval('[data-dvt-upload="DVT-OPT-003|U1||1"]', b => ({ t: b.textContent.trim(), h: Math.round(b.getBoundingClientRect().height) }));
  check(/Upload scan file/.test(up.t) && up.h >= 44, 'it has a thumb-sized "Upload scan file" button: ' + JSON.stringify(up));
  check(!(await page.$('[data-dvt-uvmap]')), 'no "View uniformity" before anything is uploaded');

  await page.tap('[data-dvt-upload="DVT-OPT-003|U1||1"]');
  await page.waitForSelector('[data-dvt-upload-form]', { timeout: 3000 });
  const form = await page.evaluate(() => ({
    date: document.getElementById('up-date').value, accept: document.getElementById('up-file').accept, who: !!document.getElementById('up-who'),
    fonts: [...document.querySelectorAll('[data-dvt-upload-form] input')].map(i => getComputedStyle(i).fontSize),
    wide: document.documentElement.scrollWidth <= window.innerWidth }));
  check(/^\d{4}-\d{2}-\d{2}$/.test(form.date), 'the form opens with today\'s date filled in: ' + form.date);
  check(/\.csv/.test(form.accept) && /\.xlsx/.test(form.accept), 'the file picker takes the jig\'s CSV and its Excel workbook: ' + form.accept);
  check(form.who, 'signed in with the shared password, the form asks who uploads');
  check(form.fonts.every(f => f === '16px') && form.wide, 'the fields are 16 px (no zoom on a phone) and nothing scrolls sideways: ' + form.fonts.join(','));

  // nothing chosen: said in the form, nothing sent
  await page.tap('#up-go');
  await sleep(200);
  check(/Choose the scan file/.test(await page.$eval('#up-msg', m => m.textContent)) && (await page.evaluate(() => window.__calls.length)) === 0, 'Upload without a file says what is missing and sends nothing');

  const input = await page.$('#up-file');
  const tmp = path.join(require('os').tmpdir(), 'uv_scan.xlsx');
  require('fs').writeFileSync(tmp, Buffer.from('PK fake workbook bytes'));
  await input.uploadFile(tmp);
  await page.$eval('#up-date', i => { i.value = '2026-11-14'; });
  await page.$eval('#up-who', i => { i.value = 'Amit'; });
  await page.evaluate(() => { window.__refuseNext = true; });
  await page.tap('#up-go');
  await sleep(500);
  check(/fill in the date/.test(await page.$eval('#up-msg', m => m.textContent)) && !!(await page.$('[data-dvt-upload-form]')),
    'a refusal from the site is shown in the form, which stays open with the file still chosen');

  await page.tap('#up-go');
  await page.waitForFunction(() => !document.querySelector('[data-dvt-upload-form]'), { timeout: 5000 });
  await sleep(300);
  const c = (await page.evaluate(() => window.__calls))[1];
  check(c && c.unit === 'U1' && c.testId === 'DVT-OPT-003' && c.date === '2026-11-14' && c.fileName === 'uv_scan.xlsx' && c.who === 'Amit' && c.machine === 'CureBox-1', 'the site gets the unit, the test, the date, the file name, who and the CureBox: ' + JSON.stringify({ ...c, content: '…', csv: '…' }));
  check(Buffer.from(c.content, 'base64').toString() === 'PK fake workbook bytes', 'the workbook goes up byte for byte (base64)');
  check(c.csv === 'x_idx,y_idx,z_idx,direction,reading\n1,1,1,FRONT,106.5\n1,1,1,UP,81.5', 'the Readings sheet becomes the jig\'s readings CSV - directions upper-case, a row without a reading left out: ' + JSON.stringify(c.csv));

  const done = await page.evaluate(() => document.querySelector('[data-dvt-test="DVT-OPT-003"]').textContent);
  check(/scan of 2026-11-14/.test(done) && /uploaded by Amit/.test(done) && !!(await page.$('[data-dvt-test="DVT-OPT-003"] .dvt-ic.on')), 'the test is recorded as passed, with the date of the scan and who uploaded: ' + done.replace(/\s+/g, ' ').slice(0, 120));
  const view = await page.$eval('[data-dvt-uvmap]', a => ({ href: a.getAttribute('href'), target: a.target, t: a.textContent.trim(), h: Math.round(a.getBoundingClientRect().height) }));
  check(view.t === 'View uniformity' && view.target === '_blank' && /\?uvmap=DVT-OPT-003%7CU1%7C%7C1&t=/.test(view.href) && view.h >= 44, '"View uniformity" opens the heatmap of this run in a new tab: ' + JSON.stringify(view));
  check(/Replace/.test(await page.$eval('[data-dvt-upload="DVT-OPT-003|U1||1"]', b => b.textContent)), 'a recorded upload can be replaced');

  // Replace with the jig's CSV (how it saves a scan): read without the Excel reader, the same five columns
  await page.tap('[data-dvt-upload="DVT-OPT-003|U1||1"]');
  await page.waitForSelector('[data-dvt-upload-form]', { timeout: 3000 });
  const csvPath = path.join(require('os').tmpdir(), 'Scan Results 15_11.csv');
  require('fs').writeFileSync(csvPath, '\uFEFFutc,row,id,phase,x_idx,y_idx,z_idx,x_mm,y_mm,z_mm,direction,servo_deg,reading\n'
    + '2026-11-15T10:00:00Z,2,1,AUTO,1,1,1,0,0,0,FRONT,180,106.5\n2026-11-15T10:00:05Z,3,2,AUTO,1,1,1,0,0,0,up,90,81.5\n2026-11-15T10:00:09Z,4,3,AUTO,1,1,1,0,0,0,BACK,0,\n');
  await (await page.$('#up-file')).uploadFile(csvPath);
  await page.$eval('#up-who', i => { i.value = 'Amit'; });
  await page.evaluate(() => { window.XLSX = undefined; });          // the CSV route must not need the Excel reader
  await page.tap('#up-go');
  await page.waitForFunction(() => !document.querySelector('[data-dvt-upload-form]'), { timeout: 5000 });
  const c2 = (await page.evaluate(() => window.__calls)).slice(-1)[0];
  check(c2.fileName === 'Scan Results 15_11.csv' && c2.csv === 'x_idx,y_idx,z_idx,direction,reading\n1,1,1,FRONT,106.5\n1,1,1,UP,81.5',
    'the jig\'s CSV uploads too - read straight from the file: ' + JSON.stringify(c2.csv));
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
