#!/usr/bin/env python3
"""LED panel warm-up bench: does every LED module's thermistor rise when the
module is driven at 30 % - at 405 nm (Left/Right/Back/Door) and 450 nm (Door)?

Feeds the "LED not heating -> check the LED connection" supervision:
the rise per panel, its onset delay and the no-load behaviour of the
unpowered panels define the detection thresholds.

Runs on the Pi against the local service (no direct hardware access):
    nohup python3 ~/led_panel_warmup.py 30 405,450 > ~/led_panel_warmup.log 2>&1 &
Writes ~/led_panel_warmup.csv and ~/led_panel_warmup.done at the end.
UV is always switched off in `finally`.
"""
import csv, json, sys, time, urllib.request

API = 'http://localhost:3001'
INTENSITY = int(sys.argv[1]) if len(sys.argv) > 1 else 30
WAVELENGTHS = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [405, 450]
ON_SEC = 150
BASE_SEC = 10
COOL_SEC = 150
KEYS = ['left', 'left2', 'right', 'right2', 'back', 'door']


def api(path, method='GET'):
    req = urllib.request.Request(API + path, method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def state():
    s = api('/api/state')
    lt = s.get('ledTemps') or {}
    return {k: lt.get(k) for k in KEYS} | {'chamber': s.get('chamberTemp'),
                                           'uvOn': s.get('uvOn'),
                                           'uvWl': s.get('uvWavelength')}


def log(w, t0, phase, wl):
    row = state()
    w.writerow([round(time.time() - t0, 1), phase, wl] + [row[k] for k in KEYS]
               + [round(row['chamber'], 2) if row['chamber'] is not None else None,
                  row['uvOn'], row['uvWl']])
    return row


def main():
    t0 = time.time()
    with open('/home/testingpi/led_panel_warmup.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'phase', 'wl'] + KEYS + ['chamber', 'uvOn', 'uvWl'])
        try:
            for wl in WAVELENGTHS:
                for _ in range(BASE_SEC):
                    log(w, t0, 'base', wl); time.sleep(1)
                r = api(f'/api/uv?on=1&intensity={INTENSITY}&wavelength={wl}', 'POST')
                print(f'[{time.time()-t0:6.1f}] UV ON {wl} nm @ {INTENSITY}% -> {r}', flush=True)
                if not r.get('ok'):
                    print('UV refused - aborting', flush=True)
                    return
                for i in range(ON_SEC):
                    row = log(w, t0, 'on', wl)
                    if i % 10 == 0:
                        print(f'[{time.time()-t0:6.1f}] on {wl}: ' +
                              ' '.join(f'{k}={row[k]}' for k in KEYS), flush=True)
                    time.sleep(1)
                r = api('/api/uv?on=0', 'POST')
                print(f'[{time.time()-t0:6.1f}] UV OFF -> {r}', flush=True)
                for i in range(COOL_SEC):
                    row = log(w, t0, 'cool', wl)
                    if i % 30 == 0:
                        print(f'[{time.time()-t0:6.1f}] cool: ' +
                              ' '.join(f'{k}={row[k]}' for k in KEYS), flush=True)
                    time.sleep(1)
        finally:
            try:
                print('final UV OFF ->', api('/api/uv?on=0', 'POST'), flush=True)
            except Exception as e:      # noqa: BLE001
                print('final UV OFF failed:', e, flush=True)
            open('/home/testingpi/led_panel_warmup.done', 'w').write('done\n')


if __name__ == '__main__':
    main()
