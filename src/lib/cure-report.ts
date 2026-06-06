import type { CureLog } from '@/context/CureHistoryContext'

export function generateCureReport(log: CureLog) {
  const telemetry = log.telemetry ?? []
  if (telemetry.length === 0) return

  const times = telemetry.map(s => s.t)
  const chamberTemps = telemetry.map(s => s.chamberTemp)
  const uv405 = telemetry.map(s => s.uvOn && s.uvType === '405nm' ? 1 : 0)
  const uv450 = telemetry.map(s => s.uvOn && s.uvType === '450nm' ? 1 : 0)
  const ledRight = telemetry.map(s => s.ledTemps?.right ?? 0)
  const ledLeft = telemetry.map(s => s.ledTemps?.left ?? 0)
  const ledDoor = telemetry.map(s => s.ledTemps?.door ?? 0)
  const ledBack = telemetry.map(s => s.ledTemps?.back ?? 0)

  const sampleInterval = times.length > 1 ? times[1] - times[0] : 5
  const uv405Duration = uv405.filter(v => v === 1).length * sampleInterval
  const uv450Duration = uv450.filter(v => v === 1).length * sampleInterval
  const uv405Str = uv405Duration > 0 ? `${Math.floor(uv405Duration / 60)}m ${uv405Duration % 60}s` : 'Not used'
  const uv450Str = uv450Duration > 0 ? `${Math.floor(uv450Duration / 60)}m ${uv450Duration % 60}s` : 'Not used'

  const maxTemp = Math.max(...chamberTemps, 40)
  const uvScale = maxTemp + 10

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${String(sec).padStart(2, '0')}`
  }

  const timeLabels = JSON.stringify(times.map(formatTime))
  const startDate = new Date(log.startedAt).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
  const endDate = log.endedAt ? new Date(log.endedAt).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }) : 'N/A'
  const reportDate = new Date().toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })

  const durationStr = log.duration != null
    ? `${Math.floor(log.duration / 60)}m ${log.duration % 60}s`
    : '— —'

  const statusClass = log.status === 'completed' ? 'ok' : log.status === 'aborted' ? 'warn' : log.status === 'running' ? 'warn' : 'err'
  const statusLabel = log.status.charAt(0).toUpperCase() + log.status.slice(1)

  const statusPillBg = log.status === 'completed' ? '#DCFCE7' : log.status === 'aborted' ? '#FEF3C7' : log.status === 'running' ? '#FEF3C7' : '#FEE2E2'
  const statusPillColor = log.status === 'completed' ? '#166534' : log.status === 'aborted' ? '#92400E' : log.status === 'running' ? '#92400E' : '#991B1B'
  const statusPillBorder = log.status === 'completed' ? '#86EFAC' : log.status === 'aborted' ? '#FCD34D' : log.status === 'running' ? '#FCD34D' : '#FCA5A5'
  const statusDotColor = log.status === 'completed' ? '#16A34A' : log.status === 'aborted' ? '#D97706' : log.status === 'running' ? '#D97706' : '#DC2626'

  const uv405Scaled = uv405.map(v => v === 1 ? uvScale : null)
  const uv450Scaled = uv450.map(v => v === 1 ? uvScale : null)

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cure Report · ${log.materialName} · Stratasys</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {
    color-scheme: light;
    --sts-blue-900: #0A1929;
    --sts-blue-800: #0B2B5B;
    --sts-blue-700: #003DA5;
    --sts-blue-500: #0072CE;
    --sts-blue-300: #00A3E0;
    --sts-gray-900: #1C2733;
    --sts-gray-700: #5A6B7A;
    --sts-gray-500: #8A97A3;
    --sts-gray-300: #C9D3DC;
    --sts-gray-200: #DDE4EB;
    --sts-gray-100: #E6ECF2;
    --sts-gray-50:  #F4F7FA;
    --sts-white:    #FFFFFF;
    --sts-success:  #16A34A;
    --sts-warning:  #D97706;
    --sts-error:    #DC2626;
    --sts-cure:     #6D28D9;
    --sts-bleach:   #0891B2;
    --sts-heat:     #EA580C;
    --sts-cool:     #0D9488;
    --sts-dry:      #1D4ED8;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: var(--sts-gray-50); }
  body {
    font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
    color: var(--sts-blue-900);
    padding: 32px 24px 48px;
    max-width: 1120px;
    margin: 0 auto;
    font-variant-numeric: tabular-nums;
    -webkit-font-smoothing: antialiased;
  }

  .brandbar {
    display: flex; align-items: center; justify-content: space-between;
    padding-bottom: 14px; margin-bottom: 20px;
    border-bottom: 1px solid var(--sts-gray-200);
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .sts-logo { height: 34px; width: auto; display: block; }
  .brand-divider { width: 1px; height: 26px; background: var(--sts-gray-300); }
  .brand-product { font-size: 14px; font-weight: 700; color: var(--sts-blue-900); letter-spacing: 0.2px; }
  .brand-sub { font-size: 11px; color: var(--sts-gray-700); letter-spacing: 0.6px; text-transform: uppercase; margin-top: 2px; }
  .meta-right { text-align: right; }
  .meta-right .report-id { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: var(--sts-gray-700); }
  .meta-right .report-ts { font-size: 11px; color: var(--sts-gray-700); margin-top: 2px; }

  .title-block {
    background: var(--sts-white);
    border: 1px solid var(--sts-gray-200);
    border-left: 4px solid var(--sts-blue-700);
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .title-block h1 { font-size: 22px; font-weight: 700; color: var(--sts-blue-900); letter-spacing: -0.2px; }
  .title-block .subline { font-size: 13px; color: var(--sts-gray-700); margin-top: 4px; }
  .title-block .material-chip {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--sts-gray-100); color: var(--sts-blue-800);
    border: 1px solid var(--sts-gray-200);
    border-radius: 999px; padding: 4px 12px; font-size: 12px; font-weight: 600;
    margin-top: 8px;
  }
  .material-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--sts-blue-500); }
  .status-pill {
    display: inline-flex; align-items: center; gap: 8px;
    background: ${statusPillBg}; color: ${statusPillColor};
    border: 1px solid ${statusPillBorder};
    border-radius: 999px; padding: 6px 14px;
    font-size: 12px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase;
  }
  .status-pill .pulse {
    width: 8px; height: 8px; border-radius: 50%; background: ${statusDotColor};
  }

  .info-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 20px; }
  .info-card {
    background: var(--sts-white);
    border: 1px solid var(--sts-gray-200);
    border-radius: 8px;
    padding: 14px 14px 12px;
  }
  .info-card .label { font-size: 10px; color: var(--sts-gray-700); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .info-card .value { font-size: 20px; font-weight: 700; color: var(--sts-blue-900); margin-top: 6px; letter-spacing: -0.3px; }
  .info-card .value.ok { color: var(--sts-success); }
  .info-card .value.warn { color: var(--sts-warning); }
  .info-card .value.err { color: var(--sts-error); }
  .info-card .value.cure { color: var(--sts-cure); }
  .info-card .value.bleach { color: var(--sts-bleach); }
  .info-card .value.muted { color: var(--sts-gray-500); font-size: 14px; font-weight: 500; }
  .info-card .unit { font-size: 12px; color: var(--sts-gray-700); font-weight: 500; margin-left: 2px; }

  .phases {
    display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; align-items: center;
    background: var(--sts-white); border: 1px solid var(--sts-gray-200);
    border-radius: 8px; padding: 12px 14px;
  }
  .phases-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.8px; color: var(--sts-gray-700); font-weight: 600; margin-right: 6px; }
  .phase-badge { padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.2px; }
  .phase-drying   { background: rgba(29,78,216,0.10);  color: var(--sts-dry); }
  .phase-heating  { background: rgba(234,88,12,0.10);  color: var(--sts-heat); }
  .phase-cure     { background: rgba(109,40,217,0.10); color: var(--sts-cure); }
  .phase-bleacher { background: rgba(8,145,178,0.10);  color: var(--sts-bleach); }
  .phase-cooling  { background: rgba(13,148,136,0.10); color: var(--sts-cool); }
  .phase-nitrogen { background: var(--sts-gray-100);   color: var(--sts-gray-700); }

  .chart-section {
    background: var(--sts-white);
    border: 1px solid var(--sts-gray-200);
    border-radius: 10px;
    padding: 22px 24px;
    margin-bottom: 16px;
  }
  .chart-section h2 { font-size: 15px; font-weight: 700; color: var(--sts-blue-900); letter-spacing: -0.1px; }
  .chart-section .chart-sub { font-size: 12px; color: var(--sts-gray-700); margin-top: 4px; margin-bottom: 16px; }
  .chart-container { position: relative; height: 300px; }
  .legend-row {
    display: flex; gap: 20px; margin-top: 14px; padding: 10px 14px;
    background: var(--sts-gray-50);
    border: 1px solid var(--sts-gray-200);
    border-radius: 6px; flex-wrap: wrap;
  }
  .legend-item { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--sts-blue-900); font-weight: 500; }
  .legend-dot { width: 10px; height: 10px; border-radius: 2px; }

  .footer {
    margin-top: 28px; font-size: 11px; color: var(--sts-gray-700);
    border-top: 1px solid var(--sts-gray-200); padding-top: 14px;
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
  }
  .footer .fine { color: var(--sts-gray-500); }
  .footer strong { color: var(--sts-blue-900); font-weight: 600; }
  .footer-left { display: flex; align-items: center; gap: 10px; }
  .sts-logo-sm { height: 20px; width: auto; display: block; opacity: 0.85; }

  @media (max-width: 880px) { .info-grid { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 520px) { .info-grid { grid-template-columns: repeat(2, 1fr); } .title-block { flex-direction: column; align-items: flex-start; } }
  @media print {
    body { background: #fff; padding: 16px; }
    .title-block, .info-card, .chart-section, .phases { box-shadow: none; }
  }
</style>
</head>
<body>

<!-- Brand bar -->
<div class="brandbar">
  <div class="brand">
    <svg class="sts-logo" viewBox="0 0 320 48" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Stratasys">
      <svg x="2" y="6" width="32" height="36" viewBox="-3 -7 106 141" fill="none" stroke="#0A1929" stroke-width="5.5" stroke-linecap="square" stroke-linejoin="miter" stroke-miterlimit="100">
        <path d="M0 45 L50 0 L100 45"/><path d="M0 90 L50 126 L100 90"/>
        <line x1="50" y1="0" x2="50" y2="126"/><line x1="0" y1="45" x2="100" y2="45"/><line x1="0" y1="90" x2="100" y2="90"/>
        <line x1="0" y1="45" x2="50" y2="90"/><line x1="50" y1="45" x2="100" y2="90"/>
        <line x1="100" y1="45" x2="77.6" y2="69.9"/><line x1="0" y1="90" x2="22.4" y2="65.1"/>
      </svg>
      <text x="44" y="33" font-family="Inter, 'Helvetica Neue', Arial, sans-serif" font-size="26" font-weight="700" letter-spacing="1.5" fill="#0A1929">STRATASYS</text>
    </svg>
    <div class="brand-divider" aria-hidden="true"></div>
    <div>
      <div class="brand-product">S-Cure</div>
      <div class="brand-sub">Process Report</div>
    </div>
  </div>
  <div class="meta-right">
    <div class="report-id">S.N · ${log.serialNumber ?? '------'}</div>
    <div class="report-id" style="margin-top:2px">Report · ${log.id.slice(0, 8)}</div>
    <div class="report-ts">${reportDate}</div>
  </div>
</div>

<!-- Title block -->
<div class="title-block">
  <div>
    <h1>Cure Report — ${log.materialName}</h1>
    <div class="subline">Post-process curing cycle · UV + thermal · 4-LED chamber</div>
    <span class="material-chip"><span class="dot"></span>Material · ${log.materialName}</span>
  </div>
  <span class="status-pill"><span class="pulse"></span>${statusLabel}</span>
</div>

<!-- Metric grid -->
<div class="info-grid">
  <div class="info-card">
    <div class="label">Status</div>
    <div class="value ${statusClass}">${statusLabel}</div>
  </div>
  <div class="info-card">
    <div class="label">Duration</div>
    <div class="value${log.duration == null ? ' muted' : ''}">${durationStr}</div>
  </div>
  <div class="info-card">
    <div class="label">Steps</div>
    <div class="value">${log.stepsCompleted}<span class="unit"> / ${log.steps}</span></div>
  </div>
  <div class="info-card">
    <div class="label">Max Temp</div>
    <div class="value">${maxTemp}<span class="unit">°C</span></div>
  </div>
  <div class="info-card">
    <div class="label">Cure · 405 nm</div>
    <div class="value ${uv405Duration > 0 ? 'cure' : 'muted'}">${uv405Str}</div>
  </div>
  <div class="info-card">
    <div class="label">Bleach · 450 nm</div>
    <div class="value ${uv450Duration > 0 ? 'bleach' : 'muted'}">${uv450Str}</div>
  </div>
</div>

<!-- Phase ribbon -->
<div class="phases">
  <span class="phases-label">Programme</span>
  ${log.phases.map(p => {
    const label = p === 'Cure' ? 'Cure · 405 nm' : p === 'Bleacher' ? 'Bleach · 450 nm' : p === 'Nitrogen' ? 'N\u2082 Purge' : p
    return `<span class="phase-badge phase-${p.toLowerCase()}">${label}</span>`
  }).join('')}
</div>

<!-- Chamber chart -->
<div class="chart-section">
  <h2>Chamber temperature &amp; UV light activity</h2>
  <div class="chart-sub">Chamber temperature with overlaid cure and bleach windows across the cycle.</div>
  <div class="chart-container"><canvas id="tempChart"></canvas></div>
  <div class="legend-row">
    <div class="legend-item"><div class="legend-dot" style="background:var(--sts-heat)"></div>Chamber temperature</div>
    <div class="legend-item"><div class="legend-dot" style="background:rgba(109,40,217,0.35)"></div>Cure 405 nm — ON</div>
    <div class="legend-item"><div class="legend-dot" style="background:rgba(8,145,178,0.35)"></div>Bleach 450 nm — ON</div>
  </div>
</div>

<!-- LED chart -->
<div class="chart-section">
  <h2>LED module temperatures</h2>
  <div class="chart-sub">Readings from the four LED modules throughout the cure cycle.</div>
  <div class="chart-container"><canvas id="ledChart"></canvas></div>
  <div class="legend-row">
    <div class="legend-item"><div class="legend-dot" style="background:#DC2626"></div>Right LED</div>
    <div class="legend-item"><div class="legend-dot" style="background:#0072CE"></div>Left LED</div>
    <div class="legend-item"><div class="legend-dot" style="background:#16A34A"></div>Door LED</div>
    <div class="legend-item"><div class="legend-dot" style="background:#D97706"></div>Back LED</div>
  </div>
</div>

<!-- Footer -->
<div class="footer">
  <div class="footer-left">
    <svg class="sts-logo-sm" viewBox="0 0 320 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <svg x="2" y="6" width="32" height="36" viewBox="-3 -7 106 141" fill="none" stroke="#8A97A3" stroke-width="5.5" stroke-linecap="square" stroke-linejoin="miter" stroke-miterlimit="100">
        <path d="M0 45 L50 0 L100 45"/><path d="M0 90 L50 126 L100 90"/>
        <line x1="50" y1="0" x2="50" y2="126"/><line x1="0" y1="45" x2="100" y2="45"/><line x1="0" y1="90" x2="100" y2="90"/>
        <line x1="0" y1="45" x2="50" y2="90"/><line x1="50" y1="45" x2="100" y2="90"/>
        <line x1="100" y1="45" x2="77.6" y2="69.9"/><line x1="0" y1="90" x2="22.4" y2="65.1"/>
      </svg>
      <text x="44" y="33" font-family="Inter, 'Helvetica Neue', Arial, sans-serif" font-size="26" font-weight="700" letter-spacing="1.5" fill="#8A97A3">STRATASYS</text>
    </svg>
    <span>S-Cure · Report generated ${reportDate}</span>
  </div>
  <div class="fine">Software v1.1.0 · Confidential — for internal process review</div>
</div>

<script>
const labels = ${timeLabels};

const stsGrid  = '#E6ECF2';
const stsAxis  = '#5A6B7A';

const stsTooltip = {
  backgroundColor: '#0A1929',
  titleColor: '#FFFFFF',
  bodyColor: '#C9D3DC',
  borderColor: '#0072CE',
  borderWidth: 1,
  padding: 10,
  titleFont: { weight: '600', size: 12 },
  bodyFont: { size: 12 },
  cornerRadius: 6,
};

const stsScaleX = {
  ticks: { color: stsAxis, font: { size: 11, family: 'Inter, Helvetica Neue, Arial, sans-serif' }, maxTicksLimit: 25 },
  grid: { color: stsGrid, drawBorder: false },
  border: { color: stsGrid },
  title: { display: true, text: 'Time (min:sec)', color: stsAxis, font: { size: 11, weight: '600' } }
};

const stsScaleY = (opts) => ({
  title: { display: true, text: opts.text || 'Temperature (°C)', color: stsAxis, font: { size: 11, weight: '600' } },
  ticks: { color: stsAxis, stepSize: opts.step ?? 10, font: { family: 'Inter, Helvetica Neue, Arial, sans-serif' } },
  grid: { color: stsGrid, drawBorder: false },
  border: { color: stsGrid },
  min: opts.min ?? 0,
  max: opts.max,
});

// Chamber temperature + UV overlay
new Chart(document.getElementById('tempChart'), {
  type: 'line',
  data: {
    labels,
    datasets: [
      {
        label: 'Cure 405nm',
        data: ${JSON.stringify(uv405Scaled)},
        backgroundColor: 'rgba(109, 40, 217, 0.18)',
        borderColor: 'rgba(109, 40, 217, 0.35)',
        fill: true, stepped: true, pointRadius: 0, borderWidth: 0, spanGaps: false,
        yAxisID: 'y', order: 2,
      },
      {
        label: 'Bleach 450nm',
        data: ${JSON.stringify(uv450Scaled)},
        backgroundColor: 'rgba(8, 145, 178, 0.15)',
        borderColor: 'rgba(8, 145, 178, 0.35)',
        fill: true, stepped: true, pointRadius: 0, borderWidth: 0, spanGaps: false,
        yAxisID: 'y', order: 3,
      },
      {
        label: 'Chamber',
        data: ${JSON.stringify(chamberTemps)},
        borderColor: '#EA580C',
        backgroundColor: 'rgba(234, 88, 12, 0.06)',
        fill: true, tension: 0.3,
        pointRadius: 2.5, pointBackgroundColor: '#EA580C', pointBorderColor: '#FFFFFF', pointBorderWidth: 1,
        borderWidth: 2.5,
        yAxisID: 'y', order: 1,
      },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        ...stsTooltip,
        callbacks: {
          label: function(ctx) {
            if (ctx.datasetIndex === 0) return ctx.raw ? 'Cure 405 nm · ON' : null;
            if (ctx.datasetIndex === 1) return ctx.raw ? 'Bleach 450 nm · ON' : null;
            return 'Chamber · ' + ctx.raw + ' °C';
          }
        }
      }
    },
    scales: { x: stsScaleX, y: stsScaleY({ min: 0, max: ${uvScale + 5}, step: 10 }) }
  }
});

// LED temperatures
new Chart(document.getElementById('ledChart'), {
  type: 'line',
  data: {
    labels,
    datasets: [
      { label: 'Right LED', data: ${JSON.stringify(ledRight)}, borderColor: '#DC2626', backgroundColor: 'rgba(220,38,38,0.05)', fill: true, pointRadius: 1.5, pointBackgroundColor: '#DC2626', borderWidth: 2, tension: 0.3 },
      { label: 'Left LED',  data: ${JSON.stringify(ledLeft)}, borderColor: '#0072CE', backgroundColor: 'rgba(0,114,206,0.05)', fill: true, pointRadius: 1.5, pointBackgroundColor: '#0072CE', borderWidth: 2, tension: 0.3 },
      { label: 'Door LED',  data: ${JSON.stringify(ledDoor)}, borderColor: '#16A34A', backgroundColor: 'rgba(22,163,74,0.05)', fill: true, pointRadius: 1.5, pointBackgroundColor: '#16A34A', borderWidth: 2, tension: 0.3 },
      { label: 'Back LED',  data: ${JSON.stringify(ledBack)}, borderColor: '#D97706', backgroundColor: 'rgba(217,119,6,0.05)', fill: true, pointRadius: 1.5, pointBackgroundColor: '#D97706', borderWidth: 2, tension: 0.3 },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        ...stsTooltip,
        callbacks: { label: ctx => ctx.dataset.label + ' · ' + ctx.raw + ' °C' }
      }
    },
    scales: { x: stsScaleX, y: stsScaleY({ min: 0, step: 5, text: 'Temperature (°C)' }) }
  }
});
</script>
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cure-report-${log.materialName}-${new Date(log.startedAt).toISOString().slice(0, 10)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
