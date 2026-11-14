// Browser test of the program editor of the portal:  node cloud/google/test_editor.cjs
// A program whose Cure step has no heating (UV only, no temperature) must open as UV only - not with an invented temperature - and
// must be saved the same way; ventilation (a setting of such a step) must survive an edit. (user, 2026-10-23: "I edit a program defined
// without heating and it writes a temperature".)
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const PROGRAM = { id: 'p1', name: 'UV only', totalDuration: 25, steps: [
  { step: 1, process: 'Cure', temperature: null, time: 15, uvIntensity: 60, ventilation: true, timerMode: 'on-target', uvStartMode: 'at-target' },
  { step: 2, process: 'Heating', temperature: 50, time: 10 } ] };
const STUB = `
window.__saved = [];
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, runs: [], errors: [], prints: [], programs: [${JSON.stringify(PROGRAM)}] }],
    portalCommand: (tok, name, d) => { window.__saved.push(d); return { ok: true }; },
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
  await page.waitForSelector('#pw, [data-view="machines"]', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.keyboard.press('Enter'); }
  await page.waitForSelector('[data-view="machines"]', { timeout: 10000 });
  await page.click('[data-view="machines"]');
  await page.waitForSelector('[data-edit]', { timeout: 10000 });
  await page.click('[data-edit]');
  await page.waitForSelector('.steps .sp', { timeout: 5000 });

  const step = n => page.evaluate(i => {
    const r = document.querySelectorAll('.steps tr')[i];
    return { heat: r.querySelector('.sh') ? r.querySelector('.sh').value : null, temp: r.querySelector('.st') ? r.querySelector('.st').value : null,
             vent: r.querySelector('.sv') ? r.querySelector('.sv').value : null, timer: !!r.querySelector('.stm') };
  }, n);
  let s1 = await step(1);
  check(s1.heat === 'off' && s1.temp === null, 'a UV-only Cure step opens with "No heating (UV only)" and no temperature: ' + JSON.stringify(s1));
  check(s1.vent === 'on' && !s1.timer, 'its ventilation is kept (on) and the heating-ramp timer options are not offered: ' + JSON.stringify(s1));
  const heated = await step(2);
  check(heated.heat === null && heated.temp === '50', 'a Heating step is unchanged (50 C, no heating switch)');

  const save = async () => {
    await page.evaluate(() => { window.__saved.length = 0; document.querySelector('[id^="pmsg-"]').textContent = ''; });
    await page.click('[id^="psave-"]');
    await page.waitForFunction(() => window.__saved.length > 0 || document.querySelector('[id^="pmsg-"]').textContent.length > 0, { timeout: 4000 });
    return page.evaluate(() => ({ saved: window.__saved.slice(-1)[0], msg: document.querySelector('[id^="pmsg-"]').textContent }));
  };
  let out = await save();
  const st = out.saved && out.saved.payload.steps[0];
  check(!!out.saved && st.temperature === null && st.ventilation === true && !('heat' in st), 'saved as it was: temperature null (UV only), ventilation on, no editor-only field: ' + JSON.stringify(st));
  check(out.saved.payload.steps[1].temperature === 50, 'the other step keeps its 50 C');

  // switching the heating on gives it a temperature, and drops the ventilation
  await page.evaluate(() => { window.__saved.length = 0; });
  await page.$eval('.steps tr:nth-child(2) .sh', s => { s.value = 'on'; s.dispatchEvent(new Event('change')); });
  await sleep(150);
  s1 = await step(1);
  check(s1.heat === 'on' && s1.temp === '40' && s1.vent === null && s1.timer, 'heating on: a temperature field (40) and the timer options appear: ' + JSON.stringify(s1));
  out = await save();
  check(out.saved.payload.steps[0].temperature === 40 && !('ventilation' in out.saved.payload.steps[0]), 'saved with 40 C and without ventilation');

  // a new Cure step is a normal heated step, switching it to UV only works
  await page.evaluate(() => { window.__saved.length = 0; });
  await page.waitForSelector('[data-edit]', { timeout: 5000 });
  await sleep(1800);
  await page.click('[data-edit]');
  await page.waitForSelector('.steps .sp', { timeout: 5000 });
  await page.click('[id^="padd-"]');
  await sleep(150);
  const added = await step(3);
  check(added.heat === 'on' && added.temp === '40', 'a new Cure step starts heated (40 C): ' + JSON.stringify(added));
  await page.evaluate(() => { const s = document.querySelectorAll('.steps tr')[3].querySelector('.sh'); s.value = 'off'; s.dispatchEvent(new Event('change')); });
  await sleep(150);
  out = await save();
  const added2 = out.saved.payload.steps[2];
  check(added2.temperature === null && added2.ventilation === false, 'switched to UV only: saved without a temperature, ventilation off: ' + JSON.stringify(added2));
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
