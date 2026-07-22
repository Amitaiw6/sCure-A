#!/usr/bin/env python3
"""
שליטה במנוע SG90 ישירות דרך GPIO של ה-CM5 (PWM תוכנה דרך gpiozero/lgpio).

ברירת מחדל: GPIO8.
⚠️ GPIO8 הוא SPI0 CE0. אם SPI מופעל (dtparam=spi=on) הפין עלול להיות תפוס.
   במקרה כזה בטל SPI או שנה את PIN לפין פנוי (למשל 12/13/18/19).
"""

from gpiozero import AngularServo
from time import sleep

PIN = 8

# טווח רוחבי הפולס של SG90/MG90S (בשניות). 0.5ms..2.4ms נותן ~0..180°.
# אם המנוע לא מגיע לקצוות או "מזמזם" בקצה — כייל את הערכים האלה.
MIN_PULSE = 0.0005   # 500µs  → זווית מינימלית
MAX_PULSE = 0.0024   # 2400µs → זווית מקסימלית
MIN_ANGLE = 0
MAX_ANGLE = 180

# אות הבקרה הפוך בחומרה (פקודת high נותנת low ולהפך) → active_high=False.
INVERTED = True


def make_servo(pin=PIN):
    return AngularServo(
        pin,
        min_angle=MIN_ANGLE, max_angle=MAX_ANGLE,
        min_pulse_width=MIN_PULSE, max_pulse_width=MAX_PULSE,
    )


def goto(servo, angle):
    """מיקום המנוע בזווית מבוקשת (במעלות). מחיל היפוך אם INVERTED."""
    angle = max(MIN_ANGLE, min(MAX_ANGLE, angle))
    phys = (MAX_ANGLE + MIN_ANGLE - angle) if INVERTED else angle
    servo.angle = phys
    return angle


def sweep(servo, step=10, delay=0.05, cycles=2):
    """סריקה הלוך-ושוב על כל הטווח — שימושי לבדיקת כיוון וטווח."""
    for _ in range(cycles):
        for a in range(MIN_ANGLE, MAX_ANGLE + 1, step):
            goto(servo, a)
            sleep(delay)
        for a in range(MAX_ANGLE, MIN_ANGLE - 1, -step):
            goto(servo, a)
            sleep(delay)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="שליטה במנוע SG90 דרך GPIO של ה-CM5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 servo.py angle 90       # מיקום במרכז (90°)
  python3 servo.py angle 0        # קצה אחד
  python3 servo.py angle 180      # קצה נגדי
  python3 servo.py min            # זווית מינימלית
  python3 servo.py max            # זווית מקסימלית
  python3 servo.py center         # מרכז
  python3 servo.py sweep          # סריקה הלוך-ושוב (בדיקת טווח/כיוון)
  python3 servo.py --pin 12 angle 45   # שימוש בפין אחר
""")
    parser.add_argument("--pin", type=int, default=PIN, help=f"GPIO (ברירת מחדל {PIN})")
    parser.add_argument("--hold", type=float, default=1.0,
                        help="שניות להחזקת המיקום לפני שחרור (ברירת מחדל 1.0)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_angle = sub.add_parser("angle", help="מיקום בזווית מבוקשת")
    p_angle.add_argument("deg", type=float)

    sub.add_parser("min", help="זווית מינימלית")
    sub.add_parser("max", help="זווית מקסימלית")
    sub.add_parser("center", help="מרכז (אמצע הטווח)")

    p_sweep = sub.add_parser("sweep", help="סריקה הלוך-ושוב")
    p_sweep.add_argument("--step", type=int, default=10)
    p_sweep.add_argument("--delay", type=float, default=0.05)
    p_sweep.add_argument("--cycles", type=int, default=2)

    args = parser.parse_args()

    servo = make_servo(args.pin)
    try:
        if args.cmd == "angle":
            print(f"זווית → {goto(servo, args.deg)}°")
            sleep(args.hold)
        elif args.cmd == "min":
            print(f"זווית → {goto(servo, MIN_ANGLE)}°")
            sleep(args.hold)
        elif args.cmd == "max":
            print(f"זווית → {goto(servo, MAX_ANGLE)}°")
            sleep(args.hold)
        elif args.cmd == "center":
            print(f"זווית → {goto(servo, (MIN_ANGLE + MAX_ANGLE) / 2)}°")
            sleep(args.hold)
        elif args.cmd == "sweep":
            sweep(servo, step=args.step, delay=args.delay, cycles=args.cycles)
            print("סריקה הושלמה")
    finally:
        # שחרור הפולס → המנוע מפסיק לקבל אות (מפסיק "לזמזם")
        servo.detach()
        servo.close()


if __name__ == "__main__":
    main()
