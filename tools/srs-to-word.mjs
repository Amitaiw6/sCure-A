// Converts docs/SRS_v2.html into a self-contained Word document (docs/SRS_v2.doc).
// Strategy (no pandoc/LibreOffice needed):
//   1. Open the SRS in headless Chrome so Mermaid renders each diagram to an <svg>.
//   2. Rasterize every diagram to a PNG and inline it as a data: URI.
//   3. Inline every screenshot PNG as a data: URI.
//   4. Add the MS-Office HTML namespaces so Word opens it as a document.
// Word reads HTML-based .doc files natively; the user can then "Save As .docx".
import puppeteer from 'puppeteer-core'
import { readFileSync, writeFileSync, existsSync } from 'fs'
import { resolve } from 'path'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
// Usage: node tools/srs-to-word.mjs [input.html] [output.doc]
const SRC = resolve(process.argv[2] || 'docs/SRS_v2.html')
const OUT = process.argv[3] || 'docs/SRS_v2.doc'

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--allow-file-access-from-files', '--hide-scrollbars'],
})
const page = await browser.newPage()
await page.setViewport({ width: 1100, height: 1400, deviceScaleFactor: 2 })
await page.goto('file://' + SRC, { waitUntil: 'networkidle2' })

// Wait for Mermaid (loaded from CDN) to turn every .mermaid block into an <svg>.
let rendered = true
try {
  await page.waitForFunction(() => {
    const all = [...document.querySelectorAll('.mermaid')]
    return all.length > 0 && all.every(el => el.querySelector('svg'))
  }, { timeout: 60000 })
} catch {
  rendered = false
  console.warn('! Mermaid did not finish rendering (no internet?). Diagram source text will be kept.')
}
await sleep(1200)

// Rasterize each rendered diagram and swap it for an inline PNG.
const nodes = await page.$$('.mermaid')
let diagramCount = 0
for (const el of nodes) {
  const hasSvg = await el.$('svg')
  if (!hasSvg) continue
  try {
    await el.evaluate(n => { n.style.background = '#ffffff'; n.scrollIntoView() })
    const buf = await el.screenshot({ type: 'png' })
    const uri = `data:image/png;base64,${buf.toString('base64')}`
    await page.evaluate((node, u) => {
      const img = document.createElement('img')
      img.src = u
      img.setAttribute('style', 'max-width:100%;display:block;margin:12px auto;border:1px solid #d8dee7')
      node.replaceWith(img)
    }, el, uri)
    diagramCount++
  } catch (e) {
    console.warn('  diagram skip:', e.message)
  }
}

let html = await page.content()
await browser.close()

// Inline screenshots as data URIs so the .doc is fully portable.
let shotCount = 0
html = html.replace(/src="screenshots\/([a-z0-9-]+\.png)"/g, (m, file) => {
  const path = `docs/screenshots/${file}`
  if (!existsSync(path)) return m
  shotCount++
  return `src="data:image/png;base64,${readFileSync(path).toString('base64')}"`
})

// Make Word treat the HTML as a document.
html = html.replace(
  /<html[^>]*>/,
  `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">`
)
// Drop the Mermaid loader script (already rasterized; Word ignores scripts anyway).
html = html.replace(/<script[\s\S]*?<\/script>/g, '')

writeFileSync(OUT, html, 'utf8')
console.log(`Wrote ${OUT}`)
console.log(`  diagrams inlined: ${diagramCount}${rendered ? '' : ' (render incomplete)'}`)
console.log(`  screenshots inlined: ${shotCount}`)
console.log(`  size: ${(Buffer.byteLength(html) / 1024 / 1024).toFixed(1)} MB`)
