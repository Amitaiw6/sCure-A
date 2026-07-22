// Renders a .drawio file to a standalone SVG using the draw.io GraphViewer in
// headless Chrome. Usage: node tools/drawio-to-svg.mjs <in.drawio> <out.svg>
import { readFileSync, writeFileSync } from 'fs'
import { execFileSync } from 'child_process'

const inPath = process.argv[2]
const outPath = process.argv[3]
if (!inPath || !outPath) { console.error('usage: node tools/drawio-to-svg.mjs <in.drawio> <out.svg>'); process.exit(1) }

const xml = readFileSync(inPath, 'utf8')
const cfg = JSON.stringify({ highlight: 'none', nav: false, resize: true, xml })
// HTML-escape the JSON for a single-quoted attribute value.
const attr = cfg.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;')

const html = `<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;padding:0}</style></head><body>
<div class="mxgraph" data-mxgraph='${attr}'></div>
<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
</body></html>`

writeFileSync('render.html', html, 'utf8')

const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const dump = execFileSync(chrome, [
  '--headless=new', '--disable-gpu', '--no-sandbox',
  '--virtual-time-budget=12000', '--dump-dom',
  'file:///' + process.cwd().replace(/\\/g, '/') + '/render.html'
], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })

const m = dump.match(/<svg[\s\S]*?<\/svg>/i)
if (!m) {
  writeFileSync('render-dump.html', dump, 'utf8')
  console.error('No <svg> found. DOM len=' + dump.length + ', wrote render-dump.html for inspection.')
  process.exit(2)
}
let svg = m[0]
if (!/xmlns=/.test(svg)) svg = svg.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"')

// GraphViewer emits an SVG sized to fill a container (width:100%/height:100%,
// no viewBox). Convert it to a standalone, intrinsically-sized SVG so it embeds
// cleanly via <img>: derive width/height from min-width/min-height and add a viewBox.
const open = svg.match(/<svg[^>]*>/i)[0]
const w = Math.ceil(parseFloat((open.match(/min-width:\s*([\d.]+)px/i) || [])[1] || '800'))
const h = Math.ceil(parseFloat((open.match(/min-height:\s*([\d.]+)px/i) || [])[1] || '600'))
let newOpen = open
  .replace(/\sstyle="[^"]*"/i, '')
  .replace(/\swidth="[^"]*"/i, '')
  .replace(/\sheight="[^"]*"/i, '')
  .replace(/<svg/i, `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"`)
svg = svg.replace(open, newOpen)

writeFileSync(outPath, svg, 'utf8')
console.log('wrote', outPath, `${w}x${h}`, svg.length, 'bytes')
