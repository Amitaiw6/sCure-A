// Annotates a base screenshot: crops a region and draws arrow(s) + highlight
// circle(s) pointing at a UI icon, with a label. Renders at 2x via Chrome.
// Usage: node tools/annotate.mjs <baseImg> <spec.json> <out.png>
//   spec = { crop:{x,y,w,h}, arrows:[{ tx,ty, sx,sy, label }] }
//     tx,ty = target point (icon centre) in BASE-image pixels
//     sx,sy = arrow start / label anchor in BASE-image pixels
import { execFileSync } from 'child_process'
import { readFileSync, writeFileSync, unlinkSync } from 'fs'
import { pathToFileURL } from 'url'
import { join } from 'path'

const [baseImg, specPath, outPath] = process.argv.slice(2)
if (!baseImg || !specPath || !outPath) {
  console.error('usage: node tools/annotate.mjs <baseImg> <spec.json> <out.png>'); process.exit(1)
}
const spec = JSON.parse(readFileSync(specPath, 'utf8'))
const buf = readFileSync(baseImg)
const imgW = buf.readUInt32BE(16)
const b64 = buf.toString('base64')
const { x: cx, y: cy, w: cw, h: ch } = spec.crop

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

let svgEls = ''
for (const a of spec.arrows) {
  const px = a.tx - cx, py = a.ty - cy            // target in crop space
  const sx = a.sx - cx, sy = a.sy - cy            // start in crop space
  const dx = px - sx, dy = py - sy
  const len = Math.hypot(dx, dy) || 1
  const ex = px - (dx / len) * 26, ey = py - (dy / len) * 26   // stop before circle
  const label = esc(a.label)
  const tw = label.length * 8.2 + 16
  // label box centred on (sx,sy)
  const lx = Math.max(2, Math.min(cw - tw - 2, sx - tw / 2))
  const ly = Math.max(2, sy - 30)
  svgEls += `<circle cx="${px}" cy="${py}" r="22" fill="none" stroke="#e11d2e" stroke-width="4"/>`
  svgEls += `<line x1="${sx}" y1="${sy}" x2="${ex}" y2="${ey}" stroke="#e11d2e" stroke-width="4" marker-end="url(#ah)"/>`
  svgEls += `<rect x="${lx}" y="${ly}" width="${tw}" height="24" rx="6" fill="#e11d2e"/>`
  svgEls += `<text x="${lx + tw / 2}" y="${ly + 17}" font-family="Segoe UI, Arial" font-size="14" font-weight="700" fill="#ffffff" text-anchor="middle">${label}</text>`
}

const html = '<!doctype html><meta charset=utf-8>'
  + '<style>html,body{margin:0;padding:0;overflow:hidden}</style>'
  + `<div style="position:relative;width:${cw}px;height:${ch}px;overflow:hidden;background:#0a0a0a">`
  + `<img src="data:image/png;base64,${b64}" style="position:absolute;left:${-cx}px;top:${-cy}px;width:${imgW}px">`
  + `<svg width="${cw}" height="${ch}" style="position:absolute;left:0;top:0">`
  + '<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto">'
  + '<path d="M0,0 L7,3 L0,6 Z" fill="#e11d2e"/></marker></defs>'
  + svgEls + '</svg></div>'

const cwd = process.cwd()
const tmp = join(cwd, '.annotate.html')
writeFileSync(tmp, html, 'utf8')
execFileSync('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-sandbox',
  '--user-data-dir=' + join(cwd, '.chrometmp'),
  '--virtual-time-budget=8000', '--force-device-scale-factor=2',
  '--screenshot=' + join(cwd, outPath),
  '--window-size=' + cw + ',' + ch,
  pathToFileURL(tmp).href
])
unlinkSync(tmp)
const o = readFileSync(outPath)
console.log('wrote', outPath, o.readUInt32BE(16) + 'x' + o.readUInt32BE(20))
