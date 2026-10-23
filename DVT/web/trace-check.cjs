// Feeds a synthetic TC-08 recording through DVT_AUTO.fromTrace and prints what it read.
// Driven by DVT/tests/test_dvt_web.py.
const fs = require('fs'), vm = require('vm'), path = require('path');
const WEB = __dirname;
const CATALOG = JSON.parse(fs.readFileSync(path.join(WEB, 'dvt-catalog.js'), 'utf8')
  .replace(/^[\s\S]*?window\.SCURE_DVT = /, '').replace(/;\s*$/, ''));

const sandbox = { window: {}, console, document: { getElementById: () => null }, alert: () => {},
                  setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
                  performance: { now: () => 0 }, Date, AbortSignal: { timeout: () => undefined }, fetch: async () => ({}) };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-catalog.js'), 'utf8'), sandbox);    // SCURE_DVT: the thresholds
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-criteria.js'), 'utf8'), sandbox);   // DVT_CRITERIA: the page's evaluator
vm.runInContext(fs.readFileSync(path.join(WEB, 'dvt-auto.js'), 'utf8'), sandbox);
const A = sandbox.window.DVT_AUTO;
A.attach({ lang: () => 'en' });

// A cutout run as the TC-08 sees it: the body climbs from 24 C, the cutout opens at 128 C,
// the body falls, the chamber peaks a little after the trip and then cools, and the machine
// raises an alarm 30 s after the trip. Row: [t, ch1, chamber, machine_heating, alerts]
const rows = [];
let ch1 = 24, chamber = 22;
const CUT_AT = 35;                                                            // the machine drops its own drive once the chamber passes this, while the external heat carries on
const row = (t, ch1, ch, alerts) => [t, +ch1.toFixed(2), +ch.toFixed(2), ch < CUT_AT, alerts, ch < CUT_AT, ch < CUT_AT ? 100 : 0];
for (let t = 0; t <= 300; t += 1) {                                           // five quiet minutes first - but the body is
  const cooling = t <= 60 ? 80 - (80 - 24) * (t / 60) : 24;                     // still cooling from an earlier attempt for the
  rows.push(row(t, cooling, 22, ''));                                          // first minute: a dip the analyser must not
}                                                                              // mistake for the trip (it did, on the unit)
for (let t = 301; ch1 < 128; t += 1) { ch1 += 0.35; chamber += 0.06; rows.push(row(t, ch1, chamber, '')); }
const tripAt = rows[rows.length - 1][0];
const AMBIENT = 22;
for (let i = 1; i <= 600; i++) {                                              // ten minutes after the trip
  ch1 += (AMBIENT - ch1) * 0.004;                                             // the body cools towards ambient, never past it
  chamber += i <= 120 ? 0.05 : (AMBIENT - chamber) * 0.003;                   // the chamber peaks 2 min after the trip
  rows.push(row(tripAt + i, ch1, chamber, i >= 30 ? '9002' : ''));
}
const resetAt = ch1;
for (let i = 601; i <= 900; i++) { ch1 += 0.2; chamber += 0.01; rows.push(row(tripAt + i, ch1, chamber, '9002')); }  // cutout closes, the bridged heater is back on
process.env.SCURE_EXPECT_RESET = resetAt.toFixed(2);

const test = CATALOG.tests['DVT-SAF-013'];
const rec = { values: {}, autos: { tc08_record: { kind: 'tc08_record', samples: rows } } };
// does the recording know when it is complete? before the trip: no; 5 min after it: no; once the body climbs again: yes;
// and 20 minutes after a trip with no reset: yes
const at = (sec) => ({ values: {}, autos: { tc08_record: { kind: 'tc08_record', samples: rows.filter((r) => r[0] <= sec) } } });
const flat = rows.filter((r) => r[0] <= tripAt + 1250).map((r) => (r[0] > tripAt + 600 ? [r[0], 40, r[2], r[3], r[4], r[5], r[6]] : r));
const autoStop = {
  before_trip: A.autoStop(test, at(tripAt - 10)).stop,
  just_after_trip: A.autoStop(test, at(tripAt + 60)).stop,
  after_reset: A.autoStop(test, at(tripAt + 700)),
  twenty_min_no_reset: A.autoStop(test, { values: {}, autos: { tc08_record: { kind: 'tc08_record', samples: flat } } }).stop,
};
// shaped like the unit's 2nd run: recording started with the body already hot (255 C), a small climb to 262.6,
// the trip, a fall to ~200, then climbing again - the trip must be found and the recording must stop
const hot = [];
for (let t = 0; t <= 120; t++) hot.push([t, 255 + 7.6 * t / 120, 70, false, '', false, null]);
for (let t = 121; t <= 225; t++) hot.push([t, 262.6 - 62 * (t - 120) / 105, 70, false, '', false, null]);
for (let t = 226; t <= 260; t++) hot.push([t, 200.6 + 0.2 * (t - 225), 70, false, '', false, null]);
const hotRec = { values: {}, autos: { tc08_record: { kind: 'tc08_record', samples: hot } } };
const hotStop = A.autoStop(test, hotRec);
const hotRead = A.fromTrace(test, { values: {}, autos: { tc08_record: { kind: 'tc08_record', samples: hot } } });
const read = A.fromTrace(test, rec);
// the rating is the operator's one input, typed in step 1 before the run - the verdict needs it, the trace never supplies it
const completed = A.completed(test, { ...rec, values: { ...rec.values, rated_trip_temp: 125 } });      // 128.3 <= 137.5: PASS
const completedFailing = A.completed(test, { ...rec, values: { ...rec.values, rated_trip_temp: 100 } });  // 128.3 > 110: FAIL
const completedWithoutRating = A.completed(test, rec);
process.stdout.write(JSON.stringify({ trip_at_s: tripAt, filled: read.filled, message: read.message, values: rec.values,
                                      autoFields: rec.autoFields, protection: rec.protection, marks: rec.marks, autoStop, completed, completedFailing, completedWithoutRating, hotStop, hotRead }, null, 1));
