/**
 * sCure Cloud on Google - the whole portal, as an Apps Script web app (user, 2026-10-10: "everything at Google").
 * It started as a port of the Fly portal cloud/portal.py, which was deleted with that account (user, 2026-10-12).
 *
 *   machine  -> POST <web app URL>/api/agent/sync   (body: snapshot + machineKey)  -> doPost
 *   browser  -> GET  <web app URL>                  (Page.html, edited by hand)     -> doGet
 *   page     -> google.script.run.portalLogin / portalMachines / portalCommand
 *
 * Data lives in a Google Sheet ("sCure Cloud data", created on first use, id in the script property SHEET_ID):
 *   machines: name | lastSeen (unix s) | snapshot JSON (split over columns C.. when longer than one cell)
 *   commands: id | machine | type | payload JSON | created | delivered | acked
 *   reports:  machine | runId | fileName | material | startedAt | status | uploaded | html (split over columns H..)
 *   alerts:   machine | code | raised | cleared | message   (the machine's alert log, for the "Errors today" tab)
 *   dvt_runs: unit | testId | variant | rep | runId | verdict | operator | startedAt | recordedAt | note | machine | values JSON (split over L..)
 *             machine = the CureBox (portal machine name) the DVT unit is, chosen in the tool; '' = not assigned yet
 *   dvt_files: unit | runId | kind | fileName | fileId | size | uploaded   (raw sweep CSV / graph PNG, stored in Drive)
 *   dvt_catalog: updated | catalog JSON (split over B..) - phases, gates, tests and the runs each test owes per unit,
 *              sent by the DVT tool so the DVT tab lists EVERY test, recorded or not
 *
 * DVT (DVT/web/dvt-tool.html) posts to the same /exec with the DVT key:
 *   kind "dvt_run"  -> one recorded run (upsert by runId)      kind "dvt_file" -> a raw measurement file (base64 -> Drive)
 *   kind "dvt_delete_runs" -> runs the operator removed        the portal shows them in the DVT tab (portalDvt)
 *
 * Script properties (Project Settings > Script properties):
 *   PORTAL_PASSWORD  the portal login password
 *   MACHINE_KEYS     {"CureBox-1": "<key>", ...}
 *   DVT_KEY          the key the DVT tool posts with (any string; set it in the tool's Cloud box)
 *   NETBIRD_TOKEN    a NetBird management-API token (read-only use: GET /api/peers) - the machine card shows whether the
 *                    CureBox is connected to NetBird and when it was last seen there
 *   NETBIRD_PEERS    {"CureBox-1": "scurebox-9d63faba"} - the NetBird peer name of each CureBox
 *   DVT_FOLDER_ID    set automatically: the Drive folder holding the raw DVT files
 *
 * Machine commands are DATA-ONLY BY DESIGN: no command type actuates hardware. DVT tests can be REQUESTED from the
 * DVT tab (user, 2026-10-12), but nothing runs until someone AT the CureBox presses Start on its screen: the DVT
 * runner on the machine asks the firmware for that confirmation first - see "DVT runs from the site" below.
 */

var CELL_MAX = 45000;            // a Sheets cell holds 50,000 characters
var ONLINE_SEC = 90;             // a machine syncing every 30 s is online if seen in the last 90 s
var SESSION_SEC = 6 * 60 * 60;   // portal login lasts 6 h
var COMMAND_TYPES = ['upsert_program', 'delete_program', 'send_print'];
var REPORTS_KEEP = 25;            // newest reports kept per machine (the machine's history keeps its last 25 runs)
var ALERTS_KEEP_DAYS = 30;        // alert log rows kept

// ---------------------------------------------------------------------------------------------- config / storage
function cfg_() {
  // script properties win; else Secrets.gs (written by build_secrets.py from cloud/portal_secrets.local.txt, never in git)
  var p = PropertiesService.getScriptProperties();
  var fallback = (typeof SECRETS !== 'undefined') ? SECRETS : { password: '', machineKeys: {} };
  var keys = fallback.machineKeys || {};
  try { if (p.getProperty('MACHINE_KEYS')) keys = JSON.parse(p.getProperty('MACHINE_KEYS')); } catch (e) { /* keep fallback */ }
  var peers = fallback.netbirdPeers || {};
  try { if (p.getProperty('NETBIRD_PEERS')) peers = JSON.parse(p.getProperty('NETBIRD_PEERS')); } catch (e) { /* keep fallback */ }
  return { password: p.getProperty('PORTAL_PASSWORD') || fallback.password || '', keys: keys,
           dvtKey: p.getProperty('DVT_KEY') || fallback.dvtKey || '',
           netbirdToken: p.getProperty('NETBIRD_TOKEN') || fallback.netbirdToken || '', netbirdPeers: peers };
}

function book_() {
  var p = PropertiesService.getScriptProperties();
  var id = p.getProperty('SHEET_ID');
  var ss = null;
  if (id) { try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; } }
  if (!ss) {
    ss = SpreadsheetApp.create('sCure Cloud data');
    p.setProperty('SHEET_ID', ss.getId());
  }
  sheet_(ss, 'machines', ['name', 'lastSeen', 'snapshot']);
  sheet_(ss, 'commands', ['id', 'machine', 'type', 'payload', 'created', 'delivered', 'acked']);
  sheet_(ss, 'reports', ['machine', 'runId', 'fileName', 'material', 'startedAt', 'status', 'uploaded', 'html']);
  sheet_(ss, 'alerts', ['machine', 'code', 'raised', 'cleared', 'message']);
  var dr = sheet_(ss, 'dvt_runs', ['unit', 'testId', 'variant', 'rep', 'runId', 'verdict', 'operator', 'startedAt', 'recordedAt', 'note', 'machine', 'values']);
  // sheets made before the CureBox column (0.9.95): insert it in front of the values chunks, rows move with it
  if (String(dr.getRange(1, 11, 1, 1).getValues()[0][0]) === 'values') {
    dr.insertColumnBefore(11);
    dr.getRange(1, 11, 1, 1).setValues([['machine']]);
  }
  sheet_(ss, 'dvt_files', ['unit', 'runId', 'kind', 'fileName', 'fileId', 'size', 'uploaded']);
  sheet_(ss, 'dvt_catalog', ['updated', 'catalog']);
  sheet_(ss, 'dvt_requests', ['id', 'machine', 'unit', 'testId', 'status', 'requested', 'started', 'finished',
                              'line', 'prompt', 'answer', 'runIds', 'verdict']);
  sheet_(ss, 'dvt_runners', ['machine', 'lastSeen', 'version', 'unit', 'catalog']);
  sheet_(ss, 'dvt_units', DVT_UNIT_COLS.concat(['updated']));
  return ss;
}

function sheet_(ss, name, header) {
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, header.length).setValues([header]);
    sh.setFrozenRows(1);
    var first = ss.getSheetByName('Sheet1') || ss.getSheetByName('גיליון1');
    if (first && ss.getSheets().length > 1) ss.deleteSheet(first);
  }
  return sh;
}

function now_() { return Date.now() / 1000; }

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** All machine rows as {row, name, lastSeen, snapshot}. */
function machines_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  var width = Math.max(3, sh.getLastColumn());
  var vals = sh.getRange(2, 1, n, width).getValues();
  return vals.map(function (v, i) {
    var text = v.slice(2).join('');
    var snap = {};
    try { snap = text ? JSON.parse(text) : {}; } catch (e) { snap = {}; }
    return { row: i + 2, name: String(v[0]), lastSeen: Number(v[1]) || 0, snapshot: snap };
  }).filter(function (m) { return m.name; });
}

function writeMachine_(sh, name, snapshotText) {
  var chunks = [];
  for (var i = 0; i < snapshotText.length; i += CELL_MAX) chunks.push(snapshotText.substring(i, i + CELL_MAX));
  if (!chunks.length) chunks.push('');
  var existing = machines_(sh).filter(function (m) { return m.name === name; })[0];
  var row = existing ? existing.row : sh.getLastRow() + 1;
  var width = Math.max(sh.getLastColumn(), 2 + chunks.length);
  var values = [name, now_()].concat(chunks);
  while (values.length < width) values.push('');           // clear chunks left over from a longer snapshot
  sh.getRange(row, 1, 1, values.length).setValues([values]);
}

function commands_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, 7).getValues().map(function (v, i) {
    return { row: i + 2, id: Number(v[0]), machine: String(v[1]), type: String(v[2]), payload: String(v[3]),
             created: v[4], delivered: v[5], acked: v[6] };
  });
}

// ---------------------------------------------------------------------------------------------- machine agent
function doPost(e) {
  var path = String((e && e.pathInfo) || '').replace(/^\/+|\/+$/g, '');
  // Apps Script refuses anonymous POSTs with a path after /exec, so the machine posts to /exec itself (path empty)
  if (path !== '' && path !== 'api/agent/sync') return json_({ ok: false, message: 'not found' });
  var d = {};
  try { d = JSON.parse((e.postData && e.postData.contents) || '{}'); } catch (err) { return json_({ ok: false, message: 'bad json' }); }
  var key = d.machineKey || (e.parameter && e.parameter.key) || '';
  // the DVT tool is not a machine: it carries its own key and only ever writes DVT rows
  if (String(d.kind || '').indexOf('dvt') === 0) {
    var want = cfg_().dvtKey;
    if (!want || key !== want) return json_({ ok: false, message: 'bad DVT key' });
    delete d.machineKey;
    if (d.kind === 'dvt_run') return json_(bump_(saveDvtRun_(d)));
    if (d.kind === 'dvt_file') return json_(bump_(saveDvtFile_(d)));
    if (d.kind === 'dvt_delete_runs') return json_(bump_(deleteDvtRuns_(d.runIds)));
    if (d.kind === 'dvt_machines') return json_({ ok: true, machines: dvtMachineNames_() });
    if (d.kind === 'dvt_catalog') return json_(bump_(saveDvtCatalog_(d.catalog)));
    // the DVT runner on a CureBox (DVT/runner/dvt-runner.cjs): announces itself, takes requests, reports progress
    if (d.kind === 'dvt_runner_hello') return json_(bump_(dvtRunnerHello_(d)));
    if (d.kind === 'dvt_events') return json_(dvtEvents_(d));
    if (d.kind === 'dvt_next') return json_(dvtNext_(d));
    if (d.kind === 'dvt_update') return json_(dvtUpdate_(d));
    return json_({ ok: false, message: 'unknown DVT kind: ' + d.kind });
  }
  var name = null;
  var keys = cfg_().keys;
  Object.keys(keys).forEach(function (n) { if (key && keys[n] === key) name = n; });
  if (!name) return json_({ ok: false, message: 'bad machine key' });
  delete d.machineKey;                                     // never stored
  if (d.kind === 'report') return json_(saveReport_(name, d));
  if (d.kind === 'delete_reports') return json_(deleteReports_(name, d.runIds));

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ss = book_();
    var log = d.alertLog || [];
    delete d.alertLog;                                     // kept in its own sheet, not in the snapshot
    writeMachine_(ss.getSheetByName('machines'), name, JSON.stringify(d));
    saveAlerts_(ss.getSheetByName('alerts'), name, log);
    var csh = ss.getSheetByName('commands');
    var acks = (d.ackIds || []).map(Number);
    var out = [];
    var t = now_();
    commands_(csh).forEach(function (c) {
      if (c.machine !== name || c.acked) return;
      if (acks.indexOf(c.id) >= 0) { csh.getRange(c.row, 7).setValue(t); return; }
      var payload = {};
      try { payload = JSON.parse(c.payload || '{}'); } catch (err) { payload = {}; }
      out.push({ id: c.id, type: c.type, payload: payload });
      csh.getRange(c.row, 6).setValue(t);
    });
    return json_({ ok: true, acceptsReports: true, commands: out });
  } finally {
    lock.releaseLock();
  }
}

// ---------------------------------------------------------------------------------------------- alert log
function alerts_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, 5).getValues().map(function (v, i) {
    return { row: i + 2, machine: String(v[0]), code: Number(v[1]), raised: Number(v[2]) || 0,
             cleared: v[3] === '' || v[3] === null ? null : Number(v[3]), message: String(v[4] || '') };
  });
}

/** Merge the machine's alert log (entries {code, message, raised, cleared}) - one row per machine + code + raised time. */
function saveAlerts_(sh, name, log) {
  if (!log.length) return;
  var rows = alerts_(sh);
  var byKey = {};
  rows.forEach(function (r) { byKey[r.machine + '|' + r.code + '|' + r.raised] = r; });
  var add = [];
  log.forEach(function (e) {
    var raised = Number(e.raised) || 0;
    var cleared = e.cleared == null ? '' : Number(e.cleared);
    var msg = String(e.message || '');
    var have = byKey[name + '|' + Number(e.code) + '|' + raised];
    if (!have) { add.push([name, Number(e.code), raised, cleared, msg]); return; }
    if ((have.cleared == null ? '' : have.cleared) !== cleared || (msg && have.message !== msg))
      sh.getRange(have.row, 4, 1, 2).setValues([[cleared, msg || have.message]]);
  });
  if (add.length) sh.getRange(sh.getLastRow() + 1, 1, add.length, 5).setValues(add);
  // keep ALERTS_KEEP_DAYS of history (checked when the sheet grows past 2,000 rows)
  if (sh.getLastRow() > 2000) {
    var cutoff = now_() - ALERTS_KEEP_DAYS * 86400;
    alerts_(sh).filter(function (r) { return r.raised < cutoff; }).map(function (r) { return r.row; })
      .sort(function (a, b) { return b - a; }).forEach(function (r) { sh.deleteRow(r); });
  }
}

/** Alerts raised since `since` (unix s, the page sends its local midnight) plus any still active; newest first. null = not signed in. */
function portalAlerts(token, since) {
  if (!authed_(token)) return null;
  since = Number(since) || 0;
  return alerts_(book_().getSheetByName('alerts'))
    .filter(function (r) { return r.raised >= since || r.cleared == null; })
    .sort(function (a, b) { return b.raised - a.raised; })
    .map(function (r) {
      var def = errorDef_(r.code);
      return { machine: r.machine, code: r.code, raised: r.raised, cleared: r.cleared, message: r.message,
               title: def.t || '', videoUrl: def.v || '' };
    });
}

/** Title + repair video of a code from ErrorRegistry.gs (generated by build_errors.py from errors.json); {} when unknown. */
function errorDef_(code) {
  var reg = (typeof ERROR_REGISTRY !== 'undefined' && ERROR_REGISTRY.codes) || {};
  return reg[String(code)] || {};
}

// ---------------------------------------------------------------------------------------------- cure reports
/** Report rows (without the html) as {row, machine, runId, fileName, uploaded}. */
function reports_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, 7).getValues().map(function (v, i) {
    return { row: i + 2, machine: String(v[0]), runId: String(v[1]), fileName: String(v[2]), material: String(v[3]),
             startedAt: String(v[4]), status: String(v[5]), uploaded: Number(v[6]) || 0 };
  });
}

/** A machine uploads the HTML report of a finished run (body: kind "report", runId, fileName, content ...). */
function saveReport_(name, d) {
  var html = String(d.content || '');
  if (!d.runId || !html) return { ok: false, message: 'report needs runId and content' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('reports');
    var rows = reports_(sh);
    var same = rows.filter(function (r) { return r.machine === name && r.runId === String(d.runId); })[0];
    var chunks = [];
    for (var i = 0; i < html.length; i += CELL_MAX) chunks.push(html.substring(i, i + CELL_MAX));
    var values = [name, String(d.runId), String(d.fileName || ('cure-report-' + d.runId + '.html')), String(d.materialName || ''),
                  String(d.startedAt || ''), String(d.status || ''), now_()].concat(chunks);
    var row = same ? same.row : sh.getLastRow() + 1;
    var width = Math.max(sh.getLastColumn(), values.length);
    while (values.length < width) values.push('');
    sh.getRange(row, 1, 1, values.length).setValues([values]);
    // keep the newest REPORTS_KEEP of this machine
    var mine = reports_(sh).filter(function (r) { return r.machine === name; }).sort(function (a, b) { return b.uploaded - a.uploaded; });
    mine.slice(REPORTS_KEEP).map(function (r) { return r.row; }).sort(function (a, b) { return b - a; })
        .forEach(function (r) { sh.deleteRow(r); });
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** Runs the user deleted on the machine (one or all): their reports go from the portal too. */
function deleteReports_(name, runIds) {
  if (!Array.isArray(runIds)) return { ok: false, message: 'runIds must be a list' };
  var ids = runIds.map(String);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('reports');
    var rows = reports_(sh).filter(function (r) { return r.machine === name && ids.indexOf(r.runId) >= 0; })
      .map(function (r) { return r.row; }).sort(function (a, b) { return b - a; });
    rows.forEach(function (r) { sh.deleteRow(r); });
    return { ok: true, deleted: rows.length };
  } finally {
    lock.releaseLock();
  }
}

function reportHtml_(machine, runId) {
  var sh = book_().getSheetByName('reports');
  var r = reports_(sh).filter(function (x) { return x.machine === machine && x.runId === runId; })[0];
  if (!r) return null;
  var width = sh.getLastColumn();
  var cells = sh.getRange(r.row, 8, 1, Math.max(1, width - 7)).getValues()[0];
  return { fileName: r.fileName, html: cells.join('') };
}

/** GET ?report=<runId>&m=<machine>&t=<session token>[&dl=1]: the report page, or the .html file to save. */
function serveReport_(p) {
  if (!authed_(p.t)) return HtmlService.createHtmlOutput('<p style="font-family:sans-serif">Sign in to sCure Cloud again, then open the report from the site.</p>');
  var rep = reportHtml_(String(p.m || ''), String(p.report || ''));
  if (!rep) return HtmlService.createHtmlOutput('<p style="font-family:sans-serif">Report not found.</p>');
  if (p.dl) return ContentService.createTextOutput(rep.html).setMimeType(ContentService.MimeType.TEXT).downloadAsFile(rep.fileName);
  return HtmlService.createHtmlOutput(rep.html).setTitle(rep.fileName).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ---------------------------------------------------------------------------------------------- DVT campaign
/** DVT run rows (without the values JSON) as {row, unit, testId, ...}. */
function dvtRuns_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, 11).getValues().map(function (v, i) {
    return { row: i + 2, unit: String(v[0]), testId: String(v[1]), variant: String(v[2]), rep: Number(v[3]) || 0,
             runId: String(v[4]), verdict: String(v[5]), operator: String(v[6]), startedAt: String(v[7]),
             recordedAt: Number(v[8]) || 0, note: String(v[9] || ''), machine: String(v[10] || '') };
  }).filter(function (r) { return r.runId; });
}

/** The CureBoxes a DVT unit can be assigned to: every configured machine and every one that has synced (names only). */
function dvtMachineNames_() {
  var names = Object.keys(cfg_().keys);
  machines_(book_().getSheetByName('machines')).forEach(function (m) { if (names.indexOf(m.name) < 0) names.push(m.name); });
  return names.sort();
}

/** One recorded run from the DVT tool (upsert by runId; the tool re-posts a run it reopens). */
function saveDvtRun_(d) {
  if (!d.runId || !d.unit || !d.testId) return { ok: false, message: 'a DVT run needs unit, testId and runId' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_runs');
    var same = dvtRuns_(sh).filter(function (r) { return r.runId === String(d.runId); })[0];
    var text = JSON.stringify(d.values || {});
    var chunks = [];
    for (var i = 0; i < text.length; i += CELL_MAX) chunks.push(text.substring(i, i + CELL_MAX));
    if (!chunks.length) chunks.push('');
    var values = [String(d.unit), String(d.testId), String(d.variant || ''), Number(d.rep) || 1, String(d.runId),
                  String(d.verdict || ''), String(d.operator || ''), String(d.startedAt || ''), now_(),
                  String(d.note || ''), String(d.machine || '')].concat(chunks);
    var row = same ? same.row : sh.getLastRow() + 1;
    var width = Math.max(sh.getLastColumn(), values.length);
    while (values.length < width) values.push('');
    sh.getRange(row, 1, 1, values.length).setValues([values]);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** The Drive folder holding raw DVT files (created on first upload). */
function dvtFolder_() {
  var p = PropertiesService.getScriptProperties();
  var id = p.getProperty('DVT_FOLDER_ID');
  if (id) { try { return DriveApp.getFolderById(id); } catch (e) { /* recreate below */ } }
  var f = DriveApp.createFolder('sCure DVT files');
  p.setProperty('DVT_FOLDER_ID', f.getId());
  return f;
}

/** A raw measurement file (sweep CSV, UV-off graph PNG): base64 body -> Drive, one row per unit+run+name. */
function saveDvtFile_(d) {
  if (!d.runId || !d.unit || !d.fileName) return { ok: false, message: 'a DVT file needs unit, runId and fileName' };
  var b64 = String(d.contentBase64 || '');
  if (!b64) return { ok: false, message: 'a DVT file needs contentBase64' };
  var mime = String(d.mimeType || (/\.png$/i.test(d.fileName) ? 'image/png' : 'text/csv'));
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_files');
    var rows = dvtFiles_(sh);
    var same = rows.filter(function (r) { return r.unit === String(d.unit) && r.runId === String(d.runId) && r.fileName === String(d.fileName); })[0];
    var blob = Utilities.newBlob(Utilities.base64Decode(b64), mime, String(d.fileName));
    if (same) { try { DriveApp.getFileById(same.fileId).setTrashed(true); } catch (e) { /* already gone */ } }
    var file = dvtFolder_().createFile(blob);
    var values = [String(d.unit), String(d.runId), String(d.fileKind || ''), String(d.fileName), file.getId(), blob.getBytes().length, now_()];
    var row = same ? same.row : sh.getLastRow() + 1;
    sh.getRange(row, 1, 1, values.length).setValues([values]);
    return { ok: true, fileId: file.getId() };
  } finally {
    lock.releaseLock();
  }
}

function dvtFiles_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, 7).getValues().map(function (v, i) {
    return { row: i + 2, unit: String(v[0]), runId: String(v[1]), kind: String(v[2]), fileName: String(v[3]),
             fileId: String(v[4]), size: Number(v[5]) || 0, uploaded: Number(v[6]) || 0 };
  }).filter(function (r) { return r.fileId; });
}

/** Runs the operator deleted in the tool: the rows and their raw files go from the portal too. */
function deleteDvtRuns_(runIds) {
  if (!Array.isArray(runIds)) return { ok: false, message: 'runIds must be a list' };
  var ids = runIds.map(String);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ss = book_();
    var rsh = ss.getSheetByName('dvt_runs');
    var gone = dvtRuns_(rsh).filter(function (r) { return ids.indexOf(r.runId) >= 0; })
      .map(function (r) { return r.row; }).sort(function (a, b) { return b - a; });
    gone.forEach(function (r) { rsh.deleteRow(r); });
    var fsh = ss.getSheetByName('dvt_files');
    dvtFiles_(fsh).filter(function (f) { return ids.indexOf(f.runId) >= 0; })
      .map(function (f) { try { DriveApp.getFileById(f.fileId).setTrashed(true); } catch (e) { /* already gone */ } return f.row; })
      .sort(function (a, b) { return b - a; }).forEach(function (r) { fsh.deleteRow(r); });
    return { ok: true, deleted: gone.length };
  } finally {
    lock.releaseLock();
  }
}

/** The DVT tool's catalog (one row): phases with their gate, every test with its units and the runs it owes. */
function saveDvtCatalog_(cat) {
  if (!cat || !Array.isArray(cat.phases) || !cat.tests) return { ok: false, message: 'a DVT catalog needs phases and tests' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_catalog');
    var text = JSON.stringify(cat);
    var chunks = [];
    for (var i = 0; i < text.length; i += CELL_MAX) chunks.push(text.substring(i, i + CELL_MAX));
    var values = [now_()].concat(chunks);
    var width = Math.max(sh.getLastColumn(), values.length);
    while (values.length < width) values.push('');
    sh.getRange(2, 1, 1, values.length).setValues([values]);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/**
 * The catalog without each test's detail (purpose, steps, criteria ...): the DVT tab polls this, and the detail is tens of KB.
 * The page asks for the detail once, with portalDvtDetail, and again only when the catalog was replaced.
 */
function stripDetail_(cat) {
  if (!cat || !cat.tests) return cat;
  var tests = {};
  Object.keys(cat.tests).forEach(function (tid) {
    var t = {};
    Object.keys(cat.tests[tid]).forEach(function (k) { if (k !== 'd') t[k] = cat.tests[tid][k]; });
    t.hasDetail = !!cat.tests[tid].d;
    tests[tid] = t;
  });
  var out = {};
  Object.keys(cat).forEach(function (k) { out[k] = cat[k]; });
  out.tests = tests;
  return out;
}

/** Why and how of every test, for the DVT tab: {updated, tests: {testId: detail}} - null when not signed in. */
function portalDvtDetail(token) {
  if (!authed_(token)) return null;
  var cat = dvtCatalog_(book_());
  var tests = {};
  if (cat && cat.tests) Object.keys(cat.tests).forEach(function (tid) { if (cat.tests[tid].d) tests[tid] = cat.tests[tid].d; });
  return { updated: cat ? cat.updated : 0, tests: tests };
}

function cacheGet_(k) { try { return CacheService.getScriptCache().get(k); } catch (e) { return null; } }
function cachePut_(k, v, ttl) { try { CacheService.getScriptCache().put(k, String(v), ttl); } catch (e) { /* the cache is a convenience */ } }

/** Is somebody looking at the DVT tab right now? (portalDvt stamps it; the runner polls fast only then.) */
function dvtWatching_() {
  var w = Number(cacheGet_('dvt_watch')) || 0;
  return w > 0 && now_() - w < DVT_WATCH_SEC;
}

/** What a CureBox's runner last reported about its readiness (kept in the cache: it changes every poll, a sheet row would not do). */
function dvtReadiness_(machine) {
  try {
    var text = CacheService.getScriptCache().get('dvt_ready_' + machine);
    return text ? JSON.parse(text) : null;
  } catch (e) { return null; }
}

function bump_(out) { bumpVer_(); return out; }

function dvtCatalog_(ss) {
  var sh = ss.getSheetByName('dvt_catalog');
  if (sh.getLastRow() < 2) return null;
  var cells = sh.getRange(2, 1, 1, Math.max(2, sh.getLastColumn())).getValues()[0];
  try { var cat = JSON.parse(cells.slice(1).join('')); cat.updated = Number(cells[0]) || 0; return cat; } catch (e) { return null; }
}

/** Everything the DVT tab shows: every recorded run with its values, and the raw files per run. null = not signed in. */
function portalDvt(token) {
  if (!authed_(token)) return null;
  cachePut_('dvt_watch', now_(), 120);
  var ss = book_();
  var rsh = ss.getSheetByName('dvt_runs');
  var width = Math.max(12, rsh.getLastColumn());
  var n = rsh.getLastRow() - 1;
  var raw = n > 0 ? rsh.getRange(2, 1, n, width).getValues() : [];
  var url = '';
  try { url = ScriptApp.getService().getUrl(); } catch (e) { url = ''; }
  var files = dvtFiles_(ss.getSheetByName('dvt_files'));
  var runs = raw.map(function (v) {
    var vals = {};
    try { var text = v.slice(11).join(''); vals = text ? JSON.parse(text) : {}; } catch (e) { vals = {}; }
    return { unit: String(v[0]), testId: String(v[1]), variant: String(v[2]), rep: Number(v[3]) || 0,
             runId: String(v[4]), verdict: String(v[5]), operator: String(v[6]), startedAt: String(v[7]),
             recordedAt: Number(v[8]) || 0, note: String(v[9] || ''), machine: String(v[10] || ''), values: vals,
             files: files.filter(function (f) { return f.runId === String(v[4]); })
               .map(function (f) { return { name: f.fileName, kind: f.kind, size: f.size, id: f.fileId }; }) };
  }).filter(function (r) { return r.runId; });
  var t = now_();
  var requests = dvtRequests_(ss.getSheetByName('dvt_requests')).sort(function (a, b) { return b.id - a.id; }).slice(0, 200)
    .map(function (r) { return { id: r.id, machine: r.machine, unit: r.unit, testId: r.testId, status: r.status, requested: r.requested,
                                 started: r.started, finished: r.finished, line: r.line, prompt: r.prompt, verdict: r.verdict, runIds: r.runIds }; });
  var runners = runners_(ss.getSheetByName('dvt_runners')).map(function (r) {
    var ready = dvtReadiness_(r.machine);
    var seen = Math.max(r.lastSeen, Number(cacheGet_('dvt_seen_' + r.machine)) || 0);
    return { machine: r.machine, lastSeen: seen, online: t - seen < DVT_RUNNER_ONLINE_SEC, version: r.version, unit: r.unit,
             readiness: ready && t - ready.at < DVT_READY_FRESH_SEC ? ready.tests : null };
  });
  return { runs: runs, fileUrl: url, catalog: stripDetail_(dvtCatalog_(ss)), requests: requests, runners: runners, units: dvtUnits_(ss.getSheetByName('dvt_units')), race: raceGet_(), now: now_(), build: PORTAL_BUILD };
}

// ---------------------------------------------------------------------------------------------- DVT units (the machines of the campaign)
// The DVT spec (user, 2026-10-22): every machine of the campaign has an integrator, revisions and a plan. A unit is a row of
// the catalog's units (UUT-01 ...); the registry adds who works on it and when it is planned to be done.
var DVT_UNIT_COLS = ['unit', 'machine', 'integrator', 'hwRev', 'fwVersion', 'bomRev', 'planStart', 'planEnd', 'note'];

function dvtUnits_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  return sh.getRange(2, 1, n, DVT_UNIT_COLS.length + 1).getValues().map(function (v) {
    var o = {};
    DVT_UNIT_COLS.forEach(function (c, i) { o[c] = String(v[i] == null ? '' : v[i]); });
    o.updated = Number(v[DVT_UNIT_COLS.length]) || 0;
    return o;
  }).filter(function (o) { return o.unit; });
}

/** Save the registry fields of one unit (only the fields sent change). null = not signed in. */
function portalDvtUnitSave(token, unit, fields) {
  if (!authed_(token)) return null;
  unit = String(unit || '').trim();
  if (!/^[A-Za-z0-9._-]{1,40}$/.test(unit)) return { ok: false, message: 'a unit name is letters, digits, . _ - (up to 40)' };
  fields = fields || {};
  var clean = {};
  for (var i = 1; i < DVT_UNIT_COLS.length; i++) {
    var c = DVT_UNIT_COLS[i];
    if (fields[c] === undefined) continue;
    var v = String(fields[c] == null ? '' : fields[c]).trim().replace(/[\r\n]+/g, ' ').substring(0, 200);
    if ((c === 'planStart' || c === 'planEnd') && v && !/^\d{4}-\d{2}-\d{2}$/.test(v)) return { ok: false, message: c + ' is a date: YYYY-MM-DD' };
    clean[c] = v;
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_units');
    var same = dvtUnits_(sh).filter(function (o) { return o.unit === unit; })[0];
    var row = [unit];
    for (var j = 1; j < DVT_UNIT_COLS.length; j++) {
      var col = DVT_UNIT_COLS[j];
      row.push(clean[col] !== undefined ? clean[col] : same ? same[col] : '');
    }
    row.push(now_());
    var at = same ? dvtUnitRow_(sh, unit) : sh.getLastRow() + 1;
    sh.getRange(at, 1, 1, row.length).setValues([row]);
    bumpVer_();
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function dvtUnitRow_(sh, unit) {
  var names = sh.getRange(2, 1, Math.max(1, sh.getLastRow() - 1), 1).getValues();
  for (var i = 0; i < names.length; i++) if (String(names[i][0]) === unit) return i + 2;
  return sh.getLastRow() + 1;
}

/**
 * The text of recorded sample files (CSV), for the Compare tab to draw curves: {files: {fileId: {name, text}}}. Only files the portal
 * knows (the dvt_files sheet) and only text; a few at a time and not too big, so one call stays quick. null = not signed in.
 */
function portalDvtFiles(token, ids) {
  if (!authed_(token)) return null;
  if (!Array.isArray(ids) || !ids.length) return { ok: false, message: 'no files asked for' };
  var known = {};
  dvtFiles_(book_().getSheetByName('dvt_files')).forEach(function (f) { known[f.fileId] = f; });
  var out = {}, budget = DVT_FILES_BYTES;
  ids.slice(0, DVT_FILES_MAX).forEach(function (id) {
    var row = known[String(id)];
    if (!row || !/\.csv$/i.test(row.fileName)) return;
    try {
      var text = DriveApp.getFileById(row.fileId).getBlob().getDataAsString();
      if (text.length > budget) return;
      budget -= text.length;
      out[row.fileId] = { name: row.fileName, text: text };
    } catch (e) { /* a file removed from Drive is simply missing from the answer */ }
  });
  return { ok: true, files: out };
}
var DVT_FILES_MAX = 8;                 // files per call
var DVT_FILES_BYTES = 3000000;         // text per call (an Apps Script reply stays well under its limit)

// ---------------------------------------------------------------------------------------------- DVT race
// The race between the machines (user, 2026-10-23): one official start for every unit and the list of the units that take part. The
// clocks, the ranking and the winner are worked out in the page from the recorded runs; only these two facts are stored.
function raceGet_() {
  var o = {};
  try { o = JSON.parse(PropertiesService.getScriptProperties().getProperty('RACE') || '{}') || {}; } catch (e) { o = {}; }
  return { start: Number(o.start) || 0, units: Array.isArray(o.units) ? o.units.map(String) : [] };
}

/** Set the official start ({start: 'now' | 0 | seconds}) and / or who is in the race ({units: [...]}). null = not signed in. */
function portalRaceSet(token, d) {
  if (!authed_(token)) return null;
  d = d || {};
  var cur = raceGet_();
  if (d.start !== undefined) {
    if (d.start === 'now') cur.start = Math.floor(now_());
    else if (Number(d.start) === 0) cur.start = 0;
    else if (Number(d.start) > 1e9 && Number(d.start) < 4e9) cur.start = Math.floor(Number(d.start));
    else return { ok: false, message: 'start is "now", 0 or a time in seconds' };
  }
  if (d.units !== undefined) {
    if (!Array.isArray(d.units) || d.units.length > 30 || d.units.some(function (u) { return !/^[A-Za-z0-9._-]{1,40}$/.test(String(u)); }))
      return { ok: false, message: 'units is a list of unit names' };
    cur.units = d.units.map(String);
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    PropertiesService.getScriptProperties().setProperty('RACE', JSON.stringify(cur));
    bumpVer_();
    return { ok: true, race: cur };
  } finally {
    lock.releaseLock();
  }
}

// ---------------------------------------------------------------------------------------------- DVT runs from the site
// The user (2026-10-12): DVT tests are started from the portal and confirmed AT the machine - the runner on the
// CureBox shows the request on the machine's screen and waits for Start / Decline there. The portal only queues and relays: the runner on the CureBox (DVT/runner) runs the same
// dvt-auto.js scripts as the DVT tool, through the machine's own API - so the machine's interlocks, output watchdog
// and fan / sensor supervision stay in charge. A step that needs a person (open the door, pull a sensor, read a
// meter) is asked in the request's row on the site, and the answer travels back to the runner.
var DVT_RUNNER_ONLINE_SEC = 60;       // the runner polls every 10 s
var DVT_HOLD_MAX_SEC = 20;            // a long poll is held at most this long (an Apps Script execution may run minutes; the limit is 30 at once)
var DVT_WATCH_SEC = 45;               // the DVT tab was read within this: the runner polls fast
var DVT_READY_FRESH_SEC = 45;         // a readiness report older than this is not shown (the runner sends one with every poll)
var PORTAL_BUILD = '0.9.123';         // the page compares it with its own: a tab left open across a deploy is told to reload
var DVT_REQUESTS_KEEP = 300;          // finished requests kept, newest first
var DVT_ACTIVE = ['queued', 'running', 'waiting', 'cancel_requested'];
var DVT_FINAL = ['done', 'failed', 'cancelled', 'blocked'];   // blocked = could not begin (an instrument missing): nothing was measured

function dvtRequests_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  var j = function (x) { try { return x === '' || x === null || x === undefined ? null : JSON.parse(x); } catch (e) { return null; } };
  return sh.getRange(2, 1, n, 13).getValues().map(function (v, i) {
    return { row: i + 2, id: Number(v[0]) || 0, machine: String(v[1]), unit: String(v[2]), testId: String(v[3]),
             status: String(v[4]), requested: Number(v[5]) || 0, started: Number(v[6]) || 0, finished: Number(v[7]) || 0,
             line: String(v[8] || ''), prompt: j(v[9]), answer: j(v[10]), runIds: j(v[11]) || [], verdict: String(v[12] || '') };
  }).filter(function (r) { return r.id; });
}

function writeRequest_(sh, r) {
  bumpVer_();
  sh.getRange(r.row, 1, 1, 13).setValues([[r.id, r.machine, r.unit, r.testId, r.status, r.requested, r.started || '', r.finished || '',
    r.line || '', r.prompt ? JSON.stringify(r.prompt) : '', r.answer ? JSON.stringify(r.answer) : '', JSON.stringify(r.runIds || []),
    r.verdict || '']]);
}

/** Keep the newest DVT_REQUESTS_KEEP finished requests; active ones are never pruned. */
function pruneRequests_(sh) {
  var done = dvtRequests_(sh).filter(function (r) { return DVT_FINAL.indexOf(r.status) >= 0; }).sort(function (a, b) { return b.id - a.id; });
  done.slice(DVT_REQUESTS_KEEP).map(function (r) { return r.row; }).sort(function (a, b) { return b - a; })
    .forEach(function (r) { sh.deleteRow(r); });
}

function runners_(sh) {
  var n = sh.getLastRow() - 1;
  if (n < 1) return [];
  var width = Math.max(5, sh.getLastColumn());
  return sh.getRange(2, 1, n, width).getValues().map(function (v, i) {
    var cat = [];
    try { var text = v.slice(4).join(''); cat = text ? JSON.parse(text) : []; } catch (e) { cat = []; }
    return { row: i + 2, machine: String(v[0]), lastSeen: Number(v[1]) || 0, version: String(v[2] || ''), unit: String(v[3] || ''), catalog: cat };
  }).filter(function (r) { return r.machine; });
}

function touchRunner_(sh, machine) {
  var r = runners_(sh).filter(function (x) { return x.machine === machine; })[0];
  if (r) sh.getRange(r.row, 2, 1, 1).setValues([[now_()]]);
}

/** The runner introduces itself: version, the DVT unit it is, and the tests it can run (the site's Run buttons). */
function dvtRunnerHello_(d) {
  if (!d.machine) return { ok: false, message: 'the runner needs its CureBox name' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_runners');
    var same = runners_(sh).filter(function (r) { return r.machine === String(d.machine); })[0];
    var text = JSON.stringify(d.catalog || []);
    var chunks = [];
    for (var i = 0; i < text.length; i += CELL_MAX) chunks.push(text.substring(i, i + CELL_MAX));
    if (!chunks.length) chunks.push('');
    var values = [String(d.machine), now_(), String(d.version || ''), String(d.unit || '')].concat(chunks);
    var row = same ? same.row : sh.getLastRow() + 1;
    var width = Math.max(sh.getLastColumn(), values.length);
    while (values.length < width) values.push('');
    sh.getRange(row, 1, 1, values.length).setValues([values]);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** The runner asks for work: the oldest queued request of its CureBox, handed over once and marked running. */
/**
 * The runner's poll - a LONG poll. With `wait` (seconds, at most DVT_HOLD_MAX_SEC) the call is held open and answers the
 * moment a request is queued for that CureBox, instead of the runner asking again and again (each Apps Script call costs
 * about a second, so asking every 1.5 s still meant seconds of delay). Without `wait` it answers at once, as before.
 * Held or not it is cheap: when the last full look found nothing queued the answer comes from the cache alone (no lock,
 * no sheet). Whoever queues a request flips that cache entry under the same lock, so a request is never missed; once a
 * minute the sheet is read anyway. The reply says whether the portal is being watched.
 */
function dvtNext_(d) {
  if (!d.machine) return { ok: false, message: 'the runner needs its CureBox name' };
  var machine = String(d.machine);
  if (d.readiness && typeof d.readiness === 'object') {
    var sig = JSON.stringify(d.readiness);
    if (cacheGet_('dvt_readysig_' + machine) !== sig) { cachePut_('dvt_readysig_' + machine, sig, 300); bumpVer_(); }   // the card's rows changed: the page looks again
    cachePut_('dvt_ready_' + machine, JSON.stringify({ at: now_(), tests: d.readiness }), 300);
  }
  var end = Date.now() + Math.min(Math.max(Number(d.wait) || 0, 0), DVT_HOLD_MAX_SEC) * 1000;
  for (;;) {
    var t = now_();
    cachePut_('dvt_seen_' + machine, t, 300);                    // the portal reads "online" from here (the sheet row is touched less often)
    var watch = dvtWatching_();
    var fullAt = Number(cacheGet_('dvt_full_' + machine)) || 0;
    if (!(cacheGet_('dvt_q_' + machine) === '0' && t - fullAt < 60)) {
      var r = dvtNextFull_(machine, watch);
      if (r.request) return r;
    }
    if (Date.now() >= end) return { ok: true, request: null, watch: watch };
    Utilities.sleep(250);
  }
}

/** The full look: under the lock, touch the runner's row, hand over the oldest queued request - or note that there is none. */
function dvtNextFull_(machine, watch) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ss = book_();
    touchRunner_(ss.getSheetByName('dvt_runners'), machine);
    cachePut_('dvt_full_' + machine, now_(), 21600);
    var sh = ss.getSheetByName('dvt_requests');
    var next = dvtRequests_(sh).filter(function (r) { return r.machine === machine && r.status === 'queued'; })
      .sort(function (a, b) { return a.id - b.id; })[0];
    if (!next) { cachePut_('dvt_q_' + machine, '0', 21600); return { ok: true, request: null, watch: watch }; }
    next.status = 'running';
    next.started = now_();
    next.line = 'started on the CureBox';
    writeRequest_(sh, next);
    return { ok: true, request: { id: next.id, unit: next.unit, testId: next.testId }, watch: watch };
  } finally {
    lock.releaseLock();
  }
}

/**
 * The runner, while it handles a request, holds this open: it answers when the portal commanded something for that CureBox
 * (a cancel, an answer, a new request) so the runner reacts at once instead of at its next one-second look.
 */
function dvtEvents_(d) {
  if (!d.machine) return { ok: false, message: 'the runner needs its CureBox name' };
  var machine = String(d.machine);
  cachePut_('dvt_seen_' + machine, now_(), 300);
  var ver = waitFor_(function () { return String(Number(cacheGet_('dvt_cmd_' + machine)) || 0); }, String(d.since === undefined ? '' : d.since), d.wait);
  return { ok: true, ver: ver };
}

/** What the DVT tab shows changed since `since` (a version number the page got before)? Held up to 15 s; null = not signed in. */
function portalDvtWait(token, since, waitSec) {
  if (!authed_(token)) return null;
  cachePut_('dvt_watch', now_(), 120);
  var ver = waitFor_(function () { return String(Number(cacheGet_('dvt_ver')) || 0); }, String(since === undefined || since === null ? '' : since), waitSec);
  return { ver: ver };
}

/** Poll read() every 250 ms until it differs from `since`, at most `waitSec` (capped); returns what it read last. */
function waitFor_(read, since, waitSec) {
  var end = Date.now() + Math.min(Math.max(Number(waitSec) || 0, 0), DVT_HOLD_MAX_SEC) * 1000;
  var v = read();
  while (v === since && Date.now() < end) { Utilities.sleep(250); v = read(); }
  return v;
}

/** Something the DVT tab shows has changed (the page's long poll wakes up). */
function bumpVer_() { cachePut_('dvt_ver', String((Number(cacheGet_('dvt_ver')) || 0) + 1), 21600); }
/** The portal commanded something for this CureBox (a request, a cancel, an answer): the runner's long poll wakes up. */
function bumpCmd_(machine) {
  var k = 'dvt_cmd_' + String(machine);
  cachePut_(k, String((Number(cacheGet_(k)) || 0) + 1), 21600);
  bumpVer_();
}

/**
 * Progress from the runner: status, the line it shows, the prompt it waits on, the runs it wrote, the verdict.
 * The reply carries a cancel from the site and the answer to the open prompt (handed over once, then cleared).
 */
function dvtUpdate_(d) {
  var id = Number(d.id);
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ss = book_();
    var sh = ss.getSheetByName('dvt_requests');
    var r = dvtRequests_(sh).filter(function (x) { return x.id === id; })[0];
    if (!r) return { ok: false, message: 'no such request' };
    if (d.machine && r.machine !== String(d.machine)) return { ok: false, message: 'that request belongs to another CureBox' };
    touchRunner_(ss.getSheetByName('dvt_runners'), r.machine);
    var cancel = r.status === 'cancel_requested';
    var out = { ok: true, cancel: cancel };
    if ('line' in d) r.line = String(d.line || '');
    if ('prompt' in d) r.prompt = d.prompt || null;
    if (Array.isArray(d.runIds)) r.runIds = d.runIds.map(String);
    if (d.verdict) r.verdict = String(d.verdict);
    if (r.answer) { out.hasAnswer = true; out.answer = r.answer.v; r.answer = null; r.prompt = null; }
    var st = String(d.status || '');
    if (DVT_FINAL.indexOf(st) >= 0) { r.status = st; r.finished = now_(); r.prompt = null; }
    else if ((st === 'running' || st === 'waiting') && !cancel) r.status = st;       // a pending cancel is not overwritten
    writeRequest_(sh, r);
    if (DVT_FINAL.indexOf(st) >= 0) pruneRequests_(sh);
    return out;
  } finally {
    lock.releaseLock();
  }
}

/** Queue tests on a CureBox; null = not signed in. A test already queued or running there for that unit is not doubled. */
function portalDvtRequest(token, machine, unit, testIds) {
  if (!authed_(token)) return null;
  if (!machine || !unit || !Array.isArray(testIds) || !testIds.length) return { ok: false, message: 'choose a CureBox, a unit and at least one test' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_requests');
    var rows = dvtRequests_(sh);
    // a CureBox IS one unit: once its runner said which, a request for another unit is refused (a stale tab sent one for
    // UUT-02 to CureBox-1 on 2026-10-14 - it would have recorded the results under a unit that does not exist)
    var runner = runners_(book_().getSheetByName('dvt_runners')).filter(function (x) { return x.machine === String(machine); })[0];
    if (runner && runner.unit && runner.unit !== String(unit))
      return { ok: false, message: String(machine) + ' is unit ' + runner.unit + ' - the request was for ' + unit + '. Reload the page.' };
    var busy = rows.filter(function (r) { return r.machine === String(machine) && r.unit === String(unit) && DVT_ACTIVE.indexOf(r.status) >= 0; })
      .map(function (r) { return r.testId; });
    var id = rows.length ? Math.max.apply(null, rows.map(function (r) { return r.id; })) + 1 : 1;
    var t = now_(), add = [];
    testIds.map(String).forEach(function (tid) {
      if (busy.indexOf(tid) >= 0) return;
      busy.push(tid);
      add.push([id++, String(machine), String(unit), tid, 'queued', t, '', '', 'waiting for the CureBox to pick it up', '', '', '[]', '']);
    });
    if (add.length) { sh.getRange(sh.getLastRow() + 1, 1, add.length, 13).setValues(add); cachePut_('dvt_q_' + String(machine), '1', 21600); bumpCmd_(machine); }
    return { ok: true, queued: add.length, skipped: testIds.length - add.length };
  } finally {
    lock.releaseLock();
  }
}

/** Stop a request: a queued one never starts; a running one is stopped by the runner on its next report. */
function portalDvtCancel(token, id) {
  if (!authed_(token)) return null;
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_requests');
    var r = dvtRequests_(sh).filter(function (x) { return x.id === Number(id); })[0];
    if (!r || DVT_ACTIVE.indexOf(r.status) < 0) return { ok: false, message: 'that request is not active' };
    if (r.status === 'queued') { r.status = 'cancelled'; r.finished = now_(); r.line = 'cancelled from the site before it started'; }
    else { r.status = 'cancel_requested'; r.line = 'stopping - the CureBox turns everything off'; }
    writeRequest_(sh, r);
    bumpCmd_(r.machine);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** Answer the step the runner waits on: true = Done / Yes, false = No, null = Skip, or the value typed. */
function portalDvtAnswer(token, id, value) {
  if (!authed_(token)) return null;
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('dvt_requests');
    var r = dvtRequests_(sh).filter(function (x) { return x.id === Number(id); })[0];
    if (!r || !r.prompt) return { ok: false, message: 'that request is not waiting for an answer' };
    r.answer = { v: value === undefined ? null : value };
    r.line = 'answered from the site - the CureBox continues';
    writeRequest_(sh, r);
    bumpCmd_(r.machine);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** GET ?dvtfile=<Drive id>&t=<session token>: a CSV downloads, a graph opens as a picture - signed-in browsers only. */
function serveDvtFile_(p) {
  if (!authed_(p.t)) return HtmlService.createHtmlOutput('<p style="font-family:sans-serif">Sign in to sCure Cloud again, then open the file from the site.</p>');
  var row = dvtFiles_(book_().getSheetByName('dvt_files')).filter(function (f) { return f.fileId === String(p.dvtfile); })[0];
  if (!row) return HtmlService.createHtmlOutput('<p style="font-family:sans-serif">File not found.</p>');
  var blob = DriveApp.getFileById(row.fileId).getBlob();
  var mime = String(blob.getContentType() || '');
  if (/^image\//.test(mime))         // ContentService only serves text: a graph is shown as an inline picture instead
    return HtmlService.createHtmlOutput('<img alt="" style="max-width:100%" src="data:' + mime + ';base64,' +
      Utilities.base64Encode(blob.getBytes()) + '">').setTitle(row.fileName).setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  return ContentService.createTextOutput(blob.getDataAsString()).setMimeType(ContentService.MimeType.TEXT).downloadAsFile(row.fileName);
}

// ---------------------------------------------------------------------------------------------- portal page
function doGet(e) {
  if (e && e.parameter && e.parameter.report) return serveReport_(e.parameter);
  if (e && e.parameter && e.parameter.dvtfile) return serveDvtFile_(e.parameter);
  return HtmlService.createHtmlOutputFromFile('Page')
    .setTitle('sCure Cloud')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);   // shown inside Google Sites
}

function authed_(token) {
  return !!token && CacheService.getScriptCache().get('tok:' + token) === '1';
}

function portalLogin(password) {
  var want = cfg_().password;
  if (!want || password !== want) return { ok: false };
  var token = Utilities.getUuid() + Utilities.getUuid();
  CacheService.getScriptCache().put('tok:' + token, '1', SESSION_SEC);
  return { ok: true, token: token };
}

/**
 * NetBird's view of each configured CureBox (management API, read only; cached 30 s): connected, last seen, mesh IP.
 * A CureBox that syncs here while NetBird says offline is running but cannot be reached remotely (SSH, screen);
 * one that is offline in both has no power or no network. Several registrations of one peer name (a reflash
 * re-enrols the unit) -> the connected / most recently seen one counts, the rest are reported as stale.
 */
function netbirdStatus_() {
  var c = cfg_();
  if (!c.netbirdToken || !Object.keys(c.netbirdPeers).length) return null;
  var cache = CacheService.getScriptCache();
  var peers = null;
  try { peers = JSON.parse(cache.get('netbird:peers') || 'null'); } catch (e) { peers = null; }
  if (!peers) {
    try {
      var r = UrlFetchApp.fetch('https://api.netbird.io/api/peers',
        { headers: { Authorization: 'Token ' + c.netbirdToken, Accept: 'application/json' }, muteHttpExceptions: true });
      if (r.getResponseCode() !== 200) return { error: 'NetBird API answered ' + r.getResponseCode() };
      peers = JSON.parse(r.getContentText()).map(function (x) {
        return { name: String(x.name || ''), ip: String(x.ip || ''), connected: !!x.connected, lastSeen: (Date.parse(x.last_seen) / 1000) || 0 };
      });
      cache.put('netbird:peers', JSON.stringify(peers), 30);
    } catch (e) {
      return { error: 'NetBird API not reached: ' + (e.message || e) };
    }
  }
  var out = {};
  Object.keys(c.netbirdPeers).forEach(function (machine) {
    var mine = peers.filter(function (x) { return x.name === c.netbirdPeers[machine]; })
      .sort(function (a, b) { return (Number(b.connected) - Number(a.connected)) || (b.lastSeen - a.lastSeen); });
    out[machine] = mine.length ? { peer: mine[0].name, connected: mine[0].connected, lastSeen: mine[0].lastSeen, ip: mine[0].ip, stale: mine.length - 1 }
                               : { peer: c.netbirdPeers[machine], missing: true };
  });
  return { peers: out };
}

/** What the page's /api/machines call returns; null = not signed in. */
function portalMachines(token) {
  if (!authed_(token)) return null;
  var ss = book_();
  var cmds = commands_(ss.getSheetByName('commands'));
  var reps = reports_(ss.getSheetByName('reports'));
  var url = '';
  try { url = ScriptApp.getService().getUrl(); } catch (e) { url = ''; }
  var t = now_();
  var nb = netbirdStatus_();
  return machines_(ss.getSheetByName('machines')).sort(function (a, b) { return a.name < b.name ? -1 : 1; }).map(function (m) {
    var s = m.snapshot || {};
    return {
      name: m.name, lastSeen: m.lastSeen, online: t - m.lastSeen < ONLINE_SEC,
      pending: cmds.filter(function (c) { return c.machine === m.name && !c.acked; }).length,
      state: s.state || {}, programs: s.programs || [], prints: s.prints || [], cures: s.cures || [],
      reports: reps.filter(function (r) { return r.machine === m.name; }).map(function (r) { return r.runId; }),
      reportUrl: url,
      netbird: nb ? (nb.peers ? nb.peers[m.name] || null : { error: nb.error }) : null
    };
  });
}

/** Queue a data-only command for a machine; null = not signed in. */
function portalCommand(token, name, d) {
  if (!authed_(token)) return null;
  d = d || {};
  if (COMMAND_TYPES.indexOf(d.type) < 0) return { ok: false, message: 'unknown command type' };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sh = book_().getSheetByName('commands');
    var ids = commands_(sh).map(function (c) { return c.id; });
    var id = ids.length ? Math.max.apply(null, ids) + 1 : 1;
    sh.appendRow([id, name, d.type, JSON.stringify(d.payload || {}), now_(), '', '']);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/** Run once from the editor: creates the data sheet and prints its link (Executions log). */
function setup() {
  var ss = book_();
  Logger.log('Data sheet: ' + ss.getUrl());
  Logger.log('Machines configured: ' + Object.keys(cfg_().keys).join(', '));
}
