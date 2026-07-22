// Rasterizes an SVG to a PNG on a draw.io-style grid background (2x scale),
// trimmed to the SVG bounds. Usage: node tools/svg-to-grid-png.mjs <in.svg> <out.png>
import { execFileSync } from 'child_process'
import { readFileSync, writeFileSync, unlinkSync } from 'fs'
import { pathToFileURL } from 'url'
import { join } from 'path'

const inPath = process.argv[2]
const outPath = process.argv[3]
if (!inPath || !outPath) { console.error('usage: node tools/svg-to-grid-png.mjs <in.svg> <out.png>'); process.exit(1) }

const svg = readFileSync(inPath, 'utf8')
const open = svg.match(/<svg[^>]*>/i)[0]
const w = Math.ceil(parseFloat((open.match(/\bwidth="([\d.]+)"/i) || [])[1] || '800'))
const h = Math.ceil(parseFloat((open.match(/\bheight="([\d.]+)"/i) || [])[1] || '600'))
const pad = 14

const html = '<!doctype html><meta charset=utf-8>'
  + '<style>html,body{margin:0;padding:0;overflow:hidden}</style>'
  + `<body><div style="width:${w}px;height:${h}px;padding:${pad}px;box-sizing:content-box;background-color:#ffffff;`
  + 'background-image:linear-gradient(#eef0f2 1px,transparent 1px),linear-gradient(90deg,#eef0f2 1px,transparent 1px);'
  + 'background-size:10px 10px;background-position:-1px -1px">'
  + svg + '</div></body>'

const cwd = process.cwd()
const tmp = join(cwd, '.grid-render.html')
writeFileSync(tmp, html, 'utf8')
execFileSync('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-sandbox',
  '--user-data-dir=' + join(cwd, '.chrometmp'),
  '--virtual-time-budget=3000', '--force-device-scale-factor=2',
  '--screenshot=' + join(cwd, outPath),
  '--window-size=' + (w + 2 * pad) + ',' + (h + 2 * pad),
  '--default-background-color=FFFFFFFF',
  pathToFileURL(tmp).href
])
unlinkSync(tmp)
const b = readFileSync(outPath)
console.log('wrote', outPath, b.readUInt32BE(16) + 'x' + b.readUInt32BE(20))
