// Browser test of the portal's "Errors today" tab:  node cloud/google/test_errors_page.cjs
// Loads Page.html in headless Chrome with a stand-in for google.script.run and checks that every per-component code shows
// its own registry title, that a code with a repair video (errors.json videoUrl) gets a "Video" link and others do not,
// and that a row from an older server (no title) falls back to the built-in title.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const now = Math.floor(Date.now() / 1000);
const ALERTS = [
  { machine: 'CureBox-1', code: 9011, raised: now - 60, cleared: null, message: 'Temperature sensor disconnected: Left LED panel (TEMP_LEFT_ORIGIN)',
    title: 'Left LED Temperature Sensor Disconnected', videoUrl: 'https://youtu.be/left-ntc' },
  { machine: 'CureBox-1', code: 9022, raised: now - 30, cleared: now - 10, message: 'Left LED fan (FAN_LEFT): 0 RPM measured',
    title: 'Left LED Fan Below Minimum Speed - System Stopped', videoUrl: '' },
  { machine: 'CureBox-1', code: 9002, raised: now - 20, cleared: null, message: 'older server: <no title>' },
  { machine: 'CureBox-1', code: 9040, raised: now - 15, cleared: null, message: 'x', title: 'Left LED Panel Not Heating', videoUrl: 'javascript:alert(1)' },
];
const STUB = `
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, runs: [], errors: [] }],
    portalAlerts: () => ${JSON.stringify(ALERTS)},
    portalDvt: () => ({ runs: [], fileUrl: '', catalog: { tests: {}, updated: 1 }, requests: [], runners: [] }),
  };
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); ok(h(...args)); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();`;

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };

(async () => {
  // Apps Script's HTML service cuts the rest of a line at "//" - also inside a regex like /^https?:\/\//i ("\/" followed by the
  // closing "/") - which killed the whole script and the sign-in form (2026-10-22). Write \/{2} instead.
  const html = require('fs').readFileSync(path.join(__dirname, 'Page.html'), 'utf8').replace(/data:[^"')]+/g, '');
  const bad = html.split('\n').map((l, i) => [i + 1, l]).filter(([, l]) => l.includes('\\//'));
  check(bad.length === 0, 'no "//" hidden in a regex in Page.html (lines ' + bad.map(b => b[0]).join(', ') + ')');
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.evaluateOnNewDocument(STUB);
  await page.evaluateOnNewDocument("localStorage.setItem('scure-curebox', 'CureBox-1');");
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, [data-view=errors]', { timeout: 10000 });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.keyboard.press('Enter'); }
  await page.waitForSelector('[data-view=errors]', { timeout: 10000 });
  await page.click('[data-view=errors]');
  await page.waitForSelector('a.vid', { timeout: 10000 });
  const body = await page.evaluate(() => document.body.innerText);
  check(body.includes('Left LED Temperature Sensor Disconnected') && body.includes('Left LED Fan Below Minimum Speed'), 'each code shows its own registry title');
  check(body.includes('Fan failure - system stopped'), 'a row without a title falls back to the built-in title');
  check(body.includes('older server: <no title>'), 'the machine message is shown escaped');
  const links = await page.$$eval('a.vid', as => as.map(a => ({ href: a.getAttribute('href'), target: a.target, rel: a.rel })));
  check(links.length === 1 && links[0].href === 'https://youtu.be/left-ntc' && links[0].target === '_blank' && links[0].rel.includes('noopener'),
    'only the code with an https video gets a Video link, in a new tab (a javascript: URL gets none)');
  if (process.argv.includes('--shot')) await page.screenshot({ path: path.join(__dirname, 'errors-video.png'), fullPage: true });
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
