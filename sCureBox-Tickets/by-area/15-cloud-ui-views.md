## sCure Cloud portal — UI shell and views

Source: `cloud/google/Page.html` (portal build 0.9.146, 2,531 lines, one file: inline `<script>` shim, inline `<style>`, inline app script). The page is served by `doGet` in `Code.gs` via `HtmlService.createHtmlOutputFromFile('Page')`, with title "sCure Cloud", a viewport meta tag and `XFrameOptionsMode.ALLOWALL` so it can be embedded in Google Sites. Server functions, sheets and sync are covered by CLOUD-01..19 (server). Errors, DVT, the program editor, People and Simulation are covered by CLOUD-40..59. The machine side is covered by PLAT-10 (sync agent), API-10 (cloud config endpoints) and DVT-05 (remote confirm).

The page has no client framework. Each view is a function that returns an HTML string, which is assigned to `#app.innerHTML`. A matching `*Wire()` function then attaches the handlers. The whole page re-renders on every state change.

Screenshots in the folder (`run-window.png`, `live-simulation.png`, `simulation-howto.png`) show the DVT guide modal (CLOUD-40..59). They also show the header and section bar from an older build. **OPEN QUESTION:** in those screenshots primary buttons are near-black and the "Machine" tab uses an emoji icon. The current CSS uses a cobalt `--acc` (#2457d6) and SVG line icons. Build to the code, not to the screenshots.

---

### CLOUD-20 — Page shell, server-call shim and API wrapper
**Project / folder:** cloud/google/Page.html
**Goal:** The page talks to Apps Script only through `google.script.run`, but the app code calls `fetch('/api/...')`. A small shim at the top of `<head>` replaces `window.fetch` and turns REST-like paths into `google.script.run` calls. It adds the session token and returns a fetch-like response with `status`, `ok` and `json()`. This keeps the view code independent of Apps Script, so the browser tests can stub `google.script.run`.
**Depends on:** CLOUD-01..19 (server)
**Files to create:** Page.html: the first `<script>` block (IIFE: `tok`, `setTok`, `call`, `reply`, `window.fetch`, `window.scureReportHref`, `window.scureDvtFileHref`); the app script helpers `$`, `api(path, opts)`, `flash(text)`, `escH`, `fmtAgo`, `fmtTime`, `fmtDur`, `fmtWhen`, `fmtBytes`.
**Public contract:**
- Token: `sessionStorage['scure-cloud-token']`, with an in-memory fallback `mem` when storage throws.
- `call(fn, ...args)` → `Promise` wrapping `google.script.run.withSuccessHandler(res).withFailureHandler(rej)[fn](...args)`.
- Routing table (path → server function, args):
  - `/login` → `portalLogin(password)`. If `r.ok`, store `r.token` and answer 200 `{ok:true}`; otherwise answer 401 `{ok:false,message}` (default message 'Wrong password').
  - `/login/mode` → `portalLoginMode()`. On failure, answer `{google:false}`.
  - `/login/google` → `portalLoginStart()`.
  - `/login/poll` → `portalLoginPoll(body.state)`. On `{ok,token}`, store the token and answer `{ok:true}`.
  - `/logout` → `portalLogout(tok())`, then clear the token.
  - `/api/me` → `portalMe(tok)`.
  - `/api/users` → `portalUsers`; `/api/users/save` → `portalUserSave(tok,email,role,name)`; `/api/users/remove` → `portalUserRemove(tok,email)`; `/api/audit` → `portalAudit(tok,100)`.
  - `/api/machines` → `portalMachines(tok)`.
  - `/api/alerts?since=N` → `portalAlerts(tok, N)`.
  - `/api/dvt` → `portalDvt`; `/api/dvt/wait?since=X&wait=N` → `portalDvtWait(tok, X, N)`; `/api/dvt/detail` → `portalDvtDetail`.
  - `/api/dvt/race` → `portalRaceSet(tok, body)`; `/api/dvt/files` → `portalDvtFiles(tok, body.ids)`; `/api/dvt/unit` → `portalDvtUnitSave(tok, body.unit, body.fields)`.
  - `/api/dvt/approve` → `portalDvtApprove(tok, unit, testId, runIds, who, approve!==false)`.
  - `/api/dvt/request|cancel|answer|acted` → `portalDvtRequest(tok,machine,unit,testIds)` / `portalDvtCancel(tok, ids||id, force===true)` / `portalDvtAnswer(tok,id,value??null)` / `portalDvtActed(tok,id)`.
  - `/api/machines/<name>/commands` → `portalCommand(tok, decodeURIComponent(name), body)`.
  - Any other path → 404 `{ok:false,message:'not found'}`.
- Status mapping: a server `null` means 401. `{denied:true}` means 403. For write calls, `ok:false` means 400. Everything else is 200.
- `window.scureReportHref(m, runId, download)` → `m.reportUrl + '?report=<runId>&m=<m.name>&t=<token>[&dl=1]'`, or `'#'` when there is no `reportUrl`.
- `window.scureDvtFileHref(fileUrl, id)` → `fileUrl + '?dvtfile=<id>&t=<token>'`.
- `api(path, opts)`:
  - Always sends the JSON content-type header.
  - On 401: sets `ME=null`, calls `renderLogin()` and throws `Error('auth')`.
  - On 403: calls `flash(d.message || 'Your access does not allow this.')` and throws `Error('denied')`.
  - Otherwise returns `r.json()`.
**Behaviour & rules:**
1. The shim script must come before any app code. It is the first element in `<head>`.
2. The body is parsed from `opts.body` as JSON. A parse error gives `{}`.
3. `flash(text)` creates `#flash` (role=status) on first use. It sets the class `on` and removes it after 6000 ms. A new flash resets the timer.
4. `escH` escapes `& < > "`. Every value that comes from the server must pass through `escH`. **OPEN QUESTION / defect:** `machineCard` and `cureRows` insert `p.name`, `m.name` and `c.materialName` without escaping. A rebuild should escape them.
5. Formatters:
   - `fmtAgo(t)`: 'never' when t is falsy; then `Ns ago`, `Nm ago` or `Nh ago`, with thresholds at 60 s and 3600 s.
   - `fmtTime`: locale `HH:MM:SS`.
   - `fmtDur(s)`: `N s` below 60, `M min S s` below 3600, otherwise `H h M min`.
   - `fmtWhen(t)`: '—' when empty; `fmtAgo` when less than 24 h old; otherwise `DD Mon HH:MM`.
   - `fmtBytes`: B, KB or MB.
**Look & layout:** n/a, except `#flash`: a fixed toast centred at the bottom (`bottom:1.2rem`; on a phone `5.5rem`, above the bottom bar). It is at most `min(34rem, 100%-2rem)` wide, inverted colours (`background:var(--text)`, `color:var(--bg)`), radius 10px, and fades in and out over .2 s.
**Configuration:** none. No secrets live in the page; the token comes from the server at runtime.
**Acceptance criteria:**
- With `google.script.run` stubbed, every path in the table calls the named function with the listed arguments.
- A `null` server answer shows the sign-in screen.
- A `{denied:true}` answer shows a toast with the server message, and the view stays as it was.
- The report link contains `report=`, `m=` and `t=` parameters, plus `dl=1` only for Download.
**Tests:** All test_*.cjs files inject a `STUB` before the page loads (`window.google.script.run` built from a handlers map) and so exercise the shim. See CLOUD-35.
**Reference (source):** Page.html 1-121, 406-436, 586-590, 628-630, 682-694; Code.gs 1137-1144 (doGet).

### CLOUD-21 — Design tokens, theme and shared components
**Project / folder:** cloud/google/Page.html (`<style>`)
**Goal:** A calm, neutral look in which the status colours (green, red, amber) stand out, with a single cobalt accent for actions and progress. The theme follows the system light or dark setting. All views share the same small set of components: card, pill, stat, tile, banner, badge, table and fold.
**Depends on:** CLOUD-20
**Files to create:** Page.html `<style>` lines 127-301, plus the Google Fonts `<link>` for IBM Plex Sans 400/500/600.
**Public contract:** CSS custom properties on `:root`. Light values first; dark values (under `prefers-color-scheme: dark`) in brackets:
- `--bg` #f5f6f8 (#0e1116); `--panel` #ffffff (#171b22); `--line` #e3e6eb (#262d37); `--line2` #cfd4dc (#38414d)
- `--text` #14181f (#e8ecf1); `--mut` #5b6472 (#9aa5b4)
- `--acc` and `--acc2` #2457d6 (#7da2ff); `--on-acc` #ffffff (#0b1220)
- `--ok` #15803d (#4ade80); `--err` #c62828 (#f87171); `--warn` #b45309 (#fbbf24)
- `--field` #ffffff (#11151b); `--inset` #f0f2f5 (#1b2129)
- `color-scheme` is light or dark to match.
- In dark mode the header logo gets `filter:invert(1) hue-rotate(180deg)`.

Classes: `.card`, `.pill(.on|.off|.bad|.warn)`, `.badge(.safety)`, `.stat`, `.dvt-tile/.num`, `.dvt-bar`, `.now(.bad|.warn|.good)`, `details.more`, `.row`, `.mut`, `.msg(.err)`, `.ok-t/.err-t/.warn-t`, `button.primary`, `button.danger`, `a.btn(.primary)`, `.subtab(.active)`, `.dvt-prompt`.
**Behaviour & rules:**
1. The comment rule is: change the look in the tokens first. A literal colour in a rule is a smell. **Known exceptions in source** (keep, or move into tokens):
   - the race gold #d4a017;
   - the DVT and Gantt status colours in the JS `OV_COL` (PASS #16a34a, FAIL #dc2626, BLOCKED #d97706, WAIVED #6b7280, INVALID #9333ea, RUNNING #2563eb, open #d4d4d8);
   - the Compare curve palette `CMP_COLORS` (#2563eb, #dc2626, #16a34a, #d97706, #9333ea, #0891b2, #db2777, #4b5563);
   - amber #d97706 in `.pill.warn`, `.warn-t` and `.dvt-ic.warn`.
2. Body: `15px/1.5 "IBM Plex Sans", system-ui, …` with antialiasing. Tables use `font-variant-numeric:tabular-nums`.
3. `:focus-visible` gets a 2px `--acc` outline with a 2px offset. Inputs get an `--acc` border on focus. Disabled controls are at opacity .5 with a not-allowed cursor. A hovered button gets the `--inset` background; a hovered primary button gets `brightness(1.08)`.
**Look & layout:**
- Header (`<header>`): flex row with `.8rem 1.4rem` padding, `--panel` background and a bottom border `--line`. It holds:
  - a 42px-high Stratasys logo (`<img class="logo" alt="Stratasys">`, a base64 PNG inline in the file);
  - `<h1>sCure Cloud</h1>` at 1.1rem, weight 650;
  - `#who`, pushed right with `margin-left:auto` (CLOUD-22).
- `main#app`: max-width 1060px, centred, padding `1.2rem 1.4rem 3rem`.
- `.card`: `--panel` background, 1px `--line` border, radius 12px, padding `1.1rem 1.3rem`, `margin-bottom:1rem`, shadow `0 1px 2px rgba(16,24,40,.04)`.
- `h2`: 1.1rem, weight 650, colour `--text` (titles are never blue). A muted sub-title often follows inside the h2 as `<span class="mut" style="font-weight:400">`.
- Tables: full width, collapsed borders, cell padding `.45rem .6rem`, bottom border `--line`. `th` is muted, weight 600, .82rem.
- Inputs, selects and buttons: `--field` background, 1px `--line2` border, radius 8px, padding `.45rem .75rem`. `button.primary` is the `--acc` fill with `--on-acc` text, weight 600. `button.danger` has `--err` text.
- `.pill`: radius 999px, padding `.1rem .55rem`, .78rem.
  - `.on`: green text on rgba(22,163,74,.12).
  - `.off` and `.bad`: red text on a red tint.
  - `.warn`: amber text.
- `.stat`: an inline column with the value in bold 1.25rem and a muted .78rem label below.
- `.dvt-tile`: a bordered box (radius 10px) with the number centred at 1.7rem bold and a muted label below.
- `.dvt-bar`: a 6px track in `--line` with a `--ok` fill.
- `.now` banner: a flex row with radius 12px. Its title is 1.05rem/600 and the muted sub-line is .88rem. Tones:
  - `bad`: `--err` border, background `color-mix(err 8%, panel)`;
  - `warn`: 9% warn tint;
  - `good`: 8% ok tint.
- `details.more > summary`: shows ▸ or ▾, muted, min-height 44px.
**Configuration:** none
**Acceptance criteria:**
- Switching the OS to dark mode changes every surface through the tokens alone, and the logo stays visible (inverted).
- Every status uses green, red or amber; only actions use the accent.
**Tests:** test_phone.cjs checks body text ≥ 14px and 16px text in fields (CLOUD-34).
**Reference (source):** Page.html 125-301, 402.

### CLOUD-22 — Sign-in screen and the "who" area of the header
**Project / folder:** cloud/google/Page.html
**Goal:** Show a sign-in card until a session exists. It works in one of two modes: a shared password (before Google sign-in is configured) or "Sign in with Google" (a new window, plus polling). After sign-in, the header shows who is signed in, their role pill, a People button for admins and Sign out.
**Depends on:** CLOUD-20, CLOUD-21, CLOUD-01..19 (server: `portalLoginMode`, `portalLogin`, `portalLoginStart`, `portalLoginPoll`, `portalMe`, `portalLogout`)
**Files to create:** Page.html `renderLogin(msg)`, `googleWait(l)`, `doLogin()`, `signOut()`, `renderWho()`; state `ME`, `LOGIN`.
**Public contract:**
- `ME = {email, name, role, roleLabel, owner, via ('password'|'google'), canService, canAdmin}` (from `portalMe`).
- `LOGIN = {state, url, waiting}`.
**Behaviour & rules:**
1. `renderLogin()` with no message returns at once if `#login` is already on screen, so the 10 s refresh never restarts a sign-in. It clears `ME` and the header.
2. The mode comes from `/login/mode`. If that throws, use password mode.
3. Password mode: the card `#login` (max-width 340px, top margin 16vh) holds:
   - h2 "Sign in";
   - a row with `#pw` (type password, placeholder "Portal password", flex 1) and the primary button `#go` "Sign in";
   - an error line `p.msg.err`.
   Enter in `#pw` or a click on `#go` calls `doLogin`. On success, `load(true)` runs (forced, because the focused field counts as busy). On failure, the screen re-renders with the server message or 'Wrong password'.
4. Google mode: the page first POSTs `/login/google`. The card `.login-g` (max-width 30rem, margin 2rem auto) holds:
   - h2 "Sign in to sCure Cloud";
   - the muted line "Use the Google account an admin added to sCure Cloud.";
   - the link `a.btn.primary#g-go` "Sign in with Google" (target _blank, min-height 46px). If the start call failed, the red line "Google sign-in is not reachable right now - reload the page in a moment." appears instead;
   - a hidden `#g-wait` line: "Finish signing in in the Google window that opened. This page continues by itself.";
   - `#g-err`.
5. Clicking the Google link (only once, guarded by `LOGIN.waiting`) shows `#g-wait` and starts `googleWait`. It polls `/login/poll` every 1500 ms for up to 10 minutes while `LOGIN` is unchanged:
   - `pending` → keep polling;
   - `ok` → `load(true)`;
   - otherwise → `renderLogin(message || 'Sign-in failed - press Sign in again.')`.
6. `renderWho()` fills `#who`:
   - the name: "Shared password" when `via==='password'`, otherwise name or email, with the email as tooltip. Max 14rem with ellipsis (8rem on a phone);
   - `.pill.who-role` showing `roleLabel` (muted on `--inset`);
   - a "People" button for admins only. It is primary while `VIEW==='people'`; a click sets `VIEW='people'`, then calls `render()` and `loadPeople()` (People view: CLOUD-40..59);
   - a "Sign out" button: POST `/logout`, then `ME=null` and `renderLogin()`.
   All buttons are at least 44px high.
7. `ME` is fetched lazily from `load()` once per sign-in (guarded by `load.me`), without blocking the render.
**Look & layout:** As described above. `#who` is a wrapping flex row, right-aligned, with a .5rem gap.
**Configuration:** none (server script properties decide the mode).
**Acceptance criteria:**
- With `portalLoginMode` returning `{google:false}`, the password card appears, and a correct password leads to the sections.
- With `{google:true}`, the Google button appears, and polling stops after success or after 10 minutes.
- A Viewer sees no People button.
**Tests:** test_overview/race/compare/phone type into `#pw` and click `#go` (stub `portalLogin` → `{ok:true, token:'tok'}`).
**Reference (source):** Page.html 159-173, 296, 438-507; Code.gs 1259-1350.

### CLOUD-23 — Section navigation, routing, CureBox chooser and search
**Project / folder:** cloud/google/Page.html
**Goal:** A single `render()` dispatcher. It draws a row of six icon tabs (Overview, Machine, DVT, Race, Compare, Errors), plus People from the header. Under the tabs it shows a CureBox chooser with a search field, but only for the views that are about one CureBox. Routing is in-memory state; there is no URL hash.
**Depends on:** CLOUD-20, CLOUD-21, CLOUD-22
**Files to create:** Page.html `NAV_ICON`, `render()`, the state `VIEW`, `SELECTED`, `SEARCH`.
**Public contract:**
- `VIEW ∈ {'overview','machines','dvt','race','compare','errors','people'}`. The default is `'overview'` on every load (not persisted).
- `SELECTED`: `'all'` or a machine name. It is persisted in `localStorage['scure-curebox']`.
- `SEARCH`: a string, not persisted.
- DOM hooks: `[data-view]`, `[data-tab]`, `#search`, `#dvt-machine`.
**Behaviour & rules:**
1. No-machine screen: shown when `MACHINES` is empty, `VIEW` is not dvt, overview, compare, race or people, and there are no DVT runs. It renders:
   - a single button `[data-view=dvt]` "🧪 DVT";
   - a card "Machines" with the text "No machine has synced yet. Give the machine this portal's URL and its machine key (machine API: `POST /api/cloud/config` with url, key and name)." (see API-10).
2. `SELECTED` falls back to `'all'` when the machine is unknown. On the DVT tab, a name known only from DVT runs, or `DVT_NONE`, is still valid. On the DVT tab with exactly one machine and no stored choice, that machine is selected automatically.
3. Section bar: `.row.sections`, sticky at the top (z 10, `--bg` background), gap 0, bottom border `--line`. Each `button.subtab` contains `<span class="ic">` with an 18px SVG and `<span class="lb">` with the label.
   - Inactive tabs: muted text, transparent 2px bottom border.
   - Active tab: `--acc` bottom border, `--text` colour, weight 600.
   - Labels: Overview, Machine, DVT, Race, Compare, Errors.
4. Icons are 24×24 line SVGs with `stroke="currentColor"`, width 1.8, round caps (no emoji, because emoji look different on every phone):
   - overview: four squares;
   - machines: a monitor (screen plus stand);
   - dvt: a lab flask;
   - race: a flag;
   - compare: a bar chart;
   - errors: a warning triangle.
5. Chooser: hidden on overview, compare, race and people. Otherwise a row shows:
   - the muted label "CureBox:";
   - an "All" button, then one button per machine, labelled `name ●` when online or `name ○` when offline. The selected one is `.primary`;
   - `#search`, right-aligned, min-width 220px. Its placeholder depends on the view: DVT "Search unit / test / operator...", Errors "Search errors / codes...", otherwise "Search programs / prints...".
6. Tab clicks:
   - overview, race and compare → `render()` then `loadDvt()`;
   - dvt → also `dvtLongPoll()`;
   - errors → forces `SELECTED='all'` and calls `loadErrors()`;
   - machines → `render()` only.
7. Picking a CureBox (a chip, or `#dvt-machine` in the DVT view) sets `SELECTED`, stores it and re-renders. When on Errors, it switches to Machine.
8. Search: every keystroke sets `SEARCH`, re-renders, then puts focus and the caret back at the end of `#search`.
9. `render()` also wires the DVT controls (`data-dvt-*`; their behaviour is in CLOUD-40..59) and calls `dvtGuideRefresh()` at the end.
**Look & layout:** The sticky top bar sits under the header, followed by the chooser row (`margin-bottom:1rem`), then the view cards. On a phone the bar moves to the bottom (CLOUD-34).
**Configuration:** none
**Acceptance criteria:**
- The Overview, Race and Compare tabs show no `[data-tab]` and no `#search`.
- The Machine, DVT and Errors tabs show `[data-tab="all"]` and one chip per machine.
- A reload keeps the chosen CureBox but opens on Overview.
**Tests:** test_overview.cjs: "the Overview has no CureBox chooser"; for Machine, DVT and Errors, "the … section shows the CureBox chooser". The race and compare tests have the same no-chooser checks.
**Reference (source):** Page.html 175-177, 190-194, 603-608, 1943-2125.

### CLOUD-24 — Data loading, polling cadence, busy guard, live clocks and the PORTAL_BUILD reload banner
**Project / folder:** cloud/google/Page.html
**Goal:** Keep the page fresh without ever re-rendering under the user's hands. It polls machines every 10 s, polls DVT data on the DVT-related tabs, and long-polls on the DVT tab. When the server was redeployed since the tab was opened, it shows a "This page is out of date" banner with a Reload button.
**Depends on:** CLOUD-20, CLOUD-23, CLOUD-01..19 (server: `portalMachines`, `portalDvt`, `portalDvtWait`, `PORTAL_BUILD`)
**Files to create:** Page.html `userBusy()`, `load(force)`, `loadDvt()`, `refreshLoop()`, `dvtLongPoll()`, the 1 s clock interval, `PORTAL_BUILD` constant; state `MACHINES`, `DVT`, `editing`, `LAST_FULL`, `DVT_VER`, `LONGPOLL_ON`.
**Public contract:**
- `const PORTAL_BUILD = '0.9.146'`. It must equal `PORTAL_BUILD` in Code.gs, which `portalDvt` returns as `build`.
- `MACHINES`: the array from `portalMachines` (fields in CLOUD-28).
- `DVT`: `{runs, fileUrl, catalog, requests, runners, units, race, now, build}`, plus a client-added `skew = DVT.now - Date.now()/1000`.
**Behaviour & rules:**
1. `userBusy()` is true when any of these holds:
   - `editing` is set (the program editor is open);
   - the focused element is an INPUT, SELECT or TEXTAREA;
   - any `[id^="job-"]` or `[id^="printer-"]` field holds text (a half-filled print form).
2. `load(force)`:
   - when not forced, it returns while busy;
   - it fetches `/api/machines`, then fetches `ME` lazily;
   - it re-checks busy, then calls `render()`;
   - on Errors it also calls `loadErrors()`; on dvt, overview, compare or race it calls `loadDvt()`.
3. `loadDvt()` normalises the catalog:
   - tests with `group==='ELE'` become `auto=false, manual=true`, and when they list UUT-01 their units become `['UUT-01']` only;
   - each phase's tests are sorted with a numeric-aware `localeCompare`.
   It then sets `skew` and re-renders when on dvt, overview, compare or race and not busy. On the DVT tab it fetches the detail when `catalog.updated` changed (CLOUD-40..59).
4. Cadence:
   - `load()` runs immediately;
   - `refreshLoop` first fires after 4000 ms, then reschedules itself every 10000 ms (8000 ms on the DVT tab);
   - on the DVT tab, a run within 9000 ms of the last full load fetches only `loadDvt()`; otherwise it does a full `load()` and updates `LAST_FULL`;
   - errors inside the loop are swallowed.
5. Long poll (DVT tab only, single instance): loop `/api/dvt/wait?since=<DVT_VER>&wait=15`. When `ver` changes, call `loadDvt()`. On error, wait 3000 ms and retry. Stop when `VIEW !== 'dvt'`.
6. Clocks: `setInterval` every 1000 ms updates every `[data-clock]` element's text to `fmtClock((data-end || raceNow()) - data-clock)`, without re-rendering. `raceNow()` is `Date.now()/1000 + DVT.skew`, so a phone with a wrong clock does not skew the race.
7. Stale banner: on the Overview (and the DVT catalog card), when `DVT.build && DVT.build !== PORTAL_BUILD`, prepend `<div class="dvt-prompt">` with "**This page is out of date** - the portal was updated since it was opened." and a primary "Reload" button (`location.reload()`).
**Look & layout:** `.dvt-prompt` is the banner: a 3px amber left border (#d97706) on an rgba(217,119,6,.06) tint, padding `.5rem .7rem`. The Reload button is inline.
**Configuration:** `PORTAL_BUILD` is bumped together with Code.gs on every deploy.
**Acceptance criteria:**
- Typing in any field is never wiped by the 10 s refresh.
- When the stub returns `build:'x'`, the Overview shows the banner and Reload.
- A running race clock ticks once per second.
**Tests:** test_race.cjs "the running clock ticks"; all view tests stub `build: PORTAL_BUILD`, so no banner appears.
**Reference (source):** Page.html 407-419, 592-601, 610-616, 657-667, 1459-1461, 1804, 1935-1941, 2500-2531; Code.gs 734.

### CLOUD-25 — Overview: per-unit model, "what now" banner and KPI tiles
**Project / folder:** cloud/google/Page.html
**Goal:** The landing view summarises the whole DVT campaign. It starts with one sentence and one button for what needs attention now, then shows four headline numbers and eleven more numbers under a fold. It needs no CureBox chooser.
**Depends on:** CLOUD-23, CLOUD-24, CLOUD-01..19 (server: `portalDvt`)
**Files to create:** Page.html `dvtUnitModel(u, cat, runs, reg, requests)`, `dvtTestVerdict(owed, byId)`, `overviewNow(models, n)`, `overviewCard()` (first card), `overviewWire()` (`[data-now-go]`), constants `OV_COL`, `OV_DEFAULT_MIN=10`, `OV_STATUS_CLASS`, `DVT_ACTIVE_ST=['queued','waiting','running','cancel_requested']`, helpers `ovHours`, `ovToday`, `dvtWhen`.
**Public contract:** The unit model returns `{u, reg, tests:[{tid,title,phase,safety,owed,minutes,per,verdict,running}], c:{total,PASS,FAIL,BLOCKED,WAIVED,INVALID,open,doneMin,totalMin,safetyFails}, finished, complete, status, late, machine, active, remainingMin, completion, passRate, weighted}`.
**Behaviour & rules:**
1. Units are the union of every `catalog.tests[*].units` and every `DVT.units[*].unit`, sorted.
2. Per unit, tests are taken in catalog phase order, and only those whose `units` include the unit.
   - Owed run ids are `tid|unit|k` for each `k` in `t.runs`, with default `['|1']`.
   - `minutes` is `t.minutes`, or 10 when missing or ≤ 0.
   - `per = minutes / owed.length`.
3. Test verdict (`dvtTestVerdict`):
   - all owed runs empty → `open`;
   - some empty → `progress`;
   - otherwise the first present of FAIL, INVALID, BLOCKED, WAIVED, PASS.
   `running` means the test has a request for this unit whose status is in `DVT_ACTIVE_ST`.
4. Counters per owed run: `total++` and `totalMin += per`. The verdict, upper-cased, increments its own counter, or `open`.
   - PASS, FAIL and WAIVED add `per` to `doneMin`.
   - A FAIL on a safety test increments `safetyFails`.
   - `finished = PASS+FAIL+WAIVED`. INVALID is neither finished nor passed.
5. Status:
   - 'Complete' when `total>0` and finished equals total;
   - else 'Failures' if any FAIL;
   - else 'Blocked' if BLOCKED or INVALID;
   - else 'In progress' if any active request or anything finished;
   - else 'Not started'.
   `late = !complete && planEnd && today(ISO) > planEnd`.
6. `machine`: the registry machine; else the machine of the unit's most recent run; else the runner whose `unit` matches.
7. Tile maths:
   - completion = finished / total;
   - pass rate = PASS / (PASS+FAIL);
   - progress by time = doneMin / totalMin;
   - remaining = totalMin − doneMin (summed over units);
   - "Until the slowest unit is done" = max of the per-unit `remainingMin`;
   - critical = Σ safetyFails + BLOCKED.
   `pct()` shows one decimal below 10 %, otherwise an integer, and '—' when the denominator is 0.
8. "What now" (`overviewNow`), first match wins. The runner is the online runner seen most recently. The button is `[data-now-go=<box>]`, which sets `SELECTED=box`, `VIEW='dvt'` and starts the long poll.
   1. Every unit complete → good: "The whole DVT is finished" / "Every unit has all its runs." No button.
   2. failed > 0 → bad: "N test run(s) failed" / "Open the DVT list to see which, and run them again after the fix." Button "See the tests".
   3. blocked+invalid > 0 → warn: "N run(s) is/are blocked or invalid" / "They need a look before the unit can finish." Button "See the tests".
   4. Any unit active → neutral: "A test is running" / "It follows live in the DVT list." Button "Follow it".
   5. Runner offline → warn: "The DVT runner on <box> is offline" / "Tests cannot be started from here until it is back." No button.
   6. N auto tests that are open or in progress and not running on the runner's unit → "N test(s) is/are ready to run on <box>" / "Nothing starts until someone presses Start at the machine." Button "Run tests".
   7. Otherwise: "Nothing needs your attention" / "Follow the progress below."
**Look & layout:** Order: stale banner (CLOUD-24), then the `.now` banner, then the card "DVT overview" with the muted subtitle "catalog <version> · N units".
- Main tiles: a 4-column grid (`.dvt-tiles.ov-main`, gap .6rem):
  - Completion (green number);
  - Passed (green);
  - Failed (red when > 0);
  - Test time left (`ovHours`: `N min` below 60, otherwise `X.Y h`, with no decimal at 600 min or more).
- `details.more` "More numbers": an auto-fit grid of tiles at least 130px wide:
  - Machines (units), Active, Runs planned, Runs finished;
  - Blocked (amber when > 0), Invalid (amber when > 0), Waived;
  - Pass rate, Progress by time;
  - Until the slowest unit is done, Critical issues (red when > 0).
  It ends with a muted paragraph defining completion, pass rate, time and critical issues.
- Empty or loading: card "Overview" with "Loading…" while `DVT===null`, or "No DVT catalog has reached the portal yet - open the DVT tool once with the cloud connected."
**Configuration:** none
**Acceptance criteria (test_overview fixture: 2 units, 3 tests; U1 has T-1 PASS, T-2 FAIL + INVALID; U2 all PASS):**
- Machines (units)=2, Runs planned=7, Runs finished=5, Completion=71 %, Passed=4, Failed=1, Pass rate=80 %, Invalid=1, Progress by time=55 %, Critical issues=0.
**Tests:** test_overview.cjs (KPI arithmetic, INVALID handling).
**Reference (source):** Page.html 199-212, 693-703, 720, 1338-1384, 1424-1487, 1497-1502.

### CLOUD-26 — Overview: "Machines and integrators" unit table (editable registry)
**Project / folder:** cloud/google/Page.html
**Goal:** One row per DVT unit. Each row shows the CureBox it runs on, editable registry fields (integrator, HW revision, firmware, planned start and end), progress, status and remaining time. A field saves itself when the user leaves it.
**Depends on:** CLOUD-25, CLOUD-01..19 (server: `portalDvtUnitSave`, sheet `dvt_units` with columns unit, machine, integrator, hwRev, fwVersion, bomRev, planStart, planEnd, note)
**Files to create:** Page.html `overviewCard()` (the second card), `overviewWire()` (`[data-ov-unit]`).
**Public contract:** Inputs carry `data-ov-unit=<unit>` and `data-ov-field ∈ {integrator, hwRev, fwVersion, planStart, planEnd}`. On change, POST `/api/dvt/unit` `{unit, fields:{[field]: value}}`.
**Behaviour & rules:**
1. On change: clear the outline, then save.
   - `!ok` → `outline:2px solid var(--err)` and the tooltip set to the server message ('not saved').
   - Success → the tooltip becomes 'saved' and `loadDvt()` runs.
   - An exception also gives the red outline.
2. The online mark after the machine name is ` ●` (online) or ` ○` from `MACHINES`, or nothing when the machine is unknown.
3. Saving requires the Service role. A Viewer gets the 403 toast (CLOUD-20).
**Look & layout:** Card h2 "Machines and integrators". The table `table.ov-units` sits inside an `overflow-x:auto` wrapper. Columns:
- Unit: the bold unit name, with "machine ●" muted below, or "no machine yet".
- Integrator: text input, placeholder "Integrator", 8rem.
- Revisions: two stacked inputs, "HW rev" and "Firmware".
- Plan: two stacked date inputs (9.5rem), "Start" and "Planned end".
- Progress (min-width 9rem): a 6px bar filled to completion % in `OV_COL.PASS`, then "N % · finished/total runs", then a muted "N % by time".
- Status: a pill with the status (Complete → `on` green; Failures → `off` red; Blocked → `warn`; others neutral), plus a red "Delayed" pill when late. Below it, muted: "P pass · F fail[ · B blocked][ · I invalid]".
- Remaining: "≈ <ovHours>", or "—" when complete.
Each `td` has `data-l=<label>` for the phone card layout. The muted footnote reads "Changes are saved when you leave a field."
**Configuration:** none
**Acceptance criteria:**
- U1 (planEnd 2026-10-15, incomplete) shows "Delayed"; U2 shows "Complete".
- The integrator inputs read "Integrator A" and an empty value.
- Changing U2's integrator to "Integrator B" sends exactly one save `{unit:'U2', fields:{integrator:'Integrator B'}}`.
**Tests:** test_overview.cjs (Delayed/Complete, inputs, save); test_phone.cjs (unit-card fields stay inside the card).
**Reference (source):** Page.html 1462-1473, 1488-1490, 1508-1516; Code.gs 606-665.

### CLOUD-27 — Overview: Gantt chart (inline SVG)
**Project / folder:** cloud/google/Page.html
**Goal:** Draw each unit's tests end to end, scaled by their estimated minutes and coloured by verdict. Clicking a unit row expands one sub-row per test.
**Depends on:** CLOUD-25
**Files to create:** Page.html `ganttSvg(models)`, `GANTT_OPEN` (Set), the legend in `overviewCard()`, `overviewWire()` (`[data-gantt]`).
**Public contract:** `<g class="gantt-row" data-gantt="<unit>">`; the svg has `aria-label="DVT Gantt chart"`.
**Behaviour & rules:**
1. Geometry: viewBox width W=1000, left label gutter L=96, R=16, TOP=24, unit row height ROW=26, sub-row height SUB=15.
   - `maxMin = max(60, longest unit's Σ minutes)`; `scale = (W−L−R)/maxMin`.
2. Unit row: the label at x=6, `▸ U1` or `▾ U1`, 12px bold, `currentColor`.
   - Each test is a rect of width `max(1.5, minutes*scale)` and height ROW−8, with a 0.6 stroke in `var(--panel)` that separates the bars.
   - Fill: `OV_COL.RUNNING` when running, otherwise `OV_COL[verdict]`, otherwise `OV_COL.open`. Opacity .55 for open tests that are not running.
   - A `progress` test also gets a 2px `RUNNING`-blue underline at half its width.
   - `<title>` tooltip: "tid title - duration - verdict|running".
3. Expanded unit: one sub-row per test. The tid label is at x=14 (10px, opacity .8). A thin rect of height SUB−5 sits at the test's cumulative offset.
4. Time axis: the tick step is 240 min when maxMin > 1200, 120 when > 480, 60 when > 120, otherwise 30. Each tick is a vertical gridline in `var(--line)` running the full height. The label at y=12 (10px, opacity .7) reads "N h", or "N min" below 60.
5. Clicking a unit row toggles it in `GANTT_OPEN` and re-renders.
**Look & layout:** Card h2 "Gantt", muted subtitle "each unit's tests end to end by their estimated duration · click a unit for its tests". The SVG is `width:100%;height:auto` with `color:var(--text)`, so it themes automatically.
- Legend row under the chart: a .8rem square swatch plus a muted .8rem label for pass, fail, blocked, waived, invalid, running and "not run".
- Colours: PASS #16a34a, FAIL #dc2626, BLOCKED #d97706, WAIVED #6b7280, INVALID #9333ea, RUNNING #2563eb, open #d4d4d8.
**Configuration:** none
**Acceptance criteria:**
- With U1 = 3 tests and U2 = 2 tests, there are 5 bars.
- Clicking U1 gives 8 rects (3 sub-rows added).
**Tests:** test_overview.cjs (bar counts before and after the click).
**Reference (source):** Page.html 1338-1341, 1386-1422, 1491-1494, 1503-1507.

### CLOUD-28 — Machine view: machine header with live state and the NetBird pill
**Project / folder:** cloud/google/Page.html
**Goal:** In the Machine view, each CureBox (all of them, or the chosen one) is one card. Its header shows the name, an online/offline pill, the last sync time and pending command count, a NetBird pill, and three live figures (chamber temperature, LED 405 hours, heater hours).
**Depends on:** CLOUD-21, CLOUD-23, CLOUD-24, CLOUD-01..19 (server: `portalMachines`, `netbirdStatus_`), PLAT-10 (snapshot content), OPS-08 / PLAT-09 (NetBird on the unit)
**Files to create:** Page.html `machineCard(m, i)` (header part), `netbirdPill(m)`.
**Public contract:** Each `portalMachines` item has these fields:
- `name`, `lastSeen` (unix s), `online` (seen < 90 s ago), `pending` (unacked commands);
- `state` (snapshot state: `chamberTemp`, `counters.led405`, `counters.heater`);
- `programs`, `presets`, `prints`, `cures`, `reports` (run ids with an uploaded report), `reportUrl`;
- `netbird`: `null`, or `{error}`, `{peer, missing:true}`, or `{peer, connected, lastSeen, ip, stale}`.
**Behaviour & rules:**
1. Shown machines: all `MACHINES` when `SELECTED` is 'all' or `DVT_NONE`, otherwise the one with that name. They are sorted by name on the server.
2. NetBird pill:
   - `null` → nothing;
   - `error` → neutral pill "NetBird ?", with the error as tooltip;
   - `missing` → red pill "NetBird: not enrolled", tooltip "no NetBird peer named <peer>";
   - connected → green pill "NetBird connected", tooltip "NetBird <ip>", plus " · N stale registration(s) of <peer> in the dashboard" when `stale` > 0;
   - not connected → red pill "NetBird offline · seen <fmtWhen(lastSeen)>". The tooltip is "the CureBox runs and syncs, but its NetBird client is down - remote access (SSH, screen) is unavailable" when `m.online`, otherwise "off NetBird and not syncing - no power or no network".
3. Figures:
   - `chamberTemp.toFixed(1)` + "°C", or "–°C";
   - `counters.led405` + "h", or "–h";
   - `counters.heater` + "h", or "–h".
**Look & layout:** The card's top row is space-between.
- Left: `h2` (margin 0) with the machine name, a pill `online` (green `.on`) or `offline` (red `.off`), a muted non-bold "last sync 12s ago · N pending" (the pending part only when > 0), and the NetBird pill.
- Right: three `.stat` blocks, value bold 1.25rem over a muted .78rem label: "chamber", "LED 405", "heater".
The sections in CLOUD-29 follow in the same card.
**Configuration:** NetBird needs the server script properties `NETBIRD_TOKEN` and `NETBIRD_PEERS` (values are never in the page; see CLOUD-01..19).
**Acceptance criteria:**
- An online machine shows a green "online" pill and "last sync Ns ago".
- With `netbird:{connected:false,...}` and `online:true`, the red pill's tooltip names remote access as down.
**Tests:** test_phone.cjs walks the Machine section (comfort audit). **untested:** there is no browser test for the NetBird pill states.
**Reference (source):** Page.html 2127-2138, 2158-2195; Code.gs 1428-1484.

### CLOUD-29 — Machine view: programs, catalog, send print, recent prints, cure runs and reports
**Project / folder:** cloud/google/Page.html
**Goal:** The rest of the machine card. The user's work programs can be edited and deleted. The built-in catalog is read-only. A simulated print can be sent, with an optional NFC tag. Recent prints can be deleted. The last cure runs link to their uploaded reports. Every change is a data-only command that the machine picks up on its next sync.
**Depends on:** CLOUD-28, CLOUD-01..19 (server: `portalCommand`, `COMMAND_TYPES = upsert_program | delete_program | send_print | delete_print`, `doGet ?report=`), CLOUD-40..59 (program editor: `openEditor`, `stepRow`, `stepErrors`, `saveProgram`), PLAT-10 (machine applies commands, uploads reports), PLAT-14 (report HTML)
**Files to create:** Page.html `machineCard(m, i)` (sections), `programOptions(m)`, `nfcTagOf(text)`, `cureRows(m)`, `wireCard(m, i)`.
**Public contract:** Commands are POSTed to `/api/machines/<name>/commands`:
- `{type:'delete_program', payload:{id}}`;
- `{type:'delete_print', payload:{id}}` (firmware 1.0.147+);
- `{type:'send_print', payload:{printName, printerName, materialName, nfcTag?}}` (NFC: firmware 1.0.146+);
- `upsert_program`: CLOUD-40..59.
DOM hooks: `[data-edit="i:id"]`, `[data-del]`, `[data-delprint]`, `[data-new=i]`, `[data-send=i]`, `#job-i`, `#printer-i`, `#nfc-i`, `#mat-i`, `#msg-i`, `#editor-i`.
**Behaviour & rules:**
1. Search (`SEARCH`, lower-case) filters:
   - programs and presets by name;
   - prints by printName, materialName, printerName or status;
   - cures by materialName or status.
2. Recent prints show at most 5. Cures show everything the snapshot holds; per the comment that is the last 10 (sent by the machine).
3. Delete program: no confirmation. It sends `delete_program`, then `load()`.
4. Delete print: `confirm('Delete print "<name>" from <machine>?')`, then `delete_print`, then `load()`. The cure runs of that print stay.
5. Send print:
   - `nfcTagOf` strips `: - whitespace` and upper-cases. It must be hex with even length 4..32 and is returned as `AA:BB:…`. Invalid text sets `#msg-i` to "That is not an NFC tag number - use hex digits, e.g. E0:07:C0:E1:93:93:18:6D" and nothing is sent.
   - Defaults: printName 'Job', printerName 'CLOUD'. materialName is the selected program name.
   - After sending, the fields are cleared. The message is "Print sent — present tag <tag> to the machine to start it" or "Print sent — it appears on the machine within ~10 s".
6. Program select (`programOptions`): when `presets` is empty, the user programs only. Otherwise `<optgroup label="My programs">` (if any) and `<optgroup label="Catalog">`.
7. Report column: when the run id is in `m.reports`, show the links "View" and "Download" (`scureReportHref(m,id,false|true)`, target _blank). Otherwise a muted "after the run" (status running) or "not uploaded yet".
8. Duration in cure rows: `Mm Ss`, or '–'. Started is `startedAt` with 'T' replaced by a space.
9. **OPEN QUESTION:** the Edit, Delete and Send buttons are shown to Viewers too. The server refuses with 403 (Service needed), which shows the toast. Should the page hide them when `!ME.canService`? The code does not hide them.
**Look & layout:** Inside the machine card, in order. Each section is an `h2` followed by a `table.cards`.
1. "Work Programs": columns Name | Steps ("N steps") | Duration ("N min", or "– min") | actions (`td.act`: "Edit", and "Delete" with `.danger` red text). Empty: one muted row "none". Below it, the primary button "+ New Program", then the editor slot `#editor-i`.
2. "Machine Catalog", muted subtitle "built in · N programs": Name | Steps | Duration, read-only. Empty: "no match" when filtered, else "not reported - the machine needs firmware 1.0.145 or newer".
3. "Send Simulated Print": `.row.sendrow` holding:
   - Job name (flex 2, placeholder "Job name (e.g. Job 2 - Penrose)");
   - Printer (flex 1, "Printer (e.g. TZ)");
   - NFC tag (flex 1.4, "NFC tag (optional, e.g. E0:07:C0:E1:93:93:18:6D)", autocomplete off, spellcheck false);
   - the program select;
   - the primary button "Send to machine".
   Below it, the green `p.msg` result line.
4. "Recent Prints On Machine": Job (with a muted "tag <uid>" line when present) | Material | Printer | Status | a red "Delete" button. Empty: "none".
5. "Cure Runs & Reports": Program (materialName) | Started | Duration | Status | Report. Empty: "none".
**Configuration:** none
**Acceptance criteria:**
- Sending with the NFC text "e007c0e1" sends `nfcTag:'E0:07:C0:E1'`. Text "xyz" sends nothing and shows the hint.
- A run listed in `reports` shows working View and Download links that carry the session token.
**Tests:** test_phone.cjs (Machine: all four tables become cards; Edit and Delete side by side ≥ 44px and ≥ 120px wide; View and Download ≥ 44px; print fields ≥ 300px wide). **untested:** command payloads (no desktop test of `wireCard`).
**Reference (source):** Page.html 2140-2240, 2456-2498; Code.gs 39-43, 1486-1503.

### CLOUD-30 — Race view: DVT race against the clock
**Project / folder:** cloud/google/Page.html
**Goal:** A playful view in which every DVT unit races to finish all its owed runs. It shows a ranking with medals, a ticking clock per unit, pace, an ETA, per-test times against the estimate, the fastest unit per test, and a winner banner. Service users can set an official start and choose who takes part.
**Depends on:** CLOUD-24, CLOUD-25 (`dvtUnitModel`), CLOUD-01..19 (server: `portalRaceSet`, `raceGet_` → `DVT.race = {start, units}`, stored in script property RACE)
**Files to create:** Page.html `raceModel()`, `raceChampions(model)`, `raceCard()`, `raceSet(d)`, `raceWire()`, `fmtClock`, `fmtMin`, `raceNow`, `RACE_OPEN`, `RACE_PICK`, `RACE_MEDAL=['🥇','🥈','🥉']`.
**Public contract:** POST `/api/dvt/race` with `{start:'now'}`, `{start:0}` or `{units:[...]}`. The server validates units against `^[A-Za-z0-9._-]{1,40}$` with at most 30 entries. Hooks: `[data-race=<unit>]`, `#race-start`, `#race-reset`, `#race-pick`, `[data-race-unit]`, `[data-clock][data-end]`.
**Behaviour & rules:**
1. Participants: the catalog units filtered by `race.units` when that list is non-empty, otherwise all catalog units.
2. Per unit:
   - a run counts as finished when its verdict is PASS, FAIL or WAIVED and, if there is an official start, `dvtWhen(run) >= start`;
   - `doneMin += per` for each finished run;
   - a test is `done` when all its owed runs are finished, and its `end` is the latest finish.
3. Time taken per test:
   - exact: the sum of `finished − started` over requests with status 'done' for that test, started after the race start, in minutes;
   - otherwise approximate (`approx`, shown with "~"): the gap since the previous done test's end, with done tests ordered by end, starting from `begin`.
4. `begin` is the official start, otherwise the earliest of the unit's run times and request start times. `finish` is the max `end` once complete.
   - `elapsed = (finish || raceNow()) − begin`.
   - `pace = doneMin / elapsed hours`.
   - `left = totalMin − doneMin`.
   - `eta = left/pace*3600`, only when not complete, pace > 0 and at least 5 % done.
5. Ranking:
   1. complete units first, by elapsed time (ascending);
   2. then started units;
   3. then by % done (descending);
   4. then by pace (descending).
   There is a winner only when every participant is complete; it is the first finisher.
6. Champions: for each test that at least two units have done with a known time, the fastest and the second fastest.
7. "Start the race" asks `confirm('Start the race now? Every unit's clock starts together; only runs finished from now on count.')`. "Reset the race" asks `confirm('Reset the race? The clocks go back to each unit's first recorded run.')`.
8. A checkbox change sends the full list of checked units. After a set, `loadDvt()` runs and the view re-renders even if the checkbox is still focused.
9. Clicking a lane toggles its test table in `RACE_OPEN`. The picker's open state persists in `RACE_PICK`.
**Look & layout:** Card "DVT race", muted subtitle "who finishes the whole DVT first".
- Banner:
  - with a winner: `.race-win` (gold #d4a017 border on rgba(212,160,23,.14), 1.05rem) "🏆 **U2** wins · <integrator> - the whole DVT in **1 h 20 min 00 s**";
  - otherwise, once started: `.race-lead` (`--inset`) "K of N finished · in front: **U** (P %)".
- Controls row:
  - with an official start: muted "Race started <DD Mon HH:MM> · <ticking clock>" and, at the right, "Reset the race";
  - without one: muted "No official start yet - every unit's clock runs from its first recorded run." and the primary "🏁 Start the race".
- Lane `.race-card`: flex row, bordered, radius 10px, pointer cursor. It contains:
  - the rank cell: medal, number, 🏃 (running) or ⏳ (not started), at 1.7rem in a 2.2rem column;
  - the main block: the bold unit name, a muted "integrator · machine", a 6px green progress bar at % done, and a muted .85rem sub-line:
    - complete: "finished · <fmtMin doneMin> of tests · pace N min/h";
    - running: "f/t runs · pace N min/h · about X to go";
    - not started: "t runs to do";
  - the right block: `.race-clock` (1.15rem bold, tabular numbers), or a muted "not started".
  The overall first lane gets `.champ` (gold border and glow) once everyone has finished.
- `fmtClock`: "M min SS s", then "H h MM min SS s", then "D d H h MM min".
- `fmtMin`: "N min", "X.Y h" from 120 min, "X.Y d" from 2880 min.
- Expanded lane: `table.cards` with columns Test | Took ("~40 min", "—", or a muted "open") | Estimate | vs (green "-25 min" or red "+10 min").
- Picker (only with more than one unit): `details#race-pick` "Who is in the race (k of n)", with a checkbox per unit.
- Footnote explaining the clock and pace.
- Second card, "Test champions" (subtitle "fastest unit per test"): Test | Fastest (**unit** time) | Next.
- Empty: "No unit in the race." Loading/no catalog: the card "Race" with "Loading…" or "No DVT catalog has reached the portal yet."
**Configuration:** none
**Acceptance criteria (test_race fixture):**
- The order is U2, U1, U3 with 🥇 🥈 🏃. Clocks are fixed at "1 h 20 min 00 s" and "1 h 40 min 00 s"; U3's clock ticks.
- T-A took "35 min" exact (−25 min); T-B "~40 min" (+10 min).
- Once U3 finishes it gets 🥉 and the banner reads "U2 wins … 1 h 20 min".
- Start sends `{start:'now'}`; unchecking U3 sends `{units:['U1','U2']}`.
- On a phone: no sideways scroll, the clock is visible, and the lane is ≥ 44px high.
**Tests:** test_race.cjs (desktop + phone, `--shot` option).
**Reference (source):** Page.html 182-189, 1796-1941; Code.gs 690-728.

### CLOUD-31 — Compare: results table across units or across the runs of one unit
**Project / folder:** cloud/google/Page.html
**Goal:** Show the recorded values of one test (and variant) side by side. The columns are either the units (latest run, or the mean of repetitions) or the runs of one unit. Each value is compared with a reference column against a tolerance, and cells that stand out are tinted amber or red.
**Depends on:** CLOUD-24, CLOUD-01..19 (server: `portalDvt` runs with `values` and `files`)
**Files to create:** Page.html `CMP` state, `cmpRuns`, `cmpColumns(runs)`, `cmpRows(cols, tol, refIdx)`, `cmpFmt`, `cmpNum`, `cmpIsStamp`, `compareCard()` (table part), `cmpModeSelect()`, `compareWire()`.
**Public contract:** `CMP = {mode:'units'|'runs'|'matrix', test, variant, unit, basis:'latest'|'mean', ref, tol:10, kind, col, texts:{}, loading, err}`. Control ids: `#cmp-test`, `#cmp-variant`, `#cmp-mode`, `#cmp-unit`, `#cmp-ref`, `#cmp-basis`, `#cmp-tol`. Rows: `tr.cmp-row[data-flag]`.
**Behaviour & rules:**
1. Only runs with a non-empty `values` take part. The test list is the sorted unique test ids. An invalid selection falls back to the first test, first variant and first unit.
2. Units mode: one column per unit in (catalog owed units ∪ units with runs), sorted.
   - A unit without runs becomes a column with `empty`, sub-line "no results yet", shown at opacity .55, and disabled as a reference ("U4 (no results)").
   - With several runs, the sub-line is "N runs (latest|mean)", otherwise `fmtWhen`.
   - Mean: a key is averaged only when every run that has the key has a number; otherwise the latest value is used.
3. Runs mode: one column per run of `CMP.unit`, oldest first, labelled `r<rep>[ variant]` with sub-line `fmtWhen`. The reference is always the first column.
4. Row kind:
   - `stamp` when the key matches `/(^|_)(timestamp|time_stamp)$|^timestamp/i`;
   - `num` when all present values are numbers;
   - `bool` when all are booleans;
   - otherwise `text`.
   Rows are ordered num, bool, text, stamp.
5. Num rows:
   - min, max, mean, `spread = max−min`, `spreadPct = spread/|mean|·100`;
   - deviation per cell `(v−ref)/|ref|·100` (the absolute difference when ref is 0);
   - a cell is flagged 1 (amber) above `tol`, and 2 (red) above `2·tol`.
   Bool rows: a value different from the reference is flagged 2. Text rows: flagged 1. Stamps are never flagged.
6. Tolerance: a number input (min 0.1, step 0.5). Only values > 0 are accepted.
7. `cmpFmt`: ≥ 1000 → 0 decimals; ≥ 100 → 1; otherwise up to 3. true → 'yes', false → 'no', null → '—'.
**Look & layout:** Card h2 "Compare results", muted subtitle "<test> - <title>".
- Controls row `.cmp-controls` (labels muted .8rem above each select):
  - Test;
  - Variant (only when variants exist);
  - Compare (Across units / Across runs of one unit / All units, all tests);
  - in runs mode, Unit; in units mode, Reference unit plus Value of a unit (Latest run / Mean of repetitions);
  - Tolerance [input] %.
- Table `table.cmp-table` in an `overflow-x:auto` wrapper:
  - header "Field", then one right-aligned column per header (label, a `badge` "ref" on the reference, muted sub-line), then "Range" and "Spread" when there are at least 2 columns with data;
  - first row "Result": a verdict pill per column (green PASS, red FAIL, amber BLOCKED/INVALID, or 'open'; '—' for empty);
  - field rows: the bold key, then right-aligned values. Numbers carry a muted .75rem "+31.0 %" deviation line. Text and stamps are muted .8rem;
  - tints: amber rgba(217,119,6,.16); red rgba(220,38,38,.14) in bold;
  - Range "min .. max" (muted); Spread "N %", bold when above tolerance. Non-numeric rows show "differs" when flagged.
- Footnote:
  - with fewer than 2 data columns: "Only one unit has results for this test - nothing to compare yet (no results yet on U4)", or the runs-mode text "Only one run of this unit recorded this test - nothing to compare yet.";
  - otherwise: "K of N fields stand out: amber = off the reference by more than T % (or a text that differs), red = by more than 2T % (or a yes / no check that differs). Spread = (max - min) / mean. The reference is the chosen unit/first run."
- Empty states: "No run has recorded values yet. Once tests have results on the units, they can be compared here." (with the mode select still shown); "No recorded run for this selection."; card "Compare" with "Loading…" or "No DVT catalog has reached the portal yet."
**Configuration:** none
**Acceptance criteria (test_compare fixture):**
- Field order is `peak, ok, comment, stamp_timestamp`. U1 shows its latest value, 84.
- U3 at 110 is red with "+31.0 %"; U2 is not flagged. Spread is 30.4 %.
- With a 40 % tolerance, U3 is no longer flagged.
- U4 appears as "no results yet", and its reference option is disabled. With U3 as the reference, U1 shows −23.6 % in red.
- The mean basis shows 82 for U1. Runs mode gives two `r…` columns, oldest first.
**Tests:** test_compare.cjs.
**Reference (source):** Page.html 1519-1586, 1687-1737, 1766-1783.

### CLOUD-32 — Compare: "All units, all tests" matrix
**Project / folder:** cloud/google/Page.html
**Goal:** A grid of every catalog test against every unit, showing each verdict. Rows where the units finished with different results are highlighted, and clicking a row opens that test's comparison.
**Depends on:** CLOUD-25 (`dvtUnitModel`), CLOUD-31
**Files to create:** Page.html `cmpMatrix()`, the matrix branch of `compareCard()`, and the `.cmp-mrow` handler in `compareWire()`.
**Public contract:** `tr.cmp-mrow[data-test][data-flag=0|1]`.
**Behaviour & rules:**
1. Columns are the catalog units, sorted. Rows follow phase order, with a phase header row (muted, uppercase, .78rem, colspan).
2. Cell values:
   - `null` when the unit does not owe the test → muted "n/a";
   - `open` → muted "not run";
   - `progress` → pill "partly";
   - running → pill "running";
   - otherwise a verdict pill coloured with `dvtClass`.
3. A row is flagged when its set of finished verdicts (PASS, FAIL, WAIVED) has more than one member. A flagged row gets the background rgba(220,38,38,.07) and a red pill "units differ".
4. Clicking a row sets `CMP.test`, `variant=null`, `mode='units'` and clears kind and col.
**Look & layout:** Card "Compare results", subtitle "all units, all tests", with the mode select.
- The intro line reads "N test(s) have finished with a different result on different units." or "No test has finished with different results on different units.", followed by "Click a test to compare its values."
- Header cells are centred: unit name over a muted "N % done". The first column shows the bold tid and the muted title.
**Configuration:** none
**Acceptance criteria:**
- T-A reads PASS, PASS, FAIL, "not run" with flag 1.
- T-B reads PASS, n/a, n/a, n/a with flag 0.
- Clicking T-B opens Compare with `#cmp-test = T-B`.
**Tests:** test_compare.cjs (matrix section).
**Reference (source):** Page.html 1661-1685, 1691-1692, 1773.

### CLOUD-33 — Compare: curve overlay from the raw sample files
**Project / folder:** cloud/google/Page.html
**Goal:** Overlay the measured curves (CSV sample files) of the compared columns on one SVG chart. The user picks the measurement kind and the Y column. Temperature charts get dashed guide lines at 30, 40, 50 and 60 °C.
**Depends on:** CLOUD-31, CLOUD-01..19 (server: `portalDvtFiles(token, ids)` → `{ok, files:{id:{name,text}}}`)
**Files to create:** Page.html `cmpFiles(cols)`, `cmpLoadFiles(list)`, `cmpParseCsv(text)`, `cmpChart(series, xName, yName)`, the curves card in `compareCard()`, the `#cmp-kind`, `#cmp-col` and `#cmp-load` handlers.
**Public contract:** POST `/api/dvt/files {ids}`, with at most 8 ids per call. The parsed texts are cached in `CMP.texts[id] = {header, rows}`.
**Behaviour & rules:**
1. Files: only `*.csv` files of the columns' runs, grouped by `f.kind`. Labels are `unit[ rN]`, or in runs mode `rN <when>`.
2. Auto-load: after each render, if some files of the chosen kind are not loaded and the last try did not fail, load them (8 at a time). The "Load the curves" / "Reload" button clears the cache for that kind and loads again.
3. CSV parsing is quote-aware and handles `""` escapes. A numeric string becomes a number; an empty cell becomes `null`.
4. Y columns: every header except the first that has at least one numeric value in a loaded file. X is always column 0.
5. Points are down-sampled with step `max(1, floor(rows/800))`, and only rows where both X and Y are numbers are kept.
6. Chart geometry: W=1000, H=340, margins L=56, R=16, T=12, B=34.
   - The Y range is padded by 6 %; a zero-width range is widened by ±1.
   - Six gridlines (`var(--line)`) carry Y labels at the left (10px, opacity .7). Six X labels sit at y=H−18.
   - The X axis title is centred at the bottom. The Y title is rotated −90° at x=12.
   - One `polyline` per series with stroke 1.6, colour `CMP_COLORS[i % 8]` and the label as `<title>`.
   - When `yName` matches `/chamber|temp/i`, dashed lines (`stroke-dasharray 5 4`, opacity .35, `data-mark`) are drawn at 30, 40, 50 and 60 within the range, each labelled "N °C" at the right.
   - The legend row below has a 0.9rem × 3px colour swatch and the label for each series.
**Look & layout:** A second card, "Curves", muted subtitle "N file(s) of the compared units|runs, laid on one chart". Its row holds:
- Measurement select ("sweep (2)", with underscores shown as spaces);
- Column select;
- the button "Load the curves", or "Reload" when everything is loaded (disabled while loading).
States:
- the red pill with the error ("the files could not be loaded");
- "Loading the files…";
- "N file(s) not loaded yet.";
- "These files have no numeric column to plot.";
- "No numeric samples in this column."
The card is hidden when there are no CSV files.
**Configuration:** none
**Acceptance criteria:**
- Two files give two polylines.
- `chamber_c` gives marks at 30, 40, 50, 60. The text column `phase` is not offered.
- The files are fetched exactly once across redraws.
**Tests:** test_compare.cjs (curves section).
**Reference (source):** Page.html 1524-1527, 1588-1658, 1738-1765, 1782-1793.

### CLOUD-34 — Phone layout (≤ 640 px)
**Project / folder:** cloud/google/Page.html (`@media (max-width:640px)`)
**Goal:** One comfortable, thumb-friendly column on a phone. The section tabs become a bottom bar of six icons. Tables become stacked cards. Controls are at least 44px tall with 16px text, and nothing scrolls sideways.
**Depends on:** CLOUD-21, CLOUD-23, CLOUD-25..33
**Files to create:** Page.html CSS 302-400 (plus the 760px rules for `.dvt-cols` and `.dvt-chk`).
**Public contract:** The class conventions that make a table phone-ready:
- `table.cards`, where every non-first `td` carries `data-l="<Label>"`; `td.act` for buttons; `td.wide` or `[colspan]` for full-width cells;
- `table.ov-units`, `table.cmp-table` and `table.rq-table`;
- `.sendrow`, `.cmp-controls`, `.sections`.
**Behaviour & rules:**
1. Bottom bar: `.sections` becomes `position:fixed; bottom:0; left/right 0; z 20`, with the `--panel` background, a top border, the shadow `0 -6px 16px rgba(16,24,40,.08)`, and bottom padding `max(env(safe-area-inset-bottom), 10px)`. It never wraps.
   - Each `.subtab` takes `flex:1 1 0`, min-height 56px, and stacks a 22px icon over a .75rem label.
   - The active tab has `--acc` text and an icon "pill" behind it: `color-mix(acc 15%, transparent)`, radius 999px, padding `.15rem .75rem`.
   - `main` gets bottom padding 5.5rem and `html` gets `scroll-padding-bottom:6rem`, so a focused field stays clear of the bar.
2. Header: padding `.5rem .9rem`, logo 30px, h1 .95rem; `#who .who-name` max 8rem.
3. `main`: padding `.7rem .6rem 2.5rem`. `.card`: padding `.75rem .8rem`, radius 9px. `h2`: .82rem.
4. All inputs, selects and buttons get min-height 44px and font-size 16px (no zoom on focus).
5. `.now`: the button is full width and 48px high.
6. Tiles: `.dvt-tiles` become 3 per row; `.ov-main` 2×2. Numbers 1.3rem, labels .68rem.
7. `ov-units`: the header row is hidden. Each `tr` is a bordered card (radius 9px), and each `td` is a flex row with its `data-l` label (muted, uppercase, .72rem) on the left and the value on the right. Inputs are at most 62 % wide.
   - The "Revisions" and "Plan" cells wrap: the label takes a full line, then the two inputs share the width (40 % each).
8. `table.cards`: the same card treatment. The first cell is the bold 1.02rem card title.
   - `td.act` becomes a row of equal buttons/links, 46px high, bordered #d4d4d4, radius 7px. A `.danger` button keeps red text.
   - Steps tables (editor): the first cell is prefixed "Step ", and fields that a process does not use (`:has(> .mut:only-child)`) are hidden.
9. `cmp-controls` becomes a 2-column grid with the first label spanning both columns. In `cmp-table` the first column is `position:sticky; left:0` with the `--panel` background and max 8.5rem; cells are .85rem.
10. Any other table in `#app` scrolls horizontally inside its card (`display:block; overflow-x:auto`).
11. Race: lanes wrap; the time block takes a full line, left-aligned under the name (indented 2.9rem); the clock is 1.3rem.
12. `.sendrow` children are full width. Primary buttons in a row are 46px.
13. DVT and phone extras (the views themselves are in CLOUD-40..59):
    - the `.dvt-picker` is hidden;
    - `rq-table` becomes cards with full-width 46px buttons;
    - Run buttons are full width at 46px;
    - the guide modal becomes a full-screen sheet with the footer buttons stacked full-width at 48px, pinned to the bottom with safe-area padding;
    - prompt buttons are 48px.
14. `#flash` moves up to `bottom:5.5rem`.
**Look & layout:** See the rules above. At 390 × 844 the page is one column with a fixed bottom navigation bar.
**Configuration:** none
**Acceptance criteria (test_phone.cjs at 390×844, touch):** For every section:
- the page scrollWidth is ≤ 391;
- no visible control in `#app` (including `.subtab`) is shorter than 40px;
- inputs and selects use ≥ 16px text;
- body text is ≥ 14px.
In addition:
- Overview tiles sit 2 per row, the unit rows are `block` with the header hidden, and the section bar is `nowrap` and under 100px tall;
- Machine: 4 card tables, Edit and Delete on the same line, each ≥ 44px high and ≥ 120px wide;
- program editor steps are cards;
- Errors are cards;
- the only CureBox is preselected;
- the DVT guide sheet fills the screen with its buttons on screen (CLOUD-40..59).
**Tests:** test_phone.cjs; the phone sections of test_overview.cjs, test_compare.cjs (sticky first column) and test_race.cjs.
**Reference (source):** Page.html 173, 190-194, 302-400; test_phone.cjs 57-241.

### CLOUD-35 — Headless browser tests for the shell and the views
**Project / folder:** cloud/google/test_overview.cjs, test_race.cjs, test_compare.cjs, test_phone.cjs
**Goal:** Prove the views without Apps Script by loading `Page.html` from `file://` in headless Chrome (puppeteer-core) with a stub `google.script.run`. Each test drives the UI like a person and prints `ok:` per check, failing on any page script error.
**Depends on:** CLOUD-20..34
**Files to create:** the four .cjs files listed above.
**Public contract:**
- Run with `node cloud/google/test_<name>.cjs [--shot]`.
- Chrome comes from the env var `CHROME`, default `C:/Program Files/Google/Chrome/Application/chrome.exe`.
- puppeteer-core is loaded from `<repo>/node_modules`.
- The `STUB` string is injected with `evaluateOnNewDocument`. It defines `window.google.script.run` as an object whose `withSuccessHandler(ok).withFailureHandler(bad)` returns a proxy that calls `handlers[fn](...args)` on a `setTimeout(0)`. It throws 'no stub for <fn>' when a handler is missing.
**Behaviour & rules:**
1. Sign-in: if `#pw` appears, type a password and click or tap `#go`; then wait for `.subtab`.
2. Fixtures are small catalogs (`version`, `updated`, `phases`, `tests{title,safety,auto,minutes,units,runs}`) plus runs `{unit,testId,variant,rep,runId:'tid|unit||rep',verdict,…}` and units.
3. `page.on('dialog', d => d.accept())` auto-confirms dialogs. `pageerror` events are collected, and the last check asserts there are none.
4. test_phone.cjs emulates an iPhone (390×844, DPR 2, touch) and runs a shared `comfy(name)` audit per section (CLOUD-34).
**Look & layout:** n/a
**Configuration:** CHROME env var.
**Acceptance criteria:** All four scripts exit 0 with every `ok:` line printed against the current Page.html.
**Tests:** These are the tests. They cover the acceptance criteria of CLOUD-23, -25, -26, -27, -30, -31, -32, -33 and -34.
**Reference (source):** test_overview.cjs 1-111, test_race.cjs 1-126, test_compare.cjs 1-166, test_phone.cjs 1-244.
