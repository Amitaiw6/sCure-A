#!/usr/bin/env python3
"""NFC tag monitor for the Eccel Pepper C2 reader (USB CDC, /dev/ttyACM0).

Polls the reader with the Pepper binary protocol and serves a small web page
(and /api/nfc JSON) that shows whether a tag is on the antenna and its UID.

    python3 nfc_monitor.py [--port /dev/ttyACM0] [--http 3005] [--interval 0.3]

Standard library only (raw termios - pyserial's open hangs on this device).
"""
import argparse
import json
import os
import select
import sys
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TAG_TYPES = {
    0x01: "MIFARE Ultralight", 0x02: "MIFARE Ultralight-C", 0x03: "MIFARE Classic",
    0x04: "MIFARE Classic 1k", 0x05: "MIFARE Classic 4k", 0x06: "MIFARE Plus",
    0x07: "MIFARE Plus 2k", 0x08: "MIFARE Plus 4k", 0x09: "MIFARE Plus 2k sl2",
    0x0A: "MIFARE Plus 4k sl2", 0x0B: "MIFARE Plus 2k sl3", 0x0C: "MIFARE Plus 4k sl3",
    0x0D: "MIFARE DESFire", 0x0F: "JCOP", 0x10: "MIFARE Mini",
    0x21: "ICODE SLI", 0x22: "ICODE SLI-S", 0x23: "ICODE SLI-L", 0x24: "ICODE SLIX",
    0x25: "ICODE SLIX-S", 0x26: "ICODE SLIX-X", 0x27: "ICODE SLIX2", 0x28: "ICODE DNA",
}
ISO15693_MFR = {0x04: "NXP", 0x07: "Texas Instruments", 0x02: "STMicroelectronics", 0x01: "Motorola", 0x16: "EM Microelectronic"}


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frame(body):
    n = len(body) + 2  # length counts the command body AND its CRC bytes
    return bytes([0xF5]) + n.to_bytes(2, "little") + (n ^ 0xFFFF).to_bytes(2, "little") + body + crc16(body).to_bytes(2, "little")


class Reader:
    def __init__(self, path):
        self.path = path
        self.fd = None

    def open(self):
        fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(fd)
        a[0] = termios.IGNBRK
        a[1] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[3] = 0
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        # The C2 only starts servicing its USB CDC RX after a SET_LINE_CODING request, and
        # cdc_acm sends one only when the rate actually changes - so go 9600 -> 115200 every open.
        a[4] = a[5] = termios.B9600
        termios.tcsetattr(fd, termios.TCSANOW, a)
        time.sleep(0.05)
        a[4] = a[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, a)
        time.sleep(0.05)
        termios.tcflush(fd, termios.TCIOFLUSH)
        self.fd = fd

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def _read(self, n, timeout):
        out = b""
        end = time.time() + timeout
        while len(out) < n:
            rem = end - time.time()
            if rem <= 0:
                break
            if select.select([self.fd], [], [], rem)[0]:
                try:
                    chunk = os.read(self.fd, n - len(out))
                except BlockingIOError:
                    continue
                if not chunk:
                    raise OSError("port closed")
                out += chunk
        return out

    def command(self, body, timeout=1.0):
        """Send one command, return the response body (ACK/ERR byte first) or None on timeout."""
        termios.tcflush(self.fd, termios.TCIFLUSH)
        os.write(self.fd, frame(body))
        end = time.time() + timeout
        while time.time() < end:
            b = self._read(1, end - time.time())
            if b == b"\xf5":
                break
            if not b:
                return None
        else:
            return None
        hdr = self._read(4, 0.5)
        if len(hdr) < 4:
            return None
        n = int.from_bytes(hdr[:2], "little")
        if int.from_bytes(hdr[2:], "little") != (n ^ 0xFFFF) or n < 2:
            return None
        rx = self._read(n - 2, 0.5)
        crc = self._read(2, 0.2)
        if crc != crc16(rx).to_bytes(2, "little"):
            return None
        return rx


class Monitor(threading.Thread):
    def __init__(self, path, interval):
        super().__init__(daemon=True)
        self.reader = Reader(path)
        self.interval = interval
        self.lock = threading.Lock()
        self.state = {
            "readerConnected": False, "firmware": None, "port": path,
            "tagPresent": False, "tagCount": 0, "tags": [],
            "lastTag": None, "lastSeen": None, "reads": 0, "errors": 0,
            "error": None, "updated": None,
        }

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)
            self.state["updated"] = time.time()

    def _connect(self):
        self.reader.close()
        self.reader.open()
        r = self.reader.command(b"\x01")
        if not r or r[0] != 0:
            raise OSError("no ACK to dummy command")
        v = self.reader.command(b"\x0b")
        fw = v[2:].decode("ascii", "replace") if v and v[0] == 0 else None
        self.reader.command(b"\x06\x00")  # stop built-in polling so host commands work
        self._set(readerConnected=True, firmware=fw, error=None)
        print(time.strftime("%H:%M:%S"), "reader connected, firmware:", fw, flush=True)

    def _poll_once(self):
        r = self.reader.command(b"\x02")
        if r is None:
            raise OSError("no reply to GET_TAG_COUNT")
        if r[0] != 0:
            self._set(tagPresent=False, tagCount=0, tags=[], error="reader error 0x%02x" % (r[2] if len(r) > 2 else 0))
            return
        count = r[2] if len(r) > 2 else 0
        tags = []
        for idx in range(min(count, 5)):
            u = self.reader.command(bytes([0x03, idx]))
            if not u or u[0] != 0 or len(u) < 4:
                continue
            ttype, param, uid = u[2], u[3], u[4:]
            name = TAG_TYPES.get(ttype)
            if name is None:
                if len(uid) == 8 and uid[0] == 0xE0:
                    name = "ISO 15693 (%s)" % ISO15693_MFR.get(uid[1], "mfr 0x%02x" % uid[1])
                else:
                    name = "unknown (0x%02x)" % ttype
            tags.append({"uid": uid.hex(":").upper(), "typeCode": ttype, "type": name, "param": param})
        with self.lock:
            st = self.state
            st["reads"] += 1
            st["tagPresent"] = bool(tags)
            st["tagCount"] = len(tags)
            st["tags"] = tags
            st["error"] = None
            if tags:
                st["lastTag"] = tags[0]
                st["lastSeen"] = time.time()
            st["updated"] = time.time()

    def run(self):
        while True:
            try:
                if not self.state["readerConnected"]:
                    self._connect()
                self._poll_once()
                time.sleep(self.interval)
            except OSError as e:
                with self.lock:
                    self.state["errors"] += 1
                self._set(readerConnected=False, tagPresent=False, tagCount=0, tags=[], error=str(e))
                print(time.strftime("%H:%M:%S"), "reader lost:", e, flush=True)
                self.reader.close()
                time.sleep(1.0)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NFC Tag Monitor</title>
<style>
  :root{--bg:#0f1115;--panel:#181b22;--fg:#f4f4f5;--muted:#9aa0ab;--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444;--line:#2a2f3a}
  *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
  main{max-width:720px;margin:0 auto;padding:32px 20px}
  h1{font-size:20px;font-weight:600;margin:0 0 4px;color:#fff}.sub{color:var(--muted);margin:0 0 24px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;margin-bottom:16px}
  .status{display:flex;align-items:center;gap:16px}
  .dot{width:22px;height:22px;border-radius:50%;background:var(--muted);box-shadow:0 0 0 0 rgba(0,0,0,0);transition:background .2s}
  .dot.on{background:var(--ok);box-shadow:0 0 18px var(--ok)}.dot.off{background:#3a3f4a}.dot.err{background:var(--bad)}
  .big{font-size:30px;font-weight:600;color:#fff}
  .uid{font:600 34px/1.2 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.06em;color:#fff;word-break:break-all;margin:6px 0 10px}
  .row{display:grid;grid-template-columns:150px 1fr;gap:6px 12px;color:var(--muted)}.row b{color:var(--fg);font-weight:500}
  .muted{color:var(--muted)}.err{color:var(--bad)}
</style></head><body><main>
<h1>NFC Tag Monitor</h1><p class="sub">Eccel Pepper C2 on the test machine</p>
<div class="card"><div class="status"><div id="dot" class="dot"></div><div><div id="big" class="big">Connecting…</div><div id="hint" class="muted"></div></div></div></div>
<div class="card"><div class="muted" style="margin-bottom:4px">Tag UID</div><div id="uid" class="uid">—</div>
<div class="row"><span>Type</span><b id="type">—</b><span>Parameter (SAK/DSFID)</span><b id="param">—</b><span>Last seen</span><b id="seen">—</b></div></div>
<div class="card"><div class="row"><span>Reader</span><b id="reader">—</b><span>Firmware</span><b id="fw">—</b><span>Port</span><b id="port">—</b><span>Polls / errors</span><b id="stats">—</b><span>Status</span><b id="error">—</b></div></div>
</main><script>
const $=id=>document.getElementById(id);let last=null;
function ago(t){if(!t)return "never";const s=Math.max(0,Date.now()/1000-t);return s<1.5?"just now":s<60?Math.round(s)+" s ago":Math.round(s/60)+" min ago"}
async function tick(){try{const r=await fetch("/api/nfc",{cache:"no-store"});const s=await r.json();
 const dot=$("dot");if(!s.readerConnected){dot.className="dot err";$("big").textContent="Reader not connected";$("hint").textContent=s.error||"";}
 else if(s.tagPresent){dot.className="dot on";$("big").textContent="Tag detected";$("hint").textContent=s.tagCount>1?s.tagCount+" tags in the field":"";}
 else{dot.className="dot off";$("big").textContent="No tag";$("hint").textContent="Place a tag on the antenna";}
 const t=s.tagPresent?s.tags[0]:s.lastTag;
 $("uid").textContent=t?t.uid:"—";$("uid").style.opacity=s.tagPresent?1:.45;$("type").textContent=t?t.type:"—";
 $("param").textContent=t?"0x"+t.param.toString(16).padStart(2,"0"):"—";$("seen").textContent=s.tagPresent?"now":ago(s.lastSeen);
 $("reader").textContent=s.readerConnected?"connected":"disconnected";$("fw").textContent=s.firmware||"—";$("port").textContent=s.port;
 $("stats").textContent=s.reads+" / "+s.errors;$("error").textContent=s.error||"ok";$("error").className=s.error?"err":"";
 document.title=(s.tagPresent?"● ":"○ ")+"NFC Tag Monitor";
}catch(e){$("dot").className="dot err";$("big").textContent="Monitor unreachable";$("hint").textContent=String(e);}}
tick();setInterval(tick,400);
</script></body></html>
"""


def make_handler(monitor):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/nfc"):
                self._send(200, "application/json", json.dumps(monitor.snapshot()).encode())
            elif self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", PAGE.encode())
            else:
                self._send(404, "text/plain", b"not found")
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="/dev/ttyACM0", help="reader serial device")
    ap.add_argument("--http", type=int, default=3005, help="HTTP listen port")
    ap.add_argument("--interval", type=float, default=0.3, help="poll interval in seconds")
    args = ap.parse_args()
    mon = Monitor(args.port, args.interval)
    mon.start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.http), make_handler(mon))
    print(time.strftime("%H:%M:%S"), "NFC monitor on http://0.0.0.0:%d  reader %s" % (args.http, args.port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
