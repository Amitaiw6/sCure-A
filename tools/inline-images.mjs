// Inlines screenshots/*.png references in an HTML file as base64 data URIs,
// producing a fully self-contained, portable file.
// Usage: node tools/inline-images.mjs <input.html> [output.html]
import { readFileSync, writeFileSync, existsSync } from 'fs'
import { dirname, resolve } from 'path'

const input = process.argv[2]
const output = process.argv[3] || input
if (!input) { console.error('usage: node tools/inline-images.mjs <input.html> [output.html]'); process.exit(1) }

const baseDir = dirname(resolve(input))
let html = readFileSync(input, 'utf8')
let count = 0, missing = []

html = html.replace(/src="(?!data:)([^"]+\.(?:png|jpg|jpeg|gif|svg))"/g, (m, rel) => {
  const file = resolve(baseDir, rel)
  if (!existsSync(file)) { missing.push(rel); return m }
  const ext = rel.split('.').pop().toLowerCase()
  const mime = ext === 'svg' ? 'image/svg+xml' : ext === 'jpg' ? 'image/jpeg' : `image/${ext}`
  count++
  return `src="data:${mime};base64,${readFileSync(file).toString('base64')}"`
})

writeFileSync(output, html, 'utf8')
console.log(`Inlined ${count} image(s) → ${output} (${(Buffer.byteLength(html)/1024/1024).toFixed(1)} MB)`)
if (missing.length) console.warn('  missing:', missing.join(', '))
