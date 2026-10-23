// Browser test of the portal's Race tab:  node cloud/google/test_race.cjs [--shot]
// Three units against the clock: UUT-1 finishes in 100 min, UUT-2 in 80, UUT-3 is still running. Checks the ranking and the medals,
// the clock of a finished unit (fixed) and of a running one (ticks), the time each test took (exact when it was started from the
// site, "~" when it is the gap since the previous result) against the estimate, the fastest unit per test, the winner once
// everybody is done, the Start button and the choice of who takes part - on a desktop and on a phone.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const BASE = 1800000000;                                   // the start of the race, in seconds
const iso = min => new Date((BASE + min * 60) * 1000).toISOString();
const CATALOG = {
  version: '0.25', updated: 5, phases: [{ id: 1, name: 'Safety', gate: '', tests: ['T-A', 'T-B'] }],
  tests: {
    'T-A': { title: 'Door interlock', safety: true, auto: true, minutes: 60, units: ['U1', 'U2', 'U3'], runs: ['|1'] },
    'T-B': { title: 'Heater cutoff', safety: false, auto: true, minutes: 30, units: ['U1', 'U2', 'U3'], runs: ['|1'] },
  },
};
const run = (unit, tid, min) => ({ unit, testId: tid, variant: '', rep: 1, runId: `${tid}|${unit}||1`, verdict: 'PASS', operator: 'x', startedAt: iso(min), recordedAt: BASE + min * 60, note: '', machine: 'CureBox-1', values: {}, files: [] });
const RUNS = [run('U1', 'T-A', 50), run('U1', 'T-B', 100), run('U2', 'T-A', 40), run('U2', 'T-B', 80), run('U3', 'T-A', 70)];
const U3_LAST = run('U3', 'T-B', 120);
const REQS = [{ id: 1, machine: 'CureBox-1', unit: 'U2', testId: 'T-A', status: 'done', requested: BASE, started: BASE + 300, finished: BASE + 2400, line: '', prompt: null, verdict: 'PASS', runIds: [] }];
const UNITS = [{ unit: 'U1', machine: '', integrator: 'Integrator A', hwRev: '', fwVersion: '', bomRev: '', planStart: '', planEnd: '', note: '', updated: 1 },
               { unit: 'U2', machine: '', integrator: 'Integrator B', hwRev: '', fwVersion: '', bomRev: '', planStart: '', planEnd: '', note: '', updated: 1 }];
const STUB = `
window.__t0 = Date.now(); window.__calls = []; window.__u3done = false; window.__start = ${BASE}; window.__units = [];
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, runs: [], errors: [], programs: [], prints: [] }],
    portalDvt: () => ({ runs: ${JSON.stringify(RUNS)}.concat(window.__u3done ? [${JSON.stringify(U3_LAST)}] : []), fileUrl: '', catalog: ${JSON.stringify(CATALOG)},
      requests: ${JSON.stringify(REQS)}, runners: [], units: ${JSON.stringify(UNITS)}, build: '0.9.123', now: ${BASE} + 9000 + (Date.now() - window.__t0) / 1000,
      race: { start: window.__start, units: window.__units } }),
    portalRaceSet: (tok, d) => { window.__calls.push(d); if (d.start === 'now') window.__start = ${BASE}; if (d.start === 0) window.__start = 0; if (d.units) window.__units = d.units; return { ok: true }; },
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
  page.on('dialog', d => d.accept());
  await page.evaluateOnNewDocument(STUB);
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, [data-view="race"]', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.keyboard.press('Enter'); }
  await page.waitForSelector('[data-view="race"]', { timeout: 10000 });
  await page.click('[data-view="race"]');
  await page.waitForSelector('.race-card', { timeout: 10000 });
  check(!(await page.$('[data-tab]')), 'the Race tab has no CureBox chooser (it is about all the units)');

  const lanes = () => page.$$eval('.race-card', cs => cs.map(c => ({ u: c.dataset.race, rank: c.querySelector('.race-rank').textContent.trim(), clock: c.querySelector('.race-clock') ? c.querySelector('.race-clock').textContent.trim() : '', text: c.innerText.replace(/\s+/g, ' ') })));
  let l = await lanes();
  check(l.map(x => x.u).join(',') === 'U2,U1,U3', 'ranking: U2 (80 min), U1 (100 min), then U3 still running: ' + l.map(x => x.u).join(','));
  check(l[0].rank === '🥇' && l[1].rank === '🥈' && l[2].rank === '🏃', 'medals for the finishers, a runner for the one still going');
  check(l[0].clock === '1 h 20 min 00 s' && l[1].clock === '1 h 40 min 00 s', 'the clocks of the finished units are fixed: ' + l[0].clock + ' / ' + l[1].clock);
  check(l[0].text.includes('Integrator B') && /pace/.test(l[0].text), 'a lane shows the integrator and the pace');
  check(/2 of 3 finished/.test(await page.$eval('.race-lead', e => e.textContent)) && !(await page.$('.race-win')), 'no winner yet: two of three have finished');

  // the clock of the running unit ticks
  const c1 = l[2].clock;
  await sleep(1300);
  l = await lanes();
  check(l[2].clock !== c1 && /^2 h 30 min/.test(l[2].clock), 'the running clock ticks (' + c1 + ' -> ' + l[2].clock + ')');

  // the tests of a unit: exact time from a request, "~" from the gap, against the estimate
  await page.click('[data-race="U2"]');
  await sleep(200);
  const rows = await page.$$eval('table.cards tr', trs => trs.slice(1).map(t => t.innerText.replace(/\s+/g, ' ')));
  const ta = rows.find(r => r.includes('T-A')), tb = rows.find(r => r.includes('T-B'));
  check(/ 35 min /.test(ta) && !/~/.test(ta) && /-25 min/.test(ta), 'T-A took 35 min (exact, from the request), 25 min under its 60 min estimate: ' + ta);
  check(/ ~40 min /.test(tb) && /\+10 min/.test(tb), 'T-B ~40 min (the gap since the previous result), 10 min over its estimate: ' + tb);
  const champ = await page.$$eval('.card h2', hs => hs.map(h => h.textContent).join('|'));
  check(/Test champions/.test(champ), 'a table of the fastest unit per test appears');
  const champRows = await page.$$eval('.card:last-of-type table.cards tr', trs => trs.slice(1).map(t => t.innerText.replace(/\s+/g, ' ')));
  check(champRows.some(r => /T-A/.test(r) && /U2/.test(r)) && champRows.some(r => /T-B/.test(r) && /U2/.test(r)), 'U2 is the fastest on both tests: ' + champRows.join(' || '));

  // everybody finishes: the winner is declared
  await page.evaluate(() => { window.__u3done = true; return loadDvt(); });
  await sleep(400);
  l = await lanes();
  check(l.map(x => x.u).join(',') === 'U2,U1,U3' && l[2].rank === '🥉', 'U3 finishes in 120 min: third, bronze');
  const win = await page.$eval('.race-win', e => e.textContent.replace(/\s+/g, ' '));
  check(/UUT?-?2|U2/.test(win) && /1 h 20 min/.test(win) && win.includes('wins'), 'the winner is announced: ' + win);

  // start / reset / who is in the race
  await page.evaluate(() => { window.__start = 0; return loadDvt(); });
  await sleep(300);
  await page.click('#race-start');
  await sleep(300);
  check(JSON.stringify(await page.evaluate(() => window.__calls[0])) === JSON.stringify({ start: 'now' }), 'Start the race sends the official start');
  await page.click('details summary');
  await page.click('[data-race-unit="U3"]');
  await sleep(300);
  check(JSON.stringify(await page.evaluate(() => window.__calls.at(-1))) === JSON.stringify({ units: ['U1', 'U2'] }), 'taking U3 out of the race sends the list of who is in');
  l = await lanes();
  check(l.length === 2, 'the race now has two units');

  // a phone (a page of its own: switching a page to a mobile viewport reloads it)
  const ph = await browser.newPage();
  await ph.emulate({ viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148' });
  ph.on('pageerror', e => errors.push(String(e)));
  await ph.evaluateOnNewDocument(STUB);
  await ph.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await ph.waitForSelector('#pw, [data-view="race"]', { timeout: 10000 });
  if (await ph.$('#pw')) { await ph.type('#pw', 'pw'); await ph.tap('#go'); }
  await ph.waitForSelector('[data-view="race"]', { timeout: 10000 });
  await ph.tap('[data-view="race"]');
  await ph.waitForSelector('.race-card', { timeout: 10000 });
  const phone = await ph.evaluate(() => { const c = document.querySelector('.race-card'), t = c.querySelector('.race-clock').getBoundingClientRect();
    return { page: document.documentElement.scrollWidth, h: Math.round(c.getBoundingClientRect().height), clockInView: t.right <= 390 && t.left >= 0 }; });
  check(phone.page <= 391 && phone.clockInView && phone.h >= 44, 'phone: nothing scrolls sideways, the clock is on screen, the lane is a big target: ' + JSON.stringify(phone));
  if (process.argv.includes('--shot')) await ph.screenshot({ path: path.join(__dirname, 'race.png'), fullPage: true });
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
