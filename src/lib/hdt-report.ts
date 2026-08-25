import { exportReportToUsb } from '@/services/hardware-api'
import { LED_ZONES, LED_ZONE_LABELS, applyLedFactors } from '@/services/dev-api'
import type { HdtStatus, HdtSample } from '@/services/dev-api'
import type { ReportResult } from '@/lib/cure-report'

function fmtDur(sec: number | null | undefined): string {
  if (sec == null) return '— —'
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h > 0 ? `${h}h ${m}m ${s % 60}s` : `${m}m ${s % 60}s`
}

const STEP_LABEL: Record<string, string> = {
  PASS: 'PASS', RUNNING: 'RUNNING', NOT_CONVERGED: 'NOT CONVERGED',
  HDT_LIMIT: 'HDT LIMIT', ABORTED: 'ABORTED', NOT_TESTED: 'NOT TESTED',
}
const FINAL_LABEL: Record<string, string> = {
  COMPLETED: 'Completed', HDT_LIMIT_REACHED: 'HDT Limit Reached',
  ABORTED_BY_USER: 'Aborted by User', SENSOR_ERROR: 'Sensor Error',
  NOT_CONVERGED: 'Not Converged',
}

/**
 * Human-readable Material HDT Calibration report (HTML, Chart.js) —
 * same shell and export path as the cure report (src/lib/cure-report.ts):
 * USB first, browser download as the dev/off-machine fallback.
 * Works for partial runs too (abort / sensor error / HDT limit).
 */
export async function generateHdtReport(status: HdtStatus, samples: HdtSample[]): Promise<ReportResult> {
  const finalStatus = status.finalStatus ?? 'NOT_CONVERGED'
  const statusLabel = FINAL_LABEL[finalStatus] ?? finalStatus
  const good = finalStatus === 'COMPLETED'
  const warn = finalStatus === 'HDT_LIMIT_REACHED' || finalStatus === 'NOT_CONVERGED'
  const pillBg = good ? '#DCFCE7' : warn ? '#FEF3C7' : '#FEE2E2'
  const pillFg = good ? '#166534' : warn ? '#92400E' : '#991B1B'
  const pillBd = good ? '#86EFAC' : warn ? '#FCD34D' : '#FCA5A5'

  // Downsample for the chart (Chart.js chokes far later than recharts, but
  // an hour-long run at 1 Hz doesn't need every point in a report)
  const stride = Math.max(1, Math.ceil(samples.length / 2000))
  const pts = samples.filter((_, i) => i % stride === 0 || i === samples.length - 1)
  const labels = pts.map(s => {
    const m = Math.floor(s.t / 60)
    return `${m}:${String(Math.round(s.t % 60)).padStart(2, '0')}`
  })
  const transitions: { i: number; power: number }[] = []
  let lastStep = -2
  pts.forEach((s, i) => {
    if (s.step !== lastStep && s.step >= 0) transitions.push({ i, power: s.power })
    lastStep = s.step
  })

  const factors = status.factors
  const rec = status.recommendedPower
  const recOutputs = rec != null ? applyLedFactors(rec, factors) : null
  const hdt = status.hdtC ?? 0
  const margin = status.safetyMarginC
  const reportDate = new Date().toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>HDT Calibration Report · sCure</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root { color-scheme: light; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: #F4F7FA; }
  body { font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; color: #0A1929;
         padding: 32px 24px 48px; max-width: 1120px; margin: 0 auto;
         font-variant-numeric: tabular-nums; }
  .title-block { background: #fff; border: 1px solid #DDE4EB; border-left: 4px solid #003DA5;
                 border-radius: 10px; padding: 20px 24px; margin-bottom: 20px;
                 display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .title-block h1 { font-size: 22px; font-weight: 700; }
  .title-block .subline { font-size: 13px; color: #5A6B7A; margin-top: 4px; }
  .status-pill { display: inline-flex; align-items: center; background: ${pillBg}; color: ${pillFg};
                 border: 1px solid ${pillBd}; border-radius: 999px; padding: 6px 14px;
                 font-size: 12px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; }
  .grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 20px; }
  .card { background: #fff; border: 1px solid #DDE4EB; border-radius: 8px; padding: 14px 14px 12px; }
  .card .label { font-size: 10px; color: #5A6B7A; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .card .value { font-size: 20px; font-weight: 700; margin-top: 6px; }
  .card .value.ok { color: #16A34A; }
  .card .value.muted { color: #8A97A3; font-size: 14px; font-weight: 500; }
  .card .unit { font-size: 12px; color: #5A6B7A; font-weight: 500; margin-left: 2px; }
  .section { background: #fff; border: 1px solid #DDE4EB; border-radius: 10px;
             padding: 22px 24px; margin-bottom: 16px; }
  .section h2 { font-size: 15px; font-weight: 700; margin-bottom: 12px; }
  .chart-container { position: relative; height: 320px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; color: #5A6B7A; font-size: 10px; text-transform: uppercase;
       letter-spacing: 0.6px; padding: 6px 8px; border-bottom: 1px solid #DDE4EB; }
  td { padding: 7px 8px; border-bottom: 1px solid #E6ECF2; }
  .st-PASS { color: #16A34A; font-weight: 700; }
  .st-NOT_CONVERGED, .st-HDT_LIMIT { color: #D97706; font-weight: 700; }
  .st-ABORTED { color: #DC2626; font-weight: 700; }
  .st-NOT_TESTED, .st-RUNNING { color: #8A97A3; font-weight: 600; }
  .footer { margin-top: 28px; font-size: 11px; color: #5A6B7A;
            border-top: 1px solid #DDE4EB; padding-top: 14px; }
  @media print { body { background: #fff; padding: 16px; } }
</style>
</head>
<body>

<div class="title-block">
  <div>
    <h1>Material HDT Calibration Report</h1>
    <div class="subline">Calibrated system LED power sweep · PicoLog TC-08 · Channel CH1 · ${status.picolog.deviceInfo ?? 'PicoLog TC-08'}</div>
    <div class="subline">Started ${status.startedAt ?? '— —'} · Ended ${status.endedAt ?? '— —'} · Duration ${fmtDur(status.totalElapsedSec)}</div>
  </div>
  <span class="status-pill">${statusLabel}</span>
</div>

<div class="grid">
  <div class="card"><div class="label">Material HDT</div><div class="value">${hdt}<span class="unit">°C</span></div></div>
  <div class="card"><div class="label">Safety Margin</div><div class="value">${margin}<span class="unit">°C</span></div></div>
  <div class="card"><div class="label">Max Model Temp</div><div class="value">${hdt - margin}<span class="unit">°C</span></div></div>
  <div class="card"><div class="label">Max Measured</div><div class="value">${status.maxMeasuredTemp ?? '—'}<span class="unit">°C</span></div></div>
  <div class="card"><div class="label">Recommended Power</div><div class="value ${rec != null ? 'ok' : 'muted'}">${rec != null ? `${rec}%` : 'None'}</div></div>
  <div class="card"><div class="label">Levels Tested</div><div class="value">${status.results.filter(r => r.status !== 'NOT_TESTED').length}<span class="unit"> / ${status.results.length}</span></div></div>
</div>

<div class="section">
  <h2>LED calibration factors${recOutputs ? ` · physical outputs at ${rec}% system power` : ''}</h2>
  <table>
    <thead><tr><th>Zone</th>${LED_ZONES.map(z => `<th>${LED_ZONE_LABELS[z]}</th>`).join('')}</tr></thead>
    <tbody>
      <tr><td>Factor</td>${LED_ZONES.map(z => `<td>${factors[z].toFixed(2)}</td>`).join('')}</tr>
      ${recOutputs ? `<tr><td>Output @ ${rec}%</td>${LED_ZONES.map(z => `<td>${recOutputs[z].toFixed(1)}%</td>`).join('')}</tr>` : ''}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Model temperature vs time</h2>
  <div class="chart-container"><canvas id="tempChart"></canvas></div>
</div>

<div class="section">
  <h2>Results per calibrated system power level</h2>
  <table>
    <thead><tr>
      <th>System Power</th><th>Status</th><th>Start Temp</th><th>Stable Temp</th>
      <th>Min / Max</th><th>Time to Stability</th><th>Duration</th>
      <th>Back</th><th>Door</th><th>Left</th><th>Right</th>
    </tr></thead>
    <tbody>
      ${status.results.map(r => `<tr>
        <td><b>${r.power}%</b></td>
        <td class="st-${r.status}">${STEP_LABEL[r.status] ?? r.status}</td>
        <td>${r.startTemp != null ? `${r.startTemp.toFixed(1)}°C` : '—'}</td>
        <td>${r.stableTemp != null ? `${r.stableTemp.toFixed(1)}°C` : '—'}</td>
        <td>${r.minTemp != null && r.maxTemp != null ? `${r.minTemp.toFixed(1)} / ${r.maxTemp.toFixed(1)}°C` : '—'}</td>
        <td>${r.timeToStabilitySec != null ? fmtDur(r.timeToStabilitySec) : '—'}</td>
        <td>${r.durationSec != null ? fmtDur(r.durationSec) : '—'}</td>
        ${LED_ZONES.map(z => `<td>${r.outputs?.[z] != null ? `${r.outputs[z].toFixed(1)}%` : '—'}</td>`).join('')}
      </tr>`).join('')}
    </tbody>
  </table>
</div>

<div class="footer">
  sCure · Material HDT Calibration · Report generated ${reportDate} ·
  Stability: ±${status.config.stabilityBandC / 2}°C band (${status.config.stabilityBandC}°C total) for ${status.config.stabilityTimeMin} min ·
  Max stabilization ${status.config.maxStabilizationTimeMin} min · Sampling ${status.config.samplingIntervalSec}s / avg ${status.config.movingAverageWindowSec}s
</div>

<script>
const labels = ${JSON.stringify(labels)};
const transitions = ${JSON.stringify(transitions)};
new Chart(document.getElementById('tempChart'), {
  type: 'line',
  data: {
    labels,
    datasets: [
      { label: 'Raw CH1', data: ${JSON.stringify(pts.map(s => s.raw))}, borderColor: '#0072CE',
        borderWidth: 1, pointRadius: 0, tension: 0.2, spanGaps: true },
      { label: 'Average', data: ${JSON.stringify(pts.map(s => s.avg))}, borderColor: '#D97706',
        borderWidth: 2.5, pointRadius: 0, tension: 0.2, spanGaps: true },
      { label: 'Material HDT', data: labels.map(() => ${hdt}), borderColor: '#DC2626',
        borderWidth: 1.5, borderDash: [6, 4], pointRadius: 0 },
      { label: 'HDT − margin', data: labels.map(() => ${hdt - margin}), borderColor: '#EA580C',
        borderWidth: 1.5, borderDash: [3, 3], pointRadius: 0 },
      { label: 'System power %', data: ${JSON.stringify(pts.map(s => s.power))}, borderColor: '#8A97A3',
        borderWidth: 1, stepped: true, pointRadius: 0, yAxisID: 'y2' },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
      annotation: undefined,
    },
    scales: {
      x: { ticks: { maxTicksLimit: 25, font: { size: 10 } },
           title: { display: true, text: 'Time (min:sec)', font: { size: 11 } } },
      y: { title: { display: true, text: 'Temperature (°C)', font: { size: 11 } } },
      y2: { position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false },
            title: { display: true, text: 'System LED power (%)', font: { size: 11 } } },
    }
  }
});
</script>
</body>
</html>`

  const filename = `hdt-calibration-report-${new Date().toISOString().slice(0, 10)}.html`
  const usbRes = await exportReportToUsb(filename, html)
  if (usbRes.ok) return { ok: true, usb: true, message: usbRes.message || 'Saved to USB' }
  if (usbRes.code) {
    window.dispatchEvent(new CustomEvent('scure-alert', { detail: { code: usbRes.code } }))
    return { ok: false, usb: true, message: usbRes.message }
  }
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
  return { ok: true, usb: false, message: 'Downloaded in browser' }
}
