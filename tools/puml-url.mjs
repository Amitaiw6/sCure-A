// Encodes a PlantUML source file into plantuml.com server URLs (svg / png / editor).
// Usage: node tools/puml-url.mjs <path-to.puml>
import { readFileSync } from 'fs'
import zlib from 'zlib'

const path = process.argv[2]
if (!path) { console.error('usage: node tools/puml-url.mjs <file.puml>'); process.exit(1) }
const text = readFileSync(path, 'utf8')
const deflated = zlib.deflateRawSync(Buffer.from(text, 'utf8'), { level: 9 })

const enc6 = b => {
  if (b < 10) return String.fromCharCode(48 + b)
  b -= 10; if (b < 26) return String.fromCharCode(65 + b)
  b -= 26; if (b < 26) return String.fromCharCode(97 + b)
  b -= 26; return b === 0 ? '-' : b === 1 ? '_' : '?'
}
const a3 = (b1, b2, b3) =>
  enc6((b1 >> 2) & 0x3f) +
  enc6((((b1 & 0x3) << 4) | (b2 >> 4)) & 0x3f) +
  enc6((((b2 & 0xf) << 2) | (b3 >> 6)) & 0x3f) +
  enc6(b3 & 0x3f)

let r = ''
for (let i = 0; i < deflated.length; i += 3) {
  if (i + 2 === deflated.length) r += a3(deflated[i], deflated[i + 1], 0)
  else if (i + 1 === deflated.length) r += a3(deflated[i], 0, 0)
  else r += a3(deflated[i], deflated[i + 1], deflated[i + 2])
}
console.log('SVG=https://www.plantuml.com/plantuml/svg/' + r)
console.log('PNG=https://www.plantuml.com/plantuml/png/' + r)
console.log('EDIT=https://www.plantuml.com/plantuml/uml/' + r)
