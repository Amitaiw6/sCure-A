#!/usr/bin/env python3
"""
שליטה ב-PCA9685 על לוח ה-IO (CureBox) מעל CM5.
באס: /dev/i2c-0 | כתובת: 0x55
"""

from smbus2 import SMBus
import time

BUS = 0
ADDR = 0x55

# --- רגיסטרים ---
MODE1      = 0x00
MODE2      = 0x01
PRESCALE   = 0xFE
LED0_ON_L  = 0x06   # כל ערוץ = 4 רגיסטרים: ON_L, ON_H, OFF_L, OFF_H

# --- ביטים ב-MODE1 ---
SLEEP = 0x10
AI    = 0x20   # auto-increment
RESTART = 0x80

# מיפוי הערוצים בלוח שלך (לפי הסכמטיק)
CHANNELS = {
    "HEATER": 0, "DOOR": 1, "RIGHT": 2, "LEFT": 3, "BACK": 4, "CHAMBER": 5,
    "PWM_HEATER": 6, "LIGHT1": 7,
    "MOT1_EN": 8, "MOT2_EN": 9, "BOFA": 10,
    "LED_BACK": 11, "LED_DOOR": 12, "LED_RIGHT": 13, "LED_LEFT": 14,
    "LED_ANALOG5": 15,
}

# מאוורר = ערוץ PWM ב-PCA9685 + פין GPIO לקריאת הטכו.
# שמות פונקציונליים לפי הסכמטיק (HEATER=J4, DOOR, RIGHT=J5, LEFT=J6, BACK=J9, CHAMBER=J7).
# ⚠️ אמת את ה-GPIO של הטכו מול הסכמטיק שלך לפני שתסמוך על הקריאות.
FANS = {
    "HEATER":  {"pwm": 0, "tach": 22},
    "DOOR":    {"pwm": 1, "tach": 23},
    "RIGHT":   {"pwm": 2, "tach": 24},
    "LEFT":    {"pwm": 3, "tach": 19},
    "BACK":    {"pwm": 4, "tach": 25},
    "CHAMBER": {"pwm": 5, "tach": 26},
}

PULSES_PER_REV = 2   # מאוורר סטנדרטי (4-pole): 2 פולסים לכל סיבוב (מאומת בדאטה-שיט)

# מהירות נקובה מהדאטה-שיט (CBM-97B). ⚠️ הגדר לפי הדגם המדויק שלך:
#   ...-x25-... → 2500 | ...-x30-... → 3000 | ...-x35-... → 3500
RATED_RPM = {
    "HEATER": 3000, "DOOR": 3000, "RIGHT": 3000,
    "LEFT": 3000, "BACK": 3000, "CHAMBER": 3000,
}

SOFT_START_SEC = 15    # זמן soft-start מהדאטה-שיט עד הגעה למהירות נקובה
DROP_THRESHOLD = 0.20  # ירידה מותרת מהנקוב (20%) לפני כיבוי

# ערוצים שעוברים דרך דרייבר הופך → מקבלים היפוך בתוכנה.
# מאומת: המאווררים (0-5) הפוכים; גוף החימום (6), BOFA (10) וה-LED-ים (11-15) ישירים.
# תאורה(7)/מנועים(8,9): נשמרים הפוכים כמו קודם — ⚠️ בדוק כל אחד פיזית
# והסר ממ-set אם מתברר שהוא ישיר.
INVERTED_CHANNELS = {0, 1, 2, 3, 4, 5, 7, 8, 9}

# ערוצי ON/OFF בלבד (ללא עמעום). כל ערך > 0 → ON מלא; 0 → OFF.
# גוף החימום (6) מוגדר כמתג דיגיטלי, לא כעמעום PWM.
DIGITAL_CHANNELS = {6}


class FanTach:
    """קריאת RPM מיציאת הטכו של מאוורר, ע"י ספירת פולסים בחלון זמן.
    משתמש ב-gpiozero (backend lgpio, עובד על CM5)."""

    def __init__(self, gpio, pulses_per_rev=PULSES_PER_REV):
        from gpiozero import DigitalInputDevice
        # pull_up פנימי — יציאת הטכו היא open-collector
        self.dev = DigitalInputDevice(gpio, pull_up=True)
        self.ppr = pulses_per_rev
        self._count = 0
        self.dev.when_activated = self._tick

    def _tick(self):
        self._count += 1

    def read_rpm(self, window=1.0):
        """סופר פולסים למשך 'window' שניות ומחזיר RPM."""
        self._count = 0
        time.sleep(window)
        pulses = self._count
        return (pulses / self.ppr) * (60.0 / window)

    def close(self):
        self.dev.close()


def read_all_rpm(window=1.0):
    """קורא את כל המאווררים במקביל באותו חלון זמן."""
    tachs = {name: FanTach(cfg["tach"]) for name, cfg in FANS.items()}
    # איפוס וספירה משותפת לכל הטכואים בו-זמנית
    for t in tachs.values():
        t._count = 0
    time.sleep(window)
    result = {}
    for name, t in tachs.items():
        result[name] = (t._count / t.ppr) * (60.0 / window)
        t.close()
    return result


def watchdog(duties=None, poll=2.0, action="off"):
    """
    בטיחות מאווררים: מדליק, ממתין ל-soft-start, ואז מנטר RPM.
    אם מאוורר יורד מתחת ל-(1 - DROP_THRESHOLD) מהמהירות הנקובה → מבצע action.

    duties: dict {שם_מאוורר: duty%}. ריק/None = כל המאווררים ב-100%.
    action="off"    → כיבוי מלא של המאוורר התקול
    action="reduce" → הורדת ה-duty ב-20% (במקום כיבוי)
    """
    pca = PCA9685()
    if not duties:
        duties = {name: 100 for name in FANS}
    duties = dict(duties)          # עותק מקומי (נשתנה בזמן ריצה)
    fans = list(duties)

    # 1. הדלקה — כל מאוורר ל-duty שלו
    for name in fans:
        pca.set_duty(FANS[name]["pwm"], duties[name])
    summary = ", ".join(f"{n}={duties[n]:.0f}%" for n in fans)
    print(f"הופעלו: {summary}. ממתין {SOFT_START_SEC}s ל-soft start...")
    time.sleep(SOFT_START_SEC)

    # 2. טכואים — נוצרים פעם אחת וסופרים במקביל
    tachs = {name: FanTach(FANS[name]["tach"]) for name in fans}
    active = set(fans)

    print("ניטור פעיל (Ctrl+C ליציאה)\n")
    try:
        while active:
            for t in tachs.values():
                t._count = 0
            time.sleep(1.0)                       # חלון מדידה משותף
            for name in sorted(active):
                rpm = tachs[name]._count / tachs[name].ppr * 60.0
                rated = RATED_RPM[name]
                floor = rated * (1 - DROP_THRESHOLD)
                if rpm < floor:
                    if action == "reduce":
                        duties[name] = max(0, duties[name] - 20)
                        pca.set_duty(FANS[name]["pwm"], duties[name])
                        print(f"⚠️  {name}: {rpm:.0f} RPM < {floor:.0f} "
                              f"(80% מ-{rated}) → הורדה ל-{duties[name]}%")
                        if duties[name] == 0:
                            active.discard(name)
                    else:
                        pca.off(FANS[name]["pwm"])
                        print(f"⚠️  {name}: {rpm:.0f} RPM < {floor:.0f} "
                              f"(80% מ-{rated}) → כובה!")
                        active.discard(name)
                else:
                    print(f"    {name}: {rpm:.0f} RPM  (תקין, נקוב {rated})")
            print("-" * 40)
            time.sleep(max(0, poll - 1.0))
        print("כל המאווררים שניטרו כובו עקב תקלה.")
    except KeyboardInterrupt:
        print("\nניטור הופסק.")
    finally:
        for t in tachs.values():
            t.close()
        pca.close()


class PCA9685:
    def __init__(self, bus=BUS, addr=ADDR):
        self.bus = SMBus(bus)
        self.addr = addr
        self._wake()

    def _wake(self):
        # מעיר את הצ'יפ, מפעיל auto-increment, ומגדיר MODE2
        self.bus.write_byte_data(self.addr, MODE1, AI)
        # MODE2 = 0x04: totem-pole, ללא INVRT גלובלי.
        # ההיפוך מטופל פר-ערוץ בתוכנה (INVERTED_CHANNELS).
        self.bus.write_byte_data(self.addr, MODE2, 0x04)
        time.sleep(0.001)

    def set_freq(self, hz):
        """קביעת תדר PWM לכל הערוצים (חייב להיכנס ל-sleep כדי לשנות PRESCALE)."""
        prescale = round(25_000_000 / (4096 * hz)) - 1
        prescale = max(3, min(255, prescale))
        old = self.bus.read_byte_data(self.addr, MODE1)
        self.bus.write_byte_data(self.addr, MODE1, (old & 0x7F) | SLEEP)  # sleep
        self.bus.write_byte_data(self.addr, PRESCALE, prescale)
        self.bus.write_byte_data(self.addr, MODE1, old)                   # wake
        time.sleep(0.005)
        self.bus.write_byte_data(self.addr, MODE1, old | RESTART | AI)

    def set_pwm(self, ch, on, off):
        """כתיבה גולמית: ON ו-OFF הם 12-ביט (0-4095)."""
        base = LED0_ON_L + 4 * ch
        self.bus.write_i2c_block_data(self.addr, base,
                                      [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

    def _write_full(self, ch, on_state):
        """כתיבת מצב מלא ברמת הרגיסטרים: on_state=True → full-ON, False → full-OFF."""
        if on_state:
            self.set_pwm(ch, 0x1000, 0)
        else:
            self.set_pwm(ch, 0, 0x1000)

    def set_duty(self, ch, percent):
        """קביעת duty לוגי באחוזים (0-100). מחיל היפוך פר-ערוץ אם נדרש.
        ערוץ ב-DIGITAL_CHANNELS מתנהג כמתג: כל ערך > 0 → ON מלא, 0 → OFF."""
        percent = max(0.0, min(100.0, percent))
        if ch in DIGITAL_CHANNELS:
            percent = 100.0 if percent > 0 else 0.0
        # היפוך תוכנה לערוצים עם דרייבר הופך
        eff = (100.0 - percent) if ch in INVERTED_CHANNELS else percent
        if eff <= 0:
            self._write_full(ch, False)
        elif eff >= 100:
            self._write_full(ch, True)
        else:
            self.set_pwm(ch, 0, int(eff / 100 * 4095))

    def on(self, ch):
        """הדלקה לוגית מלאה (מכבדת היפוך פר-ערוץ)."""
        self.set_duty(ch, 100)

    def off(self, ch):
        """כיבוי לוגי מלא (מכבד היפוך פר-ערוץ)."""
        self.set_duty(ch, 0)

    def name(self, label, percent):
        """שליטה לפי שם מהמיפוי, למשל name('HEATER', 25)."""
        self.set_duty(CHANNELS[label], percent)

    def close(self):
        self.bus.close()


def resolve_channel(token):
    """מקבל שם ('HEATER') או מספר ('6') ומחזיר מספר ערוץ."""
    if token.upper() in CHANNELS:
        return CHANNELS[token.upper()]
    if token.isdigit() and 0 <= int(token) <= 15:
        return int(token)
    raise ValueError(f"ערוץ לא מוכר: {token}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="שליטה ב-PCA9685 על לוח ה-IO (CureBox) מהטרמינל.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 pca9685.py set HEATER 25      # חימום ל-25%%
  python3 pca9685.py set RIGHT 50       # מאוורר ימני ל-50%%
  python3 pca9685.py set 6 30           # ערוץ 6 ל-30%% (לפי מספר)
  python3 pca9685.py on MOT1_EN         # הדלקה מלאה
  python3 pca9685.py off RIGHT          # כיבוי
  python3 pca9685.py freq 1000          # קביעת תדר PWM ל-1kHz
  python3 pca9685.py alloff             # כיבוי כל הערוצים
  python3 pca9685.py status             # הצגת מצב כל הערוצים
  python3 pca9685.py list               # רשימת שמות הערוצים
""")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="קביעת duty באחוזים")
    p_set.add_argument("channel")
    p_set.add_argument("percent", type=float)

    p_on = sub.add_parser("on", help="הדלקה מלאה")
    p_on.add_argument("channel")

    p_off = sub.add_parser("off", help="כיבוי")
    p_off.add_argument("channel")

    p_freq = sub.add_parser("freq", help="קביעת תדר PWM (Hz)")
    p_freq.add_argument("hz", type=float)

    p_rpm = sub.add_parser("rpm", help="קריאת מהירות מאוורר (RPM) מהטכו")
    p_rpm.add_argument("fan", nargs="?", default="all",
                       help="שם מאוורר (HEATER/DOOR/RIGHT/LEFT/BACK/CHAMBER) או 'all'")
    p_rpm.add_argument("--window", type=float, default=1.0,
                       help="חלון מדידה בשניות (ברירת מחדל 1.0)")

    p_wd = sub.add_parser("watchdog", help="ניטור בטיחות: כיבוי מאוורר שנפל מתחת ל-80% מהנקוב")
    p_wd.add_argument("fans", nargs="*",
                      help="מאווררים: 'RIGHT LEFT' או עם duty 'RIGHT=80 BACK=100' (ריק = כולם)")
    p_wd.add_argument("--duty", type=float, default=100, help="duty ברירת מחדל למאוורר בלי ערך מפורש")
    p_wd.add_argument("--poll", type=float, default=2.0, help="מרווח בדיקה בשניות")
    p_wd.add_argument("--action", choices=["off", "reduce"], default="off",
                      help="off=כיבוי | reduce=הורדת 20%% (ברירת מחדל off)")

    sub.add_parser("alloff", help="כיבוי כל הערוצים")
    sub.add_parser("status", help="מצב כל הערוצים")
    sub.add_parser("list", help="רשימת השמות")

    args = parser.parse_args()

    if args.cmd == "list":
        for name, ch in CHANNELS.items():
            print(f"  {ch:>2}  {name}")
        return

    if args.cmd == "watchdog":
        duties = {}
        for spec in args.fans:
            if "=" in spec:
                name, _, val = spec.partition("=")
                name, val = name.upper(), float(val)
            else:
                name, val = spec.upper(), args.duty
            if name not in FANS:
                raise SystemExit(f"מאוורר לא מוכר: {spec} (HEATER/DOOR/RIGHT/LEFT/BACK/CHAMBER)")
            duties[name] = val
        watchdog(duties=duties or None, poll=args.poll, action=args.action)
        return

    if args.cmd == "rpm":
        if args.fan.lower() == "all":
            rpms = read_all_rpm(args.window)
            for name in FANS:
                print(f"  {name}: {rpms[name]:.0f} RPM")
        else:
            name = args.fan.upper()
            if name not in FANS:
                raise SystemExit(f"מאוורר לא מוכר: {args.fan} (HEATER/DOOR/RIGHT/LEFT/BACK/CHAMBER)")
            t = FanTach(FANS[name]["tach"])
            try:
                print(f"  {name}: {t.read_rpm(args.window):.0f} RPM")
            finally:
                t.close()
        return

    pca = PCA9685()
    try:
        if args.cmd == "set":
            ch = resolve_channel(args.channel)
            pca.set_duty(ch, args.percent)
            print(f"ערוץ {ch} ({args.channel}) → {args.percent}%")
        elif args.cmd == "on":
            ch = resolve_channel(args.channel)
            pca.on(ch)
            print(f"ערוץ {ch} ({args.channel}) → ON")
        elif args.cmd == "off":
            ch = resolve_channel(args.channel)
            pca.off(ch)
            print(f"ערוץ {ch} ({args.channel}) → OFF")
        elif args.cmd == "freq":
            pca.set_freq(args.hz)
            print(f"תדר PWM → {args.hz} Hz")
        elif args.cmd == "alloff":
            for ch in range(16):
                pca.off(ch)
            print("כל הערוצים כובו")
        elif args.cmd == "status":
            names = {v: k for k, v in CHANNELS.items()}
            for ch in range(16):
                base = LED0_ON_L + 4 * ch
                data = pca.bus.read_i2c_block_data(pca.addr, base, 4)
                on = data[0] | (data[1] << 8)
                off = data[2] | (data[3] << 8)
                inv = ch in INVERTED_CHANNELS
                if on & 0x1000:                      # physical full-ON
                    state = "OFF (full)" if inv else "ON (full)"
                elif off & 0x1000:                   # physical full-OFF
                    state = "ON (full)" if inv else "OFF (full)"
                else:
                    pct = off / 4095 * 100
                    if inv:
                        pct = 100 - pct              # החזרה לערך הלוגי
                    state = f"{pct:.0f}%"
                tag = " (inv)" if inv else ""
                print(f"  {ch:>2} {names.get(ch, ''):<13} {state}{tag}")
    finally:
        pca.close()


if __name__ == "__main__":
    main()
