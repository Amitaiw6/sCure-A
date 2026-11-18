// Browser test of "View uniformity" (DVT-OPT-003):  node cloud/google/test_uvmap.cjs <readings.csv>
// Builds the page the way Code.gs serveUvMap_ does - UvMap.html (the UV Uniformity Jig's analysis/uv_map.html) with a
// unit's readings baked in - and checks that the jig's heatmap draws them in its 405 nm panel, as a real scan, without errors.
// The readings CSV is the jig's schema (x_idx,y_idx,z_idx,direction,reading); without an argument a small grid is made up.
const fs = require('fs');
const path = require('path');
const puppeteer = require(path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'));
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

let readings;
if (process.argv[2]) {
  const lines = fs.readFileSync(process.argv[2], 'utf8').split(/\r?\n/).filter(l => l.trim());
  const head = lines.shift().split(',').map(h => h.trim());
  const ix = n => head.indexOf(n);
  readings = lines.map(l => { const c = l.split(','); return [+c[ix('x_idx')], +c[ix('y_idx')], +c[ix('z_idx')], c[ix('direction')].trim(), +c[ix('reading')]]; })
    .filter(r => r.every((v, i) => i === 3 ? !!v : isFinite(v)));
} else {
  readings = [];
  for (let x = 1; x <= 3; x++) for (let y = 1; y <= 3; y++) for (let z = 1; z <= 10; z++)
    for (const d of ['FRONT', 'UP', 'BACK', 'DOWN', 'LEFT', 'RIGHT']) readings.push([x, y, z, d, 50 + x * 3 + y * 2 + z]);
}
const baked = JSON.stringify({ unit: 'UUT-04', date: '2026-11-14', name: 'uv_scan.xlsx', readings }).replace(/</g, '\\u003c');
const html = fs.readFileSync(path.join(__dirname, 'UvMap.html'), 'utf8').replace('__UV_BAKED__', baked);
const tmp = path.join(require('os').tmpdir(), 'uvmap_test.html');
fs.writeFileSync(tmp, html);

let checks = 0;
const check = (cond, msg) => { if (!cond) { console.error('FAIL: ' + msg); process.exit(1); } checks++; console.log('  ok  ' + msg); };

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' });
  const page = await browser.newPage();
  await page.setViewport({ width: 1300, height: 900 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto('file:///' + tmp.replace(/\\/g, '/'));
  await new Promise(r => setTimeout(r, 800));
  const st = await page.evaluate(() => ({
    title: document.title, h1: (document.querySelector('h1') || {}).textContent,
    bReal: S.B.real, bName: S.B.name, bN: Object.keys(S.B.data || {}).length, aReal: S.A.real,
    bannerB: (document.getElementById('banner-B') || {}).textContent || '', bannerA: (document.getElementById('banner-A') || {}).textContent || '',
    text: document.body.innerText, cubes: document.querySelectorAll('.cube').length,
    cmpCols: document.querySelectorAll('#cmp thead th').length, tableCols: (document.querySelector('#table tr') || { children: [] }).children.length }));
  check(errors.length === 0, 'the jig\'s heatmap page runs without script errors: ' + errors.join(' | '));
  check(st.title === 'UV uniformity - UUT-04 (405 nm)' && /UUT-04, 405 nm scan of 2026-11-14/.test(st.h1), 'the page names the unit and the scan date: ' + st.h1);
  check(st.bReal && st.bName === 'uv_scan.xlsx' && st.bN === new Set(readings.map(r => r.slice(0, 4).join('|'))).size, `the 405 nm panel holds the uploaded scan as a real one (${st.bN} readings)`);
  check(st.cubes === 1 && !/450 nm/.test(st.text) && !/synthetic/i.test(st.text), 'only the one 405 nm scan is shown - no second cube, no 450 nm, no synthetic data (user, 2026-11-15)');
  check(st.cmpCols === 5 && st.tableCols === 4, 'the uniformity table and the number table have one scan\'s columns: ' + st.cmpCols + ' / ' + st.tableCols);
  check(/uv_scan\.xlsx/.test(st.text), 'the file the readings came from is shown');
  await page.screenshot({ path: path.join(require('os').tmpdir(), 'uvmap_test.png') });
  // the other views of the page work with one scan as well: 2D layers, per face, a single face
  const views = await page.evaluate(() => { const out = [];
    for (const [v, d] of [['2d', 'MEAN'], ['3d', 'FACES'], ['3d', 'UP'], ['2d', 'LEFT']]) { view = v; selDir = d; renderAll(); out.push(document.getElementById(v === '2d' ? 'layers' : 'cubes').innerHTML.length); }
    return out; });
  check(errors.length === 0 && views.every(n => n > 500), '2D layers, per-face and single-face views all draw the one scan: ' + views.join(','));
  await browser.close();
  console.log(`\nALL PASSED (${checks} checks)`);
})().catch(e => { console.error(e); process.exit(1); });
