// Browser test of sign-in with Google and the People screen:  node cloud/google/test_people.cjs
// (user, 2026-10-30: "replace the shared password with Google accounts and keep a list of who may use it, each with a role")
// Loads Page.html in headless Chrome with a stand-in for google.script.run and walks it like a person: the Google button,
// the wait for Google, the header (who, access, People, Sign out), adding / changing / removing someone, the activity
// fold, signing out, a viewer refused an action, and the People screen at phone width.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const STUB = (role) => `
window.__calls = [];
window.google = { script: { run: {} } };
(function () {
  const S = { polls: 0, signedIn: false, role: ${JSON.stringify(role)},
    users: [{ email: 'owner@gmail.com', role: 'admin', name: 'Owner', lastLogin: 0, owner: true },
            { email: 'sam@lab.com', role: 'service', name: 'Sam', lastLogin: Math.floor(Date.now() / 1000) - 120, owner: false }] };
  const log = (fn, args) => window.__calls.push([fn].concat(args));
  const handlers = {
    portalLoginMode: () => ({ google: true }),
    portalLoginStart: () => ({ ok: true, url: 'about:blank#google', state: 'st-1' }),
    portalLoginPoll: (st) => { S.polls++; if (S.polls < 2) return { pending: true }; S.signedIn = true; return { ok: true, token: 'tok-g' }; },
    portalLogout: () => { S.signedIn = false; return { ok: true }; },
    portalMachines: () => S.signedIn ? [{ name: 'CureBox-1', online: true, lastSeen: 1, state: {}, programs: [], prints: [], cures: [], reports: [] }] : null,
    portalMe: () => S.signedIn ? { email: S.role === 'admin' ? 'owner@gmail.com' : 'vera@lab.com', name: S.role === 'admin' ? 'Owner' : 'Vera',
      role: S.role, roleLabel: { view: 'Viewer', service: 'Service', admin: 'Admin' }[S.role], owner: S.role === 'admin', via: 'google',
      canService: S.role !== 'view', canAdmin: S.role === 'admin' } : null,
    portalUsers: () => ({ ok: true, users: S.users, google: true, redirectUri: 'x' }),
    portalAudit: () => ({ ok: true, rows: [{ unix: Math.floor(Date.now() / 1000) - 60, email: 'sam@lab.com', action: 'signed in with Google', detail: 'service' }] }),
    portalUserSave: (t, email, role, name) => { log('save', [email, role, name]);
      const u = S.users.find(x => x.email === email); if (u) u.role = role; else S.users.push({ email, role, name, lastLogin: 0, owner: false }); return { ok: true }; },
    portalUserRemove: (t, email) => { log('remove', [email]); S.users = S.users.filter(x => x.email !== email); return { ok: true }; },
    portalRaceSet: () => S.role === 'view' ? { ok: false, denied: true, message: 'Changing the race needs Service access - you are signed in as Viewer. Ask an admin.' } : { ok: true },
    portalDvt: () => ({ runs: [], fileUrl: '', catalog: { tests: {}, updated: 1 }, requests: [], runners: [], units: [], race: { start: 0, units: [] } }),
    portalDvtWait: () => ({ ver: '1' }),
    portalDvtDetail: () => ({ updated: 1, tests: {} }),
    portalAlerts: () => [],
  };
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); ok(h(...args)); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();`;

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function open(browser, role, viewport) {
  const page = await browser.newPage();
  if (viewport) await page.setViewport(viewport);
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('dialog', d => d.accept());
  await page.evaluateOnNewDocument(STUB(role));
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  return { page, errors };
}
async function signIn(page) {
  await page.waitForSelector('#g-go', { timeout: 10000 });
  await page.evaluate(() => { document.querySelector('#g-go').click(); });
  await page.waitForSelector('#who-out', { timeout: 15000 });
  await page.bringToFront();                 // the Google link opened a tab of its own; mouse clicks need this one in front
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });

  console.log('sign in with Google');
  let { page, errors } = await open(browser, 'admin');
  await page.waitForSelector('#g-go', { timeout: 10000 });
  const link = await page.$eval('#g-go', a => ({ text: a.textContent.trim(), href: a.getAttribute('href'), target: a.target }));
  check(link.text === 'Sign in with Google' && link.href === 'about:blank#google' && link.target === '_blank', 'the sign-in screen is one Google button opening Google in a new window');
  check(!(await page.$('#pw')), 'no password field once Google sign-in is on');
  await page.evaluate(() => { document.querySelector('#g-go').click(); });
  check(await page.$eval('#g-wait', e => !e.hidden), 'after the click it says to finish in the Google window');
  await page.waitForSelector('#who-out', { timeout: 15000 });
  await page.bringToFront();
  const who = await page.$eval('#who', e => e.innerText.replace(/\s+/g, ' ').trim());
  check(/Owner/.test(who) && /Admin/.test(who) && /People/.test(who) && /Sign out/.test(who), 'the header shows who, the access, People and Sign out: ' + who);

  console.log('People');
  await page.click('#who-people');
  await page.waitForSelector('[data-person-remove]', { timeout: 10000 });
  let body = await page.evaluate(() => document.querySelector('#app').innerText);
  check(body.includes('owner@gmail.com') && body.includes('(owner)') && body.includes('Sam') && body.includes('sam@lab.com'), 'the list shows the owner and each person');
  check(body.includes('Viewer - sees everything') && body.includes('Service - also') && body.includes('Admin - also'), 'what each access means is written on the screen');
  check((await page.$$('[data-person-remove]')).length === 1, 'the owner cannot be removed or changed (no controls on that row)');
  await page.type('#pp-email', 'new@lab.com');
  await page.type('#pp-name', 'Nadia');
  await page.select('#pp-role', 'service');
  await page.click('#pp-add');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'save'));
  check(JSON.stringify((await page.evaluate(() => window.__calls)).find(c => c[0] === 'save')) === '["save","new@lab.com","service","Nadia"]', 'Add saves email, role and name');
  await page.waitForFunction(() => document.querySelector('#flash.on') && document.querySelector('#flash').textContent.includes('new@lab.com can now sign in'));
  check(true, 'a message confirms the person can sign in');
  await page.waitForSelector('[data-person-role="new@lab.com"]');
  await page.select('[data-person-role="sam@lab.com"]', 'admin');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'save' && c[1] === 'sam@lab.com'));
  check((await page.evaluate(() => window.__calls)).some(c => c[0] === 'save' && c[1] === 'sam@lab.com' && c[2] === 'admin'), 'changing the access in the list saves it');
  await page.waitForSelector('[data-person-remove="new@lab.com"]');
  await page.click('[data-person-remove="new@lab.com"]');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'remove'));
  await sleep(300);
  check(!(await page.$('[data-person-remove="new@lab.com"]')), 'Remove (after the question) takes the person off the list');
  body = await page.evaluate(() => document.querySelector('#app').innerText);
  check(body.includes('Recent activity'), 'recent activity sits under a fold');
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));

  console.log('sign out');
  await page.click('#who-out');
  await page.waitForSelector('#g-go', { timeout: 10000 });
  check((await page.$eval('#who', e => e.innerText.trim())) === '', 'signing out goes back to the Google button and clears the header');
  await page.close();

  console.log('a viewer');
  ({ page, errors } = await open(browser, 'view'));
  await signIn(page);
  const vwho = await page.$eval('#who', e => e.innerText);
  check(/Vera/.test(vwho) && /Viewer/.test(vwho) && !/People/.test(vwho), 'a viewer sees their access and no People button');
  await page.evaluate(() => api('/api/dvt/race', { method: 'POST', body: JSON.stringify({ start: 'now' }) }).catch(() => {}));
  await page.waitForFunction(() => document.querySelector('#flash.on'), { timeout: 5000 });
  check((await page.$eval('#flash', e => e.textContent)).includes('needs Service access'), 'a refused action says which access it needs');
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await page.close();

  console.log('phone');
  ({ page, errors } = await open(browser, 'admin', { width: 390, height: 844, isMobile: true, hasTouch: true }));
  await signIn(page);
  await page.click('#who-people');
  await page.waitForSelector('[data-person-remove]', { timeout: 10000 });
  const ph = await page.evaluate(() => ({
    sideways: document.documentElement.scrollWidth > window.innerWidth + 1,
    small: [...document.querySelectorAll('#who button, #app button, #app select, #app input')].filter(e => e.offsetParent && e.getBoundingClientRect().height < 44)
      .map(e => (e.id || e.textContent || e.tagName).trim().slice(0, 20)),
    fields: [...document.querySelectorAll('#app input, #app select')].filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id),
  }));
  check(!ph.sideways, 'People at 390 px: no sideways scroll');
  check(ph.small.length === 0, 'every control is at least 44 px tall: ' + ph.small.join(', '));
  check(ph.fields.length === 0, 'fields use 16 px text (the phone does not zoom): ' + ph.fields.join(', '));
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
