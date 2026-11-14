// Browser test of the portal's Overview tab (DVT campaign dashboard):  node cloud/google/test_overview.cjs
// Loads Page.html in headless Chrome with a stand-in for google.script.run and a small campaign (2 units, 3 tests) and checks the
// KPI arithmetic (completion = valid finished / owed, pass rate over finished runs, progress by time), that INVALID is neither
// finished nor passed, the unit table with its integrator fields (saved through portalDvtUnitSave), and the Gantt chart.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const CATALOG = {
  version: '0.24', updated: 5,
  phases: [{ id: 1, name: 'Electrical', gate: '', tests: ['T-1', 'T-2'] }, { id: 2, name: 'Thermal', gate: '', tests: ['T-3'] }],
  tests: {
    'T-1': { title: 'Insulation', safety: true, auto: false, minutes: 60, units: ['U1', 'U2'], runs: ['|1'] },
    'T-2': { title: 'Fan sweep', safety: false, auto: true, minutes: 30, units: ['U1', 'U2'], runs: ['|1', '|2'] },
    'T-3': { title: 'Heat up', safety: false, auto: true, minutes: 120, units: ['U1'], runs: ['|1'] },
  },
};
const run = (unit, tid, k, verdict) => ({ unit, testId: tid, variant: '', rep: k, runId: `${tid}|${unit}||${k}`, verdict, operator: 'x',
                                         startedAt: '2026-10-20T10:00:00', recordedAt: 1, note: '', machine: 'CureBox-1', values: {}, files: [] });
const RUNS = [run('U1', 'T-1', 1, 'PASS'), run('U1', 'T-2', 1, 'FAIL'), run('U1', 'T-2', 2, 'INVALID'),
              run('U2', 'T-1', 1, 'PASS'), run('U2', 'T-2', 1, 'PASS'), run('U2', 'T-2', 2, 'PASS')];
const UNITS = [{ unit: 'U1', machine: 'CureBox-1', integrator: 'Integrator A', hwRev: 'B2', fwVersion: '1.0.98', bomRev: '', planStart: '2026-10-01', planEnd: '2026-10-15', note: '', updated: 1 }];
const STUB = `
window.__saved = [];
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, runs: [], errors: [] }],
    portalDvt: () => ({ runs: ${JSON.stringify(RUNS)}, fileUrl: '', catalog: ${JSON.stringify(CATALOG)}, requests: [], runners: [], units: ${JSON.stringify(UNITS)}, build: (typeof PORTAL_BUILD !== 'undefined' ? PORTAL_BUILD : '') }),
    portalDvtUnitSave: (tok, unit, fields) => { window.__saved.push({ unit, fields }); return { ok: true }; },
  };
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); ok(h(...args)); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();`;

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 900 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.evaluateOnNewDocument(STUB);
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, .dvt-tile', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.keyboard.press('Enter'); }
  await page.waitForSelector('.dvt-tile', { timeout: 10000 });

  const tiles = await page.$$eval('.dvt-tile', ts => Object.fromEntries(ts.map(t => [t.querySelector('.mut').textContent, t.querySelector('.num').textContent])));
  check(tiles['Machines (units)'] === '2', 'two units');
  check(tiles['Runs planned'] === '7' && tiles['Runs finished'] === '5', '7 runs owed, 5 finished (the INVALID run is not finished, the open ones are not)');
  check(tiles['Completion'] === '71 %', 'completion = 5 / 7 valid finished runs');
  check(tiles['Passed'] === '4' && tiles['Failed'] === '1', '4 passed, 1 failed');
  check(tiles['Pass rate'] === '80 %', 'pass rate = passed / (passed + failed) = 4 / 5');
  check(tiles['Invalid'] === '1', 'one invalid run is counted on its own');
  check(tiles['Progress by time'] === '55 %', 'progress by time = 165 of 300 estimated minutes');
  check(tiles['Critical issues'] === '0', 'no failed safety test, nothing blocked');

  const text = await page.evaluate(() => document.body.innerText);
  check(text.includes('Delayed'), 'U1 is past its planned end (2026-10-15) and not complete: Delayed');
  check(text.includes('Complete'), 'U2 has every owed run finished: Complete');
  const inputs = await page.$$eval('input[data-ov-field="integrator"]', is => is.map(i => i.value));
  check(inputs.join(',') === 'Integrator A,', 'the integrator of U1 is shown, U2 has none yet');

  // editing a field is saved through portalDvtUnitSave
  await page.$eval('input[data-ov-unit="U2"][data-ov-field="integrator"]', i => { i.value = 'Integrator B'; i.dispatchEvent(new Event('change')); });
  await new Promise(r => setTimeout(r, 300));
  const saved = await page.evaluate(() => window.__saved);
  check(saved.length === 1 && saved[0].unit === 'U2' && saved[0].fields.integrator === 'Integrator B', 'a changed integrator is sent for its unit');

  // the Gantt: a bar per test, a click on a unit shows its tests as rows
  const bars = () => page.$$eval('svg[aria-label="DVT Gantt chart"] rect title', ts => ts.length);
  check(await bars() === 5, 'the Gantt has a bar per test (U1: 3, U2: 2)');
  await page.click('[data-gantt="U1"]');
  check(await bars() === 8, 'a click on U1 adds one row per test');

  // the sections come first; the CureBox chooser belongs to Machine / DVT / Errors and is not on the Overview
  check(!(await page.$('[data-tab]')) && !(await page.$('#search')), 'the Overview has no CureBox chooser (it is about the whole campaign)');
  for (const v of ['machines', 'dvt', 'errors']) {
    await page.click(`[data-view="${v}"]`);
    await new Promise(r => setTimeout(r, 400));
    check(!!(await page.$('[data-tab="all"]')) && !!(await page.$('[data-tab="CureBox-1"]')), `the ${v} section shows the CureBox chooser`);
  }
  await page.click('[data-view="overview"]');
  await page.waitForSelector('.dvt-tile');
  // a phone: the page itself must not scroll sideways (the unit table scrolls inside its card)
  await page.setViewport({ width: 390, height: 800 });
  await new Promise(r => setTimeout(r, 200));
  const wide = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  check(wide[0] <= wide[1], 'no horizontal page scroll at phone width (' + wide.join(' / ') + ')');
  // the phone layout: numbers three to a row, one card per unit, the sections in one scrolling line
  const ph = await page.evaluate(() => {
    const ts = [...document.querySelectorAll('.dvt-tile')].map(t => Math.round(t.getBoundingClientRect().top));
    const tr = document.querySelector('.ov-units tr:nth-child(2)');
    const nav = document.querySelector('.sections');
    return { perRow: ts.filter(y => y === ts[0]).length, trDisplay: getComputedStyle(tr).display, header: getComputedStyle(document.querySelector('.ov-units tr:first-child')).display,
             navWrap: getComputedStyle(nav).flexWrap, navH: Math.round(nav.getBoundingClientRect().height), label: getComputedStyle(tr.querySelector('td[data-l]'), '::before').content };
  });
  check(ph.perRow === 2, 'phone: the four main figures sit two by two (' + ph.perRow + ' to a row)');
  check(ph.trDisplay === 'block' && ph.header === 'none', 'phone: the unit table is one card per unit, without its header row');
  check(ph.navWrap === 'nowrap' && ph.navH < 100, 'phone: the sections stay in one line (' + ph.navH + ' px)');
  check(ph.label.length > 2, 'phone: each card line carries its label (' + ph.label + ')');
  await page.setViewport({ width: 1200, height: 900 });
  if (process.argv.includes('--shot')) await page.screenshot({ path: path.join(__dirname, 'overview.png'), fullPage: true });
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
