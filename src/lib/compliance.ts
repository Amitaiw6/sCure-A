/**
 * Regulatory & compliance module — CRA / EN 18031 / EN 40000.
 *
 * This file is the single source of truth (mirrored in docs SRS §22) for:
 *   - the standards the sCure software is held to,
 *   - the requirements raised in design review (REQ-CRA-*),
 *   - which controls are actually implemented in code vs. planned,
 *   - the real secure-update integrity control (EN 18031 secure update).
 *
 * Full EN 40000 / CRA conformity is a process/certification matter and cannot
 * be "implemented" as code; the items below are the concrete, code-level
 * controls that those requirements map onto.
 */

// ---------------------------------------------------------------------------
// Secure software update — integrity verification (EN 18031)
// ---------------------------------------------------------------------------

/** SHA-256 of the given bytes as a lowercase hex string (Web Crypto). */
export async function sha256Hex(data: Uint8Array): Promise<string> {
  // Copy into a fresh ArrayBuffer-backed view so the digest input type is exact.
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(data))
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Normalize a user/manifest-supplied checksum to a bare 64-char hex digest.
 * Accepts optional `sha256:` / `sha-256=` prefixes and any case.
 * Returns null if it is not a valid SHA-256 digest.
 */
export function normalizeSha256(value: string): string | null {
  if (typeof value !== 'string') return null
  const v = value.trim().toLowerCase().replace(/^sha-?256[:=]\s*/, '')
  return /^[0-9a-f]{64}$/.test(v) ? v : null
}

export interface VerifyResult {
  ok: boolean
  reason: string
  expected?: string
  actual?: string
}

/**
 * Verify an update package against its expected SHA-256 digest.
 * This is the EN 18031 secure-update control: a missing/malformed checksum or
 * any mismatch (corrupt or tampered package) MUST block installation.
 */
export async function verifyUpdatePackage(
  packageBytes: Uint8Array,
  expectedSha256: string,
): Promise<VerifyResult> {
  const expected = normalizeSha256(expectedSha256)
  if (!expected) {
    return { ok: false, reason: 'Missing or malformed checksum — update rejected' }
  }
  const actual = await sha256Hex(packageBytes)
  if (actual !== expected) {
    return { ok: false, reason: 'Checksum mismatch — package corrupt or tampered', expected, actual }
  }
  return { ok: true, reason: 'Integrity verified (SHA-256)', expected, actual }
}

// ---------------------------------------------------------------------------
// Standards & requirements (mirrors SRS §22)
// ---------------------------------------------------------------------------

export interface ComplianceStandard {
  id: string
  name: string
}

export const COMPLIANCE_STANDARDS: ComplianceStandard[] = [
  { id: 'CRA', name: 'EU Cyber Resilience Act — Regulation (EU) 2024/2847' },
  { id: 'EN 18031', name: 'EN 18031 — Cybersecurity for network-connected products' },
  { id: 'EN 40000', name: 'EN 40000-1/2/3/4 series' },
]

export interface ComplianceRequirement {
  id: string
  area: 'Hardware / Computing' | 'Software Development'
  text: string
  /** Effective date as raised in review, or null if not date-bound. */
  effective: string | null
}

export const COMPLIANCE_REQUIREMENTS: ComplianceRequirement[] = [
  { id: 'REQ-CRA-01', area: 'Hardware / Computing', text: 'Network-connected products with a digital element fall within CRA scope and must satisfy its essential cybersecurity requirements.', effective: null },
  { id: 'REQ-CRA-02', area: 'Hardware / Computing', text: 'Compliance with EN 18031 and the relevant EN 40000 series is required for the digital element.', effective: null },
  { id: 'REQ-CRA-03', area: 'Hardware / Computing', text: 'Products must meet CRA Article 14 requirements (reporting of actively exploited vulnerabilities and severe incidents).', effective: '2026-11-11' },
  { id: 'REQ-CRA-04', area: 'Hardware / Computing', text: 'Products must comply with the EN 40000-1/2/3/4 series.', effective: '2027-12-11' },
  { id: 'REQ-CRA-05', area: 'Software Development', text: 'Software in a network-connected product must conform to CRA essential requirements (secure-by-design, secure update, vulnerability handling).', effective: null },
  { id: 'REQ-CRA-06', area: 'Software Development', text: 'Ensure alignment with EN 18031 and the EN 40000 series as applicable to the software.', effective: null },
  { id: 'REQ-CRA-07', area: 'Software Development', text: 'Prepare documentation and security evidence to support CRA conformity assessment (technical documentation, SBOM, risk assessment).', effective: null },
  { id: 'REQ-CRA-08', area: 'Software Development', text: 'Ensure full compliance with the EN 40000-1/2/3/4 series.', effective: '2027-12-11' },
]

// ---------------------------------------------------------------------------
// Code-level controls — what is actually enforced in this application
// ---------------------------------------------------------------------------

export interface ComplianceControl {
  id: string
  label: string
  status: 'active' | 'planned'
  detail: string
  /** Requirement IDs this control contributes to. */
  requirements: string[]
}

export const COMPLIANCE_CONTROLS: ComplianceControl[] = [
  {
    id: 'update-integrity',
    label: 'Secure update — SHA-256 integrity verification',
    status: 'active',
    detail: 'Update packages are hashed and compared against the expected digest before install; a mismatch or missing checksum blocks installation.',
    requirements: ['REQ-CRA-05', 'REQ-CRA-06'],
  },
  {
    id: 'sbom',
    label: 'Software Bill of Materials (SBOM)',
    status: 'active',
    detail: 'Generated from package.json into /compliance/sbom.json (npm run sbom) as conformity evidence.',
    requirements: ['REQ-CRA-07'],
  },
  {
    id: 'network-access-control',
    label: 'Network interface access control (RBAC)',
    status: 'planned',
    detail: 'Authentication / role-based access for the Network screen and local API — open item (SRS §21).',
    requirements: ['REQ-CRA-05'],
  },
  {
    id: 'vuln-handling',
    label: 'Vulnerability & incident reporting (CRA Art. 14)',
    status: 'planned',
    detail: 'Documented detect / report / remediate process for actively exploited vulnerabilities.',
    requirements: ['REQ-CRA-03'],
  },
]
