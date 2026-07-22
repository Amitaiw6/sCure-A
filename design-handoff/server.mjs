// Zero-dependency static server for the sCure UI build (folder ./app).
// Serves files with correct MIME types and SPA fallback to index.html,
// then opens the browser once it is actually listening. Needs only Node.js.
import { createServer } from 'http'
import { readFile, stat } from 'fs/promises'
import { join, normalize, extname, dirname } from 'path'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = join(__dirname, 'app')
const PORT = Number(process.env.PORT) || 5050

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.mp4': 'video/mp4',
  '.ico': 'image/x-icon',
}

async function tryFile(path) {
  try {
    const s = await stat(path)
    if (s.isFile()) return path
  } catch { /* not a file */ }
  return null
}

const server = createServer(async (req, res) => {
  try {
    const url = decodeURIComponent((req.url || '/').split('?')[0])
    // Resolve safely inside ROOT (block path traversal)
    const rel = normalize(url).replace(/^(\.\.[/\\])+/, '')
    let filePath = join(ROOT, rel)
    if (!filePath.startsWith(ROOT)) { res.writeHead(403).end('Forbidden'); return }

    let resolved = await tryFile(filePath)
    if (!resolved && url.endsWith('/')) resolved = await tryFile(join(filePath, 'index.html'))
    // SPA fallback: extensionless route → index.html
    if (!resolved && !extname(url)) resolved = await tryFile(join(ROOT, 'index.html'))

    if (!resolved) { res.writeHead(404).end('Not found'); return }

    const body = await readFile(resolved)
    res.writeHead(200, { 'Content-Type': MIME[extname(resolved)] || 'application/octet-stream' })
    res.end(body)
  } catch (err) {
    res.writeHead(500).end('Server error: ' + err.message)
  }
})

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\n  Port ${PORT} is already in use. Set a different one, e.g.:  PORT=5060 node server.mjs\n`)
  } else {
    console.error('\n  Server error:', err.message, '\n')
  }
  process.exit(1)
})

server.listen(PORT, () => {
  const urlStr = `http://localhost:${PORT}`
  console.log(`\n  sCure UI is running at  ${urlStr}`)
  console.log(`  (keep this window open; press Ctrl+C to stop)\n`)
  // Open the default browser now that we are actually listening.
  const cmd = process.platform === 'win32' ? ['cmd', ['/c', 'start', '', urlStr]]
    : process.platform === 'darwin' ? ['open', [urlStr]]
    : ['xdg-open', [urlStr]]
  try { spawn(cmd[0], cmd[1], { stdio: 'ignore', detached: true }).unref() } catch { /* open manually */ }
})
