#!/usr/bin/env python3
"""
שליטה ביציאות GPIO דיגיטליות ישירות של ה-CM5 (הפעלה/כיבוי).
מרכז רכיבים הנשלטים ישירות מפין GPIO, להבדיל מרכיבי I2C/PWM.

מימוש מבוסס pinctrl: המצב נשמר לאחר סיום הפקודה (חיוני לרכיב נועל כמו ברז),
בניגוד ל-gpiozero שעלול לשחרר/לאפס את הפין עם סיום התהליך.

הערה: הגדרת הפין אינה שורדת אתחול. לקיבוע קבוע יש להשתמש בשירות הפעלה.

⚠️ פולריות: ברירת המחדל היא ישירה (on → רמה גבוהה). אם רכיב מתברר כהפוך,
   הוסף את שמו ל-INVERTED.
"""

import subprocess

# מיפוי אותות: שם → מספר GPIO (BCM)
SIGNALS = {
    "NITROGEN_VALVE": 13,   # ברז החנקן — GPIO13
}

# אותות עם היפוך לוגי (on לוגי = רמה פיזית נמוכה).
INVERTED = set()


def _pinctrl(*args):
    """הרצת pinctrl והחזרת הפלט; שגיאה אם הפקודה נכשלה."""
    res = subprocess.run(["pinctrl", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"pinctrl נכשל: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def set_signal(name, on):
    """הפעלה/כיבוי לוגי של אות לפי שם. מחיל היפוך אם האות ב-INVERTED."""
    if name not in SIGNALS:
        raise ValueError(f"אות לא מוכר: {name}")
    gpio = SIGNALS[name]
    level = (not on) if name in INVERTED else bool(on)
    _pinctrl("set", str(gpio), "op", "dh" if level else "dl")


def get_signal(name):
    """קריאת המצב הלוגי של אות (מתקן היפוך אם נדרש). מחזיר 0/1 או None."""
    if name not in SIGNALS:
        raise ValueError(f"אות לא מוכר: {name}")
    gpio = SIGNALS[name]
    out = _pinctrl("get", str(gpio)).lower()
    if "hi" in out:
        phys = 1
    elif "lo" in out:
        phys = 0
    else:
        return None
    return (1 - phys) if name in INVERTED else phys


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="שליטה ביציאות GPIO דיגיטליות ישירות של ה-CM5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 gpio_control.py on NITROGEN_VALVE    # פתיחת ברז החנקן
  python3 gpio_control.py off NITROGEN_VALVE   # סגירת ברז החנקן
  python3 gpio_control.py status               # מצב כל האותות
  python3 gpio_control.py status NITROGEN_VALVE
  python3 gpio_control.py list                 # רשימת האותות והמיפוי
""")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_on = sub.add_parser("on", help="הפעלת אות")
    p_on.add_argument("name")

    p_off = sub.add_parser("off", help="כיבוי אות")
    p_off.add_argument("name")

    p_st = sub.add_parser("status", help="קריאת מצב אות/אותות")
    p_st.add_argument("name", nargs="?", default="all")

    sub.add_parser("list", help="רשימת האותות")

    args = parser.parse_args()

    if args.cmd == "list":
        for name, gpio in SIGNALS.items():
            inv = "  (הפוך)" if name in INVERTED else ""
            print(f"  {name:<16} GPIO{gpio}{inv}")
        return

    if args.cmd == "on":
        set_signal(args.name.upper(), True)
        print(f"{args.name.upper()} → ON")
    elif args.cmd == "off":
        set_signal(args.name.upper(), False)
        print(f"{args.name.upper()} → OFF")
    elif args.cmd == "status":
        names = list(SIGNALS) if args.name == "all" else [args.name.upper()]
        for name in names:
            if name not in SIGNALS:
                raise SystemExit(f"אות לא מוכר: {name}")
            v = get_signal(name)
            print(f"  {name:<16} {v if v is not None else '?'}")


if __name__ == "__main__":
    main()
