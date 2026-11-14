// Settings screen (NFC + BOFA toggles) for the expo film + their on-screen boxes. Needs vite on :5173.
import puppeteer from 'puppeteer-core'
import { writeFileSync } from 'fs'
const OUT = 'marketing/expo-video/shots', BASE = 'http://localhost:5173'
const sleep = ms => new Promise(r => setTimeout(r, ms))
const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--no-sandbox', '--hide-scrollbars'] })
const page = await browser.newPage()
await page.setViewport({ width: 800, height: 480, deviceScaleFactor: 2 })
await page.goto(BASE, { waitUntil: 'domcontentloaded' })
await page.evaluate(() => localStorage.setItem('scure-org', JSON.stringify({ organizationId: '11111111-2222-3333-4444-555555555555', setupComplete: true })))
await page.goto(BASE + '/settings', { waitUntil: 'networkidle2' })
await page.waitForFunction(() => document.body.innerText.includes('BOFA'), { timeout: 60000 })
// scroll the BOFA row into view
await page.evaluate(() => { const e = [...document.querySelectorAll('*')].find(x => x.childElementCount === 0 && x.textContent.trim() === 'BOFA Control'); e && e.scrollIntoView({ block: 'center' }) })
await sleep(800)
const boxes = await page.evaluate(() => {
  const row = t => { const e = [...document.querySelectorAll('*')].find(x => x.childElementCount === 0 && x.textContent.trim() === t); if (!e) return null
    let r = e; for (let i = 0; i < 4 && r.parentElement; i++) { r = r.parentElement; if (r.getBoundingClientRect().width > 300) break }
    const b = r.getBoundingClientRect(); return { x: b.x / 800, y: b.y / 480, w: b.width / 800, h: b.height / 480 } }
  return { nfc: row('NFC'), bofa: row('BOFA Control') }
})
await page.screenshot({ path: `${OUT}/ui-settings.png` })
writeFileSync(`${OUT}/ui-settings.json`, JSON.stringify(boxes))
console.log(JSON.stringify(boxes))
await browser.close()
