// Generates a minimal CycloneDX-style SBOM from package.json into
// public/compliance/sbom.json — conformity evidence for CRA Article / REQ-CRA-07.
// Run: npm run sbom
import { readFileSync, writeFileSync, mkdirSync } from 'fs'

const pkg = JSON.parse(readFileSync('package.json', 'utf8'))
const OUT_DIR = 'public/compliance'
const OUT = `${OUT_DIR}/sbom.json`

const toComponents = (deps = {}, scope) =>
  Object.entries(deps).map(([name, version]) => ({
    type: 'library',
    name,
    version: String(version).replace(/^[\^~]/, ''),
    scope,
    purl: `pkg:npm/${name}@${String(version).replace(/^[\^~]/, '')}`,
  }))

const components = [
  ...toComponents(pkg.dependencies, 'required'),
  ...toComponents(pkg.devDependencies, 'optional'),
].sort((a, b) => a.name.localeCompare(b.name))

const sbom = {
  bomFormat: 'CycloneDX',
  specVersion: '1.5',
  metadata: {
    timestamp: new Date().toISOString(),
    component: { type: 'application', name: pkg.name, version: pkg.version },
    standards: ['EU CRA (Regulation (EU) 2024/2847)', 'EN 18031', 'EN 40000'],
  },
  components,
}

mkdirSync(OUT_DIR, { recursive: true })
writeFileSync(OUT, JSON.stringify(sbom, null, 2), 'utf8')
console.log(`Wrote ${OUT} — ${components.length} components`)
