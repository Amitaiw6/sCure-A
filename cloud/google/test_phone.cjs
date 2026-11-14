// QA of the portal as a PHONE user:  node cloud/google/test_phone.cjs [--shot]
// Emulates a phone (390 x 844, touch) and walks the way a person would: open every section, run a test from the phone (the Run
// button, the guide sheet, the question the machine asks, the answer) and checks that it is comfortable - nothing scrolls sideways,
// every control is a thumb-sized target, text is readable, the buttons of the guide stay on screen and the one CureBox is chosen for you.
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const now = Math.floor(Date.now() / 1000);
const CATALOG = {
  version: '0.25', updated: 5,
  phases: [{ id: 1, name: 'Protective functions', gate: 'All SAF tests PASS', tests: ['T-1', 'T-2', 'DVT-ELE-002'] }],
  tests: {
    'T-1': { title: 'Door interlock - UV inhibited with the door open', safety: true, auto: true, minutes: 90, units: ['U1'], runs: ['|1'], hasDetail: true },
    'T-2': { title: 'Software stack failure - heater and UV response per layer', safety: false, auto: true, minutes: 45, units: ['U1'], runs: ['L1|1', 'L2|1', 'L3|1'], hasDetail: true },
    'DVT-ELE-002': { title: 'Insulation resistance', group: 'ELE', safety: false, auto: false, minutes: 30, units: ['U1'], runs: ['|1'], hasDetail: true },
  },
};
const DETAIL = { updated: 5, tests: Object.fromEntries(['T-1', 'T-2', 'DVT-ELE-002'].map(t => [t, {
  purpose: 'Verify that the machine does what it should, in a sentence long enough to wrap on a phone screen at least twice.',
  equipment: ['A StarBright sensor', 'A door magnet'], preconditions: ['The unit is idle', 'The door can be opened by hand'], dependencies: [],
  steps: ['Close the door.', 'Start the test from the machine screen.', 'Open the door when asked.', 'Read the value shown.'],
  prompts: [{ kind: 'do', text: 'Close the door, then press Done.' }, { kind: 'value', text: 'Input voltage', field: 'applied_voltage', unit: 'V', type: 'float' }, { kind: 'yesno', text: 'Did any fuse open?', field: 'fuse_opened' }],
  criteria: 'uv_off_time <= 1 AND alarm_raised == true', bench: false, kind: 'guided', note: 'The runner drives the machine and asks only for what no API can do.' }])) };
const RUN = (tid, verdict) => ({ unit: 'U1', testId: tid, variant: '', rep: 1, runId: `${tid}|U1||1`, verdict, operator: 'x', startedAt: '2026-10-20T10:00:00Z', recordedAt: 1, note: '', machine: 'CureBox-1', values: { peak: 80 }, files: [] });
const STUB = `
window.__calls = [];
window.scureReportHref = (m, id, dl) => '#report-' + id + (dl ? '-dl' : '');
window.__reqs = [];
window.google = { script: { run: {} } };
(function () {
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => [{ name: 'CureBox-1', online: true, lastSeen: ${now}, state: { chamberTemp: 24.9 }, runs: [], errors: [], programs: [{ id: 'p1', name: 'WeatherX', totalDuration: 20, steps: [{ process: 'Drying', temperature: 45, time: 10 }, { process: 'Cure', temperature: 40, time: 10, uvIntensity: 30 }] }], prints: [{ printName: 'Job 1', materialName: 'WeatherX', printerName: 'TZ', status: 'done' }], cures: [{ id: 'c1', materialName: 'WeatherX', startedAt: '2026-10-22T10:00:00', duration: 600, status: 'completed' }], reports: ['c1'], netbird: { connected: true, ip: '100.1.1.1' } }],
    portalAlerts: () => [{ machine: 'CureBox-1', code: 9011, raised: ${now} - 60, cleared: null, message: 'Temperature sensor disconnected: Left LED panel', title: 'Left LED Temperature Sensor Disconnected', videoUrl: '' }],
    portalDvt: () => ({ runs: [${JSON.stringify(RUN('DVT-ELE-002', 'PASS'))}], fileUrl: '', catalog: ${JSON.stringify(CATALOG)}, requests: window.__reqs, units: [], build: (typeof PORTAL_BUILD !== 'undefined' ? PORTAL_BUILD : ''),
      runners: [{ machine: 'CureBox-1', lastSeen: ${now}, online: true, version: '0.9.100', unit: 'U1', readiness: null }] }),
    portalDvtDetail: () => (${JSON.stringify(DETAIL)}),
    portalDvtRequest: (tok, machine, unit, ids) => { window.__calls.push(['request', machine, unit, ids.join(',')]);
      window.__reqs.push({ id: 1, machine, unit, testId: ids[0], status: 'waiting', requested: ${now}, started: 0, finished: 0, line: 'waiting for you at the machine',
        prompt: { kind: 'yesno', text: 'Is the door fully open?' }, verdict: '', runIds: [] });
      return { ok: true, queued: ids.length, skipped: 0 }; },
    portalDvtAnswer: (tok, id, value) => { window.__calls.push(['answer', id, value]); window.__reqs[0].prompt = null; window.__reqs[0].status = 'running'; return { ok: true }; },
    portalDvtApprove: (tok, unit, testId, runIds, who, approve) => { window.__calls.push(['approve', testId, runIds.join(','), approve]); return { ok: true }; },
    portalDvtCancel: (tok, id) => { window.__calls.push(['cancel', id]); return { ok: true }; },
    portalDvtActed: (tok, id) => { window.__calls.push(['acted', id]); if (window.__reqs[0].act) window.__reqs[0].act.acked = true; return { ok: true }; },
    portalDvtWait: () => ({ ver: 1 }),
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
  page.on('dialog', d => d.accept());
  await page.evaluateOnNewDocument(STUB);
  await page.goto('file:///' + path.join(__dirname, 'Page.html').replace(/\\/g, '/'));
  await page.waitForSelector('#pw, .subtab', { timeout: 10000 }).catch(e => { console.error('page errors:', errors.join(' | ')); throw e; });
  if (await page.$('#pw')) { await page.type('#pw', 'pw'); await page.tap('#go'); }
  await page.waitForSelector('.subtab', { timeout: 10000 });
  await sleep(300);

  // what a thumb needs: no sideways scroll, targets of at least 44 px (40 for a row), 16 px in a field, 14 px for text
  const audit = name => page.evaluate(() => {
    const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
    const small = [...document.querySelectorAll('#app button, #app select, #app input:not([type=hidden]), .subtab, .dvt-test, .dvt-ph-head, #app a')]
      .filter(vis).map(e => ({ t: (e.tagName + ' ' + (e.textContent || e.id || e.placeholder || '').trim().slice(0, 24)), h: Math.round(e.getBoundingClientRect().height) }))
      .filter(x => x.h < 40);
    const smallFont = [...document.querySelectorAll('#app input:not([type=hidden]), #app select')].filter(vis).filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.id || e.tagName);
    const wide = [...document.querySelectorAll('#app *')].filter(e => { const r = e.getBoundingClientRect(); return r.right > 392 && r.width > 0 && !e.closest('[style*="overflow-x"], .sections'); }).slice(0, 4).map(e => e.tagName + '.' + String(e.className).slice(0, 24) + '#' + e.id + ' ' + Math.round(e.getBoundingClientRect().right));
    return { scroll: [document.documentElement.scrollWidth, window.innerWidth], wide, small, smallFont, body: parseFloat(getComputedStyle(document.body).fontSize) };
  });
  const comfy = async name => {
    const a = await audit(name);
    check(a.scroll[0] <= 391, `${name}: nothing scrolls sideways (the page is ${a.scroll[0]} px wide on a 390 px phone)` + (a.wide.length ? ' - too wide: ' + a.wide.join('; ') : ''));
    check(a.small.length === 0, `${name}: every control is at least 40 px tall` + (a.small.length ? ' - too small: ' + JSON.stringify(a.small.slice(0, 5)) : ''));
    check(a.smallFont.length === 0, `${name}: fields use 16 px text, so the phone does not zoom in` + (a.smallFont.length ? ': ' + a.smallFont.join(',') : ''));
    check(a.body >= 14, `${name}: body text is ${a.body} px`);
  };

  await comfy('Overview');
  const unitCard = await page.evaluate(() => { const c = document.querySelector('.ov-units tr:nth-child(2)'); if (!c) return null; const r = c.getBoundingClientRect(); return [...c.querySelectorAll('input')].filter(i => i.getBoundingClientRect().width > 0).map(i => Math.round(i.getBoundingClientRect().right - r.right)); });
  if (unitCard) check(unitCard.every(d => d <= 0), 'Overview: the fields of a unit card stay inside the card: ' + unitCard.join(','));
  await page.tap('[data-view="machines"]'); await sleep(300);
  await comfy('Machine');
  const mach = await page.evaluate(() => {
    const box = e => { const r = e.getBoundingClientRect(); return { top: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
    const prog = document.querySelector('[data-edit]');
    const rows = [...document.querySelectorAll('table.cards')].map(t => getComputedStyle(t.rows[1]).display + '/' + getComputedStyle(t.rows[0]).display);
    return { edit: box(prog), del: box(document.querySelector('[data-del]')), rows, links: [...document.querySelectorAll('.cards td.act a')].map(box),
             send: [...document.querySelectorAll('.sendrow > *')].map(e => Math.round(e.getBoundingClientRect().width)) };
  });
  check(mach.rows.length === 4 && mach.rows.every(r => r === 'block/none'), 'Machine: programs, the built-in catalog, prints and cure runs are lists of cards: ' + mach.rows.join(' '));
  check(mach.edit.top === mach.del.top && mach.edit.h >= 44 && mach.del.h >= 44 && mach.edit.w >= 120, 'Machine: Edit and Delete sit side by side as big buttons: ' + JSON.stringify([mach.edit, mach.del]));
  check(mach.links.length === 2 && mach.links.every(l => l.h >= 44), 'Machine: the report View / Download are big buttons');
  check(mach.send.every(w => w >= 300), 'Machine: the print form fields are full width: ' + mach.send.join(','));
  await page.tap('[data-edit]');
  await page.waitForSelector('.steps tr:nth-child(2) .sp', { timeout: 3000 });
  await sleep(300);
  const ed = await page.evaluate(() => {
    const steps = document.querySelectorAll('.steps tr');
    const r1 = steps[1].getBoundingClientRect();
    const fields = [...steps[2].querySelectorAll('input, select, button')].map(e => Math.round(e.getBoundingClientRect().height));
    const wideEls = [...document.querySelectorAll('#app *')].filter(e => e.getBoundingClientRect().right > 392 && !e.closest('.sections')).slice(0, 4).map(e => e.tagName + '.' + String(e.className).slice(0, 14) + '#' + e.id + ' ' + Math.round(e.getBoundingClientRect().right));
    return { wideEls, rows: steps.length - 1, display: getComputedStyle(steps[1]).display, header: getComputedStyle(steps[0]).display, w: Math.round(r1.width), fields, page: document.documentElement.scrollWidth };
  });
  check(ed.rows === 2 && ed.display === 'block' && ed.header === 'none' && ed.w < 391, 'Program editor: every step is a card: ' + JSON.stringify(ed));
  check(ed.fields.every(h => h >= 40) && ed.page <= 391, 'Program editor: every field of a step is at least 40 px, the page does not widen ' + JSON.stringify(ed.fields) + ed.page + ' ' + ed.wideEls.join('; '));
  if (process.argv.includes('--shot')) await page.screenshot({ path: path.join(__dirname, 'phone-machine.png'), fullPage: true });
  await page.evaluate(() => document.querySelector('[id^="pcancel-"]').scrollIntoView({ block: 'center' }));   // a person scrolls it clear of the bottom bar
  await page.tap('[id^="pcancel-"]');
  await sleep(200);
  await page.tap('[data-view="errors"]'); await sleep(400);
  await comfy('Errors');
  await page.waitForSelector('table.cards', { timeout: 5000 });
  const err = await page.evaluate(() => { const t = document.querySelector('table.cards'); return { row: getComputedStyle(t.rows[1]).display, head: getComputedStyle(t.rows[0]).display, text: t.rows[1].innerText.replace(/\s+/g, ' ').slice(0, 90), ph: document.querySelector('#search').placeholder }; });
  check(err.row === 'block' && err.head === 'none' && /Left LED Temperature Sensor/.test(err.text), 'Errors: each error is a card with its title: ' + err.text);
  check(/errors/i.test(err.ph), 'Errors: the search box says what it searches: ' + err.ph);
  await page.tap('[data-view="compare"]'); await sleep(400);
  await comfy('Compare');

  // ---- run a test from the phone ----
  await page.tap('[data-view="dvt"]');
  await page.waitForSelector('[data-dvt-test]', { timeout: 8000 });
  await sleep(300);
  check(!!(await page.$('[data-tab="CureBox-1"].primary')), 'the only CureBox is already chosen: nobody has to pick it before running a test');
  await comfy('DVT');
  const runBtns = await page.$$eval('[data-dvt-run-test]', bs => bs.map(b => { const r = b.getBoundingClientRect(); return { t: b.dataset.dvtRunTest, w: Math.round(r.width), h: Math.round(r.height), inView: r.left >= 0 && r.right <= window.innerWidth }; }));
  check(runBtns.length === 2, 'both automatic tests have a Run button: ' + runBtns.map(b => b.t).join(','));
  check(runBtns.every(b => b.h >= 44 && b.w >= 300 && b.inView), 'the Run buttons are wide thumb targets inside the screen: ' + JSON.stringify(runBtns[0]));
  const appr = await page.$$eval('[data-dvt-approve]', bs => bs.map(b => { const r = b.getBoundingClientRect(); return { t: b.dataset.dvtApprove, v: b.dataset.v, h: Math.round(r.height), w: Math.round(r.width) }; }));
  check(appr.length === 1 && appr[0].t === 'DVT-ELE-002' && appr[0].v === '0' && appr[0].h >= 44, 'the hand-made test has a big Withdraw button when it is approved, and no Run button: ' + JSON.stringify(appr));
  await page.tap('[data-dvt-approve="DVT-ELE-002"]');
  await sleep(300);
  check((await page.evaluate(() => window.__calls)).some(c => c[0] === 'approve' && c[1] === 'DVT-ELE-002' && c[2] === 'DVT-ELE-002|U1||1' && c[3] === false), 'Withdraw asks the site to take the approval back');
  const caption = await page.evaluate(() => document.body.innerText);
  check(caption.includes('0/3 cases'), 'the test with three layers reads "0/3 cases"');

  await page.tap('[data-dvt-run-test="T-1"]');
  await page.waitForSelector('.dvt-modal', { timeout: 5000 });
  await sleep(200);
  const sheet = await page.evaluate(() => {
    const m = document.querySelector('.dvt-modal').getBoundingClientRect(), f = document.querySelector('.dvt-modal-foot');
    const bs = [...f.querySelectorAll('button')].map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.trim().slice(0, 20), h: Math.round(r.height), w: Math.round(r.width), bottom: Math.round(r.bottom) }; });
    const body = document.querySelector('.dvt-modal-body');
    return { m: [Math.round(m.width), Math.round(m.height)], vh: window.innerHeight, vw: window.innerWidth, bs, scrolls: body.scrollHeight > body.clientHeight, footBottom: Math.round(f.getBoundingClientRect().bottom) };
  });
  check(sheet.m[0] === sheet.vw && sheet.m[1] <= sheet.vh, `the guide fills the phone screen (${sheet.m.join(' x ')} in ${sheet.vw} x ${sheet.vh})`);
  check(sheet.footBottom <= sheet.vh && sheet.bs.every(b => b.bottom <= sheet.vh), 'the Queue / Cancel buttons are on screen without scrolling');
  check(sheet.bs.every(b => b.h >= 44 && b.w >= 300), 'the Queue / Cancel buttons are full width and at least 44 px: ' + JSON.stringify(sheet.bs));
  check(sheet.scrolls, 'a long guide scrolls inside the sheet while its buttons stay put');

  // the simulation asks the same questions as a real run, one at a time
  const simAsked = [];
  await page.tap('[data-sim="pass"]');
  for (const [kind, type] of [['do'], ['value', '220'], ['yesno']]) {
    await page.waitForSelector('[data-sim-out] .dvt-auto', { timeout: 15000 });
    simAsked.push(await page.$eval('[data-sim-out] .dvt-auto .note', n => n.textContent));
    if (kind === 'value') await page.type('#sim-ans', type);
    await page.tap(kind === 'do' ? '[data-sim-out] [data-a="done"]' : kind === 'value' ? '[data-sim-out] [data-a="ok"]' : '[data-sim-out] [data-a="no"]');
    await sleep(900);
  }
  await page.waitForSelector('.dvt-sim-verdict', { timeout: 15000 });
  check(simAsked.length === 3 && /door/.test(simAsked[0]) && /Input voltage/.test(simAsked[1]) && /fuse/.test(simAsked[2]), 'the simulation asks the questions of the real run in order: ' + JSON.stringify(simAsked));
  await page.tap('[data-guide="go"]');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'request'), { timeout: 5000 });
  check(JSON.stringify(await page.evaluate(() => window.__calls.find(c => c[0] === 'request'))) === JSON.stringify(['request', 'CureBox-1', 'U1', 'T-1']), 'Queue sends the test for the chosen CureBox and unit');

  const queue = await page.evaluate(() => {
    const tr = document.querySelector('.rq-table tr:nth-child(2)');
    return { row: getComputedStyle(tr).display, header: getComputedStyle(document.querySelector('.rq-table tr:first-child')).display,
             picker: getComputedStyle(document.querySelector('.dvt-picker')).display };
  });
  check(queue.row === 'block' && queue.header === 'none', 'the queue is a list of cards, not a cramped four-column table');
  check(queue.picker === 'none', 'the second CureBox dropdown is hidden (the chips already choose it)');

  // the machine asks a question: big answer buttons, reachable with the thumb
  await page.waitForSelector('.dvt-modal-run [data-dvt-answer]', { timeout: 8000 });
  const ans = await page.$$eval('.dvt-modal-run [data-dvt-answer]', bs => bs.map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.trim(), h: Math.round(r.height), inView: r.bottom <= window.innerHeight && r.top >= 0 }; }));
  check(ans.length === 3 && ans.every(a => a.h >= 44 && a.inView), 'the machine\'s question has Yes / No / Skip buttons of at least 44 px, on screen: ' + JSON.stringify(ans));
  await page.tap('.dvt-modal-run [data-dvt-answer][data-v="true"]');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'answer'), { timeout: 5000 });
  check(JSON.stringify(await page.evaluate(() => window.__calls.find(c => c[0] === 'answer'))) === JSON.stringify(['answer', 1, true]), 'tapping Yes answers the machine');

  // the step the person has to do NOW: before 0.9.145 it arrived as a grey line while the box said
  // "nothing to do", and DVT-SAF-008 timed out with nobody told to open the door (user, 2026-10-29)
  await page.evaluate(() => {
    window.__reqs[0].status = 'running';
    window.__reqs[0].line = 'OPEN THE DOOR and keep it open';
    window.__reqs[0].act = { text: 'OPEN THE DOOR and keep it open', sec: 24, ack: true, acked: false, stage: { n: 4, of: 6, text: 'a magnet must not fool the door sensor' } };
    dvtGuideRefresh();
  });
  await page.waitForSelector('.dvt-modal-run .dvt-act .txt', { timeout: 8000 });
  const step = await page.evaluate(() => {
    const t = document.querySelector('.dvt-modal-run .dvt-act .txt');
    const sec = document.querySelector('.dvt-modal-run .dvt-act .sec');
    const stage = document.querySelector('.dvt-modal-run .dvt-act .stage');
    const box = document.querySelector('.dvt-modal-run .dvt-now');
    const r = t.getBoundingClientRect();
    return { text: t.textContent.trim(), size: Math.round(parseFloat(getComputedStyle(t).fontSize)),
             sec: sec && sec.textContent.trim(), stage: stage && stage.textContent.trim(),
             amber: box.classList.contains('act'), width: Math.round(r.width), vw: window.innerWidth,
             body: document.body.innerText.includes('nothing to do') };
  });
  check(/OPEN THE DOOR/.test(step.text) && step.size >= 20, `the step is the headline of "What to do now", not a log line (${step.size} px: ${step.text})`);
  check(step.sec === '24 s' && /step 4 of 6/.test(step.stage || ''), `the step says how long is left and which stage it is (${step.sec} · ${step.stage})`);
  check(step.amber && !step.body, 'the card turns amber and never says "nothing to do" while it waits for the person');
  check(step.width <= step.vw, `the instruction fits the phone screen (${step.width} <= ${step.vw})`);

  // the person confirms the step: a thumb-sized button, and the test does not go on without it
  const did = await page.$eval('.dvt-modal-run [data-dvt-acted]', (b) => {
    const r = b.getBoundingClientRect();
    return { text: b.textContent.trim(), h: Math.round(r.height), inView: r.bottom <= window.innerHeight && r.top >= 0 };
  });
  check(/I did it/i.test(did.text) && did.h >= 44, `the step has an "I did it" button of at least 44 px (${did.h} px: ${did.text})`);
  await page.tap('.dvt-modal-run [data-dvt-acted]');
  await page.waitForFunction(() => window.__calls.some(c => c[0] === 'acted'), { timeout: 5000 });
  check(JSON.stringify(await page.evaluate(() => window.__calls.find(c => c[0] === 'acted'))) === JSON.stringify(['acted', 1]),
        'pressing it tells the machine the action was done');
  await page.evaluate(() => dvtGuideRefresh());
  const after = await page.evaluate(() => ({ btn: !!document.querySelector('.dvt-modal-run [data-dvt-acted]'),
                                             text: document.querySelector('.dvt-modal-run .dvt-now').innerText }));
  check(!after.btn && /waiting for the machine/i.test(after.text), 'after the press it waits for the machine to agree, and cannot be pressed twice');

  // a step the machine watches by itself (the UV-off timing) asks for no press at all
  await page.evaluate(() => { window.__reqs[0].act = { text: 'OPEN THE DOOR NOW', sec: null, ack: false, stage: null }; dvtGuideRefresh(); });
  const watched = await page.evaluate(() => ({ btn: !!document.querySelector('.dvt-modal-run [data-dvt-acted]'),
                                               text: document.querySelector('.dvt-modal-run .dvt-now').innerText }));
  check(!watched.btn && /OPEN THE DOOR NOW/.test(watched.text) && /machine is watching/i.test(watched.text),
        'a step the machine times itself is shown without a button');

  if (process.argv.includes('--shot')) await page.screenshot({ path: path.join(__dirname, 'phone-guide.png') });
  check(errors.length === 0, 'no script errors: ' + errors.join(' | '));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
