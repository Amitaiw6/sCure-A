#!/usr/bin/env python3
"""
שליטה במרחיב ה-I/O מסוג TCA6424A על לוח ה-CureBox.
באס: /dev/i2c-0 | כתובת: 0x23

שולט במנועים (גשר-H), בברזים ובאות ה-NFC_RESET.

⚠️ מיפוי הפינים (PINS) נקרא מהסכמטיק וייתכן שאינו מדויק — אמת מול הסכמטיק
   לפני הסתמכות. כל ערך הוא (port, bit): port 0/1/2, bit 0-7 (לדוגמה P23 = (2, 3)).
"""

from smbus2 import SMBus

BUS = 0
ADDR = 0x23

# --- רגיסטרים (עם auto-increment דרך ביט 0x80) ---
REG_INPUT  = 0x80   # קריאת קלט, פורטים 0-2
REG_OUTPUT = 0x84   # כתיבת פלט, פורטים 0-2
REG_CONFIG = 0x8C   # כיוון: 0=output, 1=input

# מיפוי האותות לפינים (מאומת מול הסכמטיק).
PINS = {
    "NFC_RESET":  (0, 1),   # P01 — פעיל-נמוך
    "LED_SWITCH": (0, 5),   # P05
    "FAN1_ONOFF": (1, 1),   # P11
    "FAN2_ONOFF": (1, 2),   # P12
    "FAN3_ONOFF": (1, 3),   # P13
    "FAN4_ONOFF": (1, 4),   # P14
    "FAN5_ONOFF": (1, 5),   # P15
    "FAN6_ONOFF": (1, 6),   # P16
    "MOT1_IN1":   (2, 5),   # P25
    "MOT1_IN2":   (2, 4),   # P24
    "MOT2_IN1":   (2, 2),   # P22
    "MOT2_IN2":   (2, 1),   # P21
    "VALVE_2_ON": (2, 6),   # P26
    "VALVE_1_ON": (2, 7),   # P27
}

# ערכים בטוחים באתחול (כל השאר = 0). אותות פעילי-נמוך מתחילים גבוה.
SAFE_HIGH = {"NFC_RESET"}

# פינים עם היפוך לוגי (פעיל-נמוך / דרייבר הופך): פקודה לוגית 1 → רמה פיזית 0.
# מאומת: אותות ה-ONOFF הפוכים. ⚠️ בדוק פינים נוספים והוסף לכאן לפי הצורך.
INVERTED_PINS = {
    "FAN1_ONOFF", "FAN2_ONOFF", "FAN3_ONOFF",
    "FAN4_ONOFF", "FAN5_ONOFF", "FAN6_ONOFF",
}


class TCA6424A:
    def __init__(self, bus=BUS, addr=ADDR):
        self.bus = SMBus(bus)
        self.addr = addr
        self.out = [0x00, 0x00, 0x00]   # shadow של רגיסטרי הפלט (פורט 0,1,2)
        self._safe_init()

    def _safe_init(self):
        """קובע ערכים בטוחים, ואז מגדיר את הפינים שבשימוש כיציאות."""
        # 1. ערכים בטוחים ב-shadow (רמות פיזיות):
        #    - SAFE_HIGH: רמה פיזית גבוהה.
        #    - INVERTED_PINS: מצב OFF לוגי = רמה פיזית גבוהה (כי הם הפוכים).
        for name in SAFE_HIGH:
            port, bit = PINS[name]
            self.out[port] |= (1 << bit)
        for name in INVERTED_PINS:
            port, bit = PINS[name]
            self.out[port] |= (1 << bit)   # OFF לוגי = רמה גבוהה
        # 2. כתיבת הפלט הבטוח בעוד הפינים עדיין קלט (ללא השפעה פיזית)
        self.bus.write_i2c_block_data(self.addr, REG_OUTPUT, self.out)
        # 3. הגדרת כיוון: כל פין שבמיפוי = output (0), השאר = input (1)
        cfg = [0xFF, 0xFF, 0xFF]
        for port, bit in PINS.values():
            cfg[port] &= ~(1 << bit)
        self.bus.write_i2c_block_data(self.addr, REG_CONFIG, cfg)

    def _commit(self):
        self.bus.write_i2c_block_data(self.addr, REG_OUTPUT, self.out)

    def set_pin(self, name, value):
        """קובע פין בודד לפי שם (0/1 לוגי). מחיל היפוך אם הפין ב-INVERTED_PINS."""
        port, bit = PINS[name]
        level = (0 if value else 1) if name in INVERTED_PINS else (1 if value else 0)
        if level:
            self.out[port] |= (1 << bit)
        else:
            self.out[port] &= ~(1 << bit)
        self._commit()

    def get_pin(self, name):
        """קורא את המצב הלוגי של הפין (מתקן היפוך אם נדרש)."""
        port, bit = PINS[name]
        data = self.bus.read_i2c_block_data(self.addr, REG_INPUT, 3)
        level = (data[port] >> bit) & 1
        return (1 - level) if name in INVERTED_PINS else level

    def motor(self, n, direction):
        """
        שליטה במנוע (שני אותות IN, ללא EN). direction אחד מ:
          'fwd'   → IN1=1, IN2=0
          'rev'   → IN1=0, IN2=1
          'stop'  → IN1=0, IN2=0 (coast — שני הקלטים נמוכים)
          'brake' → IN1=1, IN2=1 (בלימה — שני הקלטים גבוהים)
        """
        in1, in2 = f"MOT{n}_IN1", f"MOT{n}_IN2"

        def setbit(name, val):
            b = PINS[name][1]
            if val:
                self.out[PINS[name][0]] |= (1 << b)
            else:
                self.out[PINS[name][0]] &= ~(1 << b)

        if direction == "fwd":
            setbit(in1, 1); setbit(in2, 0)
        elif direction == "rev":
            setbit(in1, 0); setbit(in2, 1)
        elif direction == "brake":
            setbit(in1, 1); setbit(in2, 1)
        elif direction == "stop":
            setbit(in1, 0); setbit(in2, 0)
        else:
            raise ValueError("direction: fwd/rev/stop/brake")
        self._commit()

    def diagnose(self, name):
        """אבחון פר-פין: קורא ישירות מהצ'יפ את הכיוון, הרמה המונעת והרמה הנמדדת."""
        port, bit = PINS[name]
        cfg = self.bus.read_i2c_block_data(self.addr, REG_CONFIG, 3)
        out = self.bus.read_i2c_block_data(self.addr, REG_OUTPUT, 3)
        inp = self.bus.read_i2c_block_data(self.addr, REG_INPUT, 3)
        is_output = not ((cfg[port] >> bit) & 1)     # 0 = output
        driven = (out[port] >> bit) & 1
        measured = (inp[port] >> bit) & 1
        return {
            "pin": f"P{port}{bit}",
            "direction": "output" if is_output else "input",
            "driven_level": driven,
            "measured_level": measured,
        }

    def valve(self, n, on):
        """פתיחה/סגירה של ברז (1/2)."""
        self.set_pin(f"VALVE_{n}_ON", 1 if on else 0)

    def fan_onoff(self, n, on):
        """חיבור/ניתוק הזנת מאוורר ה-ONOFF (1-6) שעל המרחיב — רכיב נפרד."""
        self.set_pin(f"FAN{n}_ONOFF", 1 if on else 0)

    def nfc_reset(self, pulse=True):
        """פולס reset ל-NFC (פעיל-נמוך): נמוך לרגע ואז חזרה לגבוה."""
        import time
        self.set_pin("NFC_RESET", 0)
        time.sleep(0.01)
        self.set_pin("NFC_RESET", 1)

    def all_safe(self):
        """החזרת כל הרכיבים למצב בטוח: מנועים מנוטרלים, ברזים סגורים."""
        for n in (1, 2):
            self.motor(n, "stop")
            self.valve(n, False)

    def close(self):
        self.bus.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="שליטה במרחיב TCA6424A (מנועים/ברזים/NFC) מהטרמינל.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 tca6424a.py motor 1 fwd      # מנוע 1 קדימה
  python3 tca6424a.py motor 1 rev      # מנוע 1 אחורה
  python3 tca6424a.py motor 1 stop     # עצירה (coast)
  python3 tca6424a.py motor 2 brake    # בלימת מנוע 2
  python3 tca6424a.py valve 1 on       # פתיחת ברז 1
  python3 tca6424a.py valve 2 off      # סגירת ברז 2
  python3 tca6424a.py pin VALVE_1_ON 1 # שליטה ישירה בפין לפי שם
  python3 tca6424a.py nfc-reset        # פולס reset ל-NFC
  python3 tca6424a.py safe             # החזרת הכל למצב בטוח
  python3 tca6424a.py status           # קריאת מצב כל הפינים
  python3 tca6424a.py list             # רשימת הפינים והמיפוי
""")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_m = sub.add_parser("motor", help="שליטת כיוון במנוע")
    p_m.add_argument("n", type=int, choices=[1, 2])
    p_m.add_argument("direction", choices=["fwd", "rev", "stop", "brake"])

    p_v = sub.add_parser("valve", help="פתיחה/סגירת ברז")
    p_v.add_argument("n", type=int, choices=[1, 2])
    p_v.add_argument("state", choices=["on", "off"])

    p_p = sub.add_parser("pin", help="שליטה ישירה בפין לפי שם")
    p_p.add_argument("name")
    p_p.add_argument("value", type=int, choices=[0, 1])

    sub.add_parser("nfc-reset", help="פולס reset ל-NFC")
    sub.add_parser("safe", help="החזרת הכל למצב בטוח")
    sub.add_parser("status", help="קריאת מצב כל הפינים")
    sub.add_parser("list", help="רשימת הפינים")

    p_d = sub.add_parser("diag", help="אבחון פין: כיוון, רמה מונעת ורמה נמדדת")
    p_d.add_argument("name")

    args = parser.parse_args()

    if args.cmd == "list":
        for name, (port, bit) in PINS.items():
            print(f"  {name:<12} P{port}{bit}")
        return

    io = TCA6424A()
    try:
        if args.cmd == "motor":
            io.motor(args.n, args.direction)
            print(f"מנוע {args.n} → {args.direction}")
        elif args.cmd == "valve":
            io.valve(args.n, args.state == "on")
            print(f"ברז {args.n} → {args.state}")
        elif args.cmd == "pin":
            io.set_pin(args.name.upper(), args.value)
            print(f"{args.name.upper()} → {args.value}")
        elif args.cmd == "nfc-reset":
            io.nfc_reset()
            print("בוצע פולס reset ל-NFC")
        elif args.cmd == "safe":
            io.all_safe()
            print("כל הרכיבים הוחזרו למצב בטוח")
        elif args.cmd == "status":
            for name in PINS:
                print(f"  {name:<12} {io.get_pin(name)}")
        elif args.cmd == "diag":
            name = args.name.upper()
            if name not in PINS:
                raise SystemExit(f"פין לא מוכר: {name}")
            d = io.diagnose(name)
            inv = name in INVERTED_PINS
            print(f"  פין:           {name} ({d['pin']})")
            print(f"  כיוון:          {d['direction']}")
            print(f"  רמה מונעת:      {d['driven_level']}  (0=נמוך, 1=גבוה)")
            print(f"  רמה נמדדת:      {d['measured_level']}")
            print(f"  היפוך בתוכנה:   {'כן' if inv else 'לא'}")
    finally:
        io.close()


if __name__ == "__main__":
    main()
