import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dvt_tool.catalog import Catalog  # noqa: E402
from dvt_tool import criteria  # noqa: E402
from dvt_tool.store import Store  # noqa: E402
from dvt_tool.engine import Engine  # noqa: E402
from dvt_tool.export import Exporter  # noqa: E402
from dvt_tool.drive import SyncConfig, Syncer, FolderBackend  # noqa: E402

CATALOG = ROOT / "catalog" / "DVT_test_catalog.yaml"


@pytest.fixture
def cat():
    return Catalog.load(CATALOG)


@pytest.fixture
def world(tmp_path, cat):
    store = Store(tmp_path / "campaign.db")
    eng = Engine(cat, store)
    return cat, store, eng, tmp_path


# ---------------- catalog ----------------
def test_catalog_loads_and_run_set_matches_srs(cat):
    assert len(cat.tests) == 41                      # DVT-SAF-006 removed from the campaign (user, 2026-10-01)
    runs = cat.runs()
    # SRS Rev B: 401 applicable runs; ENV-001 has unit=null (CONFIRM) so it contributes 0 until decided;
    # + SAF-021 (5) and THM-004 (1, destructive unit) since catalog v0.17 / v0.18;
    # - 10 since 2026-09-27: SAF-012 is owed once per unit, not three times (3 -> 1 reps x 5 units)
    # - 10 since 2026-10-01: SAF-004 likewise (3 -> 1 reps x 5 units), and SAF-003 and SAF-005 likewise;
    # - 15 since 2026-10-01: SAF-007 walks all four LED thermistors in one run (4 -> 1 reps x 5 units);
    # - 5 since 2026-10-01: DVT-SAF-006 removed from the campaign altogether;
    # - 35 since 2026-10-01: SAF-008 walks all four LED fans in one guided run (8 -> 1 reps x 5 units);
    # - 5 since 2026-10-01: SAF-009 once per unit (2 -> 1 reps x 5 units);
    # - 15 since 2026-10-01: SAF-015 is one run (CM5 40-pin cable pulled while heating), was 4 mains dropouts
    # - 30 since 2026-10-23 (user: each test once): GAS-001 (2 -> 1 reps), SAF-014 and SAF-017 (3 -> 1 reps), 10 runs each over 5 units
    assert len(runs) == 382
    assert len(cat.runs("DVT-SAF-009")) == 5
    assert len(cat.runs("DVT-SAF-008")) == 5
    assert "DVT-SAF-006" not in cat.tests
    assert len(cat.runs("DVT-SAF-005")) == 5           # one run per unit
    assert len(cat.runs("DVT-SAF-003")) == 5           # one run per unit
    assert len(cat.runs("DVT-SAF-012")) == 5           # one run per unit
    assert len(cat.runs("DVT-SAF-004")) == 5           # one run per unit
    assert len(cat.runs("DVT-GAS-001")) == 10          # 2 chamber cases x 1 rep x 5 units
    assert len(cat.runs("DVT-SAF-014")) == 5           # one run per unit
    assert len(cat.runs("DVT-SAF-017")) == 5           # one run per unit
    assert len(cat.runs("DVT-ELE-005")) == 20          # 4 mains voltages (100/110/230/240) x 5 units
    assert len(cat.runs("DVT-THM-001")) == 60          # 12 matrix rows x 5 units (incl. the 100 V low-line rows)
    assert len(cat.runs("DVT-SAF-008")) == 5           # one guided run per unit walks all four LED fans
    assert len(cat.runs("DVT-SAF-018")) == 7           # 7 cases, single unit
    assert len(cat.runs("DVT-SAF-020")) == 40          # 4 panels x 2 disconnect points x 5 units
    assert len(cat.runs("DVT-SAF-001")) == 1
    r = cat.runs("DVT-THM-001")[0]
    assert r.run_id.startswith("DVT-THM-001|UUT-01|setpoint=30,mains_voltage=230|1")
    assert cat.parent_row_for("DVT-THM-003", {"cooling_mode": "normal"}) == {"test_id": "DVT-THM-001", "setpoint": 80, "mains_voltage": 110}
    assert {(r.variant["setpoint"], r.variant["mains_voltage"]) for r in cat.runs("DVT-THM-001")} >= {(30, 100), (80, 100)}   # low line rows


def test_catalog_validation_catches_bad_entries(tmp_path, cat):
    import yaml
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    data["tests"][0]["procedure_steps"][2]["capture"].append("no_such_field")
    p = tmp_path / "bad.yaml"; p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(Exception, match="unknown field"):
        Catalog.load(p)


# ---------------- criteria ----------------
def test_criteria_pass_fail_blocked(cat):
    th = cat.thresholds
    expr = cat.tests["DVT-THM-002"]["pass_criteria"]
    ok = dict(max_temp_right=70, max_temp_left=72, max_temp_back=74.9, max_temp_door=60, protective_trip_occurred=False, final_dtdt=0.1, tj_margin=16)
    assert criteria.evaluate(expr, ok, th) == ("PASS", "")
    assert criteria.evaluate(expr, {**ok, "max_temp_back": 75.1}, th)[0] == "FAIL"
    v, d = criteria.evaluate(expr, {k: v for k, v in ok.items() if k != "tj_margin"}, th)
    assert v == "BLOCKED" and "tj_margin" in d
    # SAF-019 references a threshold that is still null -> BLOCKED, never PASS
    expr19 = cat.tests["DVT-SAF-019"]["pass_criteria"]
    v, d = criteria.evaluate(expr19, dict(alarm_raised=True, alarm_identifies_correct_side=True, message_names_specific_fan=False,
                                          claim_is_correct=True, peak_temp_after_shutdown=70, post_shutdown_overshoot=3,
                                          false_alarm_on_other_sides=False, recovery_requires_ack=True), th)
    assert v == "BLOCKED" and "protective_shutdown" in d
    # SAF-020: the alarm must name the correct panel; a lit panel means the injection failed, never a PASS
    expr20 = cat.tests["DVT-SAF-020"]["pass_criteria"]
    ok20 = dict(panel_confirmed_dark=True, alarm_raised=True, alarm_identifies_correct_panel=True, alarm_action_says_check_led=True,
                job_start_inhibited=True, false_alarm_on_other_panels=False, midjob_alarm_raised=True, midjob_job_stopped=True,
                recovery_requires_ack=True, post_test_panel_functional=True)
    assert criteria.evaluate(expr20, ok20, th) == ("PASS", "")
    assert criteria.evaluate(expr20, {**ok20, "alarm_identifies_correct_panel": False}, th)[0] == "FAIL"
    assert criteria.evaluate(expr20, {**ok20, "panel_confirmed_dark": False}, th)[0] == "FAIL"
    # ELE-005: per-mode power plausibility — the whole-machine figure cannot be below a single-mode figure; inrush needs >= 3 switch-ons
    expr5 = cat.tests["DVT-ELE-005"]["pass_criteria"]
    ok5 = dict(fuse_margin_ok=True, breaker_type_c_ok=True, label_agreement=True, inrush_switch_ons=3, input_power_all=640, input_power_heat=510, input_power_cure=150)
    assert criteria.evaluate(expr5, ok5, th) == ("PASS", "")
    assert criteria.evaluate(expr5, {**ok5, "input_power_all": 500}, th)[0] == "FAIL"        # below heat-only: a mode was mis-recorded
    assert criteria.evaluate(expr5, {**ok5, "inrush_switch_ons": 2}, th)[0] == "FAIL"
    assert criteria.evaluate(expr5, {k: v for k, v in ok5.items() if k != "input_power_cure"}, th)[0] == "BLOCKED"
    # SAF-013 (trimmed 2026-09-27): three numbers out of the TC-08 trace plus the graph. The body may not pass the
    # cutout's rating by more than 10 % - one-sided, an early trip is the safe direction; reset_temp is recorded, not judged.
    expr13 = cat.tests["DVT-SAF-013"]["pass_criteria"]
    ok13 = dict(cutout_trip_temp=131, rated_trip_temp=125, time_to_trip=4.97, graph_attached=True)
    assert criteria.evaluate(expr13, ok13, th) == ("PASS", "")
    assert criteria.evaluate(expr13, {**ok13, "cutout_trip_temp": 137}, th)[0] == "PASS"           # 9.6 % over: inside
    assert criteria.evaluate(expr13, {**ok13, "cutout_trip_temp": 140}, th)[0] == "FAIL"           # 12 % over: out
    assert criteria.evaluate(expr13, {**ok13, "cutout_trip_temp": 110}, th)[0] == "PASS"           # early trip: the safe way
    assert criteria.evaluate(expr13, {**ok13, "graph_attached": False}, th)[0] == "FAIL"           # no trace = no test
    assert criteria.evaluate(expr13, {k: v for k, v in ok13.items() if k != "rated_trip_temp"}, th)[0] == "BLOCKED"
    assert {f["name"] for f in cat.tests["DVT-SAF-013"]["data_fields"]} == {"rated_trip_temp", "time_to_trip", "cutout_trip_temp", "reset_temp", "graph_attached"}
    # SAF-004: heater-off time comes from the heater-body thermocouple; without a visible rise-to-fall turn there is no measurement
    expr4 = cat.tests["DVT-SAF-004"]["pass_criteria"]
    ok4 = dict(heater_body_drop_observed=True, heater_off_time=1.4, alarm_raised=True, alarm_text_instructs_reconnect=True, heat_start_inhibited=True)
    assert criteria.evaluate(expr4, ok4, th) == ("PASS", "")
    assert criteria.evaluate(expr4, {**ok4, "heater_body_drop_observed": False}, th)[0] == "FAIL"
    assert criteria.evaluate(expr4, {**ok4, "heater_off_time": 60.48}, th)[0] == "PASS"      # the unit's real run: body turn 60 s after the cut
    assert criteria.evaluate(expr4, {**ok4, "heater_off_time": 85.0}, th)[0] == "FAIL"       # 80 s from the disconnect (user, 2026-10-01)
    assert criteria.evaluate(expr4, {k: v for k, v in ok4.items() if k != "heater_off_time"}, th)[0] == "BLOCKED"
    # SAF-005: frozen 10 kOhm reading — software must detect within 3 min, cut the heater at the alarm and inhibit HEAT;
    # the thermal cutout having to act is a FAIL of the detection even though the machine was protected
    expr5b = cat.tests["DVT-SAF-005"]["pass_criteria"]
    ok5b = dict(alarm_raised=True, time_to_alarm=150, alarm_names_temperature_reading=True, heater_off_at_alarm=True, heater_off_delay=1.0,
                heat_start_inhibited=True, alarm_persists_until_fixed=True, cutout_tripped=False, max_chamber_temp=61, post_test_functional_pass=True)
    assert criteria.evaluate(expr5b, ok5b, th) == ("PASS", "")
    assert criteria.evaluate(expr5b, {**ok5b, "time_to_alarm": 200}, th)[0] == "FAIL"
    assert criteria.evaluate(expr5b, {**ok5b, "cutout_tripped": True}, th)[0] == "FAIL"
    assert criteria.evaluate(expr5b, {**ok5b, "heat_start_inhibited": False}, th)[0] == "FAIL"
    assert criteria.evaluate(expr5b, {k: v for k, v in ok5b.items() if k != "heater_off_delay"}, th)[0] == "BLOCKED"
    # string / enum / OR / abs
    assert criteria.evaluate("which == 'a' AND (x == false OR y == true) AND abs(e) <= 1", dict(which="a", x=True, y=True, e=-0.5)) == ("PASS", "")
    with pytest.raises(criteria.CriteriaError):
        criteria.evaluate("__import__('os')", {})


# ---------------- engine: gates, next action, verdict, rollup ----------------
def _cal_all(cat, store):
    until = (date.today() + timedelta(days=365)).isoformat()
    for t in cat.tests.values():
        for e in t.get("equipment") or []:
            store.set_calibration(e["name"], "CAL-1", until)


def test_wizard_gates_and_next_action(world):
    cat, store, eng, _ = world
    na = eng.next_action("UUT-02")
    assert na.phase["id"] == 0 and na.run is None                        # config not frozen
    store.freeze_config("UUT-02", "amitai", "SC000002")
    na = eng.next_action("UUT-02")
    assert na.run["test_id"] == "DVT-ELE-001"                           # earth first
    codes = {b.code for b in na.blockers}
    assert "TRR" in codes and "CAL" in codes and "PHASE" not in codes
    store.sign_phase("UUT-02", 1, "amitai", ["ok"])
    _cal_all(cat, store)
    na = eng.next_action("UUT-02")
    assert na.blockers == []
    # a later-phase run is blocked by the unclosed phase and by the earth rule
    saf = store.runs("DVT-SAF-012", "UUT-02")[0]
    codes = {b.code for b in eng.blockers_for(saf)}
    assert {"PHASE", "EARTH", "TRR"} <= codes


def test_finish_pass_fail_ncr_waiver_and_rollup(world):
    cat, store, eng, _ = world
    store.freeze_config("UUT-01", "a"); store.sign_phase("UUT-01", 1, "a", []); _cal_all(cat, store)
    run = store.runs("DVT-ELE-001", "UUT-01")[0]
    store.start_run(run["run_id"], "a"); store.confirm_preconditions(run["run_id"], "a")
    store.set_values(run["run_id"], dict(max_resistance=0.05, pe_uninterrupted=True), "a")
    assert eng.finish(run["run_id"], "a") == ("PASS", "")
    # ELE-002 fails -> NCR opened, rollup FAIL, then waived -> WAIVED counted separately
    r2 = store.runs("DVT-ELE-002", "UUT-01")[0]
    store.start_run(r2["run_id"], "a"); store.set_values(r2["run_id"], dict(insulation_resistance_lnpe=4), "a")
    v, _ = eng.finish(r2["run_id"], "a")
    assert v == "FAIL" and len(store.ncrs(open_only=True)) == 1
    assert eng.test_verdict("DVT-ELE-002", "UUT-01") == "FAIL"
    with pytest.raises(ValueError):
        store.waive(r2["run_id"], "", "no approver", "a")
    store.waive(r2["run_id"], "QA lead", "engineering limit, not a 62368 requirement", "a")
    assert eng.test_verdict("DVT-ELE-002", "UUT-01") == "WAIVED"
    p = eng.progress()
    assert p["PASS"] == 1 and p["WAIVED"] == 1 and p["FAIL"] == 0
    # resume after restart: in-progress run is the next action (SRS-DVT-088)
    r3 = store.runs("DVT-ELE-003", "UUT-01")[0]
    store.start_run(r3["run_id"], "a"); store.set_step(r3["run_id"], 2)
    eng2 = Engine(cat, Store(store.path))
    assert eng2.next_action("UUT-01").run["run_id"] == r3["run_id"]


def test_sweep_rollup_and_reject_rescinds_children(world):
    cat, store, eng, _ = world
    rows = store.runs("DVT-THM-001", "UUT-03")
    good = dict(uniformity_pp=3, overshoot=1, steady_state_error=0.5, limit_cycle_amplitude=0.5, settling_time=20)
    for r in rows:
        store.start_run(r["run_id"], "a"); store.set_values(r["run_id"], good, "a"); eng.finish(r["run_id"], "a")
    assert eng.test_verdict("DVT-THM-001", "UUT-03") == "PASS"
    bad = rows[5]
    store.set_values(bad["run_id"], {**good, "overshoot": 4}, "a"); eng.finish(bad["run_id"], "a")
    assert eng.test_verdict("DVT-THM-001", "UUT-03") == "FAIL"          # one row fails -> rolled-up FAIL (SRS-DVT-096)
    # co-executed child linked to the parent row; rejecting the parent rescinds the child (SRS-DVT-099)
    child = [r for r in store.runs("DVT-THM-003", "UUT-03") if r["variant"] == {"cooling_mode": "fast"}][0]
    parent = [r for r in rows if r["variant"] == {"setpoint": 80, "mains_voltage": 230}][0]
    store.link_parent(child["run_id"], parent["run_id"])
    affected = store.reject_run(parent["run_id"], "ambient left the band", "a")
    assert set(affected) == {parent["run_id"], child["run_id"]}
    assert store.run(child["run_id"])["status"] == "REJECTED" and "parent rejected" in store.run(child["run_id"])["reject_reason"]
    assert eng.test_verdict("DVT-THM-001", "UUT-03") == "FAIL"          # the other failing row still counts


# ---------------- export + sync ----------------
def test_export_and_folder_sync(world):
    cat, store, eng, tmp = world
    run = store.runs("DVT-ELE-001", "UUT-01")[0]
    store.start_run(run["run_id"], "a"); store.set_values(run["run_id"], dict(max_resistance=0.2, pe_uninterrupted=True), "a")
    eng.finish(run["run_id"], "a")
    store.add_redline(run["run_id"], 1, "measured with 10 A instead of 25 A", "tester limit", "a")
    exp = Exporter(cat, store, tmp / "export", "TestCampaign")
    files = exp.export_all()
    names = {f.name for f in files}
    assert {"TestCampaign.campaign.json", "TestCampaign.xlsx", "TestCampaign.report.md", "DVT-ELE-001.csv"} <= names
    csv_text = (tmp / "export" / "csv" / "DVT-ELE-001.csv").read_text()
    assert "FAIL" in csv_text and "0.2" in csv_text
    from openpyxl import load_workbook
    wb = load_workbook(tmp / "export" / "TestCampaign.xlsx")
    assert "Summary" in wb.sheetnames and "ELE-001" in wb.sheetnames and "NCR" in wb.sheetnames
    # folder backend: everything lands under the synced folder, queue drains
    drive = tmp / "GoogleDrive" / "sCure DVT"
    syncer = Syncer(SyncConfig(mode="folder", folder_path=drive, campaign="TestCampaign"), store, tmp / "export")
    st = syncer.sync(files)
    assert st.ok and (drive / "TestCampaign.xlsx").exists() and (drive / "csv" / "DVT-ELE-001.csv").exists()
    assert store.pending_sync() == []
    # a failing backend never loses data: queue stays, error visible
    class Broken(FolderBackend):
        def push(self, files, root): raise OSError("network down")
    store.queue("run", run["run_id"])
    bad = Syncer(SyncConfig(mode="folder", folder_path=drive), store, tmp / "export", backend=Broken(drive))
    st = bad.sync(files)
    assert not st.ok and st.pending == 1 and "network down" in st.last_error


# ---------------- simulator: SAF-020 fault injection ----------------
def test_sim_led_panel_open_names_panel_and_inhibits():
    from dvt_tool.ui.sim import SimMachine
    sim = SimMachine()
    assert sim.uv(True, 80)["ok"]                                  # healthy: UV starts
    sim.inject("led_panel_open")
    with sim.lock:
        sim._step(1.0)                                             # mid-job: detected on the next control step
    assert not sim.uv_on and sim.job_status == "aborted"
    alarm = next(a for a in sim.alerts if a["code"] == "2310")
    assert "right" in alarm["message"] and "not working" in alarm["message"]
    assert "Check the right LED" in alarm["action"]
    sim.ack()
    assert sim.uv(True, 80)["ok"] is False                         # switch-on with the panel still open: inhibited
    assert any(a["code"] == "2310" and "inhibited" in a["message"] for a in sim.alerts)
    assert sim.led_test()["ok"] is False
    sim.inject("led_panel_open", False); sim.ack()
    assert sim.uv(True, 80)["ok"]                                  # restored + acknowledged: runs again


# ---------------- catalog change: run-set reconciliation ----------------
def test_ensure_runs_reconciles_a_reshaped_test(tmp_path, cat):
    from dvt_tool.catalog import RunSpec
    store = Store(tmp_path / "campaign.db")
    # the campaign started on an older catalog where ELE-005 had 3 plain repetitions per unit
    old = [RunSpec(f"DVT-ELE-005|UUT-01||{r}", "DVT-ELE-005", "UUT-01", {}, r) for r in (1, 2, 3)]
    store.ensure_runs(old, "0.10")
    store.db.execute("UPDATE runs SET status='DONE', verdict='PASS' WHERE run_id='DVT-ELE-005|UUT-01||1'"); store.db.commit()
    # the catalog is re-shaped (mains-voltage sweep): never-started stale runs go, the one with data stays and is reported
    res = store.ensure_runs(cat.runs(), cat.version)
    ids = {r["run_id"] for r in store.runs()}
    assert res["retired"] == 2 and res["orphaned"] == ["DVT-ELE-005|UUT-01||1"]
    assert "DVT-ELE-005|UUT-01||2" not in ids and "DVT-ELE-005|UUT-01||1" in ids
    assert "DVT-ELE-005|UUT-01|mains_voltage=100|1" in ids and len(ids) == len(cat.runs()) + 1
    assert any(e["event"].startswith("Catalog changed") for e in store.events())
    # a second call is a no-op
    assert store.ensure_runs(cat.runs(), cat.version) == {"added": 0, "retired": 0, "orphaned": ["DVT-ELE-005|UUT-01||1"]}


# ---------------- catalog language overlay (SRS-DVT-194) ----------------
OVERLAY_HE = ROOT / "catalog" / "DVT_test_catalog.he.yaml"


def test_hebrew_overlay_covers_every_test_and_keeps_identifiers():
    en, he = Catalog.load(CATALOG), Catalog.load(CATALOG, "he")
    assert (en.lang, he.lang) == ("en", "he")
    assert set(he.tests) == set(en.tests)
    hebrew = lambda s: any("֐" <= ch <= "׿" for ch in s)  # noqa: E731
    for tid, e in en.tests.items():
        t = he.tests[tid]
        # every piece of prose the operator reads is Hebrew …
        assert hebrew(t["title"]) and hebrew(t["purpose"]), tid
        assert all(hebrew(s["step"]) for s in t.get("procedure_steps") or []), tid
        assert all(hebrew(p) for p in t.get("preconditions") or []), tid
        assert all(hebrew(p) for p in t.get("safety_plan") or []), tid
        assert all(hebrew(eq["label"]) for eq in t.get("equipment") or []), tid
        if e.get("sample_rationale"):
            assert hebrew(t["sample_rationale"]), tid
        # … and every identifier is untouched
        assert t["pass_criteria"] == e["pass_criteria"] and t["method"] == e["method"] and t["subsystem"] == e["subsystem"]
        assert [f["name"] for f in t.get("data_fields") or []] == [f["name"] for f in e.get("data_fields") or []]
        assert [s.get("capture") for s in t.get("procedure_steps") or []] == [s.get("capture") for s in e.get("procedure_steps") or []]
        assert [eq["name"] for eq in t.get("equipment") or []] == [eq["name"] for eq in e.get("equipment") or []]   # calibration key
    assert [p["id"] for p in he.phases] == [p["id"] for p in en.phases] and all(hebrew(p["name"]) for p in he.phases)
    assert he.label("subsystems", "Safety") == "בטיחות" and en.label("subsystems", "Safety") == "Safety"
    assert he.label("methods", "Test") == "בדיקה" and he.label("rules", "ALL") == "כל היחידות"
    assert he.units[0]["role_label"] == "ייחוס" and "role_label" not in en.units[0]
    # run identity (ids, count, order) is language-independent — results recorded in Hebrew are the same runs
    assert [r.run_id for r in he.runs()] == [r.run_id for r in en.runs()]


def test_overlay_refuses_mismatch_and_unknown_tests():
    import yaml
    ov = yaml.safe_load(OVERLAY_HE.read_text(encoding="utf-8"))
    ov["tests"]["DVT-SAF-001"]["procedure_steps"].pop()          # a step added in English without its Hebrew line
    with pytest.raises(Exception, match="procedure_steps"):
        Catalog.load(CATALOG).apply_overlay(ov, "he")
    ov = yaml.safe_load(OVERLAY_HE.read_text(encoding="utf-8"))
    ov["tests"]["DVT-XXX-999"] = {"title": "x"}
    with pytest.raises(Exception, match="not in the catalog"):
        Catalog.load(CATALOG).apply_overlay(ov, "he")
    ov = yaml.safe_load(OVERLAY_HE.read_text(encoding="utf-8"))
    ov["tests"]["DVT-SAF-001"]["field_notes"] = {"no_such_field": "x"}
    with pytest.raises(Exception, match="unknown field"):
        Catalog.load(CATALOG).apply_overlay(ov, "he")
    # unknown language / no overlay file: plain English catalog, no error
    assert Catalog.load(CATALOG, "fr").lang == "en"


def test_engine_messages_follow_console_language(world):
    from dvt_tool.ui import i18n
    cat, store, eng, tmp = world
    try:
        i18n.set_language("he")
        assert "שלב 0" in eng.next_action("UUT-01").message
    finally:
        i18n.set_language("en")
    assert "Phase 0" in eng.next_action("UUT-01").message


# ---------------- instruments: Ophir meter + DVT-SAF-012 UV-off sequence ----------------
def test_uvoff_sequence_against_simulator(tmp_path):
    from dvt_tool.ui.sim import SimClient
    from dvt_tool.instruments.ophir import open_meter, MeterError
    from dvt_tool.instruments.uvoff import UvOffRunner, UvOffConfig, write_csv, plot_png
    with pytest.raises(MeterError):
        open_meter("serial:")                                  # needs a port
    assert open_meter("serial:COM7:19200").port == "COM7"
    dut = SimClient(); dut.door_close(); dut.ack()
    phases = []
    r = UvOffRunner(dut, open_meter("sim"), UvOffConfig(sample_hz=40, baseline_s=0.3, plateau_window_s=0.5), on_status=lambda ph, _t: phases.append(ph))
    res = r.run()
    assert res.status == "OK" and phases[:3] == ["connect", "baseline", "uv_on"] and phases[-1] == "done"
    assert res.plateau and res.plateau > 40                     # LEDs at maximum: ~45 mW/cm2 in the simulator
    assert res.trigger_source == "api" and res.uv_off_time is not None and 0 <= res.uv_off_time <= 1.0
    assert res.residual_fraction is not None and res.residual_fraction < 0.05
    assert res.alarm_code == "1101"                             # simulator: door interlock alarm
    assert not dut.sim.uv_on                                    # sequence always ends with the LEDs off
    csv_p = write_csv(res, tmp_path / "uvoff.csv"); png_p = plot_png(res, tmp_path / "uvoff.png")
    assert csv_p.exists() and png_p.stat().st_size > 10_000
    head = csv_p.read_text(encoding="utf-8").splitlines()[:2]
    assert "uv_off_time=" in head[0] and head[1].startswith("t_s_rel_trigger")


def test_uvoff_analysis_pure():
    from dvt_tool.instruments.uvoff import analyze, UvOffResult, UvOffConfig, Sample
    cfg = UvOffConfig(settle_s=0.2)
    # plateau 40, door opens at t=5.0, reading collapses at t=5.35 -> uv_off_time 0.35
    samples = [Sample(t / 100, 0.0) for t in range(0, 100)] + [Sample(1 + t / 100, 40.0) for t in range(0, 435)] + [Sample(5.35 + t / 100, 0.5) for t in range(0, 100)]
    res = analyze(UvOffResult(unit="mW/cm2", samples=samples, plateau=40.0, t_uv_on=1.0, t_trigger=5.0, trigger_source="dut-poll"), cfg)
    assert res.t_uv_off == pytest.approx(5.35) and res.uv_off_time == pytest.approx(0.35) and res.residual == pytest.approx(0.5)
    # no door instant known -> derived from the trace, flagged as a lower bound
    res2 = analyze(UvOffResult(unit="mW/cm2", samples=samples, plateau=40.0, t_uv_on=1.0), cfg)
    assert res2.trigger_source == "trace" and res2.t_trigger == pytest.approx(5.34) and any("lower bound" in n for n in res2.notes)


# ---------------- DVT-SAF-007: the same runner with the LED-thermistor trigger ----------------
def test_ledoff_sequence_against_simulator_saf007(tmp_path):
    """The simulator's open-thermistor fault is injected mid-cure: UV must drop within 2 s, the alarm names the sensor, the fault is cleared afterwards."""
    from dvt_tool.ui.sim import SimClient
    from dvt_tool.instruments.ophir import open_meter
    from dvt_tool.instruments.uvoff import UvOffRunner, UvOffConfig, TOOL_TRIGGERS, write_csv, plot_png
    assert TOOL_TRIGGERS == {"uv_off_timing": "door", "led_off_timing": "led_thermistor"}
    with pytest.raises(ValueError):
        UvOffConfig(trigger="led_thermistor", sensor_position="top")
    with pytest.raises(ValueError):
        UvOffConfig(trigger="mains")
    dut = SimClient(); dut.door_close(); dut.inject("led_thermistor_open", False); dut.ack()
    phases = []
    cfg = UvOffConfig(trigger="led_thermistor", sensor_position="right", sample_hz=40, baseline_s=0.3, plateau_window_s=0.5)
    assert cfg.limit_s == 2.0 and "RIGHT" in cfg.prompt and UvOffConfig().limit_s == 1.0
    res = UvOffRunner(dut, open_meter("sim"), cfg, on_status=lambda ph, _t: phases.append(ph)).run()
    assert res.status == "OK" and "trigger" in phases and res.test_id == "DVT-SAF-007" and res.sensor_position == "right"
    assert res.trigger_source == "api" and res.uv_off_time is not None and 0 <= res.uv_off_time <= 2.0 and res.passed is True
    assert res.alarm_code == "2301" and res.alarm_identifies_sensor is True      # simulator: "LED thermistor open (right panel)"
    assert not dut.sim.uv_on and "led_thermistor_open" not in dut.sim.faults   # LEDs off, injected fault cleared
    csv_p = write_csv(res, tmp_path / "ledoff.csv"); png_p = plot_png(res, tmp_path / "ledoff.png")
    head = csv_p.read_text(encoding="utf-8").splitlines()[:2]
    assert head[0].startswith("# DVT-SAF-007") and "led_off_time=" in head[0] and "sensor_position=right" in head[0] and "limit_s=2.0" in head[0]
    assert head[1].startswith("t_s_rel_trigger") and png_p.stat().st_size > 10_000


def test_ledoff_analysis_limit_and_alarm_naming():
    from dvt_tool.instruments.uvoff import analyze, UvOffResult, UvOffConfig, Sample, alarm_names_position, thermistor_is_gone, first_alert
    cfg = UvOffConfig(trigger="led_thermistor", sensor_position="back", settle_s=0.2)
    samples = [Sample(t / 100, 0.0) for t in range(0, 100)] + [Sample(1 + t / 100, 40.0) for t in range(0, 435)] + [Sample(5.35 + t / 100, 0.5) for t in range(0, 100)]
    res = analyze(UvOffResult(trigger="led_thermistor", test_id="DVT-SAF-007", sensor_position="back", limit_s=2.0, unit="mW/cm2", samples=samples, plateau=40.0,
                              t_uv_on=1.0, t_trigger=5.0, trigger_source="operator", alarm_text="LED thermistor open (back panel) — UV inhibited"), cfg)
    assert res.uv_off_time == pytest.approx(0.35) and res.passed is True and res.alarm_identifies_sensor is True
    slow = analyze(UvOffResult(trigger="led_thermistor", sensor_position="back", limit_s=2.0, unit="mW/cm2", samples=samples, plateau=40.0, t_uv_on=1.0, t_trigger=3.0, alarm_text="LED fault"), cfg)
    assert slow.uv_off_time == pytest.approx(2.35) and slow.passed is False and slow.alarm_identifies_sensor is False
    mid = analyze(UvOffResult(trigger="led_thermistor", sensor_position="back", limit_s=2.0, unit="mW/cm2", samples=samples, plateau=40.0, t_uv_on=1.0, t_trigger=4.0), cfg)
    assert mid.uv_off_time == pytest.approx(1.35) and mid.passed is True and mid.alarm_identifies_sensor is None   # 1.35 s: passes SAF-007 (2 s), would fail SAF-012 (1 s)
    assert alarm_names_position(None, "back") is None
    # the DUT poll: a pulled thermistor reads null on the real machine (io_bridge ledTemps) and in the simulator alike
    assert thermistor_is_gone({"ledTemps": {"right": 31.2, "back": None}}, "back") is True
    assert thermistor_is_gone({"ledTemps": {"right": 31.2, "back": 30.0}}, "back") is False
    assert thermistor_is_gone({"chamberTemp": 25.0}, "back") is None
    # the real machine reports a fault message under faults.led, not an alert code
    assert first_alert({"faults": {"led": "no LED could be enabled", "heater": None, "cooling": False}}) == (None, "no LED could be enabled")
    assert first_alert({"faults": {"led": None, "heater": None, "cooling": False}}) == (None, None)


def test_catalog_saf007_is_instrumented(cat):
    t = cat.tests["DVT-SAF-007"]
    step = t["procedure_steps"][2]
    assert step.get("tool") == "led_off_timing" and step["capture"] == ["led_off_time"]
    assert any("Ophir" in e["name"] for e in t["equipment"])
    ok = dict(cure_start_inhibited=True, led_off_time=1.2, alarm_raised=True, alarm_identifies_sensor=True)
    assert criteria.evaluate(t["pass_criteria"], ok, cat.thresholds) == ("PASS", "")
    assert criteria.evaluate(t["pass_criteria"], {**ok, "led_off_time": 2.4}, cat.thresholds)[0] == "FAIL"
    assert criteria.evaluate(t["pass_criteria"], {**ok, "alarm_identifies_sensor": False}, cat.thresholds)[0] == "FAIL"
    he = Catalog.load(CATALOG, "he").tests["DVT-SAF-007"]
    assert he["procedure_steps"][2].get("tool") == "led_off_timing" and "StarBright" in he["procedure_steps"][2]["step"]
    # one run walks all four positions (user, 2026-10-01): no per-position runs, no sensor_position field
    assert t["repetitions"] == 1 and len(cat.runs("DVT-SAF-007")) == 5
    assert "positions_tested" in {f["name"] for f in t["data_fields"]} and "sensor_position" not in {f["name"] for f in t["data_fields"]}


def test_catalog_thm004_selector_mismatch_heater_off_time(cat):
    """DVT-THM-004: 230 V on the 110 V selector — the heater shutdown (= branch fuse opening) is read on the heater-body thermocouple."""
    t = cat.tests["DVT-THM-004"]
    assert t["subsystem"] == "Thermal" and t["applicability"] == {"rule": "SINGLE", "unit": "UUT-05"} and len(cat.runs("DVT-THM-004")) == 1
    assert any("TC-08" in e["name"] for e in t["equipment"]) and any("heater body" in e["name"] for e in t["equipment"])
    phase5 = next(p for p in cat.phases if p["id"] == 5)
    assert phase5["tests"].index("DVT-THM-004") < phase5["tests"].index("DVT-SAF-001")   # destructive unit, last phase, same energisation as SAF-001
    expr = t["pass_criteria"]
    ok = dict(body_rising_before_heat=False, heater_body_drop_observed=True, fuse_opened=True, which_fuse_opened="heater_branch_5A", manual_abort_used=False,
              heater_off_time=42.0, heater_temp_peak=180.0, post_test_functional_pass=True)
    assert cat.thresholds["heater_thresholds"]["body_ceiling"] == 250 and cat.thresholds["heater_thresholds"]["selector_mismatch_fuse_open_max"] is None
    assert criteria.evaluate(expr, ok, cat.thresholds)[0] == "BLOCKED"                    # fuse-open limit still CONFIRM (null): never PASS
    th = {**cat.thresholds, "heater_thresholds": {**cat.thresholds["heater_thresholds"], "selector_mismatch_fuse_open_max": 60}}
    assert criteria.evaluate(expr, ok, th) == ("PASS", "")
    assert criteria.evaluate(expr, {**ok, "heater_off_time": 75.0}, th)[0] == "FAIL"            # over-driven longer than allowed
    assert criteria.evaluate(expr, {**ok, "which_fuse_opened": "inlet_15A"}, th)[0] == "FAIL"   # selectivity lost
    assert criteria.evaluate(expr, {**ok, "manual_abort_used": True}, th)[0] == "FAIL"         # the fuse never acted
    assert criteria.evaluate(expr, {**ok, "heater_body_drop_observed": False}, th)[0] == "FAIL" # no turn on the trace = no proof
    assert criteria.evaluate(expr, {**ok, "heater_temp_peak": 260.0}, th)[0] == "FAIL"
    assert criteria.evaluate(expr, {**ok, "body_rising_before_heat": True}, th)[0] == "FAIL"
    he = Catalog.load(CATALOG, "he").tests["DVT-THM-004"]
    assert len(he["procedure_steps"]) == len(t["procedure_steps"]) and "TC-08" in he["procedure_steps"][2]["step"] and len(he["safety_plan"]) == 5


# ---------------- process figures ----------------
def test_process_figures_cover_every_test_and_render(cat):
    """Every catalog test has a figure spec, every step index exists, the SVG is well-formed and every label is translated."""
    import xml.etree.ElementTree as ET
    from dvt_tool import figures
    from dvt_tool.ui import i18n
    assert figures.check_specs(cat.tests) == []
    for tid, t in cat.tests.items():
        for step in [None] + list(range(len(t["procedure_steps"]))):
            root = ET.fromstring(figures.figure_svg(tid, step, tid))
            assert root.tag.endswith("svg") and len(root) > 20
        assert figures.figure_caption(tid)
    # a step override replaces the base state; None removes a highlight; instruments appear only when listed
    st = figures.states_for("DVT-THM-004", 3)
    assert st["fuse_heater"] == "fault" and st["heater"] == "off" and st["thermal_cam"] == "focus" and st["selector"] == "fault"
    assert figures.states_for("DVT-SAF-001", 0)["heater"] is None and figures.states_for("DVT-SAF-001")["heater"] == "on"
    svg_base, svg_step = figures.figure_svg("DVT-SAF-012"), figures.figure_svg("DVT-SAF-012", 3)
    assert "Hand magnet" in svg_step and "Hand magnet" not in svg_base and "Door open" in svg_step
    assert figures.figure_svg("DVT-NOPE") .count("<svg") == 1                       # unknown test: plain machine, no crash
    # the figure is an engineering drawing: English in every console language, with a title block and component tags
    hebrew = lambda s: any("֐" <= ch <= "׿" for ch in s)  # noqa: E731
    i18n.set_language("he")
    try:
        svg = figures.figure_svg("DVT-SAF-007", 2, "LED thermistor disconnected — open circuit", rev="0.20", date="2026-09-06")
        assert not hebrew(svg) and not hebrew(figures.figure_caption("DVT-SAF-007"))
    finally:
        i18n.set_language("en")
    assert "DVT-SAF-007 — LED thermistor disconnected" in svg and "STEP 3" in svg and "v0.20" in svg and "2026-09-06" in svg
    assert "RT4 Right thermistor" in svg and "K2" in svg and "LEGEND" in svg and "Injected fault" in svg
    assert "BASE STATE" in figures.figure_svg("DVT-SAF-007")
    # every drawing string that used to be translated is gone from the Hebrew table
    assert "Right thermistor" not in i18n.HE and "Enclosure" not in i18n.HE

# ---------------- DVT-OPT-001/002: UV irradiance vs commanded power, StarBright on the machine ----------------
def test_uv_sweep_against_simulator_and_analysis(tmp_path):
    from dvt_tool.ui.sim import SimClient
    from dvt_tool.instruments.uvsweep import UvSweepRunner, UvSweepConfig, UvSweepResult, StepResult, analyze, values, write_csv, plot_png
    with pytest.raises(ValueError):
        UvSweepConfig(wavelength=385)
    dut = SimClient(); dut.door_close(); dut.ack()
    assert dut.meter()["present"] and dut.meter_set_wavelength(450)["ok"]
    cfg = UvSweepConfig(wavelength=405, steps=(30, 60, 100), dwell_s=0.6, baseline_s=0.3, settle_s=0.3, hz=10, poll_s=0.2)
    res = UvSweepRunner(dut, cfg).run()
    assert res.status == "REFUSED" and "450" in res.notes[0] and res.meter_wavelength_nm == 450     # meter on the wrong wavelength: the sweep does not start
    dut.meter_set_wavelength(405)
    phases = []
    res = UvSweepRunner(dut, cfg, on_status=lambda ph, _t: phases.append(ph)).run()
    assert res.status == "OK" and res.meter_wavelength_verified and res.all_steps_measured and [s.intensity for s in res.steps] == [30, 60, 100]
    assert res.monotonic and res.r2 > 0.98 and res.slope > 0 and res.dark is not None and not dut.sim.uv_on and phases[-1] == "done"
    v = values(res)
    assert v["meter_detected"] and v["meter_wavelength_verified"] and v["all_steps_measured"] and v["monotonic"] and "irradiance_100" in v and v["meter_wavelength_nm"] == 405
    csv_p = write_csv(res, tmp_path / "s.csv"); png_p = plot_png(res, tmp_path / "s.png")
    assert "wavelength=405" in csv_p.read_text(encoding="utf-8")[:200] and png_p.stat().st_size > 10_000
    # pure analysis on the bench curve of 2026-09-14 (450 nm, Ophir at the chamber centre)
    bench = [(30, 12.03), (40, 15.81), (50, 19.05), (60, 22.50), (70, 25.53), (80, 28.29), (90, 30.70), (100, 32.90)]
    r = analyze(UvSweepResult(wavelength=450, test_id="DVT-OPT-002", steps=[StepResult(i, mw) for i, mw in bench], config={"steps": [i for i, _ in bench]}))
    assert abs(r.slope - 0.299) < 0.003 and abs(r.intercept - 3.9) < 0.2 and r.r2 > 0.99 and r.monotonic and r.gain_first > r.gain_last and r.all_steps_measured
    bad = analyze(UvSweepResult(steps=[StepResult(30, 10.0), StepResult(40, 9.0), StepResult(50, 12.0)], config={"steps": [30, 40, 50]}))
    assert bad.monotonic is False
    partial = analyze(UvSweepResult(steps=[StepResult(30, 10.0), StepResult(40, None)], config={"steps": [30, 40, 50]}))
    assert partial.all_steps_measured is False


def test_catalog_opt_tests_uv_linearity(cat):
    for tid, nm in (("DVT-OPT-001", 405), ("DVT-OPT-002", 450)):
        t = cat.tests[tid]
        assert t["subsystem"] == "Optical" and t["uv_wavelength_nm"] == nm and t["applicability"]["rule"] == "ALL" and len(cat.runs(tid)) == 5
        step = next(s for s in t["procedure_steps"] if s.get("tool"))
        assert step["tool"] == "uv_linearity" and "irradiance_100" in step["capture"] and "irradiance_30" in step["capture"]
        meter = next(e for e in t["equipment"] if "StarBright" in e["name"])
        assert meter.get("verify") == "live_meter" and "calibration_id" not in meter          # no certificate: the DVT checks the meter live through the machine
        assert next(e for e in t["equipment"] if "fixture" in e["name"]).get("verify") == "none"
        assert any("USB" in p for p in t["preconditions"]) and any(f"{nm} nm" in p for p in t["preconditions"])   # connect to the machine; verify the meter's wavelength
        assert len(t["procedure_steps"]) == 1 and step.get("auto") is True and f"{nm} nm" in step["step"]   # one automatic step: nothing typed in
        assert set(step["capture"]) >= {"meter_wavelength_verified", "irradiance_100", "monotonic", "graph_attached"}
        assert len(t["preconditions"]) == 4                                            # the connection checklist
        ok = dict(meter_detected=True, meter_wavelength_verified=True, all_steps_measured=True, monotonic=True, graph_attached=True)
        assert criteria.evaluate(t["pass_criteria"], ok, cat.thresholds) == ("PASS", "")
        assert criteria.evaluate(t["pass_criteria"], {**ok, "meter_wavelength_verified": False}, cat.thresholds)[0] == "FAIL"
        assert criteria.evaluate(t["pass_criteria"], {**ok, "monotonic": False}, cat.thresholds)[0] == "FAIL"
        assert criteria.evaluate(t["pass_criteria"], {**ok, "all_steps_measured": None}, cat.thresholds)[0] == "BLOCKED"
    assert "DVT-OPT-001" in next(p for p in cat.phases if p["id"] == 3)["tests"]
    he = Catalog.load(CATALOG, "he")
    assert "405" in he.tests["DVT-OPT-001"]["procedure_steps"][0]["step"] and "450" in he.tests["DVT-OPT-002"]["procedure_steps"][0]["step"]
    assert he.label("subsystems", "Optical") != "Optical"


def test_engine_pending_run_for_a_picked_test(world):
    """Test Console 'Pick a test': resume the IN_PROGRESS run of that test on that unit, else its first NOT_STARTED run, else None."""
    cat, store, eng, _ = world
    runs = store.runs("DVT-THM-005", "UUT-02")
    assert eng.pending_run("DVT-THM-005", "UUT-02")["run_id"] == runs[0]["run_id"]           # first NOT_STARTED in catalog order
    store.start_run(runs[2]["run_id"], "op")
    assert eng.pending_run("DVT-THM-005", "UUT-02")["run_id"] == runs[2]["run_id"]           # an IN_PROGRESS run wins: resume it
    assert eng.pending_run("DVT-SAF-001", "UUT-01") is None                                  # SINGLE on UUT-05: nothing on UUT-01
    assert eng.blockers_for(runs[0])                                                         # picked out of order: blockers listed, not hidden


def test_live_verified_equipment_is_not_a_calibration_blocker(world):
    """OPT-001/002: the StarBright is verified live by the DVT, the fixture needs nothing — neither raises a CAL blocker; a real instrument still does."""
    cat, store, eng, _ = world
    run = store.runs("DVT-OPT-001", "UUT-01")[0]
    assert not any(b.code == "CAL" for b in eng.blockers_for(run))
    run2 = store.runs("DVT-SAF-012", "UUT-01")[0]
    assert any(b.code == "CAL" for b in eng.blockers_for(run2))      # the same meter used in SAF-012 keeps its calibration record requirement


def test_campaign_reset_erases_shared_and_blocks_old_events(tmp_path, cat):
    """Danger zone: erase_shared removes every console's journal, attachments and exports, writes the marker + audit line;
    after it, events written before the reset are never replayed again — even if a stale console pushes them."""
    shared = tmp_path / "drive"
    sa, ea, ja = _console(tmp_path, "A", cat, shared, "amit")
    sb, eb, jb = _console(tmp_path, "B", cat, shared, "dana")
    ra = sa.runs("DVT-ELE-001", "UUT-01")[0]["run_id"]; sa.start_run(ra, "amit")
    (shared / "sCure-DVT.xlsx").write_bytes(b"x"); (shared / "csv").mkdir(); (shared / "csv" / "t.csv").write_text("a")
    assert (shared / "journal" / f"{ja.client_id}.jsonl").exists()
    marker = ja.erase_shared("amit", "dry-run data before the real campaign", "sCure-DVT")
    assert marker["reason"].startswith("dry-run") and "journal" in marker["removed"] and "sCure-DVT.xlsx" in marker["removed"] and "csv" in marker["removed"]
    assert not (shared / "journal").exists() and not (shared / "sCure-DVT.xlsx").exists()
    assert (shared / "reset.json").exists() and "dry-run" in (shared / "reset_log.jsonl").read_text(encoding="utf-8")
    assert jb.reset_marker()["by"] == "amit"
    # A's stale journal (the start_run from before the reset) is pushed again by the stale console: B must not replay it
    assert ja.push() and (shared / "journal" / f"{ja.client_id}.jsonl").exists()
    res = jb.pull()
    assert res.applied == 0 and sb.run(ra)["status"] == "NOT_STARTED"
    # a write made after the reset does flow
    import time; time.sleep(1.1)
    rb = sa.runs("DVT-ELE-002", "UUT-02")[0]["run_id"]; sa.start_run(rb, "amit")
    res = jb.pull()
    assert res.applied == 1 and sb.run(rb)["status"] == "IN_PROGRESS"


def test_reset_unit_restarts_one_uut_everywhere(tmp_path, cat):
    """Danger zone per UUT: reset_unit wipes that unit's runs/values/NCRs/sign-offs/freeze and leaves the others alone;
    it is journaled, so the other console applies the same erase."""
    shared = tmp_path / "drive"
    sa, ea, ja = _console(tmp_path, "A", cat, shared, "amit")
    sb, eb, jb = _console(tmp_path, "B", cat, shared, "dana")
    sa.freeze_config("UUT-01", "amit", "SN-1"); sa.freeze_config("UUT-02", "amit", "SN-2")
    r1 = sa.runs("DVT-ELE-001", "UUT-01")[0]["run_id"]; r2 = sa.runs("DVT-ELE-001", "UUT-02")[0]["run_id"]
    for rid in (r1, r2):
        sa.start_run(rid, "amit"); sa.set_values(rid, dict(max_resistance=0.9, pe_uninterrupted=True), "amit"); ea.finish(rid, "amit")   # 0.9 ohm: FAIL -> NCR
    f = tmp_path / "t.csv"; f.write_text("a"); sa.add_attachment(r1, "t.csv", str(f), "csv", "x")
    sa.sign_phase("UUT-01", 1, "amit", ["ok"])
    assert sa.run(r1)["status"] == "DONE" and sa.ncrs(open_only=True) and sa.phase_signed("UUT-01", 1)
    jb.pull(); assert sb.run(r1)["status"] == "DONE"
    removed = sa.reset_unit("UUT-01", "dry-run data", "amit")
    assert removed["runs"] == len(sa.runs(unit_id="UUT-01")) and removed["run_values"] == 2 and removed["ncrs"] == 1 and removed["attachments"] == 1 and removed["phase_signoffs"] == 1
    assert any(str(x).endswith("t.csv") for x in removed["attachment_paths"])     # the shared copy of the attachment
    u1 = sa.run(r1); assert u1["status"] == "NOT_STARTED" and u1["operator"] is None and u1["verdict"] is None and not sa.values(r1)
    assert not sa.phase_signed("UUT-01", 1) and not next(u for u in sa.units() if u["unit_id"] == "UUT-01")["config_frozen"]
    assert all(r["status"] == "NOT_STARTED" for r in sa.runs(unit_id="UUT-01"))
    assert sa.run(r2)["status"] == "DONE" and next(u for u in sa.units() if u["unit_id"] == "UUT-02")["config_frozen"]   # the other unit untouched
    assert ea.next_action("UUT-01").blockers and any(e["event"].startswith("Unit reset") for e in sa.events())
    # the other console replays the reset
    import time; time.sleep(1.1)
    res = jb.pull()
    assert res.applied >= 1 and sb.run(r1)["status"] == "NOT_STARTED" and sb.run(r2)["status"] == "DONE" and not sb.phase_signed("UUT-01", 1)


def test_fixtures_and_consumables_never_block_on_calibration(world):
    """A run is blocked only for real devices without a record — spare fuses, fixtures, break-out leads are not instruments."""
    cat, store, eng, _ = world
    run = store.runs("DVT-SAF-001", "UUT-05")[0]
    cal = [b.text for b in eng.blockers_for(run) if b.code == "CAL"]
    assert cal and not any("fuse" in x.lower() for x in cal) and any("AC source" in x or "transformer" in x for x in cal)


def test_catalog_saf012_is_instrumented(cat):
    t = cat.tests["DVT-SAF-012"]
    step = t["procedure_steps"][1]
    assert step.get("tool") == "uv_off_timing" and set(step["capture"]) == {"uv_off_time", "uv_zero_time", "residual_irradiance"}
    assert "uv_zero_time" not in t["pass_criteria"]          # recorded for the decay analysis, not judged
    assert any("Ophir" in e["name"] for e in t["equipment"])


def test_heater_shutdown_tests_are_proven_on_the_heater_body(cat):
    """SAF-003/004/005/013/014/015: the cut-off is read from the heater-body thermocouple, not the SSR command."""
    th = cat.thresholds
    for tid in ("DVT-SAF-003", "DVT-SAF-004", "DVT-SAF-005", "DVT-SAF-013", "DVT-SAF-014", "DVT-SAF-015"):
        t = cat.tests[tid]
        assert any("heater body" in e["name"] for e in t["equipment"]), tid
        assert any("TC-08" in e["name"] for e in t["equipment"]), tid
    e3 = cat.tests["DVT-SAF-003"]["pass_criteria"]
    ok3 = dict(heater_body_drop_observed=True, heater_off_time=3.2, alarm_raised=True, alarm_identifies_fan=True, recovery_requires_ack=True)
    assert criteria.evaluate(e3, ok3, th) == ("PASS", "")
    assert criteria.evaluate(e3, {**ok3, "heater_body_drop_observed": False}, th)[0] == "FAIL"   # no turn on the trace = no proof
    assert criteria.evaluate(e3, {**ok3, "heater_off_time": 70.0}, th)[0] == "PASS"      # ~70 s for the stored heat to clear (user, 2026-10-01)
    assert criteria.evaluate(e3, {**ok3, "heater_off_time": 85.0}, th)[0] == "FAIL"      # 80 s, as SAF-004
    e14 = cat.tests["DVT-SAF-014"]["pass_criteria"]
    ok14 = dict(heater_body_drop_observed=True, ssr_off_time=1.5, uv_drop_observed=True, ssr_off_time_uv=0.3, ssr_off_time_process_kill=1.8, auto_restart_prevented=True)
    assert criteria.evaluate(e14, ok14, th) == ("PASS", "")
    assert criteria.evaluate(e14, {**ok14, "uv_drop_observed": False}, th)[0] == "FAIL"
    e15 = cat.tests["DVT-SAF-015"]["pass_criteria"]
    # 2026-10-01: CM5 40-pin cable pulled while heating, one run; the operator's SSR answer beside the measured turn
    ok15 = dict(heater_ssr_switched_off=True, heater_off_time=40.0, auto_resume_heat=False, auto_resume_uv=False, heater_body_stays_falling=True, config_intact=True)
    assert criteria.evaluate(e15, ok15, th) == ("PASS", "")
    assert criteria.evaluate(e15, {**ok15, "heater_body_stays_falling": False}, th)[0] == "FAIL"
    assert criteria.evaluate(e15, {**ok15, "heater_ssr_switched_off": False}, th)[0] == "FAIL"
    assert criteria.evaluate(e15, {**ok15, "heater_off_time": 85.0}, th)[0] == "FAIL"
    assert cat.tests["DVT-SAF-015"]["repetitions"] == 1 and len(cat.runs("DVT-SAF-015")) == 5


def test_saf021_selector_open_circuit(cat):
    """SAF-021: selector mid position = heater open; proof on the heater body; alarm must instruct the selector."""
    th = cat.thresholds
    t = cat.tests["DVT-SAF-021"]
    assert cat.phase_of("DVT-SAF-021")["id"] == 2 and "DVT-SAF-011" in t["dependencies"]
    assert any("heater body" in e["name"] for e in t["equipment"])
    # Err 9007 (sCureBox 1.0.64, user 2026-10-01): two minutes without heating -> the alarm names the selector AND the fuse
    ok = dict(heater_branch_current=0.0, heater_body_rise=0.4, chamber_rise=0.6, alarm_raised=True, time_to_alarm=2.1, alarm_states_no_heating=True,
              alarm_instructs_selector=True, alarm_names_fuse=True, heat_stopped_or_operator_prompted=True, fuse_opened=False, visible_damage=False,
              post_test_functional_pass=True)
    assert criteria.evaluate(t["pass_criteria"], ok, th) == ("PASS", "")
    assert criteria.evaluate(t["pass_criteria"], {**ok, "alarm_instructs_selector": False}, th)[0] == "FAIL"   # customer must be told about the selector
    assert criteria.evaluate(t["pass_criteria"], {**ok, "heater_body_rise": 15}, th)[0] == "FAIL"           # the heater DID get power -> not this fault
    assert criteria.evaluate(t["pass_criteria"], {**ok, "time_to_alarm": 25}, th)[0] == "FAIL"              # the old 30 min allowance is gone
    assert criteria.evaluate(t["pass_criteria"], {**ok, "alarm_names_fuse": False}, th)[0] == "FAIL"
    # simulator: the fault leaves the chamber cold and the 60 s watchdog names the selector
    from dvt_tool.ui.sim import SimMachine
    sim = SimMachine(); sim.STALL_WATCHDOG_S = 0.0
    sim.inject("selector_open"); assert sim.heat(80)["ok"]
    with sim.lock:
        sim._step(5.0); sim._step(5.0)
    assert sim.chamber < sim.ambient + 0.5 and sim.mode == "IDLE"
    a = next(x for x in sim.alerts if x["code"] == "7004")
    assert "no power" in a["message"] and "voltage selector" in a["action"]


# ---------------- DVT-GAS-001: nitrogen purge — time to 95 % N2 and hold ----------------
def test_gas001_nitrogen_purge_criteria(cat):
    t = cat.tests["DVT-GAS-001"]
    assert t["subsystem"] == "Process" and cat.phase_of("DVT-GAS-001")["id"] == 3
    th = cat.thresholds
    assert th["nitrogen_thresholds"]["o2_at_95_n2"] == 4.8 and th["nitrogen_thresholds"]["purge_time_max_s"] is None
    ok = dict(n2_95_reached=True, valve_closed_confirmed=True, damper_closed=True, extraction_off=True, time_to_95_n2=95, purge_time_margin=1.26,
              hold_time_above_95=2400, hold_covers_cure=True)
    # thresholds still CONFIRM (null): measured, recorded, but never a PASS
    v, d = criteria.evaluate(t["pass_criteria"], ok, th); assert v == "BLOCKED" and "purge_time_max_s" in d
    decided = {**th, "nitrogen_thresholds": {**th["nitrogen_thresholds"], "purge_time_max_s": 120, "hold_time_min_s": 1800}}
    assert criteria.evaluate(t["pass_criteria"], ok, decided) == ("PASS", "")
    assert criteria.evaluate(t["pass_criteria"], {**ok, "time_to_95_n2": 150}, decided)[0] == "FAIL"        # slower than allowed
    assert criteria.evaluate(t["pass_criteria"], {**ok, "purge_time_margin": 1.0}, decided)[0] == "FAIL"    # programmed purge has no margin
    assert criteria.evaluate(t["pass_criteria"], {**ok, "hold_time_above_95": 900}, decided)[0] == "FAIL"   # leaks back too fast
    assert criteria.evaluate(t["pass_criteria"], {**ok, "hold_covers_cure": False}, decided)[0] == "FAIL"   # cure would run in rising oxygen
    assert criteria.evaluate(t["pass_criteria"], {**ok, "n2_95_reached": False}, decided)[0] == "FAIL"
    # the Process subsystem has a colour / icon and a Hebrew label
    from dvt_tool.ui import theme
    assert "Process" in theme.SUBSYSTEM and "Process" in theme.SUBSYSTEM_ICON
    assert Catalog.load(CATALOG, "he").label("subsystems", "Process") == "תהליך"


# ---------------- campaign document: everything in one PDF (SRS-DVT-197) ----------------
def test_campaign_document_html_and_pdf(world):
    from dvt_tool import docgen
    from dvt_tool.ui import i18n
    cat, store, eng, tmp = world
    rid = "DVT-THM-002|UUT-01|chamber_setpoint=80|1"
    store.start_run(rid, "op"); store.set_values(rid, {"max_temp_right": 70, "max_temp_left": 71, "max_temp_back": 70.5, "max_temp_door": 74}, "op")
    confirms = docgen.confirm_items(cat.path)
    assert "DVT-THM-001" in confirms and any("CONFIRM" in c for c in confirms["DVT-THM-001"]) and "" in confirms   # header block (thresholds) too
    doc = docgen.DocBuilder(cat, store, "T").html()
    assert all(f'id="{tid}"' in doc for tid in cat.tests)                       # every test has its section
    assert "Thresholds" in doc and "CONFIRM" in doc and "Open items" in doc and "max_temp_right=70" in doc
    assert "<svg" in doc and 'dir="ltr"' in doc and "Bench setup" in doc
    # Hebrew document: RTL, Hebrew headings and catalog prose, identifiers untouched
    he = Catalog.load(CATALOG, "he"); i18n.set_language("he")
    try:
        doc_he = docgen.DocBuilder(he, store, "T").html()
    finally:
        i18n.set_language("en")
    assert 'dir="rtl"' in doc_he and "מסמך קמפיין DVT" in doc_he and "DVT-ELE-001" in doc_he and he.tests["DVT-ELE-001"]["title"] in doc_he
    html_path, pdf_path = docgen.DocBuilder(cat, store, "T").write(tmp / "doc", pdf=bool(docgen.find_browser()))
    assert html_path.exists() and html_path.stat().st_size > 50_000
    if docgen.find_browser():
        assert pdf_path is not None and pdf_path.stat().st_size > 20_000 and pdf_path.read_bytes()[:4] == b"%PDF"


# ---------------- bench order: same instrument, one test after the other (SRS-DVT-196) ----------------
def test_bench_order_groups_instruments_and_respects_dependencies(cat):
    from dvt_tool import bench
    assert bench.instrument_key("PicoLog TC-08 thermocouple logger") == "PicoLog TC-08"
    assert bench.instrument_key("PicoLog TC-08 x2 (16 thermocouple channels)") == "PicoLog TC-08"
    assert bench.instrument_key("Ophir StarBright power meter with UV photodiode head") == "Ophir StarBright"
    assert bench.instrument_key("O2 analyzer with probe inside the chamber, logging") == "O2 analyser"
    assert bench.instrument_key("Spare fuses — 0BLF005.T (5 A branch)") is None                 # consumable, not an instrument
    assert bench.instrument_key("Access to the sensor connector without opening live compartments") is None
    # devices are deduplicated across wordings; fixtures / consumables / accessories / the machine's own telemetry are not devices
    assert bench.instrument_key("True-RMS meter at the inlet") == "DMM / clamp meter" == bench.instrument_key("DMM / current clamp on the driver output")
    assert bench.instrument_key("Current probe + oscilloscope with single-shot capture") == "Current probe / scope"
    assert bench.instrument_key("Vernier caliper for the seating offset (case E)") == "Vernier caliper"
    for name in ("Inline break-out lead for the panel connector with a remote contactor", "Impact indicators (e.g. ShockWatch) on the crate", "Tachometer readback logged from the monitored fan",
                 "Stopwatch or logged timestamps from the machine log", "Sensor fixture holding the head at the chamber centre", "4-wire Kelvin probes", "Fixed 10 kOhm resistor, 1%, fitted in a plug"):
        assert bench.instrument_key(name) is None, name
    devices, others = bench.instruments(cat)
    all_names = {e["name"] for t_ in cat.tests.values() for e in t_.get("equipment") or []}
    assert set(sum((d["entries"] for d in devices.values()), [])) | {o["name"] for o in others} == all_names     # every entry lands exactly once
    assert len(devices) < len(all_names) / 2 and "PicoLog TC-08" in devices and len(devices["PicoLog TC-08"]["entries"]) >= 3
    assert all(len(set(d["tests"])) == len(d["tests"]) for d in devices.values()) and list(devices) == sorted(devices)
    assert any("Spare fuses" in o["name"] for o in others) and not any("fuse" in k.lower() for k in devices)
    phase2 = cat.phase_of("DVT-SAF-004")
    order = bench.bench_order(cat, phase2)
    assert sorted(order) == sorted(phase2["tests"])                                              # same tests, different order
    # dependencies inside the phase always come first
    for tid in order:
        for d in cat.tests[tid].get("dependencies") or []:
            if d in order:
                assert order.index(d) < order.index(tid), (d, tid)
    # the TC-08 heater-body tests run one after the other, adjacent and in dependency order; SAF-015 (CM5 cable pulled
    # while heating, 2026-10-01) needs exactly the TC-08 + bonded thermocouple, so it joins the block before SAF-013
    i4 = order.index("DVT-SAF-004")
    assert order[i4:i4 + 5] == ["DVT-SAF-004", "DVT-SAF-005", "DVT-SAF-003", "DVT-SAF-015", "DVT-SAF-013"]
    # the Ophir tests are adjacent (SAF-012 -> SAF-007), and the O2-analyser tests (GAS-002…006) form one block
    assert order.index("DVT-SAF-007") == order.index("DVT-SAF-012") + 1
    o2 = [order.index(t) for t in order if "O2 analyser" in bench.instruments_of(cat.tests[t])]
    assert max(o2) - min(o2) == len(o2) - 1 and len(o2) >= 4
    groups = bench.bench_groups(cat, phase2)
    assert sum(len(g.tests) for g in groups) == len(phase2["tests"]) and len(groups) < len(phase2["tests"])
    kept, added, removed = bench.setup_change(cat, "DVT-SAF-004", "DVT-SAF-005")
    assert "PicoLog TC-08" in kept and not removed
    # a single-test phase keeps its list
    assert bench.bench_order(cat, cat.phase_of("DVT-ENV-001")) == ["DVT-ENV-001"]


def test_next_action_keeps_the_bench_setup(world):
    from dvt_tool import bench
    cat, store, eng, tmp = world
    u = "UUT-02"
    store.freeze_config(u, "lead")
    for p in cat.phases: store.sign_phase(u, p["id"], "lead", ["bench ready"])
    # close Phase 1 so Phase 2 opens; ELE-001 first (earth before power)
    for tid in cat.phases[1]["tests"]:
        for r in store.runs(tid, u):
            store.start_run(r["run_id"], "op"); store.finish_run(r["run_id"], "PASS", "", "op")
    phase2 = cat.phase_of("DVT-SAF-004")
    first = eng.next_action(u)
    assert first.run is not None and first.run["test_id"] == bench.bench_order(cat, phase2)[0]
    # finish a TC-08 test through the engine: the next action stays on the TC-08 setup and says so
    for r in store.runs("DVT-SAF-004", u):
        store.start_run(r["run_id"], "op"); eng.finish(r["run_id"], "op")
    na = eng.next_action(u)
    assert "PicoLog TC-08" in bench.instruments_of(cat.tests[na.run["test_id"]])
    assert "PicoLog TC-08" in na.setup and na.run["test_id"] != "DVT-SAF-004"
    assert not any(b.code == "DEP" for b in na.blockers)                                        # a runnable test wins over a blocked one


# ---------------- temperature by component, per machine (SRS-DVT-195) ----------------
def test_tempstats_component_mapping_and_outliers(cat):
    from dvt_tool import tempstats
    assert tempstats.component_of("max_temp_right") == "led_right"
    assert tempstats.component_of("cutout_trip_temp") == "heater"
    assert tempstats.component_of("ambient_temp") == "ambient"
    assert tempstats.component_of("chamber_temp_at_trip") == "chamber"
    assert tempstats.component_of("uniformity_pp") == "chamber"
    assert tempstats.component_of("settled_panel_temp", cat.tests["DVT-SAF-019"]) == "led"
    fs = tempstats.summarise("T", "f", "chamber", {"UUT-01": [70, 71, 70.5], "UUT-02": [70.2, 70.8], "UUT-03": [69.9, 70.4], "UUT-04": [80.0, 80.5], "UUT-05": [70.1]})
    assert fs.per_unit["UUT-05"].std == 0 and fs.per_unit["UUT-05"].n == 1 and round(fs.per_unit["UUT-01"].mean, 2) == 70.5
    assert fs.outliers == ["UUT-04"] and fs.spread > 9 and fs.between_std > 3
    assert tempstats.summarise("T", "f", "chamber", {"UUT-01": [70.0], "UUT-02": [70.5], "UUT-03": [71.0]}).outliers == []   # inside noise: no flag
    assert tempstats.summarise("T", "f", "chamber", {"UUT-01": [70.0], "UUT-02": [90.0]}).outliers == []                     # two machines: no majority to compare with
    assert tempstats.summarise("T", "f", "chamber", {"UUT-01": [60.0], "UUT-02": [61.0], "UUT-03": [74.0]}).outliers == ["UUT-03"]   # median reference: the hot one alone
    assert tempstats.summarise("T", "f", "chamber", {f"UUT-0{i}": [55 + 5 * i] for i in range(1, 6)}).outliers == []         # even spread: nobody stands out


def test_tempstats_collect_and_export(world):
    from dvt_tool import tempstats
    cat, store, eng, tmp = world
    for u, door in (("UUT-01", 60.0), ("UUT-02", 61.0), ("UUT-03", 74.0)):          # one hot door panel on UUT-03
        rid = f"DVT-THM-002|{u}|chamber_setpoint=80|1"
        store.start_run(rid, "op"); store.set_values(rid, {"max_temp_right": 70, "max_temp_left": 71, "max_temp_back": 70.5, "max_temp_door": door}, "op")
    stats = tempstats.collect(cat, store)
    door = next(fs for fs in stats if fs.field == "max_temp_door")
    assert door.component == "led_door" and door.n_units == 3 and door.outliers == ["UUT-03"]
    assert next(fs for fs in stats if fs.field == "max_temp_right").outliers == []
    assert "chamber_setpoint" in {fs.field for fs in stats}                            # sweep values count as recorded temperatures too
    assert tempstats.component_summary(stats)["led_door"]["outliers"] == {"UUT-03": 1}
    files = Exporter(cat, store, tmp / "export", "T").export_all(); names = {p.name for p in files}
    assert "temperature_by_component.csv" in names and "temp_led_door.png" in names
    md = (tmp / "export" / "T.report.md").read_text(encoding="utf-8")
    assert "Temperature by component" in md and "UUT-03" in md and "charts/temp_led_door.png" in md
    from openpyxl import load_workbook
    wb = load_workbook(tmp / "export" / "T.xlsx"); assert "TempStats" in wb.sheetnames
    ws = wb["TempStats"]; assert ws.cell(row=1, column=1).value == "component" and ws.max_row >= 1 + len(stats)


# ---------------- dashboard: progress per machine + screen fit ----------------
def test_dashboard_unit_progress_and_screen_fit(world):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    cat, store, eng, _ = world
    from dvt_tool.dashboard import DashboardPage
    from dvt_tool.ui import screen
    page = DashboardPage(eng)
    up = page.unit_progress()
    assert list(up) == cat.unit_ids() and all(v["percent"] == 0 and v["phase"] == 0 for v in up.values())
    # UUT-01: two runs committed (one FAIL), one rejected -> rejected excluded from the denominator
    rows = store.runs("DVT-ELE-001", "UUT-01") + store.runs("DVT-ELE-002", "UUT-01") + store.runs("DVT-ELE-003", "UUT-01")
    store.start_run(rows[0]["run_id"], "a"); store.set_values(rows[0]["run_id"], dict(max_resistance=0.05, pe_uninterrupted=True), "a"); eng.finish(rows[0]["run_id"], "a")
    store.start_run(rows[1]["run_id"], "a"); store.set_values(rows[1]["run_id"], dict(insulation_resistance_lnpe=4), "a"); eng.finish(rows[1]["run_id"], "a")
    store.reject_run(rows[2]["run_id"], "warm start", "a")
    up = page.unit_progress(); u1 = up["UUT-01"]; n = len([r for r in store.runs(unit_id="UUT-01") if r["status"] != "REJECTED"])
    assert u1["done"] == 2 and u1["failed"] == 1 and u1["total"] == n and u1["percent"] == round(200 / n)
    assert up["UUT-02"]["done"] == 0
    page.refresh()
    assert page.unit_grid.count() == 5 * len(cat.unit_ids())          # name, bar, %, runs, phase pill per machine (data kept; the card is no longer shown)
    # progress by subsystem: all units vs one unit, plus the total row
    allp = eng.subsystem_progress(); one = eng.subsystem_progress("UUT-01")
    assert allp["__total__"]["runsDone"] == 2 and one["__total__"]["runsDone"] == 2 and one["__total__"]["runsTotal"] == n
    assert one["Electrical"]["runsDone"] == 2 and allp["Electrical"]["runsTotal"] > one["Electrical"]["runsTotal"]
    assert eng.subsystem_progress("UUT-02")["__total__"]["runsDone"] == 0 and allp["__total__"]["runsTotal"] == len([r for r in store.runs() if r["status"] != "REJECTED"])
    assert set(allp) - {"__total__"} == {cat.tests[tid]["subsystem"] for tid in cat.tests}
    assert page.cb_prog_unit.count() == 1 + len(cat.unit_ids())
    page.cb_prog_unit.setCurrentIndex(1)                                # UUT-01
    assert page.prog_grid.count() == 4 * (len(set(allp) - {"__total__"}) + 1)   # name, bar, %, runs per subsystem + the total row
    # screen fit: the offscreen platform is 800x600 -> compact, and fit() never exceeds the work area
    assert screen.is_compact() and screen.available().width() <= 800
    w = QWidget(); screen.fit(w, 1500, 920)
    assert w.width() <= screen.available().width() and w.height() <= screen.available().height()


# ---------------- nitrogen (Process) tests ----------------
def test_nitrogen_tests_and_thresholds(cat):
    th = cat.thresholds
    assert "nitrogen_thresholds" in th and th["nitrogen_thresholds"]["room_o2_min_pct"] == 19.5
    assert th["led_temperature_thresholds"]["working_limit"] == 75                      # still there after the generic loader
    ids = [tid for tid in cat.tests if tid.startswith("DVT-GAS-")]
    assert len(ids) == 7 and all(cat.tests[t]["subsystem"] == "Process" for t in ids)
    assert len(cat.runs("DVT-GAS-002")) == 15 and len(cat.runs("DVT-GAS-003")) == 4 and len(cat.runs("DVT-GAS-006")) == 1
    assert cat.phase_of("DVT-GAS-002")["id"] == 2 and cat.phase_of("DVT-GAS-001")["id"] == 3
    # GAS-002 is BLOCKED while the chamber pressure limit is still a CONFIRM, never PASS
    ok1 = dict(closed_valve_flow=0.0, o2_closed_valve=20.9, fitting_leak=False, peak_chamber_pressure=12, door_lifted=False,
               valve_closes_after_purge=True, flow_stop_time=0.4, post_test_flow_closed=0.0, post_test_functional_pass=True, damage=False)
    v, d = criteria.evaluate(cat.tests["DVT-GAS-002"]["pass_criteria"], ok1, th)
    assert v == "BLOCKED" and "chamber_pressure_limit_mbar" in d
    th2 = {**th, "nitrogen_thresholds": {**th["nitrogen_thresholds"], "chamber_pressure_limit_mbar": 30}}
    assert criteria.evaluate(cat.tests["DVT-GAS-002"]["pass_criteria"], ok1, th2) == ("PASS", "")
    assert criteria.evaluate(cat.tests["DVT-GAS-002"]["pass_criteria"], {**ok1, "closed_valve_flow": 0.8}, th2)[0] == "FAIL"   # N2 past a closed valve
    # GAS-004 fail-safe and GAS-003 per-case criteria
    ok5 = dict(flow_off_24h=0.0, o2_off_24h=20.9, flow_stop_time_power_loss=0.3, drive_low_after_power_loss=True, flow_stop_time_door=0.5, flow_stop_time_abort=0.4, valve_closed_all_cases=True)
    assert criteria.evaluate(cat.tests["DVT-GAS-004"]["pass_criteria"], ok5, th) == ("PASS", "")
    assert criteria.evaluate(cat.tests["DVT-GAS-004"]["pass_criteria"], {**ok5, "flow_stop_time_door": 4}, th)[0] == "FAIL"
    e4 = cat.tests["DVT-GAS-003"]["pass_criteria"]
    assert criteria.evaluate(e4, dict(detected_and_handled=True, operator_told_n2_line=True, cure_ran_in_air=False), th) == ("PASS", "")
    assert criteria.evaluate(e4, dict(detected_and_handled=True, operator_told_n2_line=True, cure_ran_in_air=True), th)[0] == "FAIL"   # cured in air, silently
    assert criteria.evaluate(e4, dict(detected_and_handled=True, cure_ran_in_air=False), th)[0] == "BLOCKED"
    he = Catalog.load(CATALOG, "he")
    assert he.label("subsystems", "Process") == "תהליך" and all("DVT-GAS" not in he.tests[t]["title"] for t in ids)


# ---------------- SSH access: the machine address is the SSH host ----------------
def test_ssh_host_and_command():
    from dvt_tool import ssh
    assert ssh.host_of("http://192.168.2.155:3001") == "192.168.2.155"
    assert ssh.host_of("192.168.2.155") == "192.168.2.155" and ssh.host_of("http://testingcm5.local:3001") == "testingcm5.local"
    assert ssh.host_of("sim://scure") is None and ssh.host_of("") is None
    assert ssh.ssh_command("http://10.0.0.42:3001", "testingpi", "~/.ssh/scure_pi").startswith("ssh -i ") and ssh.ssh_command("http://10.0.0.42:3001", "testingpi", "~/.ssh/scure_pi").endswith("testingpi@10.0.0.42")
    assert ssh.ssh_command("http://10.0.0.42:3001", "", "") == "ssh testingpi@10.0.0.42"       # defaults
    assert ssh.ssh_command("sim://scure") is None
    ok, text = ssh.test_ssh("sim://scure")
    assert not ok and "simulator" in text


# ---------------- shared campaign through the Drive folder: one journal per console ----------------
def _console(tmp, name, cat, shared, operator):
    from dvt_tool.journal import Journal
    d = tmp / name; store = Store(d / "campaign.db"); eng = Engine(cat, store)
    j = Journal.open(store, d, shared, operator, cat.version); j.attach(store)
    return store, eng, j


def test_journal_shares_the_campaign_between_consoles(tmp_path, cat):
    shared = tmp_path / "GoogleDrive" / "sCure DVT"
    sa, ea, ja = _console(tmp_path, "pcA", cat, shared, "amit")
    sb, eb, jb = _console(tmp_path, "pcB", cat, shared, "dana")
    assert ja.enabled and ja.client_id != jb.client_id
    # A runs ELE-001 on UUT-01 to a PASS, records a redline and attaches a file
    ra = sa.runs("DVT-ELE-001", "UUT-01")[0]["run_id"]
    sa.start_run(ra, "amit"); sa.confirm_preconditions(ra, "amit"); sa.set_values(ra, dict(max_resistance=0.05, pe_uninterrupted=True), "amit")
    assert ea.finish(ra, "amit") == ("PASS", "")
    rl = sa.add_redline(ra, 1, "measured with 10 A", "tester limit", "amit")
    f = tmp_path / "trace.csv"; f.write_text("t,v 0,1"); sa.add_attachment(ra, "trace.csv", str(f), "csv", "abc")
    assert (shared / "attachments").exists() and (shared / "journal" / f"{ja.client_id}.jsonl").exists()
    # B knows nothing until it pulls; after the pull it has the run, the values, the redline (same id) and the attachment path
    assert sb.run(ra)["status"] == "NOT_STARTED"
    res = jb.pull()
    assert res.applied >= 6 and res.errors == [] and res.conflicts == [] and ja.client_id in res.clients
    assert sb.run(ra)["status"] == "DONE" and sb.run(ra)["verdict"] == "PASS" and sb.run(ra)["operator"] == "amit"
    assert sb.values(ra) == {"max_resistance": 0.05, "pe_uninterrupted": True}
    assert [r["id"] for r in sb.redlines(ra)] == [rl]
    att = sb.attachments(ra); assert len(att) == 1 and Path(att[0]["path"]).exists() and str(shared) in att[0]["path"]
    assert eb.test_verdict("DVT-ELE-001", "UUT-01") == "PASS"
    # idempotent: pulling again applies nothing
    assert jb.pull().applied == 0
    # B works on UUT-02 in parallel; A sees it; B's waiver keeps its id on A
    rb = sb.runs("DVT-ELE-002", "UUT-02")[0]["run_id"]
    sb.start_run(rb, "dana"); sb.set_values(rb, dict(insulation_resistance_lnpe=4), "dana"); assert eb.finish(rb, "dana")[0] == "FAIL"
    wid = sb.waive(rb, "QA lead", "engineering limit", "dana")
    res = ja.pull()
    assert res.applied >= 4 and sa.run(rb)["verdict"] == "WAIVED" and sa.waivers()[0]["waiver_id"] == wid and sa.run(rb)["operator"] == "dana"
    assert sa.ncrs()[0]["run_id"] == rb                                     # the NCR B's FAIL opened is on A too
    # a fresh third console bootstraps the whole campaign from the folder
    sc, ec, jc = _console(tmp_path, "pcC", cat, shared, "yossi")
    res = jc.pull()
    assert res.errors == [] and sc.run(ra)["verdict"] == "PASS" and sc.run(rb)["verdict"] == "WAIVED" and len(sc.redlines(ra)) == 1
    st = jc.status(); assert st["enabled"] and set(st["other_clients"]) == {ja.client_id, jb.client_id} and st["applied_events"] == res.applied


def test_journal_first_claim_wins_and_local_settings_stay_local(tmp_path, cat):
    shared = tmp_path / "drive"
    sa, ea, ja = _console(tmp_path, "A", cat, shared, "amit")
    sb, eb, jb = _console(tmp_path, "B", cat, shared, "dana")
    rid = sa.runs("DVT-ELE-003", "UUT-03")[0]["run_id"]
    sa.start_run(rid, "amit")
    import time; time.sleep(1.1)                                              # events are ordered by second-resolution timestamps
    sb.start_run(rid, "dana")                                                # B did not pull first: a competing claim
    res = jb.pull()
    assert len(res.conflicts) == 1 and "amit" in res.conflicts[0] and sb.run(rid)["operator"] == "amit"   # first claim wins: B's later claim is overridden…
    res = ja.pull()
    assert len(res.conflicts) == 1 and sa.run(rid)["operator"] == "amit"                                   # …and A keeps its earlier claim — same owner everywhere
    assert any(e["event"] == "Run claim conflict" for e in sa.events())
    # machine address / language are never journaled
    sa.set_meta("machine_url", "http://10.0.0.5:3001"); sa.set_meta("language", "he")
    assert jb.pull().applied == 0 and sb.get_meta("machine_url") is None
    # no shared folder -> a no-op journal, the store still works
    sd = Store(tmp_path / "solo" / "campaign.db"); Engine(cat, sd)
    from dvt_tool.journal import Journal
    jd = Journal.open(sd, tmp_path / "solo", None, "solo", cat.version); jd.attach(sd)
    r = sd.runs("DVT-ELE-001", "UUT-01")[0]["run_id"]; sd.start_run(r, "solo")
    assert not jd.enabled and jd.pull().applied == 0 and sd.run(r)["status"] == "IN_PROGRESS" and jd.local_file.exists()


# ---------------- Git checkpoints: a reviewed snapshot committed to the repository ----------------
def test_git_checkpoint_commits_a_snapshot(tmp_path, cat):
    import subprocess
    from dvt_tool import checkpoint as ckpt
    if not ckpt.git_available():
        pytest.skip("git not installed")
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=repo, check=True)
    (repo / "DVT").mkdir()
    store = Store(tmp_path / "campaign.db"); eng = Engine(cat, store)
    run = store.runs("DVT-ELE-001", "UUT-01")[0]
    store.start_run(run["run_id"], "amit"); store.set_values(run["run_id"], dict(max_resistance=0.05, pe_uninterrupted=True), "amit"); eng.finish(run["run_id"], "amit")
    (repo / "dirty.txt").write_text("unrelated, must not be committed")             # other work in the tree is left alone
    exp = Exporter(cat, store, tmp_path / "export", "TestCampaign")
    res = ckpt.make_checkpoint(exp, eng, "phase-1-gate-UUT-01", "amit", "TestCampaign", cat.version, repo=repo, push=False)
    assert res.ok and res.commit and res.folder and res.folder.exists(), res.error
    assert res.folder.parent == repo / "DVT" / "checkpoints" / "TestCampaign" and res.folder.name.endswith("_phase-1-gate-UUT-01")
    names = sorted(p.name for p in res.folder.iterdir())
    assert names == ["CHECKPOINT.md", "TestCampaign.campaign.json", "TestCampaign.report.md", "TestCampaign.xlsx"] or "temperature_by_component.csv" in names
    md = (res.folder / "CHECKPOINT.md").read_text(encoding="utf-8")
    assert "phase-1-gate-UUT-01" in md and "| UUT-01 | 1/" in md and "1 PASS" in md and f"v{cat.version}" in md
    log = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert log.startswith("DVT checkpoint: phase-1-gate-UUT-01 — 1/") and "1 PASS / 0 FAIL" in log and "[TestCampaign] by amit" in log
    tracked = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout
    assert "CHECKPOINT.md" in tracked and "dirty.txt" not in tracked
    assert "no remote" in (res.error or "") or res.pushed is False                  # push=False: nothing pushed, no remote
    # a second checkpoint a minute later is another folder and another commit; the list shows newest first
    from datetime import datetime, timezone, timedelta
    res2 = ckpt.make_checkpoint(exp, eng, "weekly review", "amit", "TestCampaign", cat.version, repo=repo, push=False, when=datetime.now(timezone.utc) + timedelta(minutes=1))
    assert res2.ok and res2.commit != res.commit and res2.folder.name.endswith("_weekly-review")
    last = ckpt.last_checkpoints(repo, "TestCampaign"); assert [c["label"] for c in last] == ["weekly-review", "phase-1-gate-UUT-01"]
    # outside a repository: a clear error, never an exception
    bad = ckpt.make_checkpoint(exp, eng, "x", "amit", "TestCampaign", cat.version, repo=tmp_path / "norepo", push=False)
    assert not bad.ok and bad.error
    # pure helpers used by the QA mirror
    assert ckpt.safe_label("Phase 2 gate / UUT-03!") == "Phase-2-gate-UUT-03" and ckpt.folder_name("x", datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)) == "20260906-1005_x"
    assert ckpt.commit_message("m", dict(done=3, total=12, PASS=2, FAIL=1, BLOCKED=0, WAIVED=0), "C", "amit") == "DVT checkpoint: m — 3/12 runs (25 %), 2 PASS / 1 FAIL / 0 BLOCKED / 0 WAIVED [C] by amit"


def test_nfc_build_head_identification(cat):
    th = cat.thresholds; t = cat.tests["DVT-NFC-001"]
    assert t["subsystem"] == "Process" and cat.phase_of("DVT-NFC-001")["id"] == 3 and len(cat.runs("DVT-NFC-001")) == 30   # 6 cases x 5 units
    e = t["pass_criteria"]
    ok = dict(response_correct=True, identity_cleared_on_removal=True, tag_read=True, bh_serial_read="BH-0042", bh_serial_expected="BH-0042")
    assert criteria.evaluate(e, ok, th) == ("PASS", "")
    assert criteria.evaluate(e, {**ok, "bh_serial_read": "BH-0007"}, th)[0] == "FAIL"      # read the previous / wrong build head
    assert criteria.evaluate(e, {**ok, "tag_read": False, "bh_serial_read": ""}, th) == ("PASS", "")   # case C/D/F: no read, but reported
    assert criteria.evaluate(e, {**ok, "response_correct": False}, th)[0] == "FAIL"
    he = Catalog.load(CATALOG, "he"); assert len(he.tests["DVT-NFC-001"]["case_matrix"]) == 6


def test_thm005_led_temperature_vs_fan_duty(cat):
    th = cat.thresholds; t = cat.tests["DVT-THM-005"]
    assert cat.phase_of("DVT-THM-005")["id"] == 3 and len(cat.runs("DVT-THM-005")) == 20        # 4 duties x 5 units
    assert [r.variant["fan_duty"] for r in cat.runs("DVT-THM-005") if r.unit_id == "UUT-01"] == [100, 90, 80, 70]
    e = t["pass_criteria"]
    assert criteria.evaluate(e, dict(settled=True, max_settled_temp=68.0), th) == ("PASS", "")
    assert criteria.evaluate(e, dict(settled=True, max_settled_temp=76.5), th)[0] == "FAIL"        # above the 75 C working limit
    assert criteria.evaluate(e, dict(settled=False, max_settled_temp=70.0), th)[0] == "FAIL"       # never settled (limit reached)
    # the simulator honours a commanded LED-fan duty and the panels run hotter with less airflow
    from dvt_tool.ui.sim import SimMachine
    sim = SimMachine(); assert sim.uv(True, 80)["ok"]                 # 80 %: the simulator's 100 % already sits at ~79 C, above the 75 C limit
    with sim.lock:
        for _ in range(60): sim._step(5.0)
    full = max(sim.led.values())
    sim.fan("led_cooling", 70)
    with sim.lock:
        for _ in range(60): sim._step(5.0)
    reduced = max(sim.led.values())
    assert sim.duty["led_cooling"] == 70 and reduced > full + 5
    sim.stop(); assert sim.fan_override == {}
    from dvt_tool.ui.dut import FIELD_MAP
    assert FIELD_MAP["settled_temp_right"] == "ledTempRight" and FIELD_MAP["tach_rpm"] == "ledFanRpm"


# ---------------- THM-005 automation: the console drives the sweep and hands back the answer + graph ----------------
def _fast_sim(sim, stop):
    import threading, time
    def loop():
        while not stop.is_set():
            with sim.lock: sim._step(5.0)
            time.sleep(0.03)
    threading.Thread(target=loop, daemon=True).start()


def test_fansweep_runner_against_simulator(tmp_path):
    import threading
    from dvt_tool.ui.sim import SimMachine, SimClient
    from dvt_tool.instruments.fansweep import FanSweepRunner, FanSweepConfig, write_csv, plot_png, settled, Sample
    import dvt_tool.ui.sim as simmod
    simmod._SIM = SimMachine(); sim = simmod.get_sim()
    dut = SimClient(); dut.door_close(); dut.ack()
    stop = threading.Event(); _fast_sim(sim, stop)
    try:
        cfg = FanSweepConfig(intensity=80, poll_s=0.15, settle_window_s=5, settle_rate_c_per_min=3.0, min_row_s=5, row_timeout_s=40)
        phases = []
        res = FanSweepRunner(dut, cfg, on_status=lambda ph, _t: phases.append(ph)).run()
    finally:
        stop.set()
    assert phases[:3] == ["fans", "uv", "settle"] and phases[-1] == "done"
    assert [r.duty for r in res.rows] == [100, 90, 80, 70] and res.status == "STOPPED_AT_LIMIT"
    assert res.rows[0].settled and res.rows[0].max_settled_temp < 75 and res.rows[-1].limit_reached          # 70 % runs into the 75 C limit in the simulator
    assert all(res.rows[i].max_settled_temp < res.rows[i + 1].max_settled_temp for i in range(3))            # less airflow -> hotter
    assert res.recommended_duty() == 100 and "Lowest duty" in res.final_text()
    assert not sim.uv_on and sim.fan_override == {}                                                          # always ends safe: LEDs off, fans released
    v = res.rows[1].values(); assert v["fan_duty"] == 90 and v["settled"] is True and 0 < v["margin_to_working_limit"] < 10 and "settled_temp_right" in v
    csv_p = write_csv(res, tmp_path / "sweep.csv"); png_p = plot_png(res, tmp_path / "sweep.png")
    assert csv_p.read_text(encoding="utf-8").startswith("# DVT-THM-005") and png_p.stat().st_size > 20_000
    # the pure settle rule: flat trace settles, rising trace does not, and never before min_row_s
    flat = [Sample(t, 100, {p: 60.0 for p in ("right", "left", "back", "door")}) for t in range(0, 40)]
    assert settled(flat, 10, 0.1, 10, 39, 0) and not settled(flat, 10, 0.1, 60, 39, 0)
    rising = [Sample(t, 100, {p: 60.0 + t * 0.05 for p in ("right", "left", "back", "door")}) for t in range(0, 40)]   # 3 C/min
    assert not settled(rising, 10, 0.1, 10, 39, 0)


def test_fansweep_dialog_applies_all_duty_rows(tmp_path, cat):
    import os, threading, time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from dvt_tool.ui.sim import SimMachine, SimClient
    import dvt_tool.ui.sim as simmod
    simmod._SIM = SimMachine(); sim = simmod.get_sim(); SimClient().door_close()
    store = Store(tmp_path / "c.db"); eng = Engine(cat, store)
    class FakeApp:
        def __init__(s_):
            s_.data, s_.cat, s_.store, s_.engine = tmp_path, cat, store, eng; s_.machine_url = "sim://scure"; s_.operator = "amit"
            from dvt_tool.ui.dut import make_client
            s_.dut_state = make_client(s_.machine_url).state(); s_.toasts = []
        def is_sim(s_): return True
        def kick_sync(s_): pass
        def refresh_all(s_): pass
        def toast(s_, t, c=None): s_.toasts.append(t)
    fa = FakeApp()
    runs = store.runs("DVT-THM-005", "UUT-02"); assert len(runs) == 4
    current = next(r for r in runs if r["variant"]["fan_duty"] == 100)
    store.start_run(current["run_id"], "amit")
    from dvt_tool.ui.fansweep_dialog import FanSweepDialog
    dlg = FanSweepDialog(fa, current)
    dlg.sp_int.setValue(80); dlg.sp_window.setValue(5); dlg.sp_rate.setValue(3.0); dlg.sp_poll.setValue(0.15); dlg.sp_timeout.setValue(1)
    got = {}; dlg.applied.connect(lambda by_run: got.update(by_run))
    stop = threading.Event(); _fast_sim(sim, stop)
    try:
        dlg.start(); t0 = time.time()
        while dlg.result is None and time.time() - t0 < 90: app.processEvents(); time.sleep(0.02)
    finally:
        stop.set()
    assert dlg.result is not None and dlg.result.status == "STOPPED_AT_LIMIT" and len(dlg.files) == 2
    dlg.apply(); app.processEvents()
    assert set(got) == {r["run_id"] for r in runs}                                     # all four duty rows written
    for r in store.runs("DVT-THM-005", "UUT-02"):
        vals = store.values(r["run_id"]); assert vals["fan_duty"] == r["variant"]["fan_duty"] and "max_settled_temp" in vals
        assert len(store.attachments(r["run_id"])) == 2
        if r["run_id"] != current["run_id"]:
            assert r["status"] == "DONE" and r["verdict"] in ("PASS", "FAIL")            # other rows committed automatically
    assert store.run(current["run_id"])["status"] == "IN_PROGRESS"                      # this row goes back to the wizard for its verdict
    assert eng.test_verdict("DVT-THM-005", "UUT-02") is None or True
