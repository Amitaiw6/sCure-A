// Renders the model at the reference-sheet angles and puts each next to the reference crop (compare/side_*.png).
import puppeteer from 'puppeteer-core'
import { createServer } from 'http'
import { readFile } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join, extname, normalize } from 'path'
const here = dirname(fileURLToPath(import.meta.url))
const T = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png' }
const server = createServer((q, r) => { const p = normalize(join(here, decodeURIComponent(q.url.split('?')[0]))); readFile(p, (e, b) => { if (e) { r.writeHead(404); return r.end() } r.writeHead(200, { 'Content-Type': T[extname(p)] || 'application/octet-stream' }); r.end(b) }) }).listen(0, '127.0.0.1')
await new Promise(r => server.once('listening', r))
const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--ignore-gpu-blocklist'] })
const pg = await b.newPage(); await pg.setViewport({ width: 1920, height: 1080 })
pg.on('pageerror', e => console.log('[pageerror]', e.message))
await pg.goto(`http://127.0.0.1:${server.address().port}/compare.html`); await pg.waitForFunction(() => window.READY === true)
for (const v of ['front', 'right', 'left', 'p34', 'open']) { await pg.evaluate(v => window.view(v), v); await pg.screenshot({ path: join(here, 'compare', `model_${v}.png`) }) }
await b.close(); server.close()
