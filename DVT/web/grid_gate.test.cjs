// The 16-thermocouple gate of the chamber-grid tests (DVT-THM-001 / DVT-THM-007, user 2026-11-15: "it shouldn't let me run
// the test if it doesn't detect all 16 thermocouples"). Run by DVT/tests/test_dvt_web.py; prints a JSON verdict list.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const WEB = __dirname;
const sandbox = { window: {}, console, setTimeout, clearTimeout, document: { getElementById: () => null }, alert: () => {}, fetch: async () => ({ json: async () => ({}) }) };
vm.createContext(sandbox);
for (const f of ['dvt-catalog.js', 'dvt-criteria.js', 'dvt-auto.js']) vm.runInContext(fs.readFileSync(path.join(WEB, f), 'utf8'), sandbox);
const A = sandbox.window.DVT_AUTO;
const unit = (serial, chans) => ({ serial, channels: chans });
const eight = (v) => new Array(8).fill(v);
const cases = {
  // CureBox-3, 2026-11-15: one TC-08, not a grid logger, two channels
  one_logger: { connected: true, units: [unit('AO027/073', [54.8, 52.7, null, null, null, null, null, null])] },
  // both grid loggers, one thermocouple open
  one_open: { connected: true, units: [unit('AO027/073', eight(25)), unit('AO114/209', [25, 25, 25, null, 25, 25, 25, 25])] },
  all_16: { connected: true, units: [unit('AO027/073', eight(25)), unit('AO114/209', eight(26))] },
  nothing: null,
  // only 114: the Z1-Z2 logger is missing
  only_114: { connected: true, units: [unit('AO114/209', eight(26))] },
  three: { connected: true, units: [unit('AO027/073', eight(25)), unit('AO114/209', eight(26)), unit('AA0031/111', eight(24))] },
};
const out = { needsGrid: { 'DVT-THM-001': !!(A.SCRIPTS['DVT-THM-001'] || {}).needsGrid, 'DVT-THM-007': !!(A.SCRIPTS['DVT-THM-007'] || {}).needsGrid } };
for (const [k, p] of Object.entries(cases)) out[k] = A.gridMissing(p);
out.ambient = A.gridAmbient({ connected: true, units: [{ serial: 'AO027/073', coldJunction: 20.52, channels: eight(25) }, { serial: 'AO114/209', coldJunction: 20.54, channels: eight(26) }] });
process.stdout.write(JSON.stringify(out));
