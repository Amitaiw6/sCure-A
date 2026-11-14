// Renders film.html to frames and encodes an MP4 (ffmpeg from imageio-ffmpeg).
// The folder is served over a local HTTP server so the UI screenshots can be used as WebGL textures.
// usage: node render.mjs stills [t1,t2,...]           -> stills/*.png
//        node render.mjs video <ffmpeg.exe> [audio.wav] -> sCure_Box_Expo_60s.mp4
import puppeteer from 'puppeteer-core'
import { spawn } from 'child_process'
import { createServer } from 'http'
import { mkdirSync, readFile } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join, extname, normalize } from 'path'

const here = dirname(fileURLToPath(import.meta.url))
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.json': 'application/json' }
const server = createServer((req, res) => {
  const p = normalize(join(here, decodeURIComponent(req.url.split('?')[0])))
  if (!p.startsWith(here)) { res.writeHead(403); return res.end() }
  readFile(p, (err, buf) => { if (err) { res.writeHead(404); return res.end() } res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' }); res.end(buf) })
}).listen(0, '127.0.0.1')
await new Promise(r => server.once('listening', r))
const url = `http://127.0.0.1:${server.address().port}/film.html?capture`

const browser = await puppeteer.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: 'new', args: ['--no-sandbox', '--hide-scrollbars', '--ignore-gpu-blocklist', '--enable-webgl'],
})
const page = await browser.newPage()
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.text()) })
page.on('pageerror', e => console.log('[pageerror]', e.message))
await page.setViewport({ width: 1920, height: 1080 })
await page.goto(url)
await page.waitForFunction(() => window.READY === true, { timeout: 30000 })

const mode = process.argv[2]
if (mode === 'stills') {
  mkdirSync(join(here, 'stills'), { recursive: true })
  const times = (process.argv[3] || '2,7,12,17,20,25,30,34,39,42,46,49,51,55,59').split(',').map(Number)
  for (const t of times) {
    await page.evaluate(t => window.renderAt(t), t)
    await page.screenshot({ path: join(here, 'stills', `t${String(t).padStart(4, '0')}.png`) })
  }
} else {
  const ff = process.argv[3], audio = process.argv[4], FPS = 30, N = 60 * FPS
  const args = ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-']
  if (audio) args.push('-i', audio)
  args.push('-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', '-preset', 'medium')
  if (audio) args.push('-c:a', 'aac', '-b:a', '192k', '-shortest')
  args.push('-movflags', '+faststart', join(here, 'sCure_Box_Expo_60s.mp4'))
  const p = spawn(ff, args, { stdio: ['pipe', 'inherit', 'inherit'] })
  for (let i = 0; i < N; i++) {
    await page.evaluate(t => window.renderAt(t), i / FPS)
    const buf = await page.screenshot({ type: 'jpeg', quality: 95 })
    if (!p.stdin.write(buf)) await new Promise(r => p.stdin.once('drain', r))
    if (i % 150 === 0) console.log('frame', i, '/', N)
  }
  p.stdin.end()
  await new Promise(r => p.on('close', r))
}
await browser.close()
server.close()
