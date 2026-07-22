// Opens the S-Cure app in a real (headful) Chrome window, pre-seeded so it
// skips the setup wizard and shows a populated home + cure history.
// Stays open until you close the window (the script is kept alive on purpose).
import puppeteer from 'puppeteer-core'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://localhost:5173'
const ORG = '11111111-2222-3333-4444-555555555555'

const tele = Array.from({ length: 20 }, (_, i) => ({ t: i * 30, chamberTemp: 25 + i * 1.8, uvOn: i > 8, uvType: i > 8 ? '405nm' : null }))
const HISTORY = [
  { id: 'h1', materialName: 'Carbon Fiber', steps: 5, stepsCompleted: 5, startedAt: '2026-06-06T14:20:00', endedAt: '2026-06-06T15:21:00', duration: 3660, status: 'completed', phases: ['Drying','Heating','Cure','Bleaching','Cooling'], targetTemp: 60, serialNumber: 'cure45223', telemetry: tele },
  { id: 'h2', materialName: 'st45', steps: 3, stepsCompleted: 3, startedAt: '2026-06-06T11:05:00', endedAt: '2026-06-06T11:35:00', duration: 1800, status: 'completed', phases: ['Drying','Heating','Cure'], targetTemp: 45, serialNumber: 'cure45223', telemetry: tele },
  { id: 'h3', materialName: 'Dental Model', steps: 5, stepsCompleted: 2, startedAt: '2026-06-05T16:40:00', endedAt: '2026-06-05T16:49:00', duration: 540, status: 'aborted', phases: ['Drying','Heating','Cure','Bleaching','Cooling'], targetTemp: 50, serialNumber: 'cure45223' },
  { id: 'h4', materialName: 'Fiberglass', steps: 4, stepsCompleted: 4, startedAt: '2026-06-05T09:12:00', endedAt: '2026-06-05T09:45:00', duration: 1980, status: 'completed', phases: ['Drying','Heating','Cure','Cooling'], targetTemp: 55, serialNumber: 'cure45223', telemetry: tele },
]

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  defaultViewport: null,
  args: ['--start-maximized', '--no-default-browser-check', '--no-first-run'],
  ignoreDefaultArgs: ['--enable-automation'],
})

const pages = await browser.pages()
const page = pages[0] || await browser.newPage()

await page.goto(BASE, { waitUntil: 'domcontentloaded' })
await page.evaluate((org, hist) => {
  localStorage.setItem('scure-org', JSON.stringify({ organizationId: org, setupComplete: true }))
  localStorage.setItem('scure-cure-history', JSON.stringify(hist))
}, ORG, HISTORY)
await page.goto(BASE + '/', { waitUntil: 'networkidle2' })

console.log('S-Cure app is open. Leave this running; close the Chrome window when done.')
await new Promise(() => {}) // keep the browser alive
