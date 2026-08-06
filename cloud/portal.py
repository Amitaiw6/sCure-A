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
DB_PATH = os.path.join(BASE, 'data', 'portal.sqlite3')

app = Flask(__name__)


def load_config():
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
  :root { --bg:#0b0e16; --panel:#131828; --line:#232a42; --text:#e8eaf2;
          --mut:#8a93a8; --acc:#7c6cf0; --acc2:#a99ef7; --ok:#3ecf8e; --err:#e5484d; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.45 "Segoe UI", Arial, sans-serif; }
  header { display:flex; align-items:center; gap:.8rem; padding:.9rem 1.4rem;
           border-bottom:1px solid var(--line); }
  header h1 { font-size:1.05rem; margin:0; letter-spacing:.04em; }
  header .dot { width:.55rem; height:.55rem; border-radius:50%; background:var(--acc); }
  main { max-width:1060px; margin:0 auto; padding:1.2rem 1.4rem 3rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:1rem 1.2rem; margin-bottom:1rem; }
  h2 { font-size:.95rem; color:var(--acc2); text-transform:uppercase;
       letter-spacing:.08em; margin:0 0 .7rem; }
  table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
  th, td { text-align:left; padding:.45rem .6rem; border-bottom:1px solid var(--line); }
  th { color:var(--mut); font-weight:600; font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }
  input, select, button, textarea { background:#0e1220; color:var(--text);
    border:1px solid var(--line); border-radius:7px; padding:.45rem .7rem; font:inherit; }
  input:focus, select:focus, textarea:focus { outline:none; border-color:var(--acc); }
  button { cursor:pointer; }
  button.primary { background:var(--acc); border-color:var(--acc); color:#fff; font-weight:600; }
  button.danger { color:var(--err); }
  .row { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; }
  .pill { display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.78rem; }
  .pill.on { background:rgba(62,207,142,.15); color:var(--ok); }
  .pill.off { background:rgba(229,72,77,.15); color:var(--err); }
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
<header><div class="dot"></div><h1>sCure Cloud</h1>
  <span id="who" class="mut" style="margin-left:auto"></span></header>
<main id="app"></main>
<script>
const $ = s => document.querySelector(s);
let MACHINES = [];

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

async function load() {
  try { MACHINES = await api('/api/machines'); } catch { return; }
  render();
}

function render() {
  if (!MACHINES.length) {
    $('#app').innerHTML = `<div class="card"><h2>Machines</h2>
      <p class="mut">No machine has synced yet. Configure <code>server/data/cloud.json</code>
      on the machine with this portal's URL and its machine key.</p></div>`;
    return;
  }
  $('#app').innerHTML = MACHINES.map((m, i) => machineCard(m, i)).join('');
  MACHINES.forEach((m, i) => wireCard(m, i));
}

function machineCard(m, i) {
  const st = m.state || {};
  const c = st.counters || {};
  const progRows = (m.programs||[]).map(p => `
    <tr><td>${p.name}</td><td>${(p.steps||[]).length} steps</td>
        <td>${p.totalDuration ?? '–'} min</td>
        <td><button data-edit="${i}:${p.id}">Edit</button>
            <button class="danger" data-del="${i}:${p.id}">Delete</button></td></tr>`).join('');
  const printRows = (m.prints||[]).slice(0,5).map(p => `
    <tr><td>${p.printName||''}</td><td>${p.materialName||''}</td>
        <td>${p.printerName||''}</td><td>${p.status||''}</td></tr>`).join('');
  return `<div class="card">
    <div class="row" style="justify-content:space-between">
      <h2 style="margin:0">${m.name}
        <span class="pill ${m.online?'on':'off'}">${m.online?'online':'offline'}</span>
        <span class="mut" style="font-weight:400;text-transform:none">last sync ${fmtAgo(m.lastSeen)}${m.pending?` · ${m.pending} pending`:''}</span>
      </h2>
      <div>
        <span class="stat"><b>${st.chamberTemp ?? '–'}°C</b><span>chamber</span></span>
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

const PROCESSES = ['Drying','Heating','Cure','Bleacher','Cooling','Nitrogen'];
function stepRow(s, j) {
  return `<tr>
    <td>${j+1}</td>
    <td><select class="sp">${PROCESSES.map(p=>`<option ${p===s.process?'selected':''}>${p}</option>`).join('')}</select></td>
    <td><input class="st" type="number" value="${s.temperature ?? ''}" placeholder="°C"></td>
    <td><input class="sm" type="number" value="${s.time ?? ''}" placeholder="min"></td>
    <td><input class="su" type="number" value="${s.uvIntensity ?? ''}" placeholder="%"></td>
    <td><button class="danger sx">✕</button></td></tr>`;
}

function openEditor(i, prog) {
  const el = $('#editor-' + i);
  const steps = prog ? JSON.parse(JSON.stringify(prog.steps||[])) : [{process:'Drying',temperature:45,time:10}];
  el.dataset.progId = prog ? prog.id : '';
  el.innerHTML = `<div class="card" style="background:#0e1220">
    <div class="row"><input id="pname-${i}" placeholder="Program name" value="${prog?prog.name:''}" style="flex:1"></div>
    <table class="steps" id="ptable-${i}" style="margin:.6rem 0">
      <tr><th>#</th><th>Process</th><th>Temp °C</th><th>Time min</th><th>UV %</th><th></th></tr>
      ${steps.map(stepRow).join('')}
    </table>
    <div class="row">
      <button id="padd-${i}">+ Step</button>
      <button class="primary" id="psave-${i}">Save to machine</button>
      <button id="pcancel-${i}">Cancel</button>
      <span class="msg" id="pmsg-${i}"></span>
    </div></div>`;
  $('#padd-'+i).onclick = () => {
    $('#ptable-'+i).insertAdjacentHTML('beforeend', stepRow({process:'Cure'}, $('#ptable-'+i).rows.length-1));
    wireStepDeletes(i);
  };
  $('#pcancel-'+i).onclick = () => { el.innerHTML=''; };
  $('#psave-'+i).onclick = () => saveProgram(i, prog);
  wireStepDeletes(i);
}
function wireStepDeletes(i) {
  [...document.querySelectorAll(`#ptable-${i} .sx`)].forEach(b =>
    b.onclick = () => { b.closest('tr').remove(); });
}

async function saveProgram(i, prog) {
  const name = $('#pname-'+i).value.trim();
  if (!name) { $('#pmsg-'+i).textContent = 'Name required'; return; }
  const rows = [...document.querySelectorAll(`#ptable-${i} tr`)].slice(1);
  const steps = rows.map((r, j) => {
    const v = c => { const x = r.querySelector(c).value; return x === '' ? null : +x; };
    const st = { step: j+1, process: r.querySelector('.sp').value,
                 temperature: v('.st'), time: v('.sm') ?? 0, intensity: null };
    const uv = v('.su');
    if (uv != null) { st.uvIntensity = uv; st.timerMode = 'on-target'; st.uvStartMode = 'at-target'; }
    if (st.process === 'Cooling') st.coolingMode = 'medium';
    return st;
  });
  const total = steps.reduce((a, s) => a + (s.time||0), 0);
  const payload = { id: prog ? prog.id : 'cloud-' + Date.now(), name, steps,
                    totalDuration: total, createdAt: new Date().toISOString(), isPreset: false };
  await api(`/api/machines/${MACHINES[i].name}/commands`,
            {method:'POST', body: JSON.stringify({type:'upsert_program', payload})});
  $('#pmsg-'+i).textContent = 'Queued — the machine applies it on its next sync (≤10 s)';
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
    $('#msg-'+i).textContent = 'Print queued — it appears on the machine within ~10 s';
  };
}

load();
setInterval(load, 10000);
</script></body></html>"""


if __name__ == '__main__':
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({'password': secrets.token_urlsafe(9),
                       'machine_keys': {'CureBox-1': secrets.token_urlsafe(24)}}, f, indent=2)
        print(f"[PORTAL] created {CONFIG_PATH} - set your password / machine keys there")
    cfg = load_config()
    print(f"[PORTAL] machines configured: {', '.join(cfg.get('machine_keys', {}) or ['-'])}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
