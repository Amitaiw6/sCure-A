## sCure Cloud portal — Errors, DVT, programs, people, simulation

These tickets rebuild the views in `cloud/google/Page.html` (portal build `PORTAL_BUILD = '0.9.146'`) that are not Overview, Machines, Race or Compare. The page is one HTML file served by Apps Script `doGet`. A shim at the top of the page replaces `window.fetch` and turns `/api/...` paths into `google.script.run.<portalFn>(token, ...)` calls. The shim, the theme tokens, the header, the section bar (`VIEW`), the CureBox chooser (`SELECTED`, `SEARCH`), `render()`, `load()` and `refreshLoop()` belong to **CLOUD-20..39 (shell)**. The server functions (`portalAlerts`, `portalDvt*`, `portalUser*`, `portalCommand`, `need_`, `authed_` ...) belong to **CLOUD-01..19 (server)**. They are named exactly here so the page can call them, but the server work is ticketed there.

Shared look rules for every ticket below (from the `:root` tokens, Page.html 127-158):
- Light tokens: `--bg #f5f6f8`, `--panel #ffffff`, `--line #e3e6eb`, `--line2 #cfd4dc`, `--text #14181f`, `--mut #5b6472`, `--acc #2457d6` (cobalt, primary buttons and progress), `--ok #15803d`, `--err #c62828`, `--warn #b45309`, `--inset #f0f2f5`.
- Dark tokens: `--bg #0e1116`, `--panel #171b22`, `--acc #7da2ff`, `--ok #4ade80`, `--err #f87171`, `--warn #fbbf24`.
- Font: IBM Plex Sans 15px/1.5.
- Shapes: cards are 12 px radius with 1.1rem×1.3rem padding; `h2` is 1.1rem/650 in the text colour (never blue).
- Pills: `.pill.on` is green, `.pill.off`/`.pill.bad` are red, `.pill.warn` is amber (#d97706).
- Phone breakpoint `max-width:640px`:
  - inputs and buttons are at least 44 px tall with 16 px text;
  - list tables with `class="cards"` become one card per row: the header row is hidden, the first cell is the bold title, and the other cells show their `data-l` label in small uppercase on the left.
- The screenshots `live-simulation.png`, `run-window.png` and `simulation-howto.png` (Hebrew captions, captured 2026-10-18..21) show the guide window with black primary buttons. That is the older palette. Build with the current cobalt `--acc` tokens; the layout in the screenshots is still current.

---

### CLOUD-40 — Errors view: "Errors today" (alerts log)
**Project / folder:** cloud/google/Page.html
**Goal:** Show every alert raised since local midnight on any CureBox, plus any older alert that is still active, with its registry title, an optional repair-video link and how long it lasted. This is the portal's read-only alerts log. It is filtered by the CureBox chooser and the search box.
**Depends on:** CLOUD-20..39 (shell), CLOUD-41, server `portalAlerts`
**Files to create:** Page.html: `loadErrors()`, `errorsCard()`, `errTitle`, `fmtTime`, `fmtDur`, global `ERRORS`.
**Public contract:**
- `GET /api/alerts?since=<unix s>` maps to `portalAlerts(token, since)`.
  - Returns an array, newest first: `{machine, code, raised, cleared|null, message, title, videoUrl}`.
  - Returns `null` when not signed in; the shim turns that into 401.
- The server returns rows with `raised >= since` **or** `cleared == null`.
- Sheet `alerts` columns: `machine, code, raised, cleared, message`. It is written by the machine sync (PLAT-10); one row per machine + code + raised time.
- Page state: `ERRORS` (`null` = loading).
**Behaviour & rules:**
1. Entering the section: the Errors button sets `VIEW='errors'`, **forces `SELECTED='all'`**, renders, then calls `loadErrors()`. `load()` also calls `loadErrors()` on every refresh tick while `VIEW==='errors'` (10 s cadence, shell).
2. `since` is the browser's local midnight: `Math.floor(midnight/1000)`.
3. Filters:
   - CureBox: when `SELECTED !== 'all'`, keep only `e.machine === SELECTED`.
   - Search: the trimmed, lower-cased `SEARCH` must appear in machine, `String(code)`, the title or the message.
4. Title: `e.title`, else `CODE_TITLES[code]` (a built-in fallback for 6016, 7004, 9001–9007, 9050–9052), else `'Error ' + code`.
5. Status:
   - Active (`cleared == null`): a red pill `active · <fmtDur(now - raised)>`.
   - Cleared: muted text `cleared HH:MM:SS · lasted <fmtDur(cleared - raised)>`.
   - `fmtDur`: below 60 s it is `N s`; below 1 h it is `M min S s`; otherwise `H h M min`.
6. Video link: only when `videoUrl` matches `^https?:\/{2}`. Write the regex with `\/{2}`, never `//`: Apps Script's HTML service cuts a line at `//`, even inside a regex.
7. The machine message is HTML-escaped; the title is escaped with `escH`.
8. Choosing a CureBox chip while on Errors switches to `VIEW='machines'` (shell `pick`).
9. The page never re-renders while `userBusy()` is true.
**Look & layout:**
- One card.
- `h2` "Errors today", followed in muted normal weight by "`N raised` · `M still active`" (the second part only when M > 0).
- Table `class="cards"` with the columns Time (HH:MM:SS) | Machine | **Code** (bold) | Error | Status.
  - The Error cell (`class="wide"`) shows the bold title, then a link "▶ Video" (`a.vid`: 0.78rem, 600 weight, blue #2563eb, opens in a new tab, `rel=noopener`), then a line break and the muted message.
- Empty: one row "No errors today" spanning 5 columns. Loading: card "Errors today" / "Loading…".
- Search placeholder (shell chooser): "Search errors / codes...".
- Phone: each error is a card. The Time is the bold title line; Machine, Code and Status carry their labels; the Error cell spans the full width.
**Configuration:** none
**Acceptance criteria:**
- A per-component code (e.g. 9011, 9022) shows its own registry title.
- A row without a title (older server) falls back to the CODE_TITLES title, e.g. 9002 → "Fan failure - system stopped".
- Only a code with a valid http(s) `videoUrl` shows exactly one "Video" link, with `target=_blank` and `rel` containing `noopener`.
- A message containing `<no title>` is shown literally (escaped).
- Page.html contains no `//` inside a regex literal.
- At 390 px each error renders as a card (`tr` display block, header row hidden), and the search placeholder mentions "errors".
**Tests:**
- test_errors_page.cjs (headless Chrome with stubbed `google.script.run`): titles, fallback, escaping, video link and the no-`//` lint.
- test_phone.cjs (Errors at phone width).
- test_code.cjs sections "alert log" and "per-component codes" (server side).
**Reference (source):** Page.html 603-655 (state, CODE_TITLES, loadErrors, errorsCard), 1981, 1988, 2022-2023; Code.gs 203-258 (alerts_, saveAlerts_, portalAlerts, errorDef_); test_errors_page.cjs 1-62.

### CLOUD-41 — Error registry feed for the portal (ErrorRegistry.gs + build_errors.py)
**Project / folder:** cloud/google/ErrorRegistry.gs, cloud/google/build_errors.py
**Goal:** Give the portal the same error titles and repair-video links as the firmware's error registry, without a network fetch. A build script turns `errors.json` into a committed `.gs` constant that `portalAlerts` reads.
**Depends on:** DOM-02 (error registry, errors.json); CLOUD-40 consumes it.
**Files to create:**
- `build_errors.py`: `main()`.
- `ErrorRegistry.gs`: generated; holds one global `var ERROR_REGISTRY = {"version": "...", "codes": {"<code>": {"t": title, "v"?: videoUrl}}};`.
**Public contract:**
- `ERROR_REGISTRY.version` = `errors.json` `_meta.version`.
- `codes[code].t` = `message` or `title` from errors.json, trimmed.
- `codes[code].v` is present only when `videoUrl` starts with `https://` or `http://`.
- Server helper `errorDef_(code)` returns that entry or `{}`; `portalAlerts` maps it to `title` and `videoUrl`.
**Behaviour & rules:**
1. Usage: `python cloud/google/build_errors.py [path/to/errors.json]`.
2. Default sources, first that exists:
   - `../sCureBox-CS/config/errors.json` (sibling repo);
   - else `<repo>/public/config/errors.json`;
   - none found: exit with "no errors.json (tried ...)".
3. Output:
   - The first line is the comment `// Generated by build_errors.py from errors.json - edit the titles / videos there (tools/error-editor.html), not here`.
   - JSON with `ensure_ascii=False` and compact separators; written as UTF-8 with LF line endings.
4. It prints `wrote ErrorRegistry.gs from <src>: N codes, V with a video (registry <version>)`.
5. Workflow: the service team edits titles and videos in tools/error-editor.html, saves errors.json, runs this script, then `clasp push` and deploy. The file holds no secrets and is committed.
6. Page fallback when the registry lacks a code: see CLOUD-40 rule 4.
**Look & layout:** n/a (feeds CLOUD-40)
**Configuration:** none (path argument optional)
**Acceptance criteria:**
- Running it on the firmware errors.json writes a file whose `codes` keys equal the registry's codes.
- A code with a non-http `videoUrl` gets no `v`.
- `portalAlerts` returns `title` and `videoUrl` from it.
**Tests:** test_code.cjs "per-component codes (2026-10-21): each has its own title, and a video the service team set reaches the portal". OPEN QUESTION: build_errors.py itself has no unit test.
**Reference (source):** build_errors.py 1-50; ErrorRegistry.gs 1-2; Code.gs 253-258.

### CLOUD-42 — DVT data on the page: loading, detail cache, long poll, refresh cadence, stale-build banner
**Project / folder:** cloud/google/Page.html
**Goal:** Keep the DVT tab current within 1–2 s of any change (runner update, queued request, new result) while sending as little data as possible. The test descriptions (~100 KB) are fetched once per catalog version, and an open tab is told to reload after a deploy.
**Depends on:** CLOUD-20..39 (shell); server `portalDvt`, `portalDvtDetail`, `portalDvtWait`.
**Files to create:** Page.html: `loadDvt()`, `loadDvtDetail()`, `dvtLongPoll()`, the DVT branch of `refreshLoop()`, state `DVT`, `DVT_DETAIL`, `DVT_DETAIL_AT`, `DVT_DETAIL_BUSY`, `DVT_VER`, `LONGPOLL_ON`, `PORTAL_BUILD`.
**Public contract:**
- `GET /api/dvt` → `portalDvt(token)` returns `{runs, fileUrl, catalog, requests, runners, units, race, now, build}`:
  - `runs[]`: `{unit, testId, variant, rep, runId, verdict, operator, startedAt, recordedAt, note, machine, values{}, files[{name, kind, size, id}]}`. `runId` = `testId|unit|variant|rep`.
  - `catalog`: `{version, updated, phases[{id, name, gate, tests[testId]}], tests{testId: {title, group, units[], runs[], minutes, safety, auto, manual, afterAll, hasDetail}}}`, without detail (`stripDetail_`).
  - `requests[]` (newest 200): `{id, machine, unit, testId, status, requested, started, finished, line, prompt, verdict, runIds, act}`.
  - `runners[]`: `{machine, lastSeen, online, version, unit, readiness|null, live|null}`. `online` = seen within 60 s; `readiness`/`live` are dropped when older than 45 s.
- `GET /api/dvt/detail` → `portalDvtDetail(token)` returns `{updated, tests{testId: detail}}`. The detail fields are `purpose, rationale, safetyPlan[], equipment[], preconditions[], dependencies[], steps[], criteria, note, bench, kind, prompts[]`.
- `GET /api/dvt/wait?since=<ver>&wait=15` → `portalDvtWait` returns `{ver}`. The server holds the call until the version changes or at most 20 s (`DVT_HOLD_MAX_SEC`).
- Every `portalDvt`/`portalDvtWait` call marks the tab as watched (cache `dvt_watch`, 45 s), so the runner polls faster.
**Behaviour & rules:**
1. `loadDvt()` fetches `/api/dvt`, then post-processes it:
   - every catalog test with `group==='ELE'` becomes `auto=false, manual=true`, and when its units include `UUT-01`, `units=['UUT-01']`;
   - each phase's `tests` are sorted with `localeCompare(..., 'en', {numeric:true})`;
   - `DVT.skew = DVT.now - Date.now()/1000`.
2. `loadDvt()` re-renders only on `dvt`, `overview`, `compare` or `race` and only when not `userBusy()`. On `dvt`, it calls `loadDvtDetail()` when `catalog.updated !== DVT_DETAIL_AT`.
3. `loadDvtDetail()` runs one call at a time (`DVT_DETAIL_BUSY`). It stores `d.tests` and `d.updated`; a failure is silent (rows work without detail).
4. Long poll `dvtLongPoll()`:
   - runs only while `VIEW==='dvt'`, as a single instance (`LONGPOLL_ON`);
   - when the answer's `ver` differs from `DVT_VER`, store it and call `loadDvt()`;
   - on error, wait 3 s and retry;
   - started when the DVT section button is pressed and at page start when `VIEW==='dvt'`.
5. `refreshLoop()` on the DVT tab:
   - when less than 9 s have passed since the last full load, it calls `loadDvt()` only; otherwise it runs a full `load()`;
   - the next tick is 8 s on DVT and 10 s elsewhere; the first tick is 4 s after load.
6. Stale page: when `DVT.build` is set and differs from `PORTAL_BUILD`, the catalog card shows an amber `.dvt-prompt` banner: "**This page is out of date** - the portal was updated since it was opened." with a primary **Reload** button that calls `location.reload()`.
**Look & layout:**
- Loading state: card "DVT" / "Loading…".
- Banner: 3 px amber left border, a light amber background, and the Reload button inline.
**Configuration:** `PORTAL_BUILD` constant; it must equal Code.gs `PORTAL_BUILD`.
**Acceptance criteria:**
- The detail is fetched exactly once across repeated polls with an unchanged `catalog.updated`.
- A new `ver` from the long poll triggers an immediate `/api/dvt` fetch and another long poll.
- A build mismatch shows the Reload banner.
**Tests:** test_page.py ("the detail is fetched once, not on every poll", "polling again does not refetch the detail", "the page remembers the version", "a new version reloads the DVT data at once"); test_code.cjs "the long poll" and "each test's detail ... served apart".
**Reference (source):** Page.html 611-616, 657-680, 1165-1169, 2500-2531; Code.gs 513-539, 568-604, 895-911, 730-737.

### CLOUD-43 — DVT tab frame: CureBox picker, unit chips, summary tiles, progress bar, legacy run list
**Project / folder:** cloud/google/Page.html
**Goal:** Frame the DVT campaign for one CureBox and one unit (UUT): which CureBox, which unit, how many runs are owed and passed. It also keeps a flat run list for the case where no catalog has been uploaded yet.
**Depends on:** CLOUD-42, CLOUD-20..39 (shell chooser)
**Files to create:** Page.html: `dvtCard()`, the top of `dvtCatalogCard(all, picker, where)`, `dvtMachines`, `DVT_NONE='__unassigned'`, `DVT_UNIT` (localStorage `scure-dvt-unit`), helpers `fmtWhen`, `dvtWhen`, `dvtClass`, `fmtBytes`, `dvtRunDetail`.
**Public contract:** reads `DVT` (CLOUD-42) and `MACHINES`; no server call of its own.
**Behaviour & rules:**
1. CureBox list: every portal machine name plus every `run.machine` seen in DVT runs, sorted.
   - The `<select id="dvt-machine">` adds "All CureBoxes" (`all`) first and "Not assigned to a CureBox" (`__unassigned`, runs with an empty machine) last.
   - Changing it is the same as pressing a chip (shell `pick`); the selection is kept in localStorage `scure-curebox`.
   - On the DVT tab, when only one machine exists and nothing was ever chosen, it is selected automatically.
2. Runs shown: all of them for `all`; `!r.machine` for `__unassigned`; otherwise `r.machine === SELECTED`.
   - Title suffix `where`: '' for all; " not assigned to a CureBox" for unassigned; otherwise " on <name>".
3. No runs and no catalog:
   - with runs elsewhere: "No DVT run<where> yet - choose another CureBox above.";
   - with no runs at all: instructions to open the **Cloud** box in DVT/web/dvt-tool.html, paste the web-app URL and DVT key, choose the **CureBox**, and press **Sync all**.
4. Units of the catalog view, in this order:
   - the CureBox's own units: its runner's `unit` plus units it has runs of, restricted to the catalog units;
   - if none and the selection is all or unassigned: every catalog unit;
   - otherwise: only the first catalog unit.
   - When `DVT_UNIT` is not in the list, it is reset to the first one.
5. Unit chips are shown only when there are 2 or more units: "Unit:" followed by one button per unit (primary = current). A unit with no runs gets a muted "·".
6. Counters cover every run the catalog owes on the unit. Owed ids are `testId|unit|<runKey>` with `runKey` from `t.runs`, default `'|1'`.
   - Tiles: Runs owed | Pass (green) | Fail (red) | Blocked (amber) | Open.
   - `open = owed − (PASS+FAIL+BLOCKED+WAIVED)`.
   - Progress bar `pct = round(closed/owed*100)`, with the tooltip "N% of the owed runs recorded".
7. Legacy view (no catalog):
   - a summary table Unit | Tests | Runs | Pass (green pill) | Fail (red pill when > 0) | Last;
   - unit chips "All" plus each unit;
   - a run table Test | Variant | Rep | Unit | CureBox | Verdict | Operator | Recorded, sorted newest first by `startedAt`, else `recordedAt`;
   - search over unit/test/variant/verdict/operator/note;
   - clicking a row toggles `DVT_OPEN` and shows the values table, file links and note (`dvtRunDetail`).
8. `fmtWhen`: below 24 h it is `fmtAgo` (`Ns/Nm/Nh ago`); otherwise e.g. "18 Oct, 11:19 PM"; '—' when there is no time.
9. `dvtClass`: pass → on, fail → off, blocked/invalid → warn.
10. File links use `window.scureDvtFileHref(DVT.fileUrl, f.id)`, i.e. `?dvtfile=<id>&t=<session>` served by `doGet`/`serveDvtFile_`. The link text is the file name, followed by muted `(kind, size)`.
**Look & layout:**
- Card `h2` "DVT campaign<where>", with muted "catalog <version> · <unit>" (catalog view) or "N runs uploaded" (legacy).
- Then the picker row (label "CureBox" + select), the unit chips, and a 5-column tile grid `.dvt-sum` (tile: 1px border, 10 px radius, 1.7rem bold number over a muted label).
- Then a 6 px progress bar (green fill on `--line`).
- Phone: the picker select is hidden (`.dvt-picker{display:none}`; the chips above choose); tiles become 3 per row with a 1.3rem number.
**Configuration:** localStorage `scure-curebox`, `scure-dvt-unit`
**Acceptance criteria:**
- With one machine, the DVT tab opens with it already chosen (no picking needed before Run).
- The catalog's other UUTs are not offered when a CureBox has its own unit.
- The tiles count owed runs, not uploaded runs.
**Tests:** test_phone.cjs ("the only CureBox is already chosen"); test_page.py (catalog view loads with the real catalog); test_overview.cjs (DVT section shows the CureBox chooser).
**Reference (source):** Page.html 616-618, 682-716, 1165-1204, 1251-1260, 1271-1333, 1969-1972, 2013-2021, 2034-2038.

### CLOUD-44 — DVT catalog phases and test rows (verdict icons, badges, expand, owed-run table)
**Project / folder:** cloud/google/Page.html
**Goal:** List every phase and test of the DVT catalog for the chosen unit, laid out like the DVT tool. Each test row carries a verdict icon, badges, a run count, its Run / Approve control, and opens to show its runs.
**Depends on:** CLOUD-43, CLOUD-45, CLOUD-46, CLOUD-47, CLOUD-50
**Files to create:** Page.html: the phase/test part of `dvtCatalogCard`, `dvtTestVerdict(owed, byId)`, `DVT_ICON`, `DVT_PHASE_OPEN`, `DVT_TEST_OPEN`, `DVT_PHASES_TOUCHED`, `DVT_OPEN`, and the wiring in `render()` for `[data-dvt-phase]`, `[data-dvt-test]`, `[data-dvt-run]`, `[data-dvt-run-test]`.
**Public contract:** none beyond CLOUD-42 data; Run opens CLOUD-47.
**Behaviour & rules:**
1. Test verdict from its owed runs (DVT tool rule):
   - all empty → `open`; some empty → `progress`;
   - otherwise the first present of FAIL, INVALID, BLOCKED, WAIVED, PASS.
2. Icons in a 1.5rem circle:
   - PASS ✓ green; FAIL ✗ red; BLOCKED ! amber; INVALID ? amber;
   - WAIVED W grey; progress … grey; open – grey.
3. Phases are open by default. The first click on any phase header marks all phases open and then toggles that one (`DVT_PHASES_TOUCHED`).
4. Phase header (inset background, clickable):
   - bold phase id and bold name, then muted "Gate: <gate>";
   - right-aligned counts `<P>P / <F>F / <B>B / <owed>`, coloured green/red/amber, or '—';
   - a ▾/▸ caret.
5. Test row (clickable; toggles `DVT_TEST_OPEN`):
   - icon, monospace bold id, title;
   - badges: "safety-critical" (red-bordered pill) when `t.safety`, "auto" when `t.auto`;
   - right-aligned muted `done/owed runs` (or "cases" when the run keys have more than one distinct variant) and ` · ~N min`, then the caret.
6. Row control, only when a CureBox is chosen (not all/unassigned):
   - an active request → its status pill (CLOUD-46 labels);
   - `afterAll` test with other tests still open → muted "runs last - N test(s) still open";
   - `auto` → "▶ Run" button (`data-dvt-run-test`, `stopPropagation`; tooltip "Queue this test on <box> - one click runs all N runs/cases one after another; it starts when someone there presses Start"), which opens the guide window (CLOUD-47);
   - manual tests → CLOUD-50.
7. Search: tests whose id or title contains `SEARCH`. An empty phase says "Nothing matches the search" or "No tests on this unit".
8. Opened test: the detail (CLOUD-45), then a `cards` table Variant | Rep | Verdict | Operator | Recorded with one row per owed run.
   - Not run: muted "not run yet".
   - Recorded run: clickable, toggles `DVT_OPEN`, and shows `dvtRunDetail`.
9. Recorded runs that the catalog no longer owes go in a block "Other uploaded runs" with muted "N run(s) the catalog <v> no longer owes on <unit> (older catalog, other repetitions)" and the table Test | Variant / rep | Verdict | Operator | Recorded.
**Look & layout:**
- Phase: a 10 px rounded bordered box; head padding .75rem 1rem.
- Test rows have a top border and padding .55rem 1rem; the id is monospace .85rem.
- `.run-btn` is small (.15rem .6rem, .8rem).
- The opened area `.dvt-runs` is indented 3.1rem on the left.
- Phone: phase heads and test rows are at least 48 px; the Run button is full-width (`flex:1 1 100%`), at least 46 px, 1rem text.
**Configuration:** none
**Acceptance criteria:**
- Tests within a phase are in natural numeric order.
- An `afterAll` test shows no Run while other tests are open.
- Both automatic tests on a phone get Run buttons at least 44 px tall and at least 300 px wide, inside the screen.
**Tests:** test_page.py (opened test content); test_phone.cjs (Run buttons wide thumb targets).
**Reference (source):** Page.html 689-703, 1183-1250, 1262-1267, 2058-2062, 2099-2114; CSS 209-227, 384-387.

### CLOUD-45 — DVT test detail panel and bench readiness card
**Project / folder:** cloud/google/Page.html
**Goal:** When a test is opened, show what the DVT tool shows: purpose, sample rationale, safety plan, equipment and preconditions side by side, dependencies, the numbered procedure and the pass criteria. A bench test also gets a live readiness card from the CureBox's runner, whose Run button turns on only when every check is green.
**Depends on:** CLOUD-42, CLOUD-44; DVT-08..10 (bench runner readiness on the machine side)
**Files to create:** Page.html: `dvtDetailHtml(tid, x, runner, verdictOf)`, `dvtBenchCard(tid, d, x, runner, verdictOf)`, `DVT_KIND`, `DVT_CHECKS`; wiring `[data-dvt-run-card]` → `dvtGuide`.
**Public contract:**
- `runner.readiness[testId] = {ready: bool, rows: {machine|svc|tc08|chamber|idle: {ok: true|false|'warn', text}}}`, as reported by the runner on its poll (`dvtNext_`, cached 300 s, shown while under 45 s old).
**Behaviour & rules:**
1. When `DVT_DETAIL` is not loaded yet: "Loading the test description…".
2. When the test has no detail: "The description of this test is not in the portal yet - it arrives when the DVT runner on the CureBox starts, or when the DVT tool presses **Sync all**."
3. Sections, in order (each heading is a small uppercase muted `h4`):
   - Purpose;
   - Sample rationale (optional);
   - Safety plan: a box with a red 3 px left border and a faint red background;
   - Equipment | Preconditions as two columns (`.dvt-cols`, one column below 760 px);
   - Dependencies: monospace chips, green "ID ✓" when that test's verdict is PASS or WAIVED, otherwise muted "ID …";
   - Procedure;
   - Pass criteria: a bordered box with the criteria in a code block on the inset background.
4. Procedure intro:
   - a bench test (`d.bench`) gets the readiness card;
   - otherwise, when there is a `d.note`, a blue box shows bold "<kind label>[ · about N min]." followed by the note. Kind labels: auto → fully automatic; guided → automatic, with prompts; instrumented → automatic, instrument readings asked for.
5. Procedure steps: numbered boxes (`ol.dvt-steps`, counter in bold red #dc2626, each step a bordered 8 px rounded box).
6. Readiness card, five rows in a fixed order:
   - "Machine connected";
   - "DVT bench service on the machine (port 3002)";
   - "Thermocouple on CH1 (at the cutout)";
   - "Heater thermistor (TEMP_CHAMBER) reading";
   - "Machine idle".
   - Each row is a 0.8rem dot (green ok / red bad / amber warn / grey unknown), the label (min-width 21rem), and the reported text (red on a bad row).
7. Run on the readiness card (`data-dvt-run-card`):
   - enabled only when a CureBox is chosen, `readiness.ready`, and no active request for this test exists;
   - status line: "queued - it starts when someone presses Start on the machine screen", or "everything is ready - press Run, then Start on the machine screen", or the reason.
   - Reasons: "Choose a CureBox above to see its live checks." / "The DVT runner on X is not online - no live checks." / "Waiting for the first report from X…" / "Run is enabled when all checks are green".
8. An offline runner shows no green or red rows (no state it does not know).
**Look & layout:**
- Readiness card `.dvt-auto`: blue-tinted border rgba(37,99,235,.35), 10 px radius, faint blue background; a blue note line on top, the rows, then a primary "▶ Run" and a muted status line.
- Phone: the label takes full width above its value.
**Configuration:** none
**Acceptance criteria (test_page.py with the real 41-test catalog):**
- Purpose, every equipment line, every precondition, all procedure steps in order and the exact criteria text are shown.
- Equipment and preconditions sit side by side.
- For DVT-SAF-002 the five labels appear in order with classes ok,ok,bad,ok,ok; the red reason is on the red row; Run is disabled with "Run is enabled when all checks are green".
- When all rows are green, Run is enabled and queues `{machine:'CureBox-1', unit:'UUT-01', ids:['DVT-SAF-002']}`.
**Tests:** test_page.py; test_code.cjs "the runner's readiness report ... shown while it is fresh".
**Reference (source):** Page.html 751-804, 2039-2042; CSS 228-242, 282-286; Code.gs 550-556, 836-848.

### CLOUD-46 — DVT run panel: runner state, instruments, Run all / Stop all, request queue
**Project / folder:** cloud/google/Page.html
**Goal:** For the chosen CureBox and unit, show whether its DVT runner is online, which USB instruments it sees, and the queue of tests requested from the site. The panel offers Run all, Stop all, per-request Cancel / Force stop, and inline answers to the questions a run asks.
**Depends on:** CLOUD-42, CLOUD-49; server `portalDvtRequest`, `portalDvtCancel`, `portalDvtAnswer`
**Files to create:** Page.html: `dvtRunPanel(u, runnable)`, `dvtInstruments(runner)`, `dvtPromptControls(r)`, `dvtSend(path, body)`, `DVT_ACTIVE_ST`, `DVT_REQ_LABEL`, `reqClass`, `DVT_MSG`; wiring of `[data-dvt-run-all]`, `[data-dvt-stop-all]`, `[data-dvt-cancel]`, `[data-dvt-force]`, `[data-dvt-answer]`, `[data-dvt-answer-input]`.
**Public contract:**
- `POST /api/dvt/request {machine, unit, testIds[]}` → `portalDvtRequest`; returns `{ok, queued, skipped}` or `{ok:false, message}`.
- `POST /api/dvt/cancel {id | ids[], force?}` → `portalDvtCancel(token, ids||id, force)`; returns `{ok, stopped}`.
- `POST /api/dvt/answer {id, value}` → `portalDvtAnswer`. `value` is true = Yes/Done, false = No, null = Skip, or the typed or selected string.
- Sheet `dvt_requests`: `id, machine, unit, testId, status, requested, started, finished, line, prompt, answer, runIds, verdict, act`.
- `prompt = {text, kind: 'yesno'|'value'|other, values?[], unit?}`.
- `runner.readiness._instruments = {tc08, tc08ch1, tc08ch2, ophir: {ok, text}}`.
**Behaviour & rules:**
1. Statuses:
   - active = queued, waiting, running, cancel_requested;
   - labels: queued; waiting → "waiting at the machine"; running; cancel_requested → "stopping"; done; failed; cancelled; blocked → "not started";
   - pill class: done = green, failed = red, cancelled = plain, others = amber.
2. With no CureBox chosen (all/unassigned): muted "Choose a CureBox above to run tests on it."
3. Runner state:
   - online: green pill "DVT runner online" plus muted "v<version> · unit <unit>";
   - otherwise: red pill "DVT runner offline · seen <when>" or "DVT runner not installed", plus "requests wait in the queue until it is online".
4. "▶ Run all open tests (N)" (primary, right-aligned):
   - N = auto tests that are not finished (PASS/FAIL/BLOCKED/WAIVED), not waiting to run last, and not already requested;
   - disabled when N = 0;
   - it collects the ids of the visible `[data-dvt-run-test]` buttons and asks `confirm("Queue N test(s) on X? Each one waits for Start at the machine.")`;
   - then the button turns disabled "Queuing N test(s)…" and the page sends `/api/dvt/request`.
5. "■ Stop all (N)" (danger) is shown only when active requests exist. It asks `confirm("Stop all N open request(s) on X? A test that is running there is stopped and the machine turns everything off.")`, then sends `{ids, force:true}`.
6. Instruments row: label "Instruments" and chips for tc08, tc08ch1, tc08ch2, ophir (green ok / red bad / plain). When tc08, tc08ch1 or ophir is false, a red line "Not connected: a · b".
7. A fixed note: "Nothing turns on until someone at X presses **Start** on its screen. Steps that need a person are asked here." The last refusal (`DVT_MSG`) is shown in red below it.
8. Queue table `rq-table`: Test | Status | On the machine | (action).
   - Active requests first, then the 8 most recent finished ones, for this machine + unit.
   - Status cell: status pill plus a verdict pill.
   - "On the machine": the muted `line` plus the prompt controls.
   - Action cell: `cancel_requested` → danger "Force stop" (tooltip "Close it now - for a run the machine no longer answers for", sends force); other active → "Cancel" (turns into "Cancelling…"); finished → muted finished/requested time.
9. Prompt controls (amber 3 px left-border box), headed "**The test asks:** <text>":
   - `yesno`: Yes (primary) / No / Skip;
   - `value`: a select of `values` or an input with the placeholder = unit, then OK (primary) and Skip; OK with an empty input does nothing;
   - otherwise: Done (primary) / Skip.
   - A clicked button disables itself.
10. `dvtSend` posts, sets `DVT_MSG` to the refusal text, or '' on success, or the exception text, then always runs `loadDvt()` and `render()`.
11. Role refusals come back as 403 → the shell `flash` shows the server message (CLOUD-57).
**Look & layout:**
- `.dvt-runpanel`: a bordered 10 px rounded box.
- Phone: the queue table becomes one card per request, and its buttons are full width, at least 46 px.
- Prompt buttons are at least 48 px wide at 40% each; the input takes the full width.
**Configuration:** none
**Acceptance criteria:**
- Run all queues exactly the visible runnable tests after the confirm.
- Stop all sends force with every active id.
- Force stop appears only on `cancel_requested`.
- A Skip answer sends `value:null`.
**Tests:** test_code.cjs (request queued / refused for another unit, cancel while running, a queued request cancelled before it starts, Stop all / Force stop, "blocked" is final); test_phone.cjs (queue cards).
**Reference (source):** Page.html 718-749, 1127-1163, 2063-2098; CSS 225-227, 351-357, 397-399; Code.gs 736-737, 982-1047, 1104-1122.

### CLOUD-47 — DVT guide window (modal opened by Run): explain the test, then Queue
**Project / folder:** cloud/google/Page.html
**Goal:** Pressing Run on a test never queues it straight away. A modal window first explains the test (purpose, safety plan, equipment, "Before you start", procedure, pass criteria) and offers a dry-run simulation. Only "▶ Queue on <CureBox>" requests it, after which the same window follows the run (CLOUD-48). See live-simulation.png and run-window.png.
**Depends on:** CLOUD-42, CLOUD-46, CLOUD-48, CLOUD-52
**Files to create:** Page.html: `dvtGuide(tid, title)`, `GUIDE` state `{bg, tid, machine, unit, sinceId, sent, log[], sig}`, `dvtTitleOf(tid)`.
**Public contract:** `POST /api/dvt/request {machine, unit, testIds:[tid]}` (CLOUD-46).
**Behaviour & rules:**
1. The window is appended to `document.body`, outside `#app`, so re-renders and the long poll leave it alone. Only one `GUIDE` is current at a time.
2. Body sections (from `DVT_DETAIL[tid]`):
   - Purpose; Safety plan (red box); Equipment; **Before you start** (= preconditions); the blue note box; Procedure (numbered boxes); Pass criteria; the Simulation box (CLOUD-52).
   - When the test has no detail: "The guide for this test is not in the portal yet - it arrives when the DVT runner on the CureBox starts, or when the DVT tool presses **Sync all**." In that case there is no simulation.
3. Footer:
   - muted on the left: "It starts only when someone presses Start on <CureBox>.";
   - buttons: "Cancel" and primary "▶ Queue on <CureBox>".
4. Queue pressed:
   - remember `sinceId` = the highest existing request id for this machine + test (the server reply has no id);
   - set `sent=true`; the button turns disabled "Queuing…"; Cancel is relabelled "Close";
   - post the request.
   - When the reply fails or `queued` is 0: re-enable the button, and show in red in the run strip either the server message, or "not queued - this test is already queued or every run of it is recorded", or `DVT_MSG`, or "not queued".
   - Then call `dvtGuideRefresh()`.
5. Closing:
   - Esc always closes;
   - Cancel/Close closes;
   - a click on the dark backdrop closes only while nothing has been queued (`!g.sent`).
   - Closing removes the key listener and clears `GUIDE`.
6. The machine and unit are frozen at open time (`g.machine = SELECTED`, `g.unit = DVT_UNIT`).
**Look & layout (live-simulation.png, run-window.png):**
- Backdrop: fixed, rgba(0,0,0,.45), centred, z-index 50, 1rem padding.
- Window: `min(760px,100%)` wide, at most 90vh tall, 12 px radius, shadow 0 10px 40px rgba(0,0,0,.3), flex column.
- Head: `h3` 1.1rem with the monospace test id followed by the title (e.g. "DVT-ELE-001 Protective earth bonding continuity"), and a bottom border.
- Run strip `[data-guide-run]`: inset background, hidden while empty, at most 45vh with its own scroll.
- Body: scrolls; section headings are small uppercase muted ("PROCEDURE", "PASS CRITERIA"); steps are numbered in red, each in its own bordered box.
- Footer: right-aligned buttons with a top border.
- Phone: a full-screen sheet with no radius; footer buttons are stacked full-width at least 48 px (`column-reverse`, so the primary is on top) and pinned while the body scrolls; the safe-area inset is respected.
**Configuration:** none
**Acceptance criteria:**
- Run opens the window without any request being sent.
- Queue sends exactly one request for that test.
- After queuing, a backdrop click does not close the window.
- On a phone the window fills the viewport, and a long guide scrolls inside the sheet while its buttons stay put.
**Tests:** test_phone.cjs ("the guide fills the phone screen", "a long guide scrolls inside the sheet while its buttons stay put"); test_page.py (Run queues the test on this CureBox).
**Reference (source):** Page.html 806-863, 1125, 2058-2062; CSS 243-251, 272, 389-396.

### CLOUD-48 — Following a requested run in the guide window: status, "What to do now", I did it, questions, live machine chips, run log
**Project / folder:** cloud/google/Page.html
**Goal:** After Queue, the guide window shows the run as it happens:
- its status and verdict, and the runner's current line;
- one plain instruction for the person: wait, press Start at the machine, do this physical step now, answer this, or nothing to do;
- the machine's live state;
- a time-stamped run log.
It also offers Stop. See run-window.png.
**Depends on:** CLOUD-46, CLOUD-47; DVT-05 (RemoteConfirm Start at the machine); server `portalDvtActed`, `portalDvtAnswer`, `portalDvtCancel`, `dvtUpdate_`
**Files to create:** Page.html: `dvtGuideRefresh()` (called at the end of every `render()` and after Queue), `dvtGuideNow(r, g)`, `dvtGuideSystem(name)`.
**Public contract:**
- `POST /api/dvt/acted {id}` → `portalDvtActed`. It is refused when there is no `act` ("that request is not waiting for you to do anything") or when `act.ack === false` ("that step is watched by the machine itself - nothing to press").
- `act = {text, sec?, stage?{n, of, text}, ack?, acked?, label?, pressed?}`.
- `runner.live = {chamberTemp, doorClosed, uvOn, isHeating, heaterPwm, isCooling, at}`, fresher than 45 s.
**Behaviour & rules:**
1. The followed request is the newest one for (machine, test) with `id > sinceId`. None yet → amber pill "queuing…".
2. Run log: append `{time, text}` whenever the signature `status|line|prompt.text|act.text|verdict` changes. The text is the status label, plus the verdict, plus one of: " - asks: <q>" (an active prompt), " - DO NOW: <act>" (an active act), or " - <line>". The log is shown newest first.
3. While the focus is in an input inside the window, the strip is not redrawn, so typing is not lost.
4. Top row: status pill, verdict pill, the muted line (flex), and, while active and not stopping, a danger "Stop the run" button. Stop turns into "Stopping…" and sends a non-forced cancel.
5. Queue button while the run is active: disabled "Queued". Afterwards: "▶ Run again".
6. "What to do now" box. It has a blue 4 px left border; it turns amber (`.act`) while an act is pending. Text per status:
   - queued: "Wait - the DVT runner on X picks the test up within a few seconds. If it stays queued, check that the runner shows online."
   - waiting: "Go to **X** and press **Start** on its screen (it asks to confirm <tid>). Check the "Before you start" list below first. Nothing turns on until Start is pressed."
   - running with an act: big text (1.45rem, 800 weight, #92400e). It is followed by a monospace pill "<sec> s" when `sec` is a number, and muted "step n of m · <stage text>". Below it, one of:
     - `ack===false` → "Do it now - the machine is watching for it and goes on by itself.";
     - `acked` → "You pressed it - waiting for the machine to see it.";
     - otherwise a large amber button (#b45309, white, 800 weight, at least 48 px) labelled `act.label` or "I did it". It turns into disabled "Sent…" and posts `/api/dvt/acted`. Under it: "Press it the moment you have done it - the test does not go on until you do."
   - running with a prompt: "The test is waiting for you - answer the question below.", followed by the prompt controls (CLOUD-46 rule 9).
   - running with neither: "The test is running by itself - nothing to do. (<line>) Stay clear of the machine; keep this window open to follow it, or press Stop the run."
   - cancel_requested: "Stopping - X is turning everything off."
   - done: "Finished with **<verdict>**. The result is recorded in the campaign. You can close the window." (or "Finished. You can close the window.")
   - failed: "The run did not complete - read the reason above, fix it, then press Run again."
   - blocked: "The test could not start - the reason is above. Fix it, then press Run again."
   - cancelled: "The run was stopped. You can press Run again or close the window."
7. Machine status chips (`dvtGuideSystem`):
   - Source: the runner's `live` when present (seconds old), else the machine's cloud-sync `state` (minutes old).
   - Chips: online/offline; "chamber 32.4°C"; door closed (green) / door open (amber); UV on (amber) / UV off; "heating NN%" (amber) / heater off; cooling (amber) / not cooling.
   - A muted tail "live · Ns ago" or "synced <ago>".
   - No data at all: "<name> no status from this CureBox yet".
8. Never says "nothing to do" while an act waits for the person. This rule comes from the DVT-SAF-008 timeout of 2026-10-29.
**Look & layout:**
- run-window.png: the "running" pill, the muted line "measuring point 3 of 8", and a red-outlined "Stop the run" on the right.
- Below it the white "WHAT TO DO NOW" card with a blue left bar, and inside it the amber prompt box "The test asks: Is the Kelvin probe on the door frame?" with Yes (primary) / No / Skip.
- Then the row "CUREBOX-1 STATUS" with chips (online green, chamber, door closed green, UV on amber, heater off, not cooling, "synced 2h ago").
- Then "RUN LOG" with monospace times and dashed separators.
- Phone: the instruction fits the screen width.
**Configuration:** none
**Acceptance criteria:**
- With an act "OPEN THE DOOR", `sec` 24 and stage 4/6:
  - the headline is at least 20 px and reads "OPEN THE DOOR";
  - the pill reads "24 s" and the stage reads "step 4 of 6";
  - the card is amber and contains no "nothing to do";
  - there is an "I did it" button at least 44 px tall.
- "I did it" is delivered to the runner exactly once.
**Tests:** test_phone.cjs (lines 200-241: act headline, sec, stage, amber, I did it); test_code.cjs ("the step the person must do now (c.act)", "'I did it': handed to the runner exactly once", "a step the machine watches by itself takes no press", "live state rides on the runner's reports").
**Reference (source):** Page.html 1025-1124; CSS 252-271; Code.gs 923-960, 1084-1102.

### CLOUD-49 — Run-from-site safety contract (Start only at the machine, roles, unit lock, run-last rule, orphan cleanup)
**Project / folder:** cloud/google/Page.html (+ server rules in Code.gs, ticketed in CLOUD-01..19)
**Goal:** Pin down the rules that make running DVT from the website safe. Queuing a test from the site never turns anything on. A person at the CureBox must press Start on its screen. Wrong-unit, wrong-role and out-of-order requests are refused, and cut-off runs do not stay "running" forever.
**Depends on:** CLOUD-46, CLOUD-47, CLOUD-57; DVT-05 (RemoteConfirm prompter on the machine), PLAT-10
**Files to create:** none new: rules and wording across `dvtRunPanel`, `dvtGuide`, `dvtBenchCard`, `dvtGuideNow`. The server side lives in `portalDvtRequest`, `dvtOpenOthers_`, `dvtCloseOrphans_`, `need_`.
**Public contract:**
- Every DVT action needs the `service` role: request, cancel, answer, acted. Approve needs `admin`.
- A refusal is `{ok:false, denied:true, message}` → the shim answers 403 → the page shows `flash(message)`.
**Behaviour & rules:**
1. The page wording always states that nothing starts without Start at the machine:
   - the guide footer;
   - the run panel note;
   - the Run tooltip;
   - the Run-all confirm;
   - the "waiting" instruction.
2. The site writes a request with status `queued`. The machine's runner takes it (→ `running`), asks for confirmation on the CureBox screen (→ `waiting`, DVT-05), and only then drives outputs.
3. Unit lock: when the CureBox's runner reported a unit, a request for another unit is refused: "<box> is unit <U> - the request was for <V>. Reload the page."
4. Run-last (`afterAll`) tests:
   - the page hides Run while other tests are open;
   - the server refuses with "<ids> runs last - N other test(s) on <unit> have no result yet".
5. No duplicates: a test already active on that machine + unit is skipped (`skipped` count).
6. Orphans: when the runner says hello (only between requests), its `running`, `waiting` and `cancel_requested` requests close:
   - `failed` with "interrupted - the machine or its app restarted during the test; run it again";
   - or `cancelled` with "cancelled - the runner restarted before it could stop the test".
7. Force stop closes a request on the site at once. A runner still on it is told to cancel on its next report, and that report cannot revive the row.
8. Stop always means the machine turns everything off. The page never sends hardware commands itself; machine commands are data-only (PLAT-10).
**Look & layout:** n/a (wording listed above)
**Configuration:** none
**Acceptance criteria:**
- A Viewer pressing Run sees a flash "Requesting DVT tests needs Service access - you are signed in as Viewer. Ask an admin.", and nothing is queued.
- A stale tab requesting UUT-02 on a UUT-01 CureBox is refused.
- After a runner restart no request stays running.
**Tests:** test_code.cjs (lines 275-357, 537-580: unit refusal, afterAll refusal, orphan close, force stop); test_people.cjs ("a refused action says which access it needs").
**Reference (source):** Page.html 718-724, 834, 1158, 2066; Code.gs 965-1018, 809-833, 1020-1047, 1240-1250.

### CLOUD-50 — Hand-made (electrical safety) test approval from the site
**Project / folder:** cloud/google/Page.html
**Goal:** Electrical-safety tests (catalog group `ELE`) are done by hand on UUT-01. An admin records them as passed from the site with ✓ Approve, or takes the approval back with Withdraw.
**Depends on:** CLOUD-44, CLOUD-57; server `portalDvtApprove`
**Files to create:** Page.html: `DVT_MANUAL` (test id → row model, rebuilt on each catalog render), wiring `[data-dvt-approve]`.
**Public contract:**
- `POST /api/dvt/approve {unit, testId, runIds[], who, approve}` → `portalDvtApprove`.
- Approve writes one `PASS` dvt_runs row per owed run id, with `note` "Approved on the site by <name>".
- Withdraw deletes only rows whose note starts "Approved on the site".
- Role `admin`; only `group==='ELE'`; every run id must be `testId|unit|...`.
- With Google sign-in the recorded name is the signed-in account ("Name <email>"); with the shared password it is `who`. Trimmed to 60 characters.
**Behaviour & rules:**
1. Manual test row:
   - verdict PASS: muted "approved by <operator of the first owed run>" plus a "Withdraw" `run-btn` (tooltip "Take the approval back");
   - otherwise: a primary "✓ Approve" (tooltip "The engineer did this test by hand: record it as passed").
   - No Run button on manual tests (CLOUD-42 rule 1 forces `auto=false`).
2. Approve:
   - `prompt("Who approves <tid>?", <last name>)`; the default is the localStorage `scure_approver` value, else "Alex";
   - an empty answer cancels; the name is remembered, in try/catch for private windows;
   - the request sends `runIds = x.owed`.
3. Withdraw: `confirm("Withdraw the approval of <tid>?")`, then `approve:false`.
4. The click does not toggle the row (`stopPropagation`). The button disables itself, then the page runs `dvtSend` (reload + render).
**Look & layout:** small inline buttons in the test row; on a phone at least 44 px.
**Configuration:** localStorage `scure_approver`
**Acceptance criteria:**
- An approved ELE test on a phone shows one big Withdraw and no Run.
- Withdraw calls approve with `('DVT-ELE-002', 'DVT-ELE-002|U1||1', false)`.
- A non-ELE test is refused by the server.
**Tests:** test_phone.cjs (lines 139-143); test_code.cjs ("the engineer's approval of a hand-made test").
**Reference (source):** Page.html 659-660, 1215-1217, 1244-1246, 2043-2057; Code.gs 1049-1082.

### CLOUD-51 — Pass-criteria evaluator for the simulation (critParse / critEval / critLeaves / critReadings / critText)
**Project / folder:** cloud/google/Page.html
**Goal:** Read a catalog pass-criteria expression safely (never `eval`) and make up readings that pass it, or that break exactly one check so the test fails. This drives the dry-run simulation.
**Depends on:** none (pure functions); used by CLOUD-52
**Files to create:** Page.html: `critParse(src)`, `critEval(node, env)`, `critText(node)`, `critIds(node)`, `critLeaves(node)`, `critReadings(leaves, bad)`.
**Public contract:**
- Grammar, case-insensitive keywords:
  - `or` > `and` > `not` > comparison (`<= >= == != < >`, at most one per level) > `+ -` > `* /` > unary `-` > primary;
  - primaries: numbers (`1`, `1.5`, `1e-3`), `'str'` or `"str"`, `true`/`false`, names `[A-Za-z_][\w.]*` (dotted names are catalog thresholds), calls `max/min/abs(...)`, and parentheses.
- Nodes: `{k:'lit'|'id'|'neg'|'not'|'fn'|'ar'|'bool'|'cmp', ...}`.
- An unreadable or trailing input throws `Error('unreadable criteria' | 'expected X' | 'unexpected X')`.
**Behaviour & rules:**
1. The tokenizer is a sticky regex; leftover non-space text throws.
2. `critEval`:
   - `==` and `!=` are strict;
   - an unknown function gives NaN;
   - `and`/`or` coerce to boolean.
3. `critLeaves` splits on and/or. A `not` over a non-comparison, non-name node is descended; a `not` over a comparison or name stays one leaf.
4. `critReadings(leaves, bad)` builds an env where every leaf comes out true, except leaf index `bad`:
   - a name never set and used as a limit gets 100;
   - for a numeric limit R the margin is `m = max(|R|·0.2, 0.05)`; the value is `R−m` or `R+m` (3 significant digits), chosen per operator;
   - `==` uses R itself (or `R+m` to fail);
   - booleans flip; a string fails as `R + '_other'`;
   - `not` inverts the wanted outcome;
   - a bare name leaf gets true or false.
5. `critText` prints a node back for display; and/or are printed in upper case inside parentheses.
**Look & layout:** n/a
**Configuration:** none
**Acceptance criteria:** for each of these 8 catalog shapes, the passing readings evaluate to true and at least one single broken reading evaluates to false:
- `max_resistance <= 0.1 AND pe_uninterrupted == true`
- strings with `'off'`
- `rated_trip_temp * 1.1`
- a nested OR in parentheses
- bare names joined by AND
- `max(...)` with a dotted threshold
- `abs()`
- `NOT manual_abort_used`

The inputs `x <= `, `a AND AND b`, `x <= 1 ; drop` and `f(1` all throw.
**Tests:** test_sim.cjs (extracts the functions from Page.html and runs the 8 criteria plus the 4 bad inputs).
**Reference (source):** Page.html 864-944; test_sim.cjs 1-32.

### CLOUD-52 — Live simulation panel in the guide window (dry run)
**Project / folder:** cloud/google/Page.html
**Goal:** Let an engineer rehearse a test before queuing it, inside the guide window only:
- the procedure steps light up one after another;
- the same questions as the real run are asked;
- the pass criteria are checked against made-up readings (the person's answers replace them), ending in a simulated PASS or FAIL.
Nothing is sent to the CureBox and nothing is recorded. See live-simulation.png and simulation-howto.png.
**Depends on:** CLOUD-47, CLOUD-51; catalog detail `prompts[]`
**Files to create:** Page.html: the Simulation box inside `dvtGuide`, `dvtSimulate(bg, d, wantFail)`, `simAsk(out, p)`.
**Public contract:**
- `d.prompts[] = {text, kind: 'yesno'|'value'|other, values?[], unit?, type?: 'float'|'int'|'bool'|string, field?}`, the questions the real run asks, in order. No server call.
**Behaviour & rules:**
1. Box content:
   - heading "Simulation" (purple);
   - muted text: "A dry run in this window only: the steps play through, it asks you the same questions as a real run, and the pass criteria are checked against made-up readings (your answers replace them). Nothing is sent to the CureBox and nothing is recorded.";
   - buttons "▶ Simulate a passing run" and "▶ Simulate a failing run";
   - an output area.
2. Pressing either button:
   - disables both buttons and clears earlier step marks;
   - plays the steps 700 ms each: the current step gets `sim-on` (purple border and tint), a done step gets `sim-done` (a green ✓ at the right), and each is scrolled into view.
3. With K prompts, prompt k is asked after step `round((k+1)·steps/(K+1))`. The step it waits on stays highlighted.
4. Question box (`simAsk`), headed "**The machine asks.** <text>":
   - yesno: Yes (primary) / No / Skip;
   - value: a select of `values`, or an input (number for float/int, otherwise text, `inputmode=decimal`) with the unit after it, then OK and Skip; Enter presses OK;
   - other: Done / Skip.
   - An empty OK means Skip. The answer is typed per `type`.
   - When the answer is not skipped and the prompt has a `field`, the answer is stored under it.
5. Then the rest of the steps play, and the page:
   - parses the criteria and builds passing readings;
   - for a failing run, tries leaves in random order and keeps the first broken reading that makes the whole expression false;
   - overlays the person's answers;
   - evaluates.
6. Result:
   - a table Check | Simulated reading | ✓/✗ with one row per leaf; readings are written `name = value`, with "(limit)" for dotted names and "(your answer)" for answered fields;
   - a verdict bar "Simulated verdict: PASS" (green tint) or "FAIL" (red tint); for a failing run that no single reading can fail it adds " - no single reading can fail these criteria";
   - a muted footnote "Simulation only - made-up numbers except your answers, not recorded.";
   - the buttons are re-enabled.
7. Unreadable criteria: "The steps played through, but the pass criteria could not be read for a simulated check (<error>)."
8. Closing the window mid-run stops the simulation (`bg.isConnected` checks).
**Look & layout:**
- `.dvt-sim`: a 1px dashed purple (#a855f7) border, 10 px radius, a faint purple background, and a purple `h4`.
- The table is 0.88rem with monospace checks; ✓ is green bold, ✗ red bold.
- The verdict bar is bold with an 8 px radius.
- live-simulation.png shows the four numbered steps each with a green ✓, the PASS CRITERIA box, the SIMULATION box with the two buttons, a table (`max_resistance <= 0.1` | `max_resistance = 0.05` ✓; `pe_uninterrupted == true` | `pe_uninterrupted = true` ✓), and "Simulated verdict: PASS".
- simulation-howto.png is a three-panel Hebrew how-to: (1) press ▶ Run next to a test after choosing CureBox-1; (2) scroll to Simulation and press a simulate button; (3) the steps light up one by one, then the readings table and PASS/FAIL appear, nothing is sent, and Cancel exits.
**Configuration:** none
**Acceptance criteria:**
- A test with three prompts asks them in catalog order (door, input voltage, fuse).
- A passing run ends PASS.
- A failing run ends FAIL when any single reading can fail.
- No network call is made during the simulation.
**Tests:** test_sim.cjs (evaluator); test_phone.cjs line 172 ("the simulation asks the questions of the real run in order").
**Reference (source):** Page.html 823-826, 860, 945-1024; CSS 273-281.

### CLOUD-53 — Work Programs and Machine Catalog lists on the machine card
**Project / folder:** cloud/google/Page.html
**Goal:** On each machine card (the card frame is the shell's Machines view), list the user's own curing programs, each with Edit and Delete, plus a "+ New Program" button. Below them, list the read-only built-in catalog the machine reports.
**Depends on:** CLOUD-20..39 (shell, machine card frame), CLOUD-54; PLAT-10 (machine applies `upsert_program` / `delete_program`, snapshot includes `programs` and `presets`, OD-52)
**Files to create:** Page.html: the program and catalog parts of `machineCard(m, i)`, the program wiring in `wireCard(m, i)` (`[data-edit]`, `[data-del]`, `[data-new]`), `programOptions(m)`.
**Public contract:**
- `POST /api/machines/<name>/commands {type:'delete_program', payload:{id}}` → `portalCommand(token, name, d)`.
  - Role `service`.
  - Types allowed: `COMMAND_TYPES = ['upsert_program','delete_program','send_print','delete_print']`.
  - Appends a row to sheet `commands` (`id, machine, type, payload, created, delivered, acked`).
- Machine snapshot fields used: `m.programs[] {id, name, steps[], totalDuration}` and `m.presets[]` (firmware 1.0.145+).
**Behaviour & rules:**
1. Work Programs table Name | Steps ("N steps") | Duration ("N min" or "–") | actions "Edit" and danger "Delete".
   - Filtered by `SEARCH` on the name.
   - Empty: "none".
2. Delete sends `delete_program` immediately, with **no confirmation** (unlike Delete print), then `load()`. OPEN QUESTION: whether a confirm should be added; the code has none.
3. "+ New Program" (primary) opens the editor (CLOUD-54) in `#editor-<i>` under the table.
4. Machine Catalog:
   - `h2` "Machine Catalog" with muted "built in · N programs";
   - table Name | Steps | Duration with no actions (no data-edit or data-del);
   - empty: "no match" when presets exist, else "not reported - the machine needs firmware 1.0.145 or newer".
5. `programOptions(m)` (used by the shell's Send Simulated Print select):
   - user programs in `<optgroup label="My programs">` first, then `<optgroup label="Catalog">`;
   - with no presets, plain options of the user programs only;
   - no empty user group;
   - names are escaped.
6. Program names are inserted into the Work Programs table without escaping (`${p.name}`), unlike the catalog. OPEN QUESTION: probably an oversight; escape them in the rebuild.
**Look & layout:** `h2` section headings inside the machine card; `table.cards`; on a phone each program is a card whose action cell has two equal-width buttons at least 46 px tall (Delete in red).
**Configuration:** none
**Acceptance criteria:**
- The catalog table lists built-in programs with step count and minutes and offers no edit or delete.
- An older machine says why the catalog is empty.
- The Send list shows each program once, user programs first.
**Tests:** test_programs.cjs; test_phone.cjs ("Machine: programs, the built-in catalog, prints and cure runs are lists of cards").
**Reference (source):** Page.html 2148-2156, 2158-2168, 2177-2203, 2456-2466, 2476-2477; Code.gs 42, 1487-1503.

### CLOUD-54 — Program editor (step rows per process, UV-only switch, process switch)
**Project / folder:** cloud/google/Page.html
**Goal:** An inline editor to create or change a curing program for a machine. It has a name and a table of steps; each step's fields follow the process chosen, mirroring the machine UI's step editor (StepModal). Cure and Bleaching steps can be UV only (no heating).
**Depends on:** CLOUD-53, CLOUD-55; DOM-03/DOM-04 (program and step wire contract)
**Files to create:** Page.html: `PROCESSES`, `PROC_LABEL`, `stepRow(s, j)`, `readRow(r, j)`, `openEditor(i, prog)`, `wireStepRows(i)`, `renumberSteps(i)`, global `editing`.
**Public contract:**
- Step object: `{step, process: 'Drying'|'Heating'|'Cure'|'Bleacher'|'Cooling'|'Nitrogen', temperature|null, intensity:null, time, uvIntensity?, timerMode?: 'on-target'|'on-ramp', uvStartMode?: 'at-target'|'at-start', coolingMode?: 'fast'|'medium'|'slow', ventilation?: bool}`.
- `heat` is editor-only and is removed before saving.
**Behaviour & rules:**
1. Opening:
   - sets `editing=true`, which stops the auto-refresh (shell `userBusy`);
   - deep-copies the steps; a new program starts with `[{process:'Drying', temperature:45, time:10}]`;
   - scrolls the editor into view and focuses the name.
2. Process labels: Cure → "Cure (405nm)", Bleacher → "Bleaching (450nm)"; the others keep their names.
3. Fields per process:
   - Temp °C:
     - number 30–80 (Cooling 30–75); default 40 (Cooling 30);
     - Nitrogen shows "–";
     - Cure/Bleacher first show a select "Heating on" / "No heating (UV only)", and UV only shows no number.
   - Time min: number 1–120 (Bleacher 1–720), default 10; Cooling and Nitrogen show "–".
   - UV %: Cure/Bleacher only, 10–100, default 30.
   - Options:
     - Cooling: select "Fast/Medium/Slow cooling" (default medium);
     - UV-only Cure/Bleacher: select "Ventilation: off" / "Ventilation: on (fresh air)";
     - heated Cure/Bleacher: two selects, "Timer: at temperature" (on-target, default) / "Timer: on ramp start" (on-ramp), and "UV: at temperature" (at-target, default) / "UV: on ramp start" (at-start);
     - Nitrogen: muted "auto purge";
     - otherwise "–".
   - Each row ends with a danger "✕ Remove step".
4. UV only = a Cure/Bleacher step with `heat===false`, or with `heat` undefined and `temperature===null`. An existing UV-only step must open as UV only, not with an invented temperature.
5. Changing the process re-reads the row (null-safe), switches the process, sets time 10 when it is missing (for processes with time), and redraws the row with the temperature carried over.
6. Switching Heating on gives temperature 40 when there is none and drops the ventilation. Switching to UV only drops the temperature.
7. "+ Step" appends `{process:'Cure'}`, a heated step at 40 °C. "✕ Remove step" removes the row and renumbers.
8. "Cancel" clears the editor and sets `editing=false`.
**Look & layout:**
- Card on the inset background: a full-width "Program name" input.
- Table `steps cards` with the columns # | Process | Temp °C | Time min | UV % | Options | (remove); compact .3rem padding; inputs at 100% width.
- Action row: "+ Step", primary "Save to machine", "Cancel", and a message span.
- Phone: each step is a card.
  - The first cell reads "Step N".
  - Fields carry the labels Temp °C / Time min / UV % / Options; inputs are at most 64% wide.
  - Options stack full width.
  - A field the process does not have (only a muted "–") is hidden.
  - Every field is at least 40 px; the page does not widen at 390 px.
**Configuration:** none
**Acceptance criteria:**
- A UV-only Cure step opens with "No heating (UV only)", no temperature, ventilation kept (on), and no timer options.
- A Heating step at 50 °C is unchanged.
- Heating on shows 40 and the timer options and drops ventilation.
- A new Cure step starts heated at 40.
**Tests:** test_editor.cjs; test_phone.cjs ("Program editor: every step is a card", "every field ... at least 40 px").
**Reference (source):** Page.html 2242-2314, 2370-2429; CSS 297-298, 369-375.

### CLOUD-55 — Program validation and "Save to machine" (upsert_program)
**Project / folder:** cloud/google/Page.html
**Goal:** Before sending a program, check it against the same limits and sequence rules the machine UI enforces (MaterialContext), show up to four errors inline, then queue an `upsert_program` command that the machine applies on its next sync.
**Depends on:** CLOUD-54; DOM-04 (program validation rules); PLAT-10 (command delivery)
**Files to create:** Page.html: `stepErrors(steps)`, `saveProgram(i, prog)`.
**Public contract:**
- `POST /api/machines/<name>/commands {type:'upsert_program', payload:{id, name, steps, totalDuration, createdAt, isPreset:false}}`.
- `id` = the existing program id, or `'cloud-' + Date.now()` for a new one.
- `totalDuration` = the sum of step `time` (minutes).
- `createdAt` = now (ISO), also on an edit.
**Behaviour & rules (exact messages):**
1. No name → "Name required". No rows → "Add at least one step".
2. Temperature, except Nitrogen and UV-only Cure/Bleacher: 30–80 (Cooling 30–75) → "Step n: temperature must be A-B°C".
3. Time, except Cooling/Nitrogen: 1–120 (Bleacher 720) → "Step n: time must be 1-T min".
4. UV, Cure/Bleacher: 10–100 → "Step n: UV intensity must be 10-100% (LEDs stay dark below 10%)".
5. More than two Nitrogen steps → "Step n: a maximum of 2 nitrogen purge steps is allowed".
6. After Nitrogen only Cure/Bleacher → "Step n: after nitrogen, only Cure or Bleaching is allowed".
7. After the Cure/Bleaching that follows N₂, only Cooling → "Step n: only Cooling is allowed after the Cure/Bleaching step that follows the N₂ purge".
8. N₂ not vented → "Nitrogen must be vented — add a Cooling step after the N₂ purge".
9. No Cure/Bleaching after N₂ → "Add a Cure or Bleaching step after the N₂ purge".
10. A heated step lower than the previous heated temperature without a Cooling in between → "Step n: temperature (X°C) cannot be lower than the previous step (Y°C) without a Cooling step".
11. A cooling target must be at least 5 °C below the previous temperature → "Step n: cooling target (X°C) must be at least 5°C below the previous step (Y°C)". A Cooling step resets the reference temperature.
12. Errors are shown in the red message span: the first 4 joined by line breaks, plus "…and N more".
13. On success:
    - "Saved — the machine applies it on its next sync (≤10 s)";
    - after 1.6 s the editor closes, `editing=false`, and `load(true)` runs.
    - A 403 for a Viewer is flashed (CLOUD-57).
**Look & layout:** the message in `.msg` (green) or `.msg.err` (red) next to the buttons.
**Configuration:** none
**Acceptance criteria:**
- A UV-only step saves with `temperature:null`, `ventilation` as chosen and no `heat` key.
- Other steps keep their temperatures.
- Each rule above produces its message.
**Tests:** test_editor.cjs (save payloads). OPEN QUESTION: `stepErrors` has no direct unit test in cloud/google; reuse the DOM-04 cases.
**Reference (source):** Page.html 2316-2368, 2431-2454.

### CLOUD-56 — Sign-in screen (shared password or Google) on the page
**Project / folder:** cloud/google/Page.html
**Goal:** Show the right sign-in screen:
- the shared portal password until Google sign-in is configured;
- after that, one "Sign in with Google" button that opens Google in a new window, while the page polls until the sign-in finishes.
Any 401 brings this screen back.
**Depends on:** CLOUD-20..39 (shell shim, `load`); server `portalLoginMode`, `portalLogin`, `portalLoginStart`, `portalLoginPoll`, `googleCallback_`
**Files to create:** Page.html: `renderLogin(msg)`, `googleWait(l)`, `doLogin()`, state `LOGIN {state, url, waiting}`. The shim routes `/login`, `/login/mode`, `/login/google`, `/login/poll` (shell).
**Public contract:**
- `portalLoginMode()` → `{google: bool}` (true once the script properties GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set).
- `portalLogin(password)` → `{ok, token}` or `{ok:false, message}`. It checks SECRETS.password, which build_secrets.py generates from a git-ignored file. Never put the value in tickets or source.
- `portalLoginStart()` → `{ok, url, state}`.
- `portalLoginPoll(state)` → `{pending:true}`, or once `{ok, token}` or `{ok:false, message}`.
- The token is kept in sessionStorage `scure-cloud-token`, with an in-memory fallback. A session lasts 6 h (`SESSION_SEC`).
**Behaviour & rules:**
1. `renderLogin()` with no message does nothing when `#login` is already on screen, so the 10 s refresh does not restart a sign-in. It clears `ME` and the header.
2. Password mode:
   - card `#login` (max 340px, 16vh from the top), `h2` "Sign in";
   - a row with a password input (placeholder "Portal password") and a primary "Sign in" button; Enter submits;
   - a red message below;
   - wrong password → "Wrong password" or the server message;
   - success → `load(true)` (forced, because the focused field counts as busy).
3. Google mode:
   - card `.login-g` (max 30rem), `h2` "Sign in to sCure Cloud", muted "Use the Google account an admin added to sCure Cloud.";
   - `a.btn.primary#g-go` "Sign in with Google" (`target=_blank`, `rel=noopener`, at least 46 px). If the start call failed, instead: red "Google sign-in is not reachable right now - reload the page in a moment.";
   - a hidden `#g-wait` "Finish signing in in the Google window that opened. This page continues by itself.";
   - a red `#g-err`.
   - No password field.
4. On click (once): show `#g-wait` and poll `/login/poll` every 1.5 s for at most 10 min:
   - pending → keep going;
   - ok → `load(true)`;
   - otherwise → `renderLogin(message || 'Sign-in failed - press Sign in again.')`.
   - A newer LOGIN cancels the loop.
5. Once Google sign-in is on, the password no longer works (server).
**Look & layout:** as above; on a phone the buttons are at least 44 px.
**Configuration:** script properties GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OWNER_EMAIL; SECRETS.password (mechanism only)
**Acceptance criteria:**
- With Google on, the screen is one Google button opening in a new window and there is no `#pw`.
- After the click it says to finish in the Google window.
- When the poll returns ok, the app loads and the header shows the person.
**Tests:** test_people.cjs (lines 60-80).
**Reference (source):** Page.html 4-55, 438-487; Code.gs 1259-1335.

### CLOUD-57 — Signed-in identity in the header, role gating on the page, flash toast
**Project / folder:** cloud/google/Page.html
**Goal:** Show who is signed in and with what access (Viewer / Service / Admin), offer People to admins and Sign out to everyone, and turn server refusals into a short toast that names the access needed.
**Depends on:** CLOUD-20..39 (header region `#who`), CLOUD-56; server `portalMe`, `portalLogout`, `need_`
**Files to create:** Page.html: `renderWho()`, `signOut()`, `api(path, opts)` (the 401/403 handling), `flash(text)`, state `ME`.
**Public contract:**
- `portalMe(token)` → `{email, name, role, roleLabel, owner, via: 'google'|'password', canService, canAdmin}` or `null`.
- Server role ladder `ROLES = ['view','service','admin']`:
  - view: sees everything;
  - service: plus machine commands, DVT request/cancel/answer/acted, unit registry, race;
  - admin: plus approve ELE, people list, audit log.
- A refusal is `{ok:false, denied:true, message:"<What> needs <Role> access - you are signed in as <Role>. Ask an admin."}` and is audited.
**Behaviour & rules:**
1. `ME` is fetched once per sign-in, from `load()`, without holding up the page.
2. Header:
   - the name: "Shared password" when `via==='password'`, else the name or email; ellipsis at max 14rem (8rem on a phone); the title attribute is the email;
   - a grey pill with `roleLabel`;
   - a "People" button only when `canAdmin` (primary while `VIEW==='people'`);
   - "Sign out".
   - Buttons are at least 44 px.
3. `api()`:
   - 401 → `ME=null`, `renderLogin()`, throw `auth`;
   - 403 → `flash(message || 'Your access does not allow this.')`, throw `denied`.
4. `flash`:
   - a fixed toast at the bottom centre, `max-width: min(34rem, 100% − 2rem)`;
   - inverted colours (`--text` background, `--bg` text), 10 px radius, `role=status`;
   - fades in .2s and hides after 6 s; a new message restarts the timer;
   - on a phone it sits at 5.5rem from the bottom, above the section bar.
5. Sign out: `POST /logout` → `portalLogout`, which audits "signed out" and kills the token. The page clears the token and shows the sign-in screen with an empty header.
6. The page does not hide service-only buttons from viewers. The server refuses and the toast explains. OPEN QUESTION: `canService` is sent but unused by the page.
**Look & layout:** as above (CSS 159-173).
**Configuration:** none
**Acceptance criteria:**
- The header shows "Owner", "Admin", "People" and "Sign out" for the owner.
- A viewer sees "Viewer" and no People button.
- A viewer's action produces a toast containing "needs Service access".
- After sign-out the header is empty.
**Tests:** test_people.cjs (lines 75-121).
**Reference (source):** Page.html 421-436, 488-507, 592-597; Code.gs 1150-1257, 1337-1350.

### CLOUD-58 — People screen (admins): who may sign in, access, recent activity
**Project / folder:** cloud/google/Page.html
**Goal:** Give admins one screen to add people by Google account email with an access level, change a person's access in place, and remove someone, with the owner protected. The screen also explains how to turn Google sign-in on, and shows recent activity (sign-ins, refusals, changes).
**Depends on:** CLOUD-57; server `portalUsers`, `portalUserSave`, `portalUserRemove`, `portalAudit`
**Files to create:** Page.html: `loadPeople()`, `peopleCard()`, `peopleWire()`, `ROLE_HELP`, state `PEOPLE {users, google, redirectUri, audit}`; `VIEW='people'` in `render()` (no CureBox chooser).
**Public contract:**
- `/api/users` → `portalUsers(token)` → `{ok, users[{email, role, name, added, addedBy, lastLogin, owner}], google, redirectUri}`.
- `/api/users/save {email, role, name}` → `portalUserSave`.
- `/api/users/remove {email}` → `portalUserRemove`.
- `/api/audit` → `portalAudit(token, 100)` → `{ok, rows[{unix, email, action, detail}]}`.
- All of these need `admin`.
- Sheets: `users` (`email, role, name, added, addedBy, lastLogin`) and `audit` (`time, unix, email, action, detail`).
**Behaviour & rules:**
1. A non-admin sees the card "People" / "Only an admin can see the people list."; while loading, "Loading…".
2. When Google sign-in is off, an amber box above the card reads:
   - "**Google sign-in is not on yet** - everyone still signs in with the shared password.";
   - steps: create an OAuth client (type Web application) with the shown redirect URI (`code`, wrapping), then set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the script properties;
   - "Add the people below first - yourself as Admin too - once it is on, only they can sign in."
3. Card "People":
   - muted "Who can open sCure Cloud, and what they may do.";
   - a list of the three roles: "Viewer - sees everything, changes nothing" / "Service - also requests DVT tests, sends programs, edits units and the race" / "Admin - also approves safety runs and manages people".
4. Add row:
   - email (`type=email`, placeholder "name@company.com"), "Name (optional)", an access select (default Viewer), primary "Add";
   - an empty email gives "Write the person's Google account email.";
   - a server refusal is shown in the red `#pp-msg` (e.g. "Write a full email address", "Choose Viewer, Service or Admin", "The owner is always an admin");
   - success: flash "<email> can now sign in.", clear the fields, reload.
5. Table `cards` Person | Access | Last sign-in | (action):
   - Person: the bold name or email, with the muted email under a name;
   - Access: for the owner, "Admin (owner)" with no controls; otherwise a select that saves on change (flash "Saved: <email> is now <Role>.", a refusal is flashed, e.g. "… is the last admin - make someone else an admin first");
   - Last sign-in: `fmtAgo` or "never";
   - "Remove" (not for the owner): `confirm("Remove <email>? They are signed out at once and can no longer open sCure Cloud.")`, then flash "<email> was removed."
6. `<details class="card">` with the summary "**Recent activity** sign-ins, refusals and every change" holds a table When | Who ("shared password" when the email is empty) | What (action + muted detail), the newest 50 rows; empty: "Nothing yet."
7. After every change: `loadPeople()` and `render()`.
**Look & layout:** cards as above; on a phone at 390 px: no sideways scroll, every control at least 44 px, fields 16 px text.
**Configuration:** script properties GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OWNER_EMAIL
**Acceptance criteria:** see test_people.cjs lines 80-138:
- the list shows the owner and each person;
- the role help is on screen;
- only one Remove (not the owner's);
- Add sends `('new@lab.com','service','Nadia')`;
- changing a select saves;
- Remove after the confirm takes the person off;
- "Recent activity" sits in a fold.
**Tests:** test_people.cjs; test_code.cjs "people and roles" (server).
**Reference (source):** Page.html 509-584, 1983, 1995-1997; CSS 159-169; Code.gs 1150-1432.

### CLOUD-59 — Confirmations, prompts, toasts and empty states (dialog inventory outside Overview / Machines / Race / Compare)
**Project / folder:** cloud/google/Page.html
**Goal:** List every small dialog the tool views use, so the rebuild keeps the exact wording and the exact cancel behaviour. The page uses the browser's native `confirm()`/`prompt()` (no custom modal) except for the DVT guide window (CLOUD-47).
**Depends on:** CLOUD-46, CLOUD-50, CLOUD-57, CLOUD-58; CLOUD-20..39 (shell) for Machines-only dialogs
**Files to create:** none new (wording inventory).
**Public contract:** n/a
**Behaviour & rules:** native dialogs (OK proceeds, Cancel does nothing):
1. Run all: `confirm("Queue N test(s) on <box>? Each one waits for Start at the machine.")`.
2. Stop all: `confirm("Stop all N open request(s) on <box>? A test that is running there is stopped and the machine turns everything off.")`.
3. Approve: `prompt("Who approves <tid>?", <remembered or 'Alex'>)`; an empty answer cancels.
4. Withdraw: `confirm("Withdraw the approval of <tid>?")`.
5. Remove person: `confirm("Remove <email>? They are signed out at once and can no longer open sCure Cloud.")`.
6. Delete print (Machines view, shell-owned, listed for completeness): `confirm('Delete print "<name>" from <box>?')`.
7. No confirm on Delete program (CLOUD-53 open question), Cancel request, Force stop, or Stop the run.

Toasts (`flash`, 6 s): refusals (403 message); "<email> can now sign in."; "Saved: <email> is now <Role>."; "<email> was removed."; "Not saved" / "Not removed" fallbacks.

Inline banners:
- the stale-build Reload banner (CLOUD-42);
- "Google sign-in is not on yet" (CLOUD-58);
- the DVT refusal line `DVT_MSG` (red, in the run panel and the guide strip).

Empty and loading states:
- "Loading…" cards for Errors, DVT and People;
- "No errors today";
- the DVT no-results instructions (CLOUD-43);
- "none" / "no match" / firmware note in program tables;
- "not run yet" for owed runs;
- "Nothing matches the search" / "No tests on this unit";
- the no-machine screen: card "Machines" with "No machine has synced yet. Give the machine this portal's URL and its machine key (machine API: POST /api/cloud/config with url, key and name)." and a "🧪 DVT" button that keeps DVT reachable (shell `render`, see API-10).

Busy-state rule: re-renders are skipped while an editor is open, a field has focus, or the send-print form is half filled (`userBusy`). The guide window lives outside `#app`, so it survives re-renders.
**Look & layout:** native dialogs; the toast as in CLOUD-57.
**Configuration:** none
**Acceptance criteria:**
- Each listed action shows exactly the listed text.
- Cancelling any confirm sends no request.
**Tests:** test_people.cjs (the remove confirm accepted through a dialog handler); test_phone.cjs (Withdraw dialog). OPEN QUESTION: Run all and Stop all confirms are not exercised by a test.
**Reference (source):** Page.html 412-436, 1958-1967, 2043-2088, 2468-2471, 574-583.
