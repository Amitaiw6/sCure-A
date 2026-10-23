#!/usr/bin/env python3
"""End-to-end check of the LED connection supervision (Err 9004) on the Pi.

Phases (all at INTENSITY % system power, UV through the local service):
  A  405 nm for A_SEC  - Left and Right must reach ledHealth status 'ok'
  B  450 nm for B_SEC  - Door only is lit: Left / Right stay 'off', no alert
  C  fault injection   - components.json led_heating.min_rise_c is raised to
     FAULT_RISE so no panel can pass; 405 nm for C_SEC -> Err 9004 expected
     in /api/state alerts with every panel named in alertDetails; then the
     value is restored and the alert must clear on the next tick.

Logs ~/led_connection_check.csv (t, phase, wl, per-panel temp / rise / litSec /
status, alerts, alertDetails) and ~/led_connection_check.log, writes
~/led_connection_check.done at the end. UV is always switched off and the
config restored in `finally`.

    nohup python3 ~/led_connection_check.py > ~/led_connection_check.log 2>&1 &
"""
import csv, json, sys, time, urllib.request

API = 'http://localhost:3001'
CFG = '/home/testingpi/sCure-A/io_controller/components.json'
HOME = '/home/testingpi/'
INTENSITY = int(sys.argv[1]) if len(sys.argv) > 1 else 30
A_SEC, B_SEC, C_SEC = 120, 120, 110
GAP_SEC = 20
FAULT_RISE = 50.0
# supervised panels and the /api/state ledTemps key of their REGULAR thermistor
# (TEMP_LEFT / TEMP_RIGHT are reported as left2 / right2)
LEDS = ['LED_LEFT', 'LED_RIGHT']
TEMP_KEY = {'LED_LEFT': 'left2', 'LED_RIGHT': 'right2'}


def api(path, method='GET'):
    req = urllib.request.Request(API + path, method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def set_min_rise(value):
    cfg = json.load(open(CFG))
    cfg.setdefault('led_heating', {})['min_rise_c'] = value
    json.dump(cfg, open(CFG, 'w'), indent=2)
    open(CFG, 'a').write('\n')


def snapshot():
    s = api('/api/state')
    lt, lh = s.get('ledTemps') or {}, s.get('ledHealth') or {}
    return s, lt, lh


def log(w, t0, phase, wl, verbose=False):
    s, lt, lh = snapshot()
    row = [round(time.time() - t0, 1), phase, wl]
    for led in LEDS:
        h = lh.get(led) or {}
        row += [lt.get(TEMP_KEY[led]), h.get('rise'), h.get('litSec'), h.get('status')]
    row += [json.dumps(s.get('alerts')), json.dumps(s.get('alertDetails'))]
    w.writerow(row)
    if verbose:
        print(f'[{row[0]:6.1f}] {phase} {wl}: ' +
              ' '.join(f"{led[4:].lower()}={lt.get(TEMP_KEY[led])}/{(lh.get(led) or {}).get('rise')}/"
                       f"{(lh.get(led) or {}).get('status')}" for led in LEDS) +
              f" alerts={s.get('alerts')}", flush=True)
    return s, lh


def run_phase(w, t0, phase, wl, sec, every=10):
    r = api(f'/api/uv?on=1&intensity={INTENSITY}&wavelength={wl}', 'POST')
    print(f'[{time.time()-t0:6.1f}] {phase}: UV ON {wl} nm @ {INTENSITY}% -> {r}', flush=True)
    if not r.get('ok'):
        raise RuntimeError(f'UV refused: {r}')
    last = None
    for i in range(sec):
        last = log(w, t0, phase, wl, verbose=(i % every == 0))
        time.sleep(1)
    r = api('/api/uv?on=0', 'POST')
    print(f'[{time.time()-t0:6.1f}] {phase}: UV OFF -> {r}', flush=True)
    return last


def main():
    t0 = time.time()
    orig_rise = json.load(open(CFG)).get('led_heating', {}).get('min_rise_c', 1.0)
    verdict = {}
    with open(HOME + 'led_connection_check.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'phase', 'wl'] +
                   [f'{k}_{x}' for k in ('left', 'right')
                    for x in ('temp', 'rise', 'litSec', 'status')] + ['alerts', 'alertDetails'])
        try:
            s, lh = run_phase(w, t0, 'A', 405, A_SEC)
            verdict['A'] = {led: (lh.get(led) or {}).get('status') for led in LEDS}
            verdict['A_alerts'] = s.get('alerts')
            for _ in range(GAP_SEC):
                log(w, t0, 'gapA', 0); time.sleep(1)
            s, lh = run_phase(w, t0, 'B', 450, B_SEC)
            verdict['B'] = {led: ((lh.get(led) or {}).get('status'), (lh.get(led) or {}).get('rise'))
                            for led in LEDS}
            verdict['B_alerts'] = s.get('alerts')
            for _ in range(GAP_SEC):
                log(w, t0, 'gapB', 0); time.sleep(1)
            set_min_rise(FAULT_RISE)
            print(f'[{time.time()-t0:6.1f}] C: min_rise_c -> {FAULT_RISE} (fault injection)', flush=True)
            time.sleep(2)
            s, lh = run_phase(w, t0, 'C', 405, C_SEC, every=5)
            verdict['C'] = {led: (lh.get(led) or {}).get('status') for led in LEDS}
            verdict['C_alerts'] = s.get('alerts')
            verdict['C_details'] = s.get('alertDetails')
            set_min_rise(orig_rise)
            print(f'[{time.time()-t0:6.1f}] C: min_rise_c restored -> {orig_rise}', flush=True)
            # the failed panels are now off: the latch must clear once they are
            # lit again and rise >= the restored threshold (their window is < 120 s
            # old, so the old baseline is kept and the rise is already there)
            r = api(f'/api/uv?on=1&intensity={INTENSITY}&wavelength=405', 'POST')
            print(f'[{time.time()-t0:6.1f}] D: UV ON 405 again -> {r}', flush=True)
            for i in range(8):
                s, lh = log(w, t0, 'D', 405, verbose=True); time.sleep(1)
            verdict['D_alerts'] = s.get('alerts')
            verdict['D'] = {led: (lh.get(led) or {}).get('status') for led in LEDS}
            api('/api/uv?on=0', 'POST')
        finally:
            try:
                print('final UV OFF ->', api('/api/uv?on=0', 'POST'), flush=True)
            except Exception as e:      # noqa: BLE001
                print('final UV OFF failed:', e, flush=True)
            try:
                set_min_rise(orig_rise)
            except Exception as e:      # noqa: BLE001
                print('config restore failed:', e, flush=True)
            print('VERDICT', json.dumps(verdict, indent=1), flush=True)
            open(HOME + 'led_connection_check.done', 'w').write('done\n')


if __name__ == '__main__':
    main()
