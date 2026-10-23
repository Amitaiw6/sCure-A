// The guided SAF-012 sequence goes on to the next step by itself only when the step that just finished passed
// its own part of the catalog criteria. This runs the page's decision (nextStepAfter, lifted out of dvt-tool.html)
// against the real catalog and the real evaluator, so the page can hold no threshold of its own.
const fs = require('fs'), vm = require('vm'), path = require('path');
const WEB = __dirname;
const html = fs.readFileSync(path.join(WEB, 'dvt-tool.html'), 'utf8').replace(/\r\n/g, '\n');   // the page is saved with CRLF
const src = (html.match(/\nfunction nextStepAfter\([\s\S]*?\n}\n/) || [])[0];
if (!src) { console.error('nextStepAfter not found in dvt-tool.html'); process.exit(2); }
const guided = (html.match(/\nconst GUIDED = \{[\s\S]*?\n\};\n/) || [])[0];
if (!guided) { console.error('GUIDED not found in dvt-tool.html'); process.exit(2); }
const sandbox = { window: {}, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-catalog.js'), 'utf8'), sandbox);    // SCURE_DVT: the catalog
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-criteria.js'), 'utf8'), sandbox);   // DVT_CRITERIA: the evaluator
vm.runInContext('const CAT = window.SCURE_DVT; const CRIT = window.DVT_CRITERIA;' + guided + src + '\nglobalThis.nextStepAfter = nextStepAfter;', sandbox);
const test = sandbox.window.SCURE_DVT.tests['DVT-SAF-012'];
const rec = { values: {} };
const out = {
  step1_pass: sandbox.nextStepAfter(test, rec, 'door_open_cure', { cure_start_inhibited: true, door_open_detected: true }),
  step1_fail: sandbox.nextStepAfter(test, rec, 'door_open_cure', { cure_start_inhibited: false }),
  step2_pass: sandbox.nextStepAfter(test, rec, 'uv_off_timing', { uv_off_time: 0.8, uv_zero_time: 1.2, residual_irradiance: 0.01 }),
  step2_slow: sandbox.nextStepAfter(test, rec, 'uv_off_timing', { uv_off_time: 1.5, uv_zero_time: 2.0, residual_irradiance: 0.01 }),
  step3_pass: sandbox.nextStepAfter(test, rec, 'door_lock_check', { lock_engaged: true }),
  step4_pass: sandbox.nextStepAfter(test, rec, 'door_magnet_defeat', { defeat_by_magnet_possible: false }),
  step4_fail: sandbox.nextStepAfter(test, rec, 'door_magnet_defeat', { defeat_by_magnet_possible: true }),
  step5_pass: sandbox.nextStepAfter(test, rec, 'door_status_check', { door_status_read_only_confirmed: true }),
  step6_last: sandbox.nextStepAfter(test, rec, 'door_alarm_check', { alarm_raised: true, error_code: '6016' }),
  criteria: test.pass_criteria,
};
process.stdout.write(JSON.stringify(out, null, 1));
