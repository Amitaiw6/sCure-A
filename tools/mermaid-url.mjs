// Builds a mermaid.live edit/view URL (#pako:) from a .mmd file.
// Usage: node tools/mermaid-url.mjs <file.mmd>
import { readFileSync } from 'fs'
import zlib from 'zlib'

const path = process.argv[2]
if (!path) { console.error('usage: node tools/mermaid-url.mjs <file.mmd>'); process.exit(1) }
const code = readFileSync(path, 'utf8')

const state = { code, mermaid: '{\n  "theme": "default"\n}', autoSync: true, updateDiagram: true }
const json = JSON.stringify(state)
const deflated = zlib.deflateSync(Buffer.from(json, 'utf8'), { level: 9 })
const b64 = deflated.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const pako = 'pako:' + b64
console.log('EDIT=https://mermaid.live/edit#' + pako)
console.log('VIEW=https://mermaid.live/view#' + pako)
