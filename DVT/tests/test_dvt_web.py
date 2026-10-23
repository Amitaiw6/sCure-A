"""DVT web page (DVT/web): its catalog data is current and its criteria evaluator
gives the console's verdicts (dvt_tool.criteria) on every test in the catalog."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dvt_tool.catalog import Catalog
from dvt_tool.criteria import evaluate

DVT = Path(__file__).resolve().parents[1]
WEB = DVT / "web"
CAT = Catalog.load(DVT / "catalog" / "DVT_test_catalog.yaml")

NODE_DRIVER = r"""
const fs = require('fs');
const sandbox = {};
require('vm').runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const crit = sandbox.DVT_CRITERIA;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cases.map((c) => crit.evaluate(c.expr, c.values, c.thresholds))));
"""


def js_evaluate(cases):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, "-e", NODE_DRIVER, str(WEB / "dvt-criteria.js")], input=json.dumps(cases),
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def filled(test, pick):
    vals = {}
    for f in test.get("data_fields") or []:
        typ = f["type"]
        vals[f["name"]] = pick(typ, f)
    return vals


def test_catalog_js_is_current():
    r = subprocess.run([sys.executable, str(WEB / "build_dvt_web.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_js_and_python_verdicts_agree_on_every_test():
    fills = [
        lambda typ, f: None,
        lambda typ, f: {"bool": True, "float": 0.0, "int": 0, "string": "x"}.get(typ, (f.get("values") or [None])[0]),
        lambda typ, f: {"bool": False, "float": 100.0, "int": 100, "string": "y"}.get(typ, (f.get("values") or [None])[-1]),
        lambda typ, f: {"bool": True, "float": 1.5, "int": 1, "string": "intact"}.get(typ, (f.get("values") or [None])[0]),
    ]
    cases, expected = [], []
    for tid, test in CAT.tests.items():
        for pick in fills:
            values = {k: v for k, v in filled(test, pick).items() if v is not None}
            cases.append({"expr": test["pass_criteria"], "values": values, "thresholds": CAT.thresholds})
            expected.append((tid, *evaluate(test["pass_criteria"], values, CAT.thresholds)))
    got = js_evaluate(cases)
    mismatches = [(tid, v, d, g) for (tid, v, d), g in zip(expected, got) if (v, d) != (g["verdict"], g["detail"])]
    assert not mismatches, mismatches[:5]


@pytest.mark.parametrize("expr,values,verdict", [
    ("heater_off_time <= 2 AND alarm_raised == true", {"heater_off_time": 1.4, "alarm_raised": True}, "PASS"),
    ("heater_off_time <= 2 AND alarm_raised == true", {"heater_off_time": 2.6, "alarm_raised": True}, "FAIL"),
    ("abs(a - b) <= 10", {"a": 131, "b": 125}, "PASS"),
    ("max(l, r) <= led_temperature_thresholds.working_limit", {"l": 70, "r": 76}, "FAIL"),
    ("peak < led_temperature_thresholds.protective_shutdown + 2", {"peak": 60}, "BLOCKED"),
    ("ok == true AND (tag_read == false OR read == expected)", {"ok": True, "tag_read": True, "read": "BH1", "expected": "BH1"}, "PASS"),
    ("codes_unique AND NOT all_logged", {"codes_unique": True, "all_logged": False}, "PASS"),
    ("state == 'off'", {"state": "off"}, "PASS"),
    ("state == 'off'", {"state": False}, "FAIL"),
])
def test_known_expressions(expr, values, verdict):
    py = evaluate(expr, values, CAT.thresholds)[0]
    js = js_evaluate([{"expr": expr, "values": values, "thresholds": CAT.thresholds}])[0]["verdict"]
    assert py == verdict and js == verdict


# ---------------------------------------------------------------------------
# The automatic runner (DVT/web/dvt-auto.js): every script runs to the end
# against a simulated machine on a virtual clock, with the prompts answered.
# ---------------------------------------------------------------------------

AUTO_HARNESS = WEB / "dvt-auto.test.cjs"
# Automated by their own cards in dvt-tool.html rather than by dvt-auto.js: the two UV linearity
# rows by the page itself, SAF-004 by the machine-side DVT bench (catalog tool: bench).
# (SAF-012 has both: its six cards in the page, and since 0.9.101 one script that runs them in a row from sCure Cloud.)
NOT_IN_AUTO = {"DVT-OPT-001", "DVT-OPT-002", "DVT-SAF-004", "DVT-SAF-013"}   # SAF-013: the tc08_record card + fromTrace


@pytest.fixture(scope="module")
def auto_results():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(AUTO_HARNESS)], capture_output=True, text=True, encoding="utf-8", timeout=900)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return {x["test"]: x for x in json.loads(r.stdout)}


def test_every_test_that_can_be_automated_has_a_script(auto_results):
    want = {tid for tid in CAT.tests} - NOT_IN_AUTO
    assert want - set(auto_results) == set(), f"no automatic script for {sorted(want - set(auto_results))}"
    assert set(auto_results) & NOT_IN_AUTO == set(), "those are driven by their own cards"


def test_every_script_runs_to_the_end(auto_results):
    bad = {t: x.get("error") for t, x in auto_results.items() if x.get("status") != "OK"}
    assert not bad, bad


def test_no_script_leaves_the_machine_running(auto_results):
    assert [t for t, x in auto_results.items() if x.get("left_on")] == []


def test_scripts_measure_rather_than_ask(auto_results):
    # Every test whose values the machine can supply must fill some of them without asking.
    # The bench-only rows (a hipot set, a shipment) have nothing the API can measure.
    bench_only = {"DVT-SAF-002", "DVT-ELE-001", "DVT-ELE-002", "DVT-ELE-003", "DVT-ELE-004", "DVT-SAF-016"}
    thin = {t: x["measured"] for t, x in auto_results.items() if t not in bench_only and x["measured"] < 1}
    assert not thin, thin


def test_measured_traces_are_stored_per_step(auto_results):
    # A test that logs the machine continuously keeps each trace as its own rec.autos entry, so no
    # step overwrites another's samples and each gets its own CSV (dvt-tool.html setAuto / syncNow).
    # The event-driven tests (a valve opening, a tag appearing) have no continuous trace to keep.
    logging_tests = ["DVT-SAF-003", "DVT-SAF-005", "DVT-THM-001", "DVT-THM-003",
                     "DVT-THM-005", "DVT-SAF-019"]
    thin = {t: auto_results[t].get("traces") for t in logging_tests if not auto_results[t].get("traces")}
    assert not thin, thin
    multi = [t for t in logging_tests if auto_results[t]["traces"] >= 2]
    assert multi, "no test kept more than one trace - they are overwriting each other"


def test_ambient_comes_from_the_instrument_not_the_operator(auto_results):
    # The TC-08 measures the ambient it sits in on its cold junction, so no script may ask for it
    # while a probe is on the machine (dvt-auto.js P.ambient). The bench rows have no machine at all.
    import re
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    asked = re.findall(r"c\.value\('ambient_temp'", src)
    assert len(asked) <= 1, f"{len(asked)} scripts still ask the operator for ambient_temp"
    assert "P.ambient(c, s0)" in src
    # and the simulated TC-08 ambient (21.7 C) is what those runs recorded
    assert auto_results["DVT-THM-003"]["status"] == "OK"


def test_saf013_values_are_read_out_of_the_tc08_recording():
    # SAF-013 is operator-driven (the machine has no no-setpoint heat command), so the TC-08 log is the
    # only record of the run. DVT_AUTO.fromTrace must read the three numbers the test exists for out of
    # it - the rise-to-fall turn of CH1, the climb before it, the body climbing again when the cutout
    # closes - and mark the graph. Since the 2026-09-27 trim those are the ONLY fields the catalog has,
    # so everything else the analyser knows how to derive is dropped on the floor by put(), not stored.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(WEB / "trace-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    v = out["values"]
    assert set(out["filled"]) == {"cutout_trip_temp", "time_to_trip", "reset_temp", "graph_attached"}
    assert set(out["filled"]) == set(out["autoFields"]), "every value read must lock against typing"
    assert v["cutout_trip_temp"] == pytest.approx(128.3, abs=0.2)     # the peak the synthetic body reached
    assert v["time_to_trip"] == pytest.approx(4.97, abs=0.05)         # 300 s of quiet, then the rise, then the turn
    assert v["reset_temp"] == pytest.approx(31.6, abs=0.5)            # the low the body reached before climbing again
    assert v["graph_attached"] is True
    assert "rated_trip_temp" not in v, "the rating is the operator's one input, never derived"
    # the marks the page draws the graph from
    assert out["marks"]["trip_s"] == out["trip_at_s"] and out["marks"]["onset_s"] == 300 and out["marks"]["reset_s"] > out["trip_at_s"]
    # the machine's own protection is still read from the same recording, for the record
    prot = out["protection"]
    assert prot["commanded"] is True and prot["cutOff"] is True and prot["keptRising"] is True
    assert "CUT-OFF at 128.3 C after 4.97 min of heating, closed again at 31.6 C" in out["message"]



def test_external_heat_makes_the_open_probe_rule_a_warning_only_where_the_heat_is_external():
    # DVT-SAF-013 feeds the heater from an external supply: the machine never reports heating while the
    # body is genuinely hot, so the cold-junction rule refused a correct run (182 C, Start disabled, no fan).
    # The catalog says so, the page turns the rule into a steady-reading warning + confirm there, runs the
    # heater fan from the readiness check, and draws the graph live. Every other test keeps the hard stop.
    assert CAT.tests["DVT-SAF-013"].get("external_heat") is True
    assert all(not t.get("external_heat") for tid, t in CAT.tests.items() if tid != "DVT-SAF-013")
    js = (WEB / "dvt-catalog.js").read_text(encoding="utf-8")
    assert '"external_heat": true' in js
    html = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    for needle in ("external_heat", "tcOpenExt", "tcConfirmExt", "TC_JITTER_OPEN_C", "ensureHeaterFan", "drawTc08(r.tid)"):
        assert needle in html, needle
    assert html.count("tcConfirmExt:") == 2        # both languages


def test_every_script_trace_gets_a_chart_and_a_png_beside_its_csv():
    # "add a graph - a picture of the graph" (SAF-005): every rec.autos['auto_<name>'] trace with the runner's
    # watch() columns is drawn under the automatic step (displayed / CH2 reference / CH1 heater body against
    # minutes, heater and UV bands, the first alarm marked with its code) and syncNow writes a PNG next to the CSV.
    html = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    for needle in ("function drawTrace(canvas, a)", "function renderTraceCharts(test, run)", "async function tracePng(a)",
                   "DVT_AUTO.card(test, run, locked) + renderTraceCharts(test, run)", "'tc08_ch2_c'", "'tc08_ch1_c'", "ix('alerts')"):
        assert needle in html, needle
    assert html.count("drawTc08(tid); drawTraces(tid);") == 2          # both redraw sites
    sync = html[html.index("async function syncNow()"):html.index("function persist(")]
    assert "isTrace(a) && !a.graph_file" in sync and "tracePng(a)" in sync and ".png" in sync
    assert html.count("trRef:") == 2 and html.count("trBody:") == 2
    # A SAF-004 run refused in prepare (heater thermistor left open from the previous attempt) looked like a
    # half-recorded run: the bench's English error on the status line, and a timestamp + raw_log_attached
    # from a run four days earlier still on the card. Now the readiness rows show the reason before Start,
    # a refusal reads "did not start: ..." in the operator's language, and a new run clears the old fields.
    html = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    assert "async function checkBench(tid)" in html
    for needle in ("st.sensors.chamber.ok === true", "benchChamberOpen", "benchNotStarted", "benchReason("):
        assert needle in html, needle
    run = html[html.index("async function runBench(tid)"):html.index("function drawBench(")]
    assert "if (!(await checkBench(tid))) return;" in run
    assert "(rec.autoFields || []).forEach((f) => { delete rec.values[f]; });" in run and "delete rec.marks;" in run
    assert "neverHeated" in run and "t('benchNotStarted')(benchReason(" in run
    # a run that failed AFTER measuring (the thermistor not seen back within 180 s) keeps its nine values
    assert "const measured = st.status === 'OK' || !!(st.marks && st.marks.disconnect);" in run
    assert "t('benchFailedAt')(failedPhase" in run and html.count("benchFailedAt:") == 2
    for key in ("benchChamberOpen:", "benchNotStarted:", "benchHotBody:", "benchSvc:"):
        assert html.count(key) == 2, key           # both languages


def test_a_guided_step_that_passed_goes_on_to_the_next_step_by_itself():
    # "If you passed everything successfully and under 2 seconds, you can move to the next step": the page
    # decides from the catalog criteria alone (the clauses the finished step's fields appear in), so the
    # number is the catalog's - uv_off_time <= 1 today - and a change of threshold is a catalog change only.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(WEB / "guided-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["step1_pass"]["next"] == "uv_off_timing"
    assert out["step1_fail"]["next"] is None and "cure_start_inhibited" in out["step1_fail"]["why"]
    assert out["step2_pass"]["next"] == "door_lock_check" and out["step2_pass"]["checked"] == ["uv_off_time <= 1"]
    assert out["step2_slow"]["next"] is None and "uv_off_time" in out["step2_slow"]["why"]   # the catalog's limit, not the page's
    assert out["step3_pass"]["next"] == "door_magnet_defeat"
    assert out["step4_pass"]["next"] == "door_status_check"
    assert out["step4_fail"]["next"] is None and "defeat_by_magnet_possible" in out["step4_fail"]["why"]
    assert out["step5_pass"]["next"] == "door_alarm_check"
    assert out["step6_last"]["next"] is None and out["step6_last"]["why"] == "last step"
    html = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    assert "await autoAdvance(tid, tool, advanceValues)" in html and "autoAdvance(tid, 'door_open_cure', v)" in html
    assert html.count("gCloseToContinue:") == 2


def test_a_transient_folder_write_failure_does_not_stop_the_recording_reaching_the_folder():
    # A 734-sample SAF-013 run never reached the results folder: one failed write (a CSV open in Excel,
    # OneDrive holding the file) set the folder "lost", every later persist() queued silently and nothing
    # retried. Only a lost permission may take the folder away; anything else is retried with backoff,
    # a periodic sweep flushes what is queued, and stopping a recording that is not on disk says so out loud.
    html = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    sync = html[html.index("async function syncNow()"):html.index("function persist(")]
    assert "isPermissionLoss(e)" in sync and "RETRY_DELAYS_MS" in sync
    assert "FOLDER.ok = false" in sync.split("} catch (e) {")[-1]        # only the permission branch takes the folder away
    assert "FOLDER.ok = false" not in sync.split("} catch (e) {")[0]
    assert "setInterval(() => { if (FOLDER.ok && dirty.size" in html
    stop = html[html.index("function stopTc08("):html.index("setInterval(() => {                      // keep the readiness")]
    assert "tcNotSaved" in stop and "DVT_AUTO.completed" in stop
    assert "DVT_AUTO.autoStop" in html[html.index("async function tcTick()"):html.index("function stopTc08(")]
    assert html.count("tcNotSaved:") == 2 and html.count("folderRetry:") == 2


def test_the_heater_fan_tach_is_read_where_the_machine_puts_it():
    # The machine keys fanRpm by role and fanRpmEach by fan name; fanRpm[FAN_HEATER] is null on the
    # unit while the fan spins, which made every DVT-SAF-013 start say "the heater fan is not turning".
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    assert "rpm(s, fan) {" in src
    prepare = src[src.index("A.prepare = async function"):src.index("A.finish = async function")]
    assert "P.rpm(" in prepare and "fanRpm ||" not in prepare


def test_an_open_thermocouple_is_refused_not_recorded():
    # An open or badly seated thermocouple does not read null: it floats near the top of the driver's
    # valid band. A unit sitting at room temperature was seen reading 249.31 C, which is inside
    # -25..250 and would otherwise have been taken for a real near-cutout body temperature.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(WEB / "tc-guard-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["open"]["ok"] is False and "not hot" in out["open"]["why"]
    assert out["seated"]["ok"] is True          # a probe at ambient with nothing running is fine
    assert out["heating"]["ok"] is True         # and the same hot reading is fine once something IS running
    # on a test whose heat comes from outside the machine (external_heat) the level cannot decide:
    # a steady 182 C with the machine idle is the heater body, a reading that floats is an open input
    assert out["externalHot"]["ok"] is True and out["externalHot"]["external"] is True
    assert out["externalFloating"]["ok"] is False and "floating" in out["externalFloating"]["why"]


def test_recorded_runs_are_published_to_the_cloud_without_losing_one():
    # The results folder is the record; the sCure Cloud portal is the copy everyone else sees (its DVT tab).
    # A recorded run goes up as one "dvt_run" with its values, its raw sweep follows as a "dvt_file",
    # and a portal that refuses keeps the run queued instead of dropping it.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(WEB / "cloud-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout


def test_a_test_requested_from_the_site_runs_only_after_start_at_the_machine():
    # The DVT runner on the CureBox (DVT/runner) takes the site's requests, asks for Start on the machine's screen, and
    # only then runs the same dvt-auto.js script; Decline / expiry / a cancel stop it, a busy machine or a manual test is
    # refused, and a prompt reaches the site with its answer coming back (user, 2026-10-12).
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(DVT / "runner" / "runner.test.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout
    src = (DVT / "runner" / "dvt-runner.cjs").read_text(encoding="utf-8")
    # the order that matters: the confirmation is asked before the engine is ever started
    handle = src[src.index("async function handle(req)"):src.index("async function hello()")]
    assert handle.index("confirmAtMachine(req, test)") < handle.index("A.start(tid)")
    assert "if (!ok.start)" in handle


def test_the_cloud_upload_matches_what_the_portal_stores():
    # The page and Code.gs must name the same fields: a rename on one side silently empties the DVT tab.
    page = (WEB / "dvt-tool.html").read_text(encoding="utf-8")
    code = (DVT.parent / "cloud" / "google" / "Code.gs").read_text(encoding="utf-8")
    for field in ("unit", "testId", "variant", "rep", "runId", "verdict", "operator", "startedAt", "note", "machine", "values"):
        assert f"{field}:" in page, f"the page stopped sending {field}"
        assert f"d.{field}" in code or f"'{field}'" in code, f"Code.gs stopped reading {field}"
    assert "fileKind" in page and "d.fileKind" in code      # the file's own kind, separate from the routing kind
    assert "contentBase64" in page and "d.contentBase64" in code
    assert "dvt_machines" in page and "dvt_machines" in code   # the CureBox list the unit is assigned from


def test_the_tool_version_shown_in_the_page_matches_the_repo():
    # The page is opened straight off disk, so a cached dvt-auto.js is the commonest reason a fix
    # looks like it did not land. The number the page shows is what makes that visible - it is
    # worthless if it drifts from VERSION.
    import re
    version = (DVT.parent / "VERSION").read_text(encoding="utf-8").strip()
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    m = re.search(r"const VERSION = '([^']+)'", src)
    assert m, "dvt-auto.js no longer declares a VERSION"
    assert m.group(1) == version, f"dvt-auto.js says {m.group(1)}, VERSION says {version}"
    assert "DVT_AUTO.version" in (WEB / "dvt-tool.html").read_text(encoding="utf-8")


def test_fan_tach_is_read_the_way_the_machine_reports_it(auto_results):
    # The machine keys fanRpm by ROLE and fanRpmEach by fan (seen on the unit: fanRpm.chamber_heating 3612,
    # fanRpmEach.FAN_HEATER 3612). Reading fanRpm.FAN_x is null there while the fan spins - the simulator now
    # reports both dictionaries exactly as the unit does, so a wrong read shows up here as a missing value.
    import re
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    assert not re.search(r"fanRpm \|\| \{\}\)\[", src), "a script still reads fanRpm[<fan name>] directly - use P.rpm"
    assert auto_results["DVT-THM-005"]["status"] == "OK" and auto_results["DVT-SAF-019"]["status"] == "OK"
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-THM-005", "DVT-SAF-019"],
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    got = {x["test"]: x for x in json.loads(r.stdout)}
    assert got["DVT-THM-005"]["measured"] >= 17, "tach_rpm is no longer measured on THM-005"
    assert got["DVT-SAF-019"]["measured"] >= 19, "baseline_tach / tach_reading are no longer measured on SAF-019"


def test_saf013_recording_ends_by_itself_and_records_its_own_verdict():
    # The operator drives the heater and walks away. autoStop watches the stored samples: not before the trip,
    # not in the ten minutes after it, yes once the body climbs again (the cutout closed) or 20 min after a trip
    # with no reset. completed then reads the run through the page's own evaluator: the sentence the operator
    # sees says PASSED or FAILED exactly as the recorded verdict does, and without the rating it says what is missing.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    r = subprocess.run([node, str(WEB / "trace-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    a = out["autoStop"]
    assert a["before_trip"] is False and a["just_after_trip"] is False
    assert a["after_reset"]["stop"] is True and "climbing again" in a["after_reset"]["why"]
    assert a["twenty_min_no_reset"] is True
    c = out["completed"]
    assert c["ok"] is True and c["verdict"] == "PASS" and "PASSED" in c["message"] and "CUT-OFF at 128.3" in c["message"]
    f = out["completedFailing"]
    assert f["ok"] is True and f["verdict"] == "FAIL" and "FAILED" in f["message"]
    w = out["completedWithoutRating"]
    assert w["ok"] is False and "rated_trip_temp" in w["message"]


def test_saf013_finds_the_trip_when_the_recording_starts_hot():
    # The unit's second run began with the body already at 255 C: a small climb, the trip at 262.6, a fall to 200,
    # a second climb. A "rise of 20 C before the peak" rule missed that trip and the recording never stopped. A trip
    # is recognised by SOME climb before it and a big drop after it, so a hot start is found and a cooling tail is not.
    r = subprocess.run([shutil.which("node"), str(WEB / "trace-check.cjs")], capture_output=True, text=True, encoding="utf-8", timeout=120)
    out = json.loads(r.stdout)
    assert out["hotStop"]["stop"] is True
    assert "262.6" in out["hotRead"]["message"] and "200.6" in out["hotRead"]["message"]
    assert out["values"]["cutout_trip_temp"] == pytest.approx(128.3, abs=0.2)   # the cold-start run with its cooling tail still reads right


def test_saf007_walks_all_four_thermistors_in_one_run():
    # One run, four sensors in turn (user, 2026-10-01): each disconnected alone, each refused, each with its own alarm
    # naming that sensor. The simulator removes exactly the sensor the prompt names, as the unit's ledTemps does.
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-007"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    v = x["valuesSeen"]
    assert x["status"] == "OK", x["error"]
    assert v["positions_tested"] == "right, left, back, door"
    assert v["cure_start_inhibited"] is True and v["alarm_raised"] is True and v["alarm_identifies_sensor"] is True
    for pos in ("right", "left", "back", "door"):
        assert v["error_" + pos].startswith("9004 - ") and pos in v["error_" + pos]      # each side its own code and text
    assert isinstance(v["led_off_time"], (int, float))
    for pos in ("right", "left", "back", "door"):
        rec = x["tracesSeen"]["sensor_" + pos]
        assert rec["seen_missing"] is True and rec["others_ok"] is True and pos in rec["text"]



def test_saf008_walks_all_four_led_fans_in_one_guided_run():
    # One guided run, four LED fans in turn (user, 2026-10-01): "disconnect the left fan, sees the error, says disconnect
    # the right one, the same for all the rest". Each fan out alone: cure refused, its own alarm naming that fan, the
    # error recorded per side. Run 2 on the unit stopped with "the LEDs did not light for the mid-job part" because the
    # old script lit the LEDs while the fan alarm was still latched; the walk now waits for a clean machine first.
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-008"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    v = x["valuesSeen"]
    assert x["status"] == "OK", x["error"]
    assert v["positions_tested"] == "right, left, back, door" and v["failure_mode"] == "disconnected"
    assert v["job_start_inhibited"] is True and v["alarm_raised"] is True and v["alarm_identifies_correct_fan"] is True
    for pos in ("right", "left", "back", "door"):
        assert v["error_" + pos].startswith("9002 - ") and "FAN_" + pos.upper() in v["error_" + pos]
        assert x["tracesSeen"]["fan_" + pos]["refused"] is True
    assert isinstance(v["led_off_time_midjob"], (int, float)) and isinstance(v["max_led_temp"], (int, float))
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    assert "the LEDs never came on for the mid-job part" not in src
    # sCureBox 1.0.60+: the runner acknowledges the fan alarm itself - the operator only touches fans
    body = src[src.index("def('DVT-SAF-008'"):src.index("def('DVT-SAF-009'")]
    assert "/api/fans/ack" in body and "acknowledge the alarm" not in body and "ואשר את האזעקה" not in body

def test_led_temperatures_are_read_by_place():
    # The unit keys ledTemps by place (right/left/back/door), not TEMP_*: reading TEMP_RIGHT gave null on the machine for
    # every LED temperature in every trace. The simulator now uses the unit's keys, so the old read would show up here.
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    assert "lt.TEMP_RIGHT" not in src and "lt.right" in src


def test_ambient_and_reference_come_from_the_ch2_thermocouple():
    # The user's rule (2026-10-01): the reference thermocouple on TC-08 CH2 is the real ambient / chamber reference.
    # In the simulator CH2 follows the chamber (21.6 C at rest) and the cold junction sits at 21.7 C, so the value
    # recorded tells which source was used.
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-THM-001", "DVT-SAF-005"],
                       capture_output=True, text=True, encoding="utf-8", timeout=300, env=env)
    got = {x["test"]: x for x in json.loads(r.stdout)}
    # CH2 follows the simulated chamber (21.0 .. 22.0 C, cooling while idle); the cold junction is pinned at 21.7 C
    for tid, field in (("DVT-THM-001", "ambient_temp"), ("DVT-SAF-005", "reference_temp_start")):
        v = got[tid]["valuesSeen"][field]
        assert v != 21.7 and 21.0 <= v <= 22.0, (tid, v)


def test_a_finished_run_says_passed_or_failed_in_plain_words(auto_results):
    # "say on the screen that the test passed" (user, 2026-10-01): a run whose values are all in ends with the verdict
    # from the page's own evaluator - green PASSED or red FAILED with the clause - never a neutral "done".
    finished = {t: x for t, x in auto_results.items() if x.get("status") == "OK" and "waiting for" not in (x.get("line") or "")}
    assert finished, "no simulated run finished with all its values"
    for t, x in finished.items():
        assert (("PASSED" in x["line"] and x["cls"] == "pass") or ("FAILED" in x["line"] and x["cls"] == "fail")
                or ("BLOCKED" in x["line"] and x["cls"] == "warn")), (t, x["line"])


def test_saf009_a_drying_start_is_refused_with_9003_naming_the_cooling_fan():
    # sCureBox 1.0.63 spin-tests the chamber cooling fan before every drying and cooling step (not heating / UV), so
    # stage 1 starts a drying job; the refusal and its 9003 text come back in the start response. (Before: a program
    # starting with a heat step was sent - first as 'Heat', refused as malformed and scored "inhibited" - 0.9.78.)
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-009"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    v = x["valuesSeen"]
    assert x["status"] == "OK", x["error"]
    assert x["tracesSeen"]["start_attempt"]["accepted"] is False
    assert v["job_start_inhibited"] is True and v["alarm_raised"] is True and v["error_code"] == "9003"
    assert v["alarm_identifies_correct_fan"] is True and "FAN_COOLING" in v["alarm_text"]
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    assert "/api/cure/dry?target=40" in src[src.index("def('DVT-SAF-009'"):src.index("def('DVT-SAF-010'")]


def test_every_program_step_uses_the_machines_process_names():
    # SAF-009 r1 (2026-10-01) sent process 'Heat'; the machine's ProcessType is Heating / Drying / Cure / Cooling /
    # Bleacher / Nitrogen, so the start was refused as a malformed program and scored as "start inhibited".
    import re
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    used = set(re.findall(r"process: '([A-Za-z]+)'", src))
    assert used and used <= {"Heating", "Drying", "Cure", "Cooling", "Bleacher", "Nitrogen"}, used
    # and the simulator refuses an unknown name the way the unit does
    sim = (WEB / "dvt-auto.test.cjs").read_text(encoding="utf-8")
    assert "could not be converted to SCureBox.Domain.Models.ProcessType" in sim


def test_watch_traces_carry_fan_rpm_and_damper():
    # user, 2026-10-01: read the damper position from the chamber fan RPM - every trace now records both
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    for col in ("fan_cooling_rpm", "fan_cooling_duty", "fan_heater_rpm", "damper_open"):
        assert "'" + col + "'" in src


def test_saf015_pulls_the_cm5_cable_while_heating_in_one_run():
    # user, 2026-10-01: one run; heating on, "disconnect the 40-pin flat cable of the CM5", then "did the heater SSR
    # switch off?" - beside the measured heater-body turn - then reconnect and nothing may resume by itself
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-015"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    v = x["valuesSeen"]
    assert x["status"] == "OK", x["error"]
    assert v["heater_ssr_switched_off"] is True and v["auto_resume_heat"] is False and v["auto_resume_uv"] is False
    assert v["config_intact"] is True
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    body = src[src.index("def('DVT-SAF-015'"):src.index("def('DVT-SAF-016'")]
    assert "40-pin flat cable of the CM5" in body and "Did the heater SSR switch off?" in body and "/api/cure/heat?target=50" in body


def test_saf016_reads_every_value_from_the_starbright_at_405_only():
    # user, 2026-10-01: every value comes from the connected sensor automatically, and the test runs at 405 nm only (corrected from 450 the same day)
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-016"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    v = x["valuesSeen"]
    assert x["status"] == "OK", x["error"]
    for f in ("max_irradiance_10cm", "irradiance_operator_position", "permitted_exposure_hours"):
        assert isinstance(v.get(f), (int, float)), f
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    body = src[src.index("def('DVT-SAF-016'"):src.index("def('DVT-SAF-017'")]
    assert "/api/dvt/meter/wavelength?nm=405" in body and "wavelength=405" in body
    assert "450" not in body
    assert "c.value('max_irradiance_10cm'" not in body and "c.value('irradiance_operator_position'" not in body


def test_a_timed_diagnostic_is_given_its_duration_before_the_runner_gives_up():
    # SAF-021 r1 (2026-10-01): the functional check's 15 s LED test answered 200 after 18.7 s, but post() aborted at a
    # fixed 15 s, so the PASS was lost and post_test_functional_pass was recorded false. A seconds=N request now waits N + 30 s.
    src = (WEB / "dvt-auto.js").read_text(encoding="utf-8")
    body = src[src.index("    async post(path, timeoutMs) {"):src.index("    async postJson(")]
    assert "seconds=(" in body and "(Number(m[1]) + 30) * 1000" in body and "AbortSignal.timeout(ms)" in body


def test_the_functional_check_reads_the_firmwares_ok_as_a_passed_led_test():
    # SAF-021 r1 again (2026-10-01): the LED test answered {status: 'OK', stage: 'heating'} - a pass in the C# firmware -
    # and the runner, expecting the Python firmware's 'PASS', recorded post_test_functional_pass = false
    env = dict(os.environ, SCURE_DUMP="1")
    r = subprocess.run([shutil.which("node"), str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-021"], capture_output=True, text=True,
                       encoding="utf-8", timeout=300, env=env)
    x = json.loads(r.stdout)[0]
    fc = x["tracesSeen"]["functional_check"]
    assert fc["led"]["status"] == "OK" and fc["ledOk"] is True


def _saf012(fault=""):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    env = dict(os.environ, SCURE_DUMP="1", SCURE_DOOR_FAULT=fault)
    r = subprocess.run([node, str(WEB / "dvt-auto.test.cjs"), "DVT-SAF-012"], capture_output=True, text=True, encoding="utf-8", timeout=300, env=env)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    return json.loads(r.stdout)[0]


def test_saf012_runs_all_six_steps_in_one_run_and_passes_on_a_good_door():
    x = _saf012()
    assert x["status"] == "OK" and "PASSED" in x["line"], x["line"]
    v = x["valuesSeen"]
    assert v["cure_start_inhibited"] is True and v["lock_engaged"] is True
    assert v["defeat_by_magnet_possible"] is False and v["door_status_read_only_confirmed"] is True
    assert v["alarm_raised"] is True and v["error_code"] == "6016" and v["uv_off_time"] == 0.4
    assert x["traces"] == 5, "each of the five measuring steps keeps its own trace (CSV in the cloud)"
    assert x["left_on"] is False, "UV must be off at the end"


@pytest.mark.parametrize("fault,field,wrong", [
    ("accept", "cure_start_inhibited", False),       # the machine starts UV with the door open
    ("magnet", "defeat_by_magnet_possible", True),   # the sensor is fooled
    ("pull", "lock_engaged", False),                 # the lock gives way
])
def test_saf012_fails_when_the_interlock_fails_and_still_switches_everything_off(fault, field, wrong):
    x = _saf012(fault)
    assert x["status"] == "OK", x["error"]            # the run itself completed: a failed interlock is a result, not an error
    assert x["valuesSeen"][field] is wrong, x["valuesSeen"]
    assert "FAILED" in x["line"], x["line"]
    assert x["left_on"] is False, "the UV must be off even when the machine let it on"
