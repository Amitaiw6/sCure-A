#!/usr/bin/env python3
"""Stratasys Factory Provisioning Tool — manufacturing UI.

    python ui.py --station ST-01 --server http://mfg:8440 --trust trust/ [--fake] [--signed-eeprom DIR]

Opens http://127.0.0.1:8450 — a single-screen, touch-friendly station UI:
current step + progress, image catalogue (Latest Production / Local /
status / signature), module detection, serial, device ID, image and
software versions, secure boot, encryption, license and final test
status, OFFLINE MODE banner, Provisioning Successful summary, and the
authorised "Generate New Serial Number" action.

The UI never runs provisioning logic itself: it starts a ProvisioningRun in
a background thread and polls its journal. One run at a time per station.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stratasys_appliance import crypto, serials  # noqa: E402
import provision  # noqa: E402
from image_catalog import ImageCatalog, CatalogError  # noqa: E402
from rpiboot import Rpiboot, FakeRpiboot, detect_usb_module  # noqa: E402

app = Flask(__name__)
CFG: provision.Config | None = None
FAKE = False
STATE = {"run": None, "thread": None, "events": [], "progress": {}, "catalog": None, "lastSerial": None,
         "history": []}
LOCK = threading.Lock()


def _catalog_probe():
    """What the station knows about images right now (no flashing)."""
    try:
        cat = ImageCatalog(CFG.server_url, crypto.TrustStore.from_dir(CFG.trust_dir),
                           CFG.workdir / "image-cache", CFG.product, CFG.channel)
        res = cat.resolve(None)
        local = cat.newest_cached()
        return {"ok": True, "online": res.online, "latestProduction": res.version, "buildId": res.build_id,
                "localVersion": local["payload"]["imageVersion"] if local else None,
                "versions": res.server_versions, "status": res.status, "appVersion": res.payload.get("appVersion")}
    except CatalogError as e:
        return {"ok": False, "online": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "online": False, "error": f"{type(e).__name__}: {e}"}


def _snapshot():
    with LOCK:
        run = STATE["run"]
        st = run.state if run else None
        running = bool(STATE["thread"] and STATE["thread"].is_alive())
        out = {"ok": True, "station": CFG.station_id, "fake": FAKE, "running": running,
               "catalog": STATE["catalog"], "events": STATE["events"][-60:], "progress": STATE["progress"],
               "lastSerial": STATE["lastSerial"], "history": STATE["history"][-10:],
               "defaultOperator": getpass.getuser(),
               "usbModule": ({"vid": "0a5c", "pid": "2712", "description": "BCM2712 (CM5 / Pi 5) — simulated", "mode": "rpiboot"}
                             if FAKE else (m.__dict__ if (m := detect_usb_module()) else None)),
               "steps": [s.value for s in provision.ORDER]}
        if st:
            out["run"] = {"runId": st.run_id, "step": st.step.value, "completed": st.completed, "result": st.result,
                          "error": st.error, "online": st.online, "serial": st.serial, "previousSerial": st.previous_serial,
                          "deviceId": st.device_id, "image": {k: v for k, v in st.image.items() if k != "path"},
                          "module": st.module, "provisional": st.provisional,
                          "license": (st.license or {}).get("payload", {}).get("features"),
                          "secureBoot": st.module.get("secure_boot"),
                          "encrypted": "ENCRYPT_DATA" in st.completed,
                          "policy": "APPLY_POLICY" in st.completed,
                          "selfTest": "VERIFY_MACHINE" in st.completed,
                          "softwareOk": "VERIFY_SOFTWARE" in st.completed}
        return out


def _start(operator: str, previous_serial: str | None):
    with LOCK:
        if STATE["thread"] and STATE["thread"].is_alive():
            return False, "a provisioning run is already in progress"
        STATE["events"], STATE["progress"] = [], {}
        cfg = provision.Config(**{**CFG.__dict__, "operator": operator})

        def on_event(event, detail):
            with LOCK:
                if event in ("download", "flash"):
                    STATE["progress"][event] = detail
                else:
                    STATE["events"].append({"ts": detail.get("ts"), "step": detail.get("step"), "event": event,
                                            **{k: v for k, v in detail.items() if k not in ("ts", "step", "event")}})

        if FAKE:
            from tests_support import FakeDeviceAgent
            run = provision.ProvisioningRun(cfg, FakeRpiboot(), FakeDeviceAgent(crypto.TrustStore.from_dir(cfg.trust_dir)),
                                            on_event=on_event)
        else:
            run = provision.ProvisioningRun(cfg, Rpiboot(), provision.DeviceAgent(), on_event=on_event)
        run.state.previous_serial = previous_serial
        STATE["run"] = run

        def work():
            st = run.run()
            with LOCK:
                if st.serial:
                    STATE["lastSerial"] = st.serial
                STATE["history"].append({"serial": st.serial, "result": st.result, "online": st.online,
                                         "imageVersion": st.image.get("version"), "previousSerial": st.previous_serial})
                STATE["catalog"] = _catalog_probe()

        t = threading.Thread(target=work, daemon=True)
        STATE["thread"] = t
        t.start()
        return True, None


@app.get("/api/state")
def api_state():
    return jsonify(_snapshot())


@app.post("/api/catalog/refresh")
def api_catalog():
    c = _catalog_probe()
    with LOCK:
        STATE["catalog"] = c
    return jsonify(c)


@app.post("/api/start")
def api_start():
    d = request.get_json(silent=True) or {}
    op = (d.get("operator") or "").strip()
    if not op:
        return jsonify({"ok": False, "error": "operator name required"}), 400
    ok, why = _start(op, None)
    return jsonify({"ok": ok, "error": why})


@app.post("/api/new-serial")
def api_new_serial():
    """Authorised 'Generate New Serial Number': provisions the connected
    unit with the NEXT serial from the central counter, recording the
    previous one. Never accepts a typed serial."""
    d = request.get_json(silent=True) or {}
    op = (d.get("operator") or "").strip()
    prev = (d.get("previousSerial") or "").strip().upper()
    if not op:
        return jsonify({"ok": False, "error": "operator name required"}), 400
    if not serials.is_valid(prev):
        return jsonify({"ok": False, "error": "previous serial must be the unit's current serial (SC000000)"}), 400
    if d.get("role") not in ("factory", "service"):
        return jsonify({"ok": False, "error": "only Factory or Service users may reassign a serial"}), 403
    ok, why = _start(op, prev)
    return jsonify({"ok": ok, "error": why})


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Stratasys Factory Provisioning</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1418;--card:#171f26;--line:#2a353f;--ink:#e6ebf0;--mute:#93a4b3;--acc:#3fb8ba;--ok:#5cbf86;--warn:#d9a93a;--bad:#e06a60;--amber:#f5b942}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 22px;border-bottom:1px solid var(--line);background:#121920}
header h1{font-size:18px;margin:0;letter-spacing:.02em}header .st{font-family:Consolas,monospace;color:var(--mute);font-size:12px}
.banner{display:none;background:#5a3d05;color:#ffd98a;padding:10px 22px;font-weight:600}.banner.on{display:block}
main{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:14px;padding:16px 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.card h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin:0 0 10px;font-weight:600}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;font-size:14px}.kv div:nth-child(odd){color:var(--mute)}
.kv b{font-family:Consolas,monospace;font-weight:500}
.steps{list-style:none;margin:0;padding:0;display:grid;gap:4px}.steps li{display:flex;gap:10px;align-items:center;padding:5px 8px;border-radius:5px;font-size:13px;font-family:Consolas,monospace}
.steps li .dot{width:10px;height:10px;border-radius:50%;background:#3a4650;flex:none}.steps li.done .dot{background:var(--ok)}.steps li.now{background:#1e2a33}.steps li.now .dot{background:var(--amber);box-shadow:0 0 0 4px rgba(245,185,66,.2)}.steps li.fail .dot{background:var(--bad)}
.bar{height:8px;background:#26313a;border-radius:4px;overflow:hidden;margin:6px 0 10px}.bar i{display:block;height:100%;background:var(--acc);width:0;transition:width .3s}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.04em}.ok{background:#173d2a;color:var(--ok)}.bad{background:#4a1f1b;color:var(--bad)}.warn{background:#4a3a12;color:var(--warn)}.mute{background:#26313a;color:var(--mute)}
button{background:var(--acc);color:#04191a;border:0;border-radius:7px;padding:12px 18px;font-size:15px;font-weight:700;cursor:pointer}button.sec{background:#26313a;color:var(--ink)}button:disabled{opacity:.4;cursor:not-allowed}
input{background:#0f1418;border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:10px 12px;font-size:15px;width:100%}
.row{display:flex;gap:10px;align-items:center;margin-top:10px}
.log{font-family:Consolas,monospace;font-size:12px;max-height:230px;overflow:auto;background:#0f1418;border:1px solid var(--line);border-radius:6px;padding:8px 10px}.log div{white-space:nowrap}.log .e{color:var(--mute)}
.hint{font-size:12px;color:var(--mute);margin-top:6px}
.success{grid-column:1/-1;display:none;background:#0f2a1f;border:1px solid #1f5a3d;border-radius:8px;padding:18px 22px}.success.on{display:block}.success h3{margin:0 0 8px;color:var(--ok);font-size:22px}
.success .big{font-family:Consolas,monospace;font-size:26px;font-weight:700}
.failed{grid-column:1/-1;display:none;background:#2e1512;border:1px solid #6b2a24;border-radius:8px;padding:16px 22px}.failed.on{display:block}
.wide{grid-column:1/-1}
@media(max-width:1000px){main{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Stratasys Factory Provisioning Tool</h1><div class="st"><span id="usb" class="pill mute">CM5: checking USB…</span> &nbsp; Station <span id="station">—</span> · <span id="mode"></span></div></header>
<div class="banner" id="offline">OFFLINE MODE — Unable to verify whether a newer Production Image is available. <span id="offlineImg"></span></div>
<main>
<section class="card"><h2>Provisioning</h2>
 <ul class="steps" id="steps"></ul>
 <div id="progWrap" style="display:none"><div style="font-size:12px;color:var(--mute)" id="progLabel"></div><div class="bar"><i id="prog"></i></div></div>
 <div class="row"><input id="operator" placeholder="Operator name (required)" autocomplete="off"></div>
 <div class="row"><button id="start">Start Provisioning</button><button class="sec" id="refresh">Check for newer image</button></div>
 <div id="err" style="display:none;margin-top:10px;padding:10px 12px;border-radius:6px;background:#4a1f1b;color:#ffb4ad;font-weight:600"></div>
</section>
<section class="card"><h2>Approved Image</h2>
 <div class="kv">
  <div>Latest Production Version</div><b id="latest">—</b>
  <div>Local Image Version</div><b id="local">—</b>
  <div>Development / QA</div><b id="other">—</b>
  <div>Image Signature</div><div id="sig"><span class="pill mute">—</span></div>
  <div>Image Status</div><div id="imgStatus"><span class="pill mute">—</span></div>
  <div>Build ID</div><b id="build">—</b>
 </div>
 <h2 style="margin-top:16px">Module</h2>
 <div class="kv">
  <div>Hardware</div><b id="hw">—</b>
  <div>Board serial</div><b id="board">—</b>
  <div>EEPROM</div><b id="eeprom">—</b>
  <div>Storage</div><b id="storage">—</b>
 </div>
</section>
<section class="card"><h2>Unit</h2>
 <div class="kv">
  <div>Serial Number</div><b id="serial" style="font-size:20px">—</b>
  <div>Previous Serial</div><b id="prev">—</b>
  <div>Device ID</div><b id="devid" style="font-size:12px">—</b>
  <div>Image Version</div><b id="imgver">—</b>
  <div>Software Version</div><b id="appver">—</b>
  <div>Secure Boot</div><div id="sb"><span class="pill mute">—</span></div>
  <div>Disk Encryption</div><div id="enc"><span class="pill mute">—</span></div>
  <div>License</div><div id="lic"><span class="pill mute">—</span></div>
  <div>Final Test</div><div id="test"><span class="pill mute">—</span></div>
 </div>
 <h2 style="margin-top:16px">Generate New Serial Number</h2>
 <div style="font-size:12px;color:var(--mute)">Assigns the next serial from the central counter to the connected unit. The previous serial is kept for traceability. Factory / Service only.</div>
 <div class="row"><input id="prevSerial" placeholder="Current serial of the unit (SC000000)"></div>
 <div class="row"><button class="sec" id="newSerial">Generate New Serial Number</button></div>
</section>
<section class="success" id="success"><h3>Provisioning Successful</h3>
 <div class="kv"><div>Machine Serial</div><div class="big" id="sSerial"></div><div>Device Status</div><div class="big" style="color:var(--ok)">READY FOR PRODUCTION</div><div>Image</div><b id="sImage"></b><div>Provisioning</div><b id="sOnline"></b></div></section>
<section class="failed" id="failed"><b style="color:var(--bad)">Provisioning FAILED</b> — <span id="failText"></span><div style="font-size:12px;color:var(--mute);margin-top:6px">The reserved serial (if any) was voided; it will never be reused. Fix the cause and press Start again.</div></section>
<section class="card wide"><h2>Log</h2><div class="log" id="log"></div></section>
</main>
<script>
const $=id=>document.getElementById(id);const pill=(t,c)=>`<span class="pill ${c}">${t}</span>`;
const LABEL={FETCH_APPROVED_IMAGE:'Fetch approved image',DETECT_HARDWARE:'Detect module (rpiboot)',VERIFY_COMPAT:'Verify hardware compatibility',FLASH_IMAGE:'Flash image',CONFIGURE_BOOT:'Configure secure boot (OTP)',CREATE_IDENTITY:'Create device identity',ALLOCATE_SERIAL:'Assign serial number',REQUEST_LICENSE:'Request license',BIND_LICENSE:'Bind license to device',ENCRYPT_DATA:'Encrypt data partition',APPLY_POLICY:'Apply kiosk / USB / user policy',VERIFY_MACHINE:'Machine self-test',VERIFY_SOFTWARE:'Software verification',RECORD:'Manufacturing record'};
let busy=false;
function render(s){
 $('station').textContent=s.station;$('mode').textContent=s.fake?'SIMULATED MODULE':'CM5 over USB';
 const c=s.catalog||{};$('latest').textContent=c.latestProduction||'—';$('local').textContent=c.localVersion||'none';$('build').textContent=c.buildId||'—';
 $('other').textContent=c.versions?`dev ${c.versions.development||'—'} · qa ${c.versions.qa||'—'}`:'—';
 $('offline').classList.toggle('on',c.ok&&!c.online);$('offlineImg').textContent=c.latestProduction?`Using cached approved image: ${c.latestProduction}`:'';
 const r=s.run;const done=new Set(r?r.completed:[]);const running=s.running;
 $('steps').innerHTML=s.steps.map(st=>`<li class="${done.has(st)?'done':(r&&r.step===st?(r.result==='FAILED'?'fail':'now'):'')}"><span class="dot"></span>${LABEL[st]||st}</li>`).join('');
 const p=s.progress.flash||s.progress.download;if(p&&running&&p.total){$('progWrap').style.display='block';$('progLabel').textContent=(s.progress.flash?'Flashing':'Downloading latest approved image...')+` ${Math.round(100*p.done/p.total)}%`;$('prog').style.width=(100*p.done/p.total)+'%';}else $('progWrap').style.display='none';
 const imgOk=r&&done.has('FETCH_APPROVED_IMAGE');
 $('sig').innerHTML=imgOk?pill('VALID','ok'):(c.ok?pill('cached · re-verified before flash','mute'):pill(c.error||'NO IMAGE','bad'));
 $('imgStatus').innerHTML=imgOk?pill(done.has('FLASH_IMAGE')?'INSTALLED':'READY FOR INSTALLATION','ok'):(c.ok?pill('READY TO VERIFY','mute'):pill('NOT AVAILABLE','bad'));
 const m=r?r.module:{};$('hw').textContent=m.model||'—';$('board').textContent=m.board_serial||'—';$('eeprom').textContent=m.eeprom_version||'—';$('storage').textContent=m.storage_size_bytes?(m.storage_size_bytes/1e9).toFixed(0)+' GB · '+m.storage_device:'—';
 $('serial').textContent=r&&r.serial?r.serial:'—';$('prev').textContent=r&&r.previousSerial?r.previousSerial:'—';$('devid').textContent=r&&r.deviceId?r.deviceId:'—';
 $('imgver').textContent=r&&r.image.version?`${r.image.version}`:'—';$('appver').textContent=(r&&r.image.appVersion)||c.appVersion||'—';
 $('sb').innerHTML=r&&done.has('CONFIGURE_BOOT')?(r.secureBoot?pill('PROGRAMMED','ok'):pill('NOT PROGRAMMED (lab)','warn')):pill('—','mute');
 $('enc').innerHTML=r&&r.encrypted?pill('LUKS2 · OTP key','ok'):pill('—','mute');
 $('lic').innerHTML=r&&done.has('BIND_LICENSE')?pill((r.provisional?'PROVISIONAL · ':'VALID · ')+(r.license||[]).join(','),r.provisional?'warn':'ok'):pill('—','mute');
 $('test').innerHTML=r&&r.softwareOk?pill('PASS','ok'):(r&&r.selfTest?pill('MACHINE OK','ok'):pill('—','mute'));
 $('success').classList.toggle('on',!!(r&&r.result==='READY_FOR_PRODUCTION'));if(r&&r.result==='READY_FOR_PRODUCTION'){$('sSerial').textContent=r.serial;$('sImage').textContent=`${r.image.version} (build ${r.image.buildId})`;$('sOnline').textContent=r.online?'Online':'OFFLINE — record queued for upload';}
 $('failed').classList.toggle('on',!!(r&&r.result==='FAILED'));if(r&&r.result==='FAILED')$('failText').textContent=`${r.step}: ${r.error}`;
 $('log').innerHTML=s.events.map(e=>`<div><span class="e">${(e.ts||'').slice(11,19)} ${e.step||''}</span> ${e.event}${e.status?' — '+e.status:''}${e.serial?' '+e.serial:''}</div>`).join('');$('log').scrollTop=1e9;
 const um=s.usbModule;$('usb').className='pill '+(um?'ok':'bad');$('usb').textContent=um?`CM5: CONNECTED · ${um.description} (${um.vid}:${um.pid})`:'CM5: NOT CONNECTED — connect over USB in nRPIBOOT mode';
 const hasOp=!!$('operator').value.trim()&&(s.fake||!!um);
 $('start').disabled=running||!hasOp||!(c.ok);$('newSerial').disabled=running||!hasOp;$('refresh').disabled=running;
 $('start').title=!hasOp?'Enter the operator name first':(!c.ok?'No approved image available':'');
 if(s.defaultOperator&&!$('operator').dataset.touched&&!$('operator').value){$('operator').value=s.defaultOperator;}
 if(s.lastSerial&&!$('prevSerial').value)$('prevSerial').placeholder=`Current serial of the unit (last: ${s.lastSerial})`;
}
async function poll(){try{render(await (await fetch('/api/state')).json());}catch(e){}setTimeout(poll,800);}
function showErr(t){const e=$('err');e.textContent=t||'';e.style.display=t?'block':'none';}
async function post(u,b){showErr('');try{const r=await (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json();if(!r.ok&&r.error)showErr(r.error);return r;}catch(e){showErr('UI server not reachable: '+e);return {ok:false};}}
$('operator').addEventListener('input',()=>{$('operator').dataset.touched='1';});
$('start').onclick=()=>post('/api/start',{operator:$('operator').value});
$('refresh').onclick=()=>post('/api/catalog/refresh');
$('newSerial').onclick=()=>{if(confirm(`Assign the NEXT serial number to the unit currently ${$('prevSerial').value||'(enter its serial)'}? This is recorded in the audit log.`))post('/api/new-serial',{operator:$('operator').value,previousSerial:$('prevSerial').value,role:'factory'});};
post('/api/catalog/refresh');poll();
</script></body></html>"""


def main(argv=None):
    global CFG, FAKE
    ap = argparse.ArgumentParser(description="Stratasys Factory Provisioning Tool — UI")
    ap.add_argument("--station", required=True)
    ap.add_argument("--server")
    ap.add_argument("--workdir", default=os.path.expanduser("~/.stratasys-provisioning"))
    ap.add_argument("--trust", default=str(Path(__file__).with_name("trust")))
    ap.add_argument("--channel", default="production")
    ap.add_argument("--role", default="factory")
    ap.add_argument("--signed-eeprom")
    ap.add_argument("--offline-token")
    ap.add_argument("--station-key")
    ap.add_argument("--fake", action="store_true", help="simulated module (no rpiboot)")
    ap.add_argument("--port", type=int, default=8450)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    CFG = provision.Config(a.station, "", a.server, Path(a.workdir), Path(a.trust), channel=a.channel, role=a.role,
                           signed_eeprom_dir=Path(a.signed_eeprom) if a.signed_eeprom else None,
                           offline_token=Path(a.offline_token) if a.offline_token else None,
                           station_key=Path(a.station_key) if a.station_key else None)
    FAKE = a.fake
    STATE["catalog"] = _catalog_probe()
    url = f"http://127.0.0.1:{a.port}"
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Stratasys Factory Provisioning Tool UI: {url}")
    app.run(host="127.0.0.1", port=a.port, threaded=True)


if __name__ == "__main__":
    main()
