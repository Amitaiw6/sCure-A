// An open thermocouple does not read null - it floats near the top of the driver's valid band.
// This proves the runner refuses such a run instead of recording 249 C as a body temperature.
const fs = require('fs'), vm = require('vm'), path = require('path');
const WEB = __dirname;
const sandbox = { window: {}, console, document: { getElementById: () => null }, alert: () => {},
                  setTimeout: (fn, ms) => setImmediate(fn), clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
                  performance: { now: () => Date.now() }, Date, AbortSignal: { timeout: () => undefined } };
const state = { chamberTemp: 22, uvOn: false, isHeating: false, alerts: [], sensors: {}, fanRpm: {}, ledTemps: {} };
let ch1 = 249.31;                                // a number, or a function for a reading that changes between polls
sandbox.fetch = async (url) => {
  const p = String(url).replace(/^https?:\/\/[^/]+/, '');
  const body = p.startsWith('/api/dev/picolog/status')
    ? { connected: true, ch1Available: true, temperature: typeof ch1 === 'function' ? ch1() : ch1, ambient: 21.7, deviceInfo: 'SIM', error: null }
    : p.startsWith('/api/state') ? state : { ok: true };
  return { ok: true, json: async () => body };
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-auto.js'), 'utf8'), sandbox);
const A = sandbox.window.DVT_AUTO;
A.attach({ base: () => 'http://sim:3001', lang: () => 'en', machine: () => 'sim' });
const ctx = new A._Ctx('DVT-SAF-009', { test_id: 'DVT-SAF-009', data_fields: [] }, { id: 'r', variant: {} }, { values: {} });
(async () => {
  const open = await A.P.tcCheck(ctx, state);
  ch1 = 24.1;
  const seated = await A.P.tcCheck(ctx, state);
  ch1 = 180.0;                                   // the same reading is fine once something is actually running
  const heating = await A.P.tcCheck(ctx, { ...state, isHeating: true });
  // a test whose heat comes from outside the machine (DVT-SAF-009): hot-and-steady is a real body, floating is an open input
  const ext = new A._Ctx('DVT-SAF-009', { test_id: 'DVT-SAF-009', external_heat: true, data_fields: [] }, { id: 'r', variant: {} }, { values: {} });
  ch1 = 182.0;
  const externalHot = await A.P.tcCheck(ext, state);
  let n = 0; ch1 = () => [105, 141, 180, 122][n++ % 4];
  const externalFloating = await A.P.tcCheck(ext, state);
  process.stdout.write(JSON.stringify({ open, seated, heating, externalHot, externalFloating }, null, 1));
})();
