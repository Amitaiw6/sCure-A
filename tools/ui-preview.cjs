// Screenshots of the built UI (served by server/app.py in simulation mode).
// Usage: node tools/ui-preview.cjs [outDir]  — writes home.png / home-selected.png /
// slider-mid.png / cure-process.png. Needs a running server on :3001 and Chrome.
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = process.env.URL || 'http://localhost:3001/';
const out = process.argv[2] || path.join(__dirname, '..', 'docs', 'releases', 'preview');
fs.mkdirSync(out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });     // the device's DSI panel
  page.on('pageerror', (e) => console.log('PAGE ERROR:', e.message));
  // Skip the first-run Setup wizard (SystemConfigContext reads this key)
  await page.evaluateOnNewDocument(() => {
    localStorage.setItem('scure-org', JSON.stringify({ organizationId: 'preview', setupComplete: true }));
  });
  await page.goto(URL, { waitUntil: 'networkidle2' });
  await page.waitForFunction(() => document.body.innerText.includes('Program List'), { timeout: 90000 });   // boot diagnostics finish
  await sleep(800);
  await page.screenshot({ path: path.join(out, 'home.png') });
  console.log('home.png');

  // Select the first material in the list (MaterialItem root = clickable row with a label)
  const clicked = await page.evaluate(() => {
    const rows = [...document.querySelectorAll('div')].filter((d) =>
      d.className && typeof d.className === 'string' && d.className.includes('cursor-pointer') && d.querySelector('.truncate, span, p'));
    const row = rows.find((r) => r.getBoundingClientRect().width > 200 && r.getBoundingClientRect().height > 30);
    if (row) { row.click(); return row.innerText.slice(0, 60); }
    return null;
  });
  console.log('clicked material:', clicked);
  await sleep(600);
  await page.screenshot({ path: path.join(out, 'home-selected.png') });
  console.log('home-selected.png');

  // Drag the slide-to-start knob: mid-way screenshot, then to the end
  const slider = await page.$('[role="slider"]');
  if (!slider) { console.log('no slider found'); await browser.close(); return; }
  const box = await slider.boundingBox();
  console.log('slider box', box);
  const y = box.y + box.height / 2;
  const x0 = box.x + box.height / 2;           // knob centre at rest
  await page.mouse.move(x0, y);
  await page.mouse.down();
  await page.mouse.move(x0 + box.width * 0.4, y, { steps: 10 });
  await sleep(150);
  await page.screenshot({ path: path.join(out, 'slider-mid.png') });
  console.log('slider-mid.png');
  await page.mouse.move(box.x + box.width - 5, y, { steps: 10 });
  await page.mouse.up();
  await sleep(4000);
  console.log('url now:', page.url());
  await page.screenshot({ path: path.join(out, 'cure-process.png') });
  console.log('cure-process.png');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
