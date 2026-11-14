// Real-UI screenshots for the expo film (needs vite dev on :5173). usage: node marketing/expo-video/shoot-ui.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'
const OUT = 'marketing/expo-video/shots', BASE = 'http://localhost:5173'
mkdirSync(OUT, { recursive: true })
const sleep = ms => new Promise(r => setTimeout(r, ms))
const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--no-sandbox', '--hide-scrollbars'] })
const page = await browser.newPage()
await page.setViewport({ width: 800, height: 480, deviceScaleFactor: 2 })
await page.goto(BASE, { waitUntil: 'domcontentloaded' })
await page.evaluate(() => localStorage.setItem('scure-org', JSON.stringify({ organizationId: '11111111-2222-3333-4444-555555555555', setupComplete: true })))
const txt = t => page.waitForFunction(x => document.body.innerText.includes(x), { timeout: 40000 }, t)
const clickText = (t, sel = 'button,[role=option],[role=combobox]') => page.evaluate((t, sel) => {
  const e = [...document.querySelectorAll(sel)].find(b => (b.textContent || '').trim().startsWith(t)); e && e.click(); return !!e }, t, sel)
await page.goto(BASE + '/', { waitUntil: 'networkidle2' })
await txt('Program List'); await sleep(800)
await page.screenshot({ path: `${OUT}/ui-home.png` })
// builder with several steps (wider viewport so 3-4 steps are visible)
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1.5 })
await clickText('+ New'); await sleep(700)
const procs = ['Drying', 'N₂ Purge', 'Cure', 'Cooling']
for (const p of procs) {
  await page.evaluate(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === 'Add Step'); b && b.click() })
  await sleep(500)
  await page.evaluate(() => {
    const labels = [...document.querySelectorAll('label')].filter(l => l.textContent.trim() === 'Process')
    const l = labels[labels.length - 1]; const c = l && l.parentElement.querySelector('[role=combobox]'); c && c.click()
  })
  await sleep(350)
  await clickText(p, '[role=option]'); await sleep(450)
}
await page.evaluate(() => document.querySelectorAll('div').forEach(d => { d.scrollLeft = 0 }))
await sleep(400)
await page.screenshot({ path: `${OUT}/ui-builder.png` })
// builder scrolled to the middle and to the end (steps 3-4, 5-6)
for (const [frac, name] of [[0.5, 'ui-builder2'], [1, 'ui-builder3']]) {
  await page.evaluate(f => document.querySelectorAll('div').forEach(d => { if (d.scrollWidth > d.clientWidth + 50) d.scrollLeft = (d.scrollWidth - d.clientWidth) * f }), frac)
  await sleep(500)
  await page.screenshot({ path: `${OUT}/${name}.png` })
}
// boot self-test (all 14 checks)
await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
await page.waitForFunction(() => document.body.innerText.includes('14/14'), { timeout: 60000 }).catch(() => {})
await sleep(150)
await page.screenshot({ path: `${OUT}/ui-boot.png` })
// running cure screen
await page.setViewport({ width: 800, height: 480, deviceScaleFactor: 2 })
await page.goto(BASE + '/cure-process', { waitUntil: 'networkidle2' })
await page.waitForFunction(() => !document.body.innerText.includes('SYSTEM DIAGNOSTICS') && !document.body.innerText.includes('S-CURE') && document.body.innerText.length > 20, { timeout: 60000 }).catch(() => {})
await sleep(5000)
await page.screenshot({ path: `${OUT}/ui-cure.png` })
await browser.close()
