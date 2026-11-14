"""Browser test of the portal's DVT tab: python cloud/google/test_page.py [--shots DIR]

Loads Page.html with a stand-in for google.script.run (no Apps Script), feeds it the REAL catalog (built by the DVT runner
code from DVT/catalog) and checks that an opened test shows what the DVT tool shows: purpose, equipment, preconditions, the
numbered procedure, the pass criteria, and - for a bench test - the live checks of the runner with a Run button that only
turns on when everything is green.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHOTS = None
if "--shots" in sys.argv:
    SHOTS = Path(sys.argv[sys.argv.index("--shots") + 1])
    SHOTS.mkdir(parents=True, exist_ok=True)

checks = 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(msg)
    print("  ok:", msg)


def real_catalog():
    """The catalog the runner publishes (with each test's detail) - from the real DVT files."""
    js = r"""
const { createRunner } = require(process.argv[2]);
const posts = [];
const r = createRunner({ portalUrl: 'https://portal/exec', key: 'k', machine: 'CureBox-1', unit: 'UUT-01', machineApi: 'http://127.0.0.1:3001',
  resultsFile: require('os').tmpdir() + '/dvt-page-test-results.json' },
  { log: () => {}, sleep: async () => {}, fetch: async (u, o) => { posts.push(JSON.parse(o.body)); return { status: 200, text: async () => '{"ok":true}', json: async () => ({ ok: true }) }; } });
r.hello().then(() => process.stdout.write(JSON.stringify(posts.find((p) => p.kind === 'dvt_catalog').catalog)));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False, encoding="utf-8") as f:
        f.write(js)
    out = subprocess.run(["node", f.name, str(REPO / "DVT" / "runner" / "dvt-runner.cjs")], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


STUB = """
window.__calls = [];
window.__state = %STATE%;
window.google = { script: { run: new Proxy({}, { get: (_, fn) => {
  if (fn === 'withSuccessHandler' || fn === 'withFailureHandler') return function () { return this; };
  return undefined; } }) } };
(function () {
  const S = window.__state;
  const handlers = {
    portalLogin: () => ({ ok: true, token: 'tok' }),
    portalMachines: () => S.machines,
    portalAlerts: () => [],
    portalDvt: () => {
      window.__dvtPolls = (window.__dvtPolls || 0) + 1;
      const cat = JSON.parse(JSON.stringify(S.catalog));
      Object.values(cat.tests).forEach((t) => { t.hasDetail = !!t.d; delete t.d; });
      return { runs: [], fileUrl: '', catalog: Object.assign(cat, { updated: S.updated }), requests: S.requests, build: '0.9.102',
               runners: [{ machine: 'CureBox-1', unit: 'UUT-01', version: '0.9.101', online: S.online, lastSeen: 1, readiness: S.readiness }] };
    },
    portalDvtWait: (tok, since) => { window.__waits = (window.__waits || 0) + 1; return { __delay: 600, value: { ver: String(S.ver || 1) } }; },
    portalDvtDetail: () => { window.__detailFetches = (window.__detailFetches || 0) + 1;
      const tests = {}; Object.entries(S.catalog.tests).forEach(([k, t]) => { if (t.d) tests[k] = t.d; }); return { updated: S.updated, tests }; },
    portalDvtRequest: (tok, machine, unit, ids) => { window.__calls.push({ machine, unit, ids }); S.requests.push({ id: S.requests.length + 1, machine, unit, testId: ids[0], status: 'queued' }); return { ok: true, queued: ids.length, skipped: 0 }; },
  };
  const orig = window.google.script.run;
  window.google.script.run = { withSuccessHandler(ok) { return { withFailureHandler(bad) { return new Proxy({}, { get: (_, fn) => (...args) => {
    setTimeout(() => { try { const h = handlers[fn]; if (!h) throw new Error('no stub for ' + fn); const out = h(...args);
      if (out && out.__delay) setTimeout(() => ok(out.value), out.__delay); else ok(out); } catch (e) { bad(e); } }, 0); } }); } }; } };
})();
"""

ROWS_OK = {k: {"ok": True, "text": t} for k, t in
           {"machine": "connected", "svc": "sCureBox 1.0.91", "tc08": "30.5 °C", "chamber": "22.8 °C", "idle": "nothing running"}.items()}


def open_page(browser, state):
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(STUB.replace("%STATE%", json.dumps(state)))
    page.add_init_script("localStorage.setItem('scure-curebox', 'CureBox-1'); localStorage.setItem('scure-dvt-unit', 'UUT-01');")
    page.goto((HERE / "Page.html").as_uri())
    return ctx, page, errors


def go_dvt(page):
    # sign in (the page asks for the portal password first), then open the DVT tab
    page.wait_for_selector("#pw, [data-view=dvt]", timeout=10000)
    if page.locator("#pw").count():
        page.fill("#pw", "pw")
        page.keyboard.press("Enter")
    page.wait_for_selector("[data-view=dvt]", timeout=10000)
    page.locator("[data-view=dvt]").first.click()
    page.wait_for_selector("[data-dvt-test]", timeout=10000)


def main():
    cat = real_catalog()
    check(len(cat["tests"]) == 41 and all(t.get("d", {}).get("steps") for t in cat["tests"].values()), "the real catalog carries steps for all 41 tests")
    base = {"catalog": cat, "updated": 1760000000, "requests": [], "online": True, "readiness": None,
            "machines": [{"name": "CureBox-1", "online": True, "lastSeen": 1, "state": {}, "runs": [], "errors": []}]}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        print("a test opened shows the description")
        ctx, page, errors = open_page(browser, dict(base))
        go_dvt(page)
        page.wait_for_function("(window.__detailFetches || 0) >= 1")
        check(page.evaluate("window.__detailFetches") == 1, "the detail is fetched once, not on every poll")
        page.locator("[data-dvt-test='DVT-ELE-001']").click()
        page.wait_for_selector(".dvt-detail")
        body = page.inner_text(".dvt-detail")
        t = cat["tests"]["DVT-ELE-001"]["d"]
        check("PURPOSE" in body.upper() and t["purpose"][:60] in body, "purpose is shown")
        check(all(e[:40] in body for e in t["equipment"]), "every equipment line is shown")
        check(all(pc[:40] in body for pc in t["preconditions"]), "every precondition is shown")
        steps = page.locator(".dvt-steps li").all_inner_texts()
        check(len(steps) == len(t["steps"]) and steps[0].startswith(t["steps"][0][:40]), f"all {len(steps)} procedure steps, in order")
        check(page.locator(".dvt-crit code").inner_text().strip() == t["criteria"], "the pass criteria are shown")
        check(page.locator(".dvt-cols").count() == 1, "equipment and preconditions sit side by side")
        shot = lambda name: page.screenshot(path=str(SHOTS / name), full_page=True) if SHOTS else None
        shot("10-test-open.png")
        # the same detail does not need a second download when the page polls again
        page.evaluate("loadDvt()")
        page.wait_for_timeout(300)
        check(page.evaluate("window.__detailFetches") == 1, "polling again does not refetch the detail")
        check(not errors, "no script errors: %s" % errors)
        ctx.close()

        print("the DVT tab is held open by a long poll and reloads the moment something changed")
        ctx, page, errors = open_page(browser, dict(base))
        go_dvt(page)
        page.wait_for_function("(window.__waits || 0) >= 2")          # the first answer (version 1) was handled and the page asked again
        check(page.evaluate("DVT_VER") == "1", "the page remembers the version it was told")
        before = page.evaluate("window.__dvtPolls || 0")
        page.evaluate("window.__state.ver = 7")                         # the runner updated something: the next answer carries a new version
        page.wait_for_function("DVT_VER === '7'", timeout=4000)         # only the long poll sets this
        page.wait_for_function("(window.__dvtPolls || 0) > %d" % before, timeout=3000)
        check(True, "a new version reloads the DVT data at once")
        check(page.evaluate("window.__waits") >= 3, "and the page asks again straight away: %s long polls" % page.evaluate("window.__waits"))
        check(not errors, "no script errors: %s" % errors)
        ctx.close()

        print("a bench test shows the live checks")
        rows_bad = dict(ROWS_OK, tc08={"ok": False, "text": "plug the TC-08 into the machine's USB"})
        ctx, page, errors = open_page(browser, dict(base, readiness={"DVT-SAF-002": {"ready": False, "rows": rows_bad}}))
        go_dvt(page)
        page.locator("[data-dvt-test='DVT-SAF-002']").click()
        page.wait_for_selector(".dvt-auto .dvt-chk")
        labels = page.locator(".dvt-chk .lab").all_inner_texts()
        check(labels == ["Machine connected", "DVT bench service on the machine (port 3002)", "Thermocouple on CH1 (at the cutout)",
                         "Heater thermistor (TEMP_CHAMBER) reading", "Machine idle"], "the five checks of the DVT tool, in its order")
        classes = page.locator(".dvt-chk").evaluate_all("els => els.map(e => e.className.replace('dvt-chk', '').trim())")
        check(classes == ["ok", "ok", "bad", "ok", "ok"], f"green and red like the tool: {classes}")
        check("plug the TC-08" in page.locator(".dvt-chk.bad .val").inner_text(), "the reason is on the red row")
        check(page.locator("[data-dvt-run-card]").is_disabled(), "Run stays off while a check is red")
        check("Run is enabled when all checks are green" in page.inner_text(".dvt-auto"), "and says why")
        check("Automatic on the machine" in page.locator(".dvt-auto .note").inner_text(), "the bench's introduction is shown")
        check(page.locator(".dvt-steps li").count() == 6, "its six procedure steps")
        shot("11-bench-not-ready.png")
        ctx.close()

        ctx, page, errors = open_page(browser, dict(base, readiness={"DVT-SAF-002": {"ready": True, "rows": ROWS_OK}}))
        go_dvt(page)
        page.locator("[data-dvt-test='DVT-SAF-002']").click()
        page.wait_for_selector("[data-dvt-run-card]")
        check(page.locator("[data-dvt-run-card]").is_enabled(), "Run turns on when every check is green")
        check(page.locator(".dvt-chk.ok").count() == 5, "five green rows")
        shot("12-bench-ready.png")
        page.locator("[data-dvt-run-card]").click()
        page.wait_for_function("window.__calls.length === 1")
        check(page.evaluate("window.__calls[0]") == {"machine": "CureBox-1", "unit": "UUT-01", "ids": ["DVT-SAF-002"]}, "Run queues the test on this CureBox")
        page.wait_for_function("document.querySelector('[data-dvt-run-card]') === null || document.querySelector('[data-dvt-run-card]').disabled")
        check("queued" in page.inner_text(".dvt-auto"), "the card says it waits for Start at the machine")
        check(not errors, "no script errors: %s" % errors)
        ctx.close()

        print("no live checks without a runner")
        ctx, page, errors = open_page(browser, dict(base, online=False, readiness=None))
        go_dvt(page)
        page.locator("[data-dvt-test='DVT-SAF-002']").click()
        page.wait_for_selector(".dvt-auto .dvt-chk")
        check("is not online" in page.inner_text(".dvt-auto"), "an offline runner is explained")
        check(page.locator("[data-dvt-run-card]").is_disabled(), "Run is off")
        check(page.locator(".dvt-chk.ok, .dvt-chk.bad").count() == 0, "no row claims a state it does not know")
        ctx.close()

        print("an old catalog without detail")
        old = json.loads(json.dumps(cat))
        for t in old["tests"].values():
            t.pop("d", None)
        ctx, page, errors = open_page(browser, dict(base, catalog=old))
        go_dvt(page)
        page.locator("[data-dvt-test='DVT-ELE-001']").click()
        page.wait_for_selector(".dvt-runs")
        check("not in the portal yet" in page.inner_text(".dvt-runs"), "tells where the description comes from instead of showing nothing")
        check(not errors, "no script errors: %s" % errors)
        ctx.close()
        browser.close()
    print(f"\nALL PASSED ({checks} checks)")


if __name__ == "__main__":
    main()
