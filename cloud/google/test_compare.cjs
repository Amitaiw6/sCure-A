// Browser test of the portal's Compare tab:  node cloud/google/test_compare.cjs [--shot]
// Three units recorded one test (U1 twice); checks the columns (latest run / mean / runs of one unit), the reference and the
// tolerance that decide what stands out, yes / no checks that differ, the spread, the "nothing to compare" case and the curve
// overlay built from the sample files.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const CATALOG = {
  version: '0.24', updated: 5, phases: [{ id: 1, name: 'Thermal', gate: '', tests: ['T-A', 'T-B', 'T-C'] }],
  tests: {
    'T-A': { title: 'Heat up with a very long title that would make the selector wider than a phone screen', safety: false, auto: true, minutes: 60, units: ['U1', 'U2', 'U3', 'U4'], runs: ['|1'] },
    'T-C': { title: 'Layers', safety: false, auto: true, minutes: 45, units: ['U1'], runs: ['L1|1', 'L2|1', 'L3|1'] },
    'T-B': { title: 'Door', safety: true, auto: false, minutes: 30, units: ['U1'], runs: ['|1'] },
  },
};
const run = (unit, tid, rep, when, verdict, values, files) => ({ unit, testId: tid, variant: '', rep, runId: `${tid}|${unit}||${rep}`, verdict, operator: 'x',
  startedAt: when, recordedAt: 1, note: '', machine: 'CureBox-1', values, files: files || [] });
const RUNS = [
  run('U1', 'T-A', 1, '2026-10-20T10:00:00Z', 'PASS', { peak: 80, ok: true, comment: 'first', stamp_timestamp: 'x' }),
  run('U1', 'T-A', 2, '2026-10-21T10:00:00Z', 'PASS', { peak: 84, ok: true, comment: 'second', stamp_timestamp: 'y' }, [{ name: 'a.csv', kind: 'sweep', size: 10, id: 'f1' }]),
  run('U2', 'T-A', 1, '2026-10-21T11:00:00Z', 'PASS', { peak: 82, ok: true, comment: 'second', stamp_timestamp: 'z' }, [{ name: 'b.csv', kind: 'sweep', size: 10, id: 'f2' }]),
  run('U3', 'T-A', 1, '2026-10-21T12:00:00Z', 'FAIL', { peak: 110, ok: false, comment: 'second', stamp_timestamp: 'w' }),
  run('U1', 'T-B', 1, '2026-10-21T13:00:00Z', 'PASS', { door_open: true }),
];
const FILES = { f1: { name: 'a.csv', text: 't_s,chamber_c,phase\n0,20,warm\n10,40,warm\n20,60,hold\n' }, f2: { name: 'b.csv', text: 't_s,chamber_c,phase\n0,21,warm\n10,45,warm\n20,70,hold\n' } };
const STUB = `
window.__files = 0;
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, runs: [], errors: [] }],
    portalDvt: () => ({ runs: ${JSON.stringify(RUNS)}, fileUrl: '', catalog: ${JSON.stringify(CATALOG)}, requests: [], runners: [], units: [], build: '0.9.123' }),
    portalDvtFiles: (tok, ids) => { window.__files += ids.length; const all = ${JSON.stringify(FILES)}; const o = {}; ids.forEach(i => { if (all[i]) o[i] = all[i]; }); return { ok: true, files: o }; },
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
  await page.setViewport({ width: 1200, height: 900 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.evaluateOnNewDocument(STUB);
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, [data-view="compare"]', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.keyboard.press('Enter'); }
  await page.waitForSelector('[data-view="compare"]', { timeout: 10000 });
  await page.click('[data-view="compare"]');
  await page.waitForSelector('.cmp-row', { timeout: 10000 });
  check(!(await page.$('[data-tab]')), 'the Compare tab has no CureBox chooser (it compares across units)');

  // a row by its field name -> its cells (text + whether tinted amber / red)
  const row = name => page.evaluate(n => {
    const r = [...document.querySelectorAll('.cmp-row')].find(x => x.firstElementChild.textContent.trim() === n);
    if (!r) return null;
    return [...r.children].map(td => ({ text: td.textContent.trim().replace(/\s+/g, ' '), red: /220,38,38/.test(td.getAttribute('style') || ''), amber: /217,119,6/.test(td.getAttribute('style') || '') }));
  }, name);
  const fields = await page.$$eval('.cmp-row', rs => rs.map(r => r.firstElementChild.textContent.trim()));
  check(fields.join(',') === 'peak,ok,comment,stamp_timestamp', 'numbers first, then checks, text, then time stamps: ' + fields.join(','));

  // default: one column per unit, the latest run of U1 (84), reference = the first unit
  let peak = await row('peak');
  check(peak[1].text.startsWith('84') && peak[2].text.startsWith('82') && peak[3].text.startsWith('110'), 'U1 shows its latest run (84), U2 82, U3 110');
  check(!peak[1].red && !peak[1].amber && !peak[2].red && !peak[2].amber && peak[3].red, 'U3 is 31 % off the reference U1: red; U2 (-2.4 %) is not flagged');
  check(peak[3].text.includes('+31.0 %'), 'the deviation from the reference is written in the cell');
  check(peak[6].text.includes('30.4 %'), 'spread = (110 - 82) / mean 92 = 30.4 %');
  const ok = await row('ok');
  check(ok[3].red && !ok[2].red, 'a yes / no check that differs is red (U3 failed it)');
  const com = await row('comment');
  check(com[1].amber === false && com[2].amber === false && com[3].amber === false, 'text equal to the reference ("second") is not flagged');
  const flagged = await page.$$eval('.cmp-row', rs => rs.filter(r => r.dataset.flag !== '0').length);
  check(flagged >= 2, 'the flagged rows are marked for the legend count');

  // tolerance: with 40 % nothing is off any more
  await page.$eval('#cmp-tol', i => { i.value = '40'; i.dispatchEvent(new Event('change')); });
  await sleep(200);
  peak = await row('peak');
  check(!peak[3].red && !peak[3].amber, 'a 40 % tolerance accepts the 31 % deviation');
  await page.$eval('#cmp-tol', i => { i.value = '10'; i.dispatchEvent(new Event('change')); });
  await sleep(200);

  // every unit of the test is a column, also one with no results yet (U4); it cannot be the reference and does not skew the numbers
  const heads0 = await page.$$eval('table tr:first-child th', ths => ths.map(t => t.textContent.trim().replace(/\s+/g, ' ')));
  check(heads0.some(h => h.startsWith('U4') && h.includes('no results yet')), 'U4 is a column marked "no results yet": ' + heads0.join(' | '));
  const refOpts = await page.$$eval('#cmp-ref option', os => os.map(o => o.value + (o.disabled ? ':off' : '')));
  check(refOpts.join(',') === 'U1,U2,U3,U4:off', 'the reference can only be a unit with results: ' + refOpts.join(','));
  check(peak[4].text === '—', 'the empty column shows nothing for the field');

  // another reference: U3 -> U1 is 23.6 % below it (amber would need > 10, red > 20)
  await page.$eval('#cmp-ref', s => { s.value = 'U3'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  peak = await row('peak');
  check(peak[1].red && peak[1].text.includes('-23.6 %'), 'with U3 as the reference U1 is -23.6 % off: red');

  // the mean of the repetitions: U1 = (80 + 84) / 2 = 82
  await page.$eval('#cmp-ref', s => { s.value = 'U1'; s.dispatchEvent(new Event('change')); });
  await page.$eval('#cmp-basis', s => { s.value = 'mean'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  peak = await row('peak');
  check(peak[1].text.startsWith('82') && peak[2].text.startsWith('82') && peak[2].text.includes('0.0 %'), 'the mean of U1\'s two runs is 82, equal to U2');

  // all units, all tests: a matrix of results, a click opens the test
  await page.$eval('#cmp-mode', s => { s.value = 'matrix'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  const m = await page.evaluate(() => [...document.querySelectorAll('.cmp-mrow')].map(r => ({ test: r.dataset.test, flag: r.dataset.flag, cells: [...r.children].slice(1).map(td => td.textContent.trim()) })));
  check(m.length === 3, 'the matrix has a row per test of the catalog');
  check(m[0].test === 'T-A' && m[0].cells.join(',') === 'PASS,PASS,FAIL,not run' && m[0].flag === '1', 'T-A: PASS on U1 and U2, FAIL on U3, not run on U4 - flagged as differing: ' + m[0].cells.join(','));
  check(m[1].test === 'T-B' && m[1].cells.join(',') === 'PASS,n/a,n/a,n/a' && m[1].flag === '0', 'T-B is only owed by U1: n/a elsewhere, nothing to differ');
  await page.click('.cmp-mrow[data-test="T-B"]');
  await sleep(200);
  check(await page.$eval('#cmp-test', s => s.value) === 'T-B' && !!(await page.$('.cmp-row')), 'a click on a test opens its comparison');
  await page.$eval('#cmp-test', s => { s.value = 'T-A'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  // across the runs of one unit
  await page.$eval('#cmp-mode', s => { s.value = 'runs'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  const heads = await page.$$eval('table tr:first-child th', ths => ths.map(t => t.textContent.trim().replace(/\s+/g, ' ')));
  check(heads.filter(h => /^r\d/.test(h)).length === 2, 'runs mode: a column per run of U1 (two): ' + heads.join(' | '));
  peak = await row('peak');
  check(peak[1].text.startsWith('80') && peak[2].text.startsWith('84'), 'oldest run first, then the later one');

  // a test only one unit has: nothing to compare yet
  await page.$eval('#cmp-test', s => { s.value = 'T-B'; s.dispatchEvent(new Event('change')); });
  await sleep(200);
  check((await page.evaluate(() => document.body.innerText)).includes('nothing to compare yet'), 'a single column says there is nothing to compare yet');

  // the DVT list: a test of several variants counts "cases", one click runs them all in turn
  await page.click('[data-view="dvt"]');
  await page.waitForSelector('[data-tab="CureBox-1"]');
  await page.click('[data-tab="CureBox-1"]');          // the Run buttons are for the chosen CureBox
  await page.waitForSelector('[data-dvt-run-test]', { timeout: 8000 });
  const dvtText = await page.evaluate(() => document.body.innerText);
  check(/0\/3 cases/.test(dvtText) && !/0\/3 runs/.test(dvtText), 'DVT list: a test with three variants shows "0/3 cases"');
  await page.click('[data-view="compare"]');
  await page.waitForSelector('#cmp-test');
  // the curves: back to T-A across units, the two sample files load by themselves and make two lines
  await page.$eval('#cmp-test', s => { s.value = 'T-A'; s.dispatchEvent(new Event('change')); });
  await page.$eval('#cmp-mode', s => { s.value = 'units'; s.dispatchEvent(new Event('change')); });
  await page.waitForSelector('svg[aria-label="Curve comparison"]', { timeout: 8000 });
  let lines = await page.$$eval('svg[aria-label="Curve comparison"] polyline', ls => ls.length);
  check(lines === 2, 'two sample files (U1, U2) are drawn as two curves');
  const cols = await page.$$eval('#cmp-col option', os => os.map(o => o.value));
  check(cols.join(',') === 'chamber_c', 'only numeric columns can be plotted (the phase text is left out): ' + cols.join(','));
  check(await page.evaluate(() => window.__files) === 2, 'the files were fetched once, not on every redraw');
  // a phone: a long test title in the selector must not widen the page
  await page.setViewport({ width: 390, height: 800 });
  await sleep(200);
  const wide = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  check(wide[0] <= wide[1], 'no horizontal page scroll at phone width (' + wide.join(' / ') + ')');
  const sticky = await page.evaluate(() => getComputedStyle(document.querySelector('.cmp-table td:first-child')).position);
  check(sticky === 'sticky', 'phone: the first column of a comparison stays in view while the table scrolls');
  if (process.argv.includes('--shot')) await page.screenshot({ path: path.join(__dirname, 'compare.png'), fullPage: true });
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
