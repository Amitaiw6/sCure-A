import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://localhost:5173'
const OUT = 'docs/screenshots'
mkdirSync(OUT, { recursive: true })

const ORG = '11111111-2222-3333-4444-555555555555'

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--hide-scrollbars'],
})

async function newPage() {
  const page = await browser.newPage()
  await page.setViewport({ width: 800, height: 480, deviceScaleFactor: 2 })
  return page
}

// seed localStorage so the setup wizard is skipped and an org is linked
async function seed(page, withOrg = true) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.evaluate((org) => {
    localStorage.setItem('scure-org', JSON.stringify({ organizationId: org, setupComplete: true }))
  }, withOrg ? ORG : '')
}

// wait until the boot screen is gone. Two-step: the logo phase shows "S-CURE"
// (no "System Diagnostics" yet), so we first wait for boot to APPEAR, then vanish.
async function waitBootDone(page) {
  const isBoot = () => {
    const t = document.body.innerText || ''
    return t.includes('S-CURE') || t.includes('System Diagnostics') || t.includes('Starting sCure')
  }
  await page.waitForFunction(isBoot, { timeout: 6000 }).catch(() => {})
  await page.waitForFunction(
    () => {
      const t = document.body.innerText || ''
      return t.length > 0 && !t.includes('S-CURE') &&
             !t.includes('System Diagnostics') && !t.includes('Starting sCure')
    },
    { timeout: 25000 }
  ).catch(() => {})
}

async function shot(route, name, { waitText, extraWait = 600, withOrg = true } = {}) {
  const page = await newPage()
  await seed(page, withOrg)
  await page.goto(BASE + route, { waitUntil: 'networkidle2' })
  await waitBootDone(page)
  if (waitText) {
    await page.waitForFunction(
      (t) => document.body.innerText.includes(t), { timeout: 15000 }, waitText
    ).catch(() => {})
  }
  await sleep(extraWait)
  await page.screenshot({ path: `${OUT}/${name}.png` })
  console.log('✓', name)
  await page.close()
}

// 1. Boot screen — capture mid-diagnostics
{
  const page = await newPage()
  await seed(page, true)
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
  await sleep(2600) // logo (1.5s) then a few checks ticking
  await page.screenshot({ path: `${OUT}/boot.png` })
  console.log('✓ boot')
  await page.close()
}

// 2. Setup wizard welcome — no org, setup not complete
{
  const page = await newPage()
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.evaluate(() => localStorage.clear())
  await page.goto(BASE + '/', { waitUntil: 'networkidle2' })
  await waitBootDone(page)
  await sleep(1200)
  await page.screenshot({ path: `${OUT}/setup.png` })
  console.log('✓ setup')
  await page.close()
}

// 3-7. Main pages
await shot('/', 'home', { waitText: 'Material List' })
await shot('/settings', 'settings', { waitText: 'REBOOT', extraWait: 800 })
await shot('/alerts', 'alerts', { extraWait: 900 })
await shot('/cure-history', 'cure-history', { extraWait: 900 })
await shot('/network', 'network', { extraWait: 900 })
await shot('/material-editor', 'material-editor', { extraWait: 800 })

// 8. Cure process — auto-starts with default fallback phases; capture mid-ramp
await shot('/cure-process', 'cure', { extraWait: 3500 })

// 9. Build Cure Program modal — open from Home via the "+ New" button
{
  const page = await newPage()
  await seed(page, true)
  await page.goto(BASE + '/', { waitUntil: 'networkidle2' })
  await waitBootDone(page)
  await page.waitForFunction(() => document.body.innerText.includes('Material List'), { timeout: 15000 }).catch(() => {})
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim().startsWith('+ New'))
    btn && btn.click()
  })
  await sleep(900)
  await page.screenshot({ path: `${OUT}/cure-builder.png` })
  console.log('✓ cure-builder')
  await page.close()
}

await browser.close()
console.log('done')