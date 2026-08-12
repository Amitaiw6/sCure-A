#!/usr/bin/env python3
"""
sCure Cloud Portal - manage work programs / work points and simulate
incoming prints for sCure machines, from anywhere in the world.

Run:
    python portal.py                # port 8080 (or PORT env)

Config (portal_config.json next to this file):
    {
      "password": "<portal login password>",
      "machine_keys": { "CureBox-1": "<long random secret>" }
    }

How it connects (no inbound ports on the machine, works behind any NAT):
    the MACHINE calls out:  POST /api/agent/sync  every ~10 s with its
    X-Machine-Key. The request body carries the machine snapshot (state,
    programs, prints); the response carries queued commands:
        upsert_program  - create/update a work program (work points)
        delete_program  - remove a work program
        send_print      - inject a simulated received print
    The machine acks applied command ids on its next sync.

DATA-ONLY BY DESIGN: there is no command type that actuates hardware.
Heaters/UV can only be started at the machine itself.
"""

import json
import os
import secrets
import sqlite3
import time

from flask import Flask, request, jsonify, make_response

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, 'portal_config.json')
# On a PaaS (Fly.io etc.) mount a persistent volume and point PORTAL_DATA_DIR
# at it - the SQLite DB must survive machine restarts/redeploys.
DATA_DIR = os.environ.get('PORTAL_DATA_DIR') or os.path.join(BASE, 'data')
DB_PATH = os.path.join(DATA_DIR, 'portal.sqlite3')

app = Flask(__name__)


def load_config():
    """Config from env (PaaS: fly secrets) or portal_config.json (self-host).

    Env form:  PORTAL_PASSWORD=...  PORTAL_MACHINE_KEYS='{"CureBox-1":"<key>"}'
    """
    if os.environ.get('PORTAL_PASSWORD'):
        try:
            keys = json.loads(os.environ.get('PORTAL_MACHINE_KEYS') or '{}')
        except Exception:                 # noqa: BLE001 - malformed env JSON
            keys = {}
        return {'password': os.environ['PORTAL_PASSWORD'], 'machine_keys': keys}
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)


def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS machines(
        name TEXT PRIMARY KEY, last_seen REAL, snapshot TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS commands(
        id INTEGER PRIMARY KEY AUTOINCREMENT, machine TEXT, type TEXT,
        payload TEXT, created REAL, delivered REAL, acked REAL)""")
    return conn


# ---------------------------------------------------------------------------
# Auth: one portal password -> session token (in-memory); machines use keys.
# ---------------------------------------------------------------------------
_sessions = set()


def _authed():
    return request.cookies.get('portal_session') in _sessions


@app.route('/login', methods=['POST'])
def login():
    if (request.get_json(silent=True) or {}).get('password') == load_config().get('password'):
        tok = secrets.token_urlsafe(32)
        _sessions.add(tok)
        resp = make_response(jsonify({'ok': True}))
        resp.set_cookie('portal_session', tok, httponly=True, samesite='Lax')
        return resp
    return jsonify({'ok': False, 'message': 'Wrong password'}), 401


def _machine_from_key():
    key = request.headers.get('X-Machine-Key', '')
    for name, k in load_config().get('machine_keys', {}).items():
        if secrets.compare_digest(k, key):
            return name
    return None


# ---------------------------------------------------------------------------
# Machine agent endpoint
# ---------------------------------------------------------------------------
@app.route('/api/agent/sync', methods=['POST'])
def agent_sync():
    name = _machine_from_key()
    if not name:
        return jsonify({'ok': False, 'message': 'bad machine key'}), 401
    d = request.get_json(silent=True) or {}
    conn = db()
    with conn:
        conn.execute("INSERT INTO machines(name, last_seen, snapshot) VALUES(?,?,?) "
                     "ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen, "
                     "snapshot=excluded.snapshot",
                     (name, time.time(), json.dumps(d, ensure_ascii=False)))
        for cid in d.get('ackIds') or []:
            conn.execute("UPDATE commands SET acked=? WHERE id=? AND machine=?",
                         (time.time(), cid, name))
        rows = conn.execute("SELECT id, type, payload FROM commands "
                            "WHERE machine=? AND acked IS NULL ORDER BY id",
                            (name,)).fetchall()
        conn.execute("UPDATE commands SET delivered=? WHERE machine=? AND acked IS NULL",
                     (time.time(), name))
    cmds = [{'id': r['id'], 'type': r['type'],
             'payload': json.loads(r['payload'])} for r in rows]
    return jsonify({'ok': True, 'commands': cmds})


# ---------------------------------------------------------------------------
# Portal API (browser, behind the login)
# ---------------------------------------------------------------------------
@app.route('/api/machines')
def machines_list():
    if not _authed():
        return jsonify({'ok': False}), 401
    conn = db()
    out = []
    for r in conn.execute("SELECT name, last_seen, snapshot FROM machines ORDER BY name"):
        snap = json.loads(r['snapshot'] or '{}')
        pending = conn.execute("SELECT COUNT(*) c FROM commands WHERE machine=? AND acked IS NULL",
                               (r['name'],)).fetchone()['c']
        out.append({'name': r['name'], 'lastSeen': r['last_seen'],
                    'online': (time.time() - (r['last_seen'] or 0)) < 30,
                    'pending': pending,
                    'state': snap.get('state') or {},
                    'programs': snap.get('programs') or [],
                    'prints': snap.get('prints') or [],
                    'cures': snap.get('cures') or []})
    return jsonify(out)


@app.route('/api/machines/<name>/commands', methods=['POST'])
def queue_command(name):
    if not _authed():
        return jsonify({'ok': False}), 401
    d = request.get_json(silent=True) or {}
    if d.get('type') not in ('upsert_program', 'delete_program', 'send_print'):
        return jsonify({'ok': False, 'message': 'unknown command type'}), 400
    conn = db()
    with conn:
        conn.execute("INSERT INTO commands(machine, type, payload, created) VALUES(?,?,?,?)",
                     (name, d['type'], json.dumps(d.get('payload') or {}, ensure_ascii=False),
                      time.time()))
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Portal UI (single page)
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return PAGE


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sCure Cloud</title>
<style>
  /* Light monochrome theme: white ground, black text, black primary buttons;
     green/red kept for online/offline + errors only. */
  :root { --bg:#ffffff; --panel:#ffffff; --line:#e5e5e5; --text:#111111;
          --mut:#6b7280; --acc:#111111; --acc2:#111111; --ok:#16a34a; --err:#dc2626;
          --field:#ffffff; --inset:#fafafa; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.45 "Segoe UI", Arial, sans-serif; }
  header { display:flex; align-items:center; gap:.8rem; padding:.9rem 1.4rem;
           border-bottom:1px solid var(--line); }
  header h1 { font-size:1.05rem; margin:0; letter-spacing:.04em; }
  header .logo { height:42px; display:block; }
  main { max-width:1060px; margin:0 auto; padding:1.2rem 1.4rem 3rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:1rem 1.2rem; margin-bottom:1rem; }
  h2 { font-size:.95rem; color:var(--text); text-transform:uppercase;
       letter-spacing:.08em; margin:0 0 .7rem; }
  table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
  th, td { text-align:left; padding:.45rem .6rem; border-bottom:1px solid var(--line); }
  th { color:var(--mut); font-weight:600; font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }
  input, select, button, textarea { background:var(--field); color:var(--text);
    border:1px solid #d4d4d4; border-radius:7px; padding:.45rem .7rem; font:inherit; }
  input:focus, select:focus, textarea:focus { outline:none; border-color:var(--acc); }
  button { cursor:pointer; }
  button.primary { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:600; }
  button.danger { color:var(--err); }
  .row { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; }
  .pill { display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.78rem; }
  .pill.on { background:rgba(22,163,74,.12); color:var(--ok); }
  .pill.off { background:rgba(220,38,38,.10); color:var(--err); }
  .stat { display:inline-flex; flex-direction:column; margin-right:1.6rem; }
  .stat b { font-size:1.25rem; }
  .stat span { color:var(--mut); font-size:.78rem; }
  #login { max-width:340px; margin:16vh auto; }
  .steps th, .steps td { padding:.3rem .4rem; }
  .steps input, .steps select { width:100%; padding:.3rem .4rem; }
  .msg { color:var(--ok); font-size:.85rem; }
  .msg.err { color:var(--err); }
  .mut { color:var(--mut); }
</style></head><body>
<header><img class="logo" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAABJ4AAAHzCAYAAABhQdfJAAAACXBIWXMAAC4jAAAuIwF4pT92AAAAJXRFWHRTb2Z0d2FyZQBXZWJkYW0gaHR0cDovL3d3dy53ZWJkYW0uY29tFioTSwAAAJB6VFh0UmF3IHByb2ZpbGUgdHlwZSBpcHRjAAB4nD1OMQ4DMQjbecU9ISEODnOnbh3uA1XuIlWq1Kr/H0puiBEW2ICQ+2O/bd/fZ7zep2wX2KQ0KBxHQsQCNPek2WeJbsNoYylPqlXT4GynwTyYsmxnIaZJRBZGvzxjiXHGQiWm2jTUCrcjjtFq7pL0emEy5A+dGSfSFx9NbAAAAyZpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0n77u/JyBpZD0nVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkJz8+Cjx4OnhtcG1ldGEgeG1sbnM6eD0nYWRvYmU6bnM6bWV0YS8nIHg6eG1wdGs9J0ltYWdlOjpFeGlmVG9vbCAxMi43MCc+CjxyZGY6UkRGIHhtbG5zOnJkZj0naHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyc+CgogPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9JycKICB4bWxuczpXZWJkYW09J2h0dHA6Ly93d3cud2ViZGFtLmNvbS9XZWJkYW1OYW1lc3BhY2UvJz4KICA8V2ViZGFtOkN1c3RvbUZpZWxkMTU+MjAyMyBOZXcgQnJhbmRpbmc8L1dlYmRhbTpDdXN0b21GaWVsZDE1PgogIDxXZWJkYW06Q3VzdG9tRmllbGQ0PkFjdGl2ZTwvV2ViZGFtOkN1c3RvbUZpZWxkND4KICA8V2ViZGFtOkN1c3RvbUZpZWxkNj5HbG9iYWw8L1dlYmRhbTpDdXN0b21GaWVsZDY+CiA8L3JkZjpEZXNjcmlwdGlvbj4KCiA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0nJwogIHhtbG5zOmRjPSdodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyc+CiAgPGRjOnN1YmplY3Q+CiAgIDxyZGY6QmFnPgogICAgPHJkZjpsaT5Mb2dvPC9yZGY6bGk+CiAgICA8cmRmOmxp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" alt="Stratasys"><h1>sCure Cloud</h1>
  <span id="who" class="mut" style="margin-left:auto"></span></header>
<main id="app"></main>
<script>
const $ = s => document.querySelector(s);
let MACHINES = [];
let editing = false;   // an editor is open: auto-refresh must not wipe it

// True while the user is interacting with any form on the page — the
// periodic refresh skips re-rendering so it never eats typed input.
function userBusy() {
  if (editing) return true;
  const a = document.activeElement;
  if (a && ['INPUT', 'SELECT', 'TEXTAREA'].includes(a.tagName)) return true;
  // half-filled send-print form counts as busy too
  return [...document.querySelectorAll('[id^="job-"], [id^="printer-"]')]
    .some(el => el.value && el.value.trim() !== '');
}

async function api(path, opts) {
  const r = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}}, opts));
  if (r.status === 401) { renderLogin(); throw new Error('auth'); }
  return r.json();
}

function renderLogin(msg) {
  $('#app').innerHTML = `<div class="card" id="login"><h2>Sign in</h2>
    <div class="row"><input id="pw" type="password" placeholder="Portal password" style="flex:1">
    <button class="primary" id="go">Sign in</button></div>
    <p class="msg err">${msg||''}</p></div>`;
  $('#go').onclick = doLogin;
  $('#pw').onkeydown = e => { if (e.key === 'Enter') doLogin(); };
}
async function doLogin() {
  const r = await fetch('/login', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({password: $('#pw').value})});
  if (r.ok) load(); else renderLogin('Wrong password');
}

function fmtAgo(t) {
  if (!t) return 'never';
  const s = Math.round(Date.now()/1000 - t);
  return s < 60 ? s + 's ago' : s < 3600 ? Math.round(s/60) + 'm ago' : Math.round(s/3600) + 'h ago';
}

async function load(force) {
  if (!force && userBusy()) return;   // never re-render under the user's hands
  try { MACHINES = await api('/api/machines'); } catch { return; }
  if (!force && userBusy()) return;
  render();
}

// Which CureBox is shown: 'all' or a machine name (kept across visits).
let SELECTED = localStorage.getItem('scure-curebox') || 'all';
// Live filter for work programs + recent prints (name/material/printer/status).
let SEARCH = '';

function render() {
  if (!MACHINES.length) {
    $('#app').innerHTML = `<div class="card"><h2>Machines</h2>
      <p class="mut">No machine has synced yet. Configure <code>server/data/cloud.json</code>
      on the machine with this portal's URL and its machine key.</p></div>`;
    return;
  }
  if (SELECTED !== 'all' && !MACHINES.some(m => m.name === SELECTED)) SELECTED = 'all';
  const tabs = `<div class="row" style="margin-bottom:1rem">
       <span class="mut" style="font-size:.85rem">CureBox:</span>
       <button class="${SELECTED==='all'?'primary':''}" data-tab="all">All</button>
       ${MACHINES.map(m => `<button class="${SELECTED===m.name?'primary':''}"
          data-tab="${m.name}">${m.name} ${m.online?'●':'○'}</button>`).join('')}
       <input id="search" placeholder="Search programs / prints..." value="${SEARCH.replace(/"/g,'&quot;')}"
              style="margin-left:auto;min-width:220px">
     </div>`;
  const shown = SELECTED === 'all' ? MACHINES : MACHINES.filter(m => m.name === SELECTED);
  $('#app').innerHTML = tabs + shown.map(m => machineCard(m, MACHINES.indexOf(m))).join('');
  shown.forEach(m => wireCard(m, MACHINES.indexOf(m)));
  [...document.querySelectorAll('[data-tab]')].forEach(b => b.onclick = () => {
    SELECTED = b.dataset.tab;
    localStorage.setItem('scure-curebox', SELECTED);
    render();
  });
  // Re-render on every keystroke, keeping focus + caret in the search box.
  $('#search').oninput = e => {
    SEARCH = e.target.value;
    render();
    const s = $('#search');
    s.focus();
    s.setSelectionRange(s.value.length, s.value.length);
  };
}

function machineCard(m, i) {
  const st = m.state || {};
  const c = st.counters || {};
  const q = SEARCH.trim().toLowerCase();
  const progRows = (m.programs||[])
    .filter(p => !q || (p.name||'').toLowerCase().includes(q))
    .map(p => `
    <tr><td>${p.name}</td><td>${(p.steps||[]).length} steps</td>
        <td>${p.totalDuration ?? '–'} min</td>
        <td><button data-edit="${i}:${p.id}">Edit</button>
            <button class="danger" data-del="${i}:${p.id}">Delete</button></td></tr>`).join('');
  const printRows = (m.prints||[])
    .filter(p => !q || [p.printName, p.materialName, p.printerName, p.status]
                       .some(v => (v||'').toLowerCase().includes(q)))
    .slice(0,5).map(p => `
    <tr><td>${p.printName||''}</td><td>${p.materialName||''}</td>
        <td>${p.printerName||''}</td><td>${p.status||''}</td></tr>`).join('');
  return `<div class="card">
    <div class="row" style="justify-content:space-between">
      <h2 style="margin:0">${m.name}
        <span class="pill ${m.online?'on':'off'}">${m.online?'online':'offline'}</span>
        <span class="mut" style="font-weight:400;text-transform:none">last sync ${fmtAgo(m.lastSeen)}${m.pending?` · ${m.pending} pending`:''}</span>
      </h2>
      <div>
        <span class="stat"><b>${st.chamberTemp != null ? (+st.chamberTemp).toFixed(1) : '–'}°C</b><span>chamber</span></span>
        <span class="stat"><b>${c.led405 ?? '–'}h</b><span>LED 405</span></span>
        <span class="stat"><b>${c.heater ?? '–'}h</b><span>heater</span></span>
      </div>
    </div>

    <h2>Work Programs</h2>
    <table><tr><th>Name</th><th>Steps</th><th>Duration</th><th></th></tr>${progRows||'<tr><td colspan=4 class="mut">none</td></tr>'}</table>
    <p><button class="primary" data-new="${i}">+ New Program</button></p>
    <div id="editor-${i}"></div>

    <h2>Send Simulated Print</h2>
    <div class="row">
      <input id="job-${i}" placeholder="Job name (e.g. Job 2 - Penrose)" style="flex:2">
      <input id="printer-${i}" placeholder="Printer (e.g. TZ)" style="flex:1">
      <select id="mat-${i}">${(m.programs||[]).map(p=>`<option>${p.name}</option>`).join('')}</select>
      <button class="primary" data-send="${i}">Send to machine</button>
    </div>
    <p class="msg" id="msg-${i}"></p>

    <h2>Recent Prints On Machine</h2>
    <table><tr><th>Job</th><th>Material</th><th>Printer</th><th>Status</th></tr>${printRows||'<tr><td colspan=4 class="mut">none</td></tr>'}</table>
  </div>`;
}

// Per-process field rules — mirror the machine UI's step editor (StepModal):
//   Drying/Heating   temp 30-80°C, time 1-120 min
//   Cure/Bleacher    temp 30-80°C, time 1-120 (Bleaching 1-720), UV 10-100%,
//                    timer start + UV start modes
//   Cooling          target temp 30-75°C, cooling mode; no time
//   Nitrogen         no fields (auto purge)
const PROCESSES = ['Drying','Heating','Cure','Bleacher','Cooling','Nitrogen'];
const PROC_LABEL = {Cure:'Cure (405nm)', Bleacher:'Bleaching (450nm)'};
function stepRow(s, j) {
  const p = s.process;
  const uvish = p === 'Cure' || p === 'Bleacher';
  const temp = p === 'Nitrogen' ? '<span class="mut">–</span>'
    : `<input class="st" type="number" min="30" max="${p==='Cooling'?75:80}"
         value="${s.temperature ?? (p==='Cooling'?30:40)}" placeholder="°C">`;
  const time = (p === 'Cooling' || p === 'Nitrogen') ? '<span class="mut">–</span>'
    : `<input class="sm" type="number" min="1" max="${p==='Bleacher'?720:120}"
         value="${s.time ?? 10}" placeholder="min">`;
  const uv = uvish
    ? `<input class="su" type="number" min="10" max="100" value="${s.uvIntensity ?? 30}" placeholder="%">`
    : '<span class="mut">–</span>';
  const opts = p === 'Cooling'
    ? `<select class="sc">${['fast','medium','slow'].map(m =>
        `<option value="${m}" ${m===(s.coolingMode||'medium')?'selected':''}>${m[0].toUpperCase()+m.slice(1)} cooling</option>`).join('')}</select>`
    : uvish
    ? `<select class="stm" title="Timer start">
         <option value="on-target" ${((s.timerMode||'on-target')==='on-target')?'selected':''}>Timer: at temperature</option>
         <option value="on-ramp" ${s.timerMode==='on-ramp'?'selected':''}>Timer: on ramp start</option>
       </select>
       <select class="ssm" title="UV start" style="margin-top:.25rem">
         <option value="at-target" ${((s.uvStartMode||'at-target')==='at-target')?'selected':''}>UV: at temperature</option>
         <option value="at-start" ${s.uvStartMode==='at-start'?'selected':''}>UV: on ramp start</option>
       </select>`
    : p === 'Nitrogen' ? '<span class="mut">auto purge</span>'
    : '<span class="mut">–</span>';
  return `<tr>
    <td>${j+1}</td>
    <td><select class="sp">${PROCESSES.map(q =>
      `<option value="${q}" ${q===p?'selected':''}>${PROC_LABEL[q]||q}</option>`).join('')}</select></td>
    <td>${temp}</td><td>${time}</td><td>${uv}</td><td>${opts}</td>
    <td><button class="danger sx">✕</button></td></tr>`;
}

// Read a step row back into a step object (no validation — see stepErrors).
// Field lookups are null-safe: on a process switch the row still holds the
// PREVIOUS process's inputs, so the new process's fields may not exist yet.
function readRow(r, j) {
  const num = c => { const el = r.querySelector(c);
                     return el && el.value !== '' ? +el.value : null; };
  const sel = (c, d) => { const el = r.querySelector(c); return el ? el.value : d; };
  const p = r.querySelector('.sp').value;
  const st = { step: j+1, process: p, temperature: null, intensity: null, time: 0 };
  if (p !== 'Nitrogen') st.temperature = num('.st');
  if (p !== 'Cooling' && p !== 'Nitrogen') st.time = num('.sm');
  if (p === 'Cooling') st.coolingMode = sel('.sc', 'medium');
  if (p === 'Cure' || p === 'Bleacher') {
    st.uvIntensity = num('.su');
    st.timerMode = sel('.stm', 'on-target');
    st.uvStartMode = sel('.ssm', 'at-target');
  }
  return st;
}

// Same limits + sequence rules the machine UI enforces (MaterialContext).
function stepErrors(steps) {
  const errs = [];
  let n2 = 0, needsVent = false, lastTemp = null;
  steps.forEach((s, i) => {
    const n = i + 1, prev = i > 0 ? steps[i-1] : null;
    if (s.process !== 'Nitrogen') {
      const [tMin, tMax] = s.process === 'Cooling' ? [30, 75] : [30, 80];
      if (s.temperature == null || s.temperature < tMin || s.temperature > tMax)
        errs.push(`Step ${n}: temperature must be ${tMin}-${tMax}°C`);
    }
    if (s.process !== 'Cooling' && s.process !== 'Nitrogen') {
      const tMax = s.process === 'Bleacher' ? 720 : 120;
      if (!s.time || s.time < 1 || s.time > tMax)
        errs.push(`Step ${n}: time must be 1-${tMax} min`);
    }
    if (s.process === 'Cure' || s.process === 'Bleacher') {
      if (s.uvIntensity == null || s.uvIntensity < 10 || s.uvIntensity > 100)
        errs.push(`Step ${n}: UV intensity must be 10-100% (LEDs stay dark below 10%)`);
    }
    if (s.process === 'Nitrogen' && ++n2 > 2)
      errs.push(`Step ${n}: a maximum of 2 nitrogen purge steps is allowed`);
    if (prev && prev.process === 'Nitrogen' &&
        s.process !== 'Cure' && s.process !== 'Bleacher')
      errs.push(`Step ${n}: after nitrogen, only Cure or Bleaching is allowed`);
    if (prev && (prev.process === 'Cure' || prev.process === 'Bleacher') &&
        i > 1 && steps[i-2].process === 'Nitrogen' && s.process !== 'Cooling')
      errs.push(`Step ${n}: only Cooling is allowed after the Cure/Bleaching step that follows the N₂ purge`);
    if (s.process === 'Nitrogen') needsVent = true;
    if (needsVent && s.process === 'Cooling') needsVent = false;
    if (s.process !== 'Cooling' && s.process !== 'Nitrogen' && s.temperature != null) {
      if (lastTemp !== null && s.temperature < lastTemp)
        errs.push(`Step ${n}: temperature (${s.temperature}°C) cannot be lower than the previous step (${lastTemp}°C) without a Cooling step`);
      lastTemp = s.temperature;
    }
    if (s.process === 'Cooling') {
      if (lastTemp !== null && s.temperature != null && s.temperature > lastTemp - 5)
        errs.push(`Step ${n}: cooling target (${s.temperature}°C) must be at least 5°C below the previous step (${lastTemp}°C)`);
      lastTemp = null;
    }
  });
  if (needsVent) errs.push('Nitrogen must be vented — add a Cooling step after the N₂ purge');
  if (steps.some(s => s.process === 'Nitrogen')) {
    let after = false, ok = false;
    for (const s of steps) {
      if (s.process === 'Nitrogen') after = true;
      if (after && (s.process === 'Cure' || s.process === 'Bleacher')) { ok = true; break; }
    }
    if (!ok) errs.push('Add a Cure or Bleaching step after the N₂ purge');
  }
  return errs;
}

function openEditor(i, prog) {
  editing = true;
  const el = $('#editor-' + i);
  const steps = prog ? JSON.parse(JSON.stringify(prog.steps||[])) : [{process:'Drying',temperature:45,time:10}];
  el.dataset.progId = prog ? prog.id : '';
  el.innerHTML = `<div class="card" style="background:var(--inset)">
    <div class="row"><input id="pname-${i}" placeholder="Program name" value="${prog?prog.name:''}" style="flex:1"></div>
    <table class="steps" id="ptable-${i}" style="margin:.6rem 0">
      <tr><th>#</th><th>Process</th><th>Temp °C</th><th>Time min</th><th>UV %</th><th>Options</th><th></th></tr>
      ${steps.map(stepRow).join('')}
    </table>
    <div class="row">
      <button id="padd-${i}">+ Step</button>
      <button class="primary" id="psave-${i}">Save to machine</button>
      <button id="pcancel-${i}">Cancel</button>
      <span class="msg" id="pmsg-${i}"></span>
    </div></div>`;
  $('#padd-'+i).onclick = () => {
    $('#ptable-'+i).insertAdjacentHTML('beforeend',
      stepRow({process:'Cure'}, $('#ptable-'+i).rows.length-1));
    wireStepRows(i);
  };
  $('#pcancel-'+i).onclick = () => { el.innerHTML=''; editing = false; };
  $('#psave-'+i).onclick = () => saveProgram(i, prog);
  wireStepRows(i);
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('#pname-'+i).focus();
}
function wireStepRows(i) {
  const rows = [...document.querySelectorAll(`#ptable-${i} tr`)].slice(1);
  rows.forEach(r => {
    r.querySelector('.sx').onclick = () => {
      r.remove();
      renumberSteps(i);
    };
    // Switching the process swaps the row to that process's field set,
    // carrying the temperature over like the machine UI does.
    r.querySelector('.sp').onchange = e => {
      const j = r.rowIndex - 1;   // header row is 0
      const cur = readRow(r, j);
      cur.process = e.target.value;
      if (cur.process !== 'Cooling' && cur.process !== 'Nitrogen' && !cur.time) cur.time = 10;
      r.outerHTML = stepRow(cur, j);
      wireStepRows(i);
    };
  });
}
function renumberSteps(i) {
  [...document.querySelectorAll(`#ptable-${i} tr`)].slice(1)
    .forEach((r, j) => { r.cells[0].textContent = j + 1; });
}

async function saveProgram(i, prog) {
  const name = $('#pname-'+i).value.trim();
  if (!name) { $('#pmsg-'+i).textContent = 'Name required'; return; }
  const rows = [...document.querySelectorAll(`#ptable-${i} tr`)].slice(1);
  if (!rows.length) { $('#pmsg-'+i).textContent = 'Add at least one step'; return; }
  const steps = rows.map(readRow);
  const errs = stepErrors(steps);
  const msg = $('#pmsg-'+i);
  if (errs.length) {
    msg.classList.add('err');
    msg.innerHTML = errs.slice(0, 4).join('<br>') +
      (errs.length > 4 ? `<br>…and ${errs.length - 4} more` : '');
    return;
  }
  msg.classList.remove('err');
  const total = steps.reduce((a, s) => a + (s.time||0), 0);
  const payload = { id: prog ? prog.id : 'cloud-' + Date.now(), name, steps,
                    totalDuration: total, createdAt: new Date().toISOString(), isPreset: false };
  await api(`/api/machines/${MACHINES[i].name}/commands`,
            {method:'POST', body: JSON.stringify({type:'upsert_program', payload})});
  $('#pmsg-'+i).textContent = 'Saved — the machine applies it on its next sync (≤10 s)';
  setTimeout(() => { const el = $('#editor-'+i); if (el) el.innerHTML = '';
                     editing = false; load(true); }, 1600);
}

function wireCard(m, i) {
  [...document.querySelectorAll(`[data-edit^="${i}:"]`)].forEach(b => b.onclick = () => {
    const id = b.dataset.edit.split(':').slice(1).join(':');
    openEditor(i, (m.programs||[]).find(p => String(p.id) === id));
  });
  [...document.querySelectorAll(`[data-del^="${i}:"]`)].forEach(b => b.onclick = async () => {
    const id = b.dataset.del.split(':').slice(1).join(':');
    await api(`/api/machines/${m.name}/commands`,
              {method:'POST', body: JSON.stringify({type:'delete_program', payload:{id}})});
    load();
  });
  const nb = document.querySelector(`[data-new="${i}"]`);
  if (nb) nb.onclick = () => openEditor(i, null);
  const sb = document.querySelector(`[data-send="${i}"]`);
  if (sb) sb.onclick = async () => {
    const payload = {
      printName: $('#job-'+i).value || 'Job',
      printerName: $('#printer-'+i).value || 'CLOUD',
      materialName: $('#mat-'+i).value,
    };
    await api(`/api/machines/${m.name}/commands`,
              {method:'POST', body: JSON.stringify({type:'send_print', payload})});
    $('#job-'+i).value = '';
    $('#printer-'+i).value = '';
    $('#msg-'+i).textContent = 'Print sent — it appears on the machine within ~10 s';
  };
}

load();
setInterval(load, 10000);
</script></body></html>"""


if __name__ == '__main__':
    if not os.environ.get('PORTAL_PASSWORD') and not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'password': secrets.token_urlsafe(9),
                       'machine_keys': {'CureBox-1': secrets.token_urlsafe(24)}}, f, indent=2)
        print(f"[PORTAL] created {CONFIG_PATH} - set your password / machine keys there")
    cfg = load_config()
    print(f"[PORTAL] machines configured: {', '.join(cfg.get('machine_keys', {}) or ['-'])}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
