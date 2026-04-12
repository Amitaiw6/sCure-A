interface SCureLogoProps {
  size?: number
  className?: string
  color?: string
}

export default function SCureLogo({ size = 24, className = '', color = 'currentColor' }: SCureLogoProps) {
  const sw = "5.5"

  // X: 0, 25, 50, 75, 100 (unchanged)
  // Y (x1.8): 0, 45, 67.5, 90, 126

  // Perpendicular lines:
  // Left diagonal: (0,45)→(50,90), slope=0.9, perp=-1/0.9=-1.111
  // From (0,90): y=90-1.111x, diagonal: y=45+0.9x
  // 45+0.9x=90-1.111x → 2.011x=45 → x=22.4, y=65.1
  // Right diagonal: (50,45)→(100,90), slope=0.9, perp=-1.111
  // From (100,45): y=45-1.111(x-100)=156.1-1.111x, diagonal: y=45+0.9(x-50)=0.9x
  // 156.1-1.111x=0.9x → x=77.6, y=69.9

  return (
    <svg
      viewBox="-3 -7 106 141"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      style={{ maxWidth: '100%', maxHeight: '100%' }}
      className={className}
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeMiterLimit="100"
    >
      {/* Top V */}
      <path d="M0 45 L50 0 L100 45" stroke={color} strokeWidth={sw} fill="none" />

      {/* Bottom V */}
      <path d="M0 90 L50 126 L100 90" stroke={color} strokeWidth={sw} fill="none" />

      {/* Vertical line */}
      <line x1="50" y1="0" x2="50" y2="126" stroke={color} strokeWidth={sw} />
      {/* Top horizontal */}
      <line x1="0" y1="45" x2="100" y2="45" stroke={color} strokeWidth={sw} />
      {/* Bottom horizontal */}
      <line x1="0" y1="90" x2="100" y2="90" stroke={color} strokeWidth={sw} />

      {/* S-weave diagonals */}
      <line x1="0" y1="45" x2="50" y2="90" stroke={color} strokeWidth={sw} />
      <line x1="50" y1="45" x2="100" y2="90" stroke={color} strokeWidth={sw} />
      {/* Top-right perpendicular to right diagonal */}
      <line x1="100" y1="45" x2="77.6" y2="69.9" stroke={color} strokeWidth={sw} />
      {/* Bottom-left perpendicular to left diagonal */}
      <line x1="0" y1="90" x2="22.4" y2="65.1" stroke={color} strokeWidth={sw} />
    </svg>
  )
}
