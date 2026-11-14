// Records what every script in dvt-auto.js asks the operator (on the simulated machine of dvt-auto.test.cjs) and writes it
// into dvt-auto.js as SIM_PROMPTS, so the portal's "Simulate" plays the same questions as a real run.
//
//     node DVT/web/build_sim_prompts.cjs            # rewrite the line
//     node DVT/web/build_sim_prompts.cjs --check    # exit 1 when it is stale
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const file = path.join(__dirname, 'dvt-auto.js');
const out = execFileSync(process.execPath, [path.join(__dirname, 'dvt-auto.test.cjs')], { env: { ...process.env, SCURE_SIM_PROMPTS: '1' }, maxBuffer: 1 << 28 }).toString();
const runs = JSON.parse(out.slice(out.indexOf('[')));
const prompts = {};
for (const r of runs) if (r.asked && r.asked.length) prompts[r.test] = r.asked;
const line = `  const SIM_PROMPTS = ${JSON.stringify(prompts)};   // @sim-prompts`;
const src = fs.readFileSync(file, 'utf8');
const crlf = src.includes('\r\n');
const next = src.replace(/^  const SIM_PROMPTS = .*\/\/ @sim-prompts\r?$/m, line + (crlf ? '\r' : ''));
if (process.argv.includes('--check')) { if (next !== src) { console.error('dvt-auto.js SIM_PROMPTS is stale - run: node DVT/web/build_sim_prompts.cjs'); process.exit(1); } process.exit(0); }
fs.writeFileSync(file, next);
console.log(`SIM_PROMPTS written for ${Object.keys(prompts).length} tests`);
