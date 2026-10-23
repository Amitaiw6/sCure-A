// DVT guide-window simulation (Page.html): for each pass criteria, the made-up "passing" readings must PASS
// and some single broken reading must FAIL. Run: node cloud/google/test_sim.cjs
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, 'Page.html'), 'utf8');
const a = html.indexOf('function critParse'), b = html.indexOf('async function dvtSimulate');
if (a < 0 || b < 0) { console.error('simulation code not found in Page.html'); process.exit(1); }
const { critParse, critEval, critLeaves, critReadings } =
  new Function(html.slice(a, b) + '; return {critParse, critEval, critLeaves, critReadings};')();

const CRITERIA = [   // the shapes found in the DVT catalog
  'max_resistance <= 0.1 AND pe_uninterrupted == true',
  "heater_state == 'off' AND uv_state == 'off' AND response_time <= 2 AND auto_resume == false",
  'cutout_trip_temp <= rated_trip_temp * 1.1 AND time_to_trip > 0 AND graph_attached == true',
  'alarm_raised == true AND (message_names_specific_fan == false OR claim_is_correct == true) AND peak_temp_after_shutdown < led_temperature_thresholds.protective_shutdown + post_shutdown_overshoot',
  'codes_unique AND codes_registered AND messages_name_component AND all_logged',
  'max(max_temp_right, max_temp_left, max_temp_back, max_temp_door) <= led_temperature_thresholds.working_limit AND final_dtdt <= 0.2 AND tj_margin >= 15',
  'uniformity_pp <= 5 AND abs(steady_state_error) <= 1 AND settling_time <= 45',
  "which_fuse_opened == 'heater_branch_5A' AND NOT manual_abort_used AND heater_off_time <= heater_thresholds.selector_mismatch_fuse_open_max",
];
let fails = 0;
const check = (ok, msg) => { if (!ok) { fails++; console.log('FAIL:', msg); } };
for (const c of CRITERIA) {
  const tree = critParse(c), leaves = critLeaves(tree);
  check(critEval(tree, critReadings(leaves, -1)) === true, 'passing readings do not pass: ' + c);
  check(leaves.some((_, k) => critEval(tree, critReadings(leaves, k)) === false), 'no single reading fails: ' + c);
}
for (const bad of ['x <= ', 'a AND AND b', 'x <= 1 ; drop', 'f(1']) {
  let threw = false; try { critParse(bad); } catch { threw = true; }
  check(threw, 'bad criteria accepted: ' + bad);
}
console.log(fails ? `${fails} simulation check(s) failed` : `simulation: all ${CRITERIA.length} criteria + 4 bad inputs checked`);
process.exit(fails ? 1 : 0);
