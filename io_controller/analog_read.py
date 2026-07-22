#!/usr/bin/env python3
"""
קריאה אנלוגית עבור לוח ה-CureBox.
שני ממירי ADS1115 על באסים נפרדים, הקוראים שמונה ערוצים אנלוגיים:

  U10 (i2c-1):  LIGHT1 / LIGHT2          — חיישני אור (AIN0 / AIN1)
                AIN2 / AIN3              — אותות J14 (מחלק 100K/100K → יחס 2.0)
  U8  (i2c-0):  SENSOR1_A1 / SENSOR1_A2  — חיישן 1 (AIN0 / AIN1)
                SENSOR2_A1 / SENSOR2_A2  — חיישן 2 (AIN2 / AIN3)

הערה: שמות הרשתות בסכמטיק הפוכים: "I2C0" = /dev/i2c-1, "I2C1" = /dev/i2c-0.

⚠️ אמת לפני שימוש:
   - כתובות הממירים: U10 מול i2cdetect -y 1, U8 מול i2cdetect -y 0
     (U8 חייב להיות שונה מ-0x49 שתפוס ע"י ממיר הטמפרטורה U6)
   - זהות האותות על AIN2/AIN3 של U10, ושנה את שמם בהתאם
"""

from smbus2 import SMBus
import time

# --- רגיסטרים של ADS1115 ---
REG_CONVERT = 0x00
REG_CONFIG  = 0x01

# --- הגדרות ADC ---
# PGA: 0 = ±6.144V. נבחר כי הממירים מוזנים ב-5V (הכניסות עשויות להגיע ל-5V).
PGA = 0
FS_VOLTAGE = {0: 6.144, 1: 4.096, 2: 2.048, 3: 1.024, 4: 0.512, 5: 0.256}
SUPPLY = 5.0         # מתח הזנה (V) — לחישוב הרמה היחסית באחוזים

# כל ממיר מוגדר עם הבאס והכתובת שלו. ⚠️ אמת מול i2cdetect על הבאס המתאים.
ADCS = {
    "U10": {"bus": 1, "addr": 0x48},   # חיישני אור — סכמטיק "I2C0" → i2c-1
    "U8":  {"bus": 0, "addr": 0x48},   # חיישנים     — סכמטיק "I2C1" → i2c-0
}

# מיפוי ערוצים: שם → (מזהה הממיר, ערוץ אנלוגי 0-3)
SENSORS = {
    "LIGHT1":     ("U10", 0),   # LIGHT1_ANALOG
    "LIGHT2":     ("U10", 1),   # LIGHT2_ANALOG
    "AIN2":       ("U10", 2),   # ⚠️ אות J14 — זהה ושנה שם
    "AIN3":       ("U10", 3),   # ⚠️ אות J14 — זהה ושנה שם
    "SENSOR1_A1": ("U8", 0),    # SENSOR1_ANALOG1
    "SENSOR1_A2": ("U8", 1),    # SENSOR1_ANALOG2
    "SENSOR2_A1": ("U8", 2),    # SENSOR2_ANALOG1
    "SENSOR2_A2": ("U8", 3),    # SENSOR2_ANALOG2
}

# ערוצים שעוברים מחלק מתח (יחס המחלק). 100K/100K = יחס 2.0.
DIVIDER_SCALE = {
    "AIN2": 2.0,
    "AIN3": 2.0,
}


class ADS1115:
    def __init__(self, bus, addr, pga=PGA):
        self.bus = bus
        self.addr = addr
        self.pga = pga

    def read_raw(self, channel):
        """קריאת ערך גולמי (single-ended) מערוץ 0-3."""
        mux = 0b100 + channel
        config = (
            (1 << 15) | (mux << 12) | (self.pga << 9) |
            (1 << 8) | (0b100 << 5) | 0b00011
        )
        self.bus.write_i2c_block_data(self.addr, REG_CONFIG,
                                      [(config >> 8) & 0xFF, config & 0xFF])
        for _ in range(50):
            time.sleep(0.002)
            cfg = self.bus.read_i2c_block_data(self.addr, REG_CONFIG, 2)
            if cfg[0] & 0x80:
                break
        data = self.bus.read_i2c_block_data(self.addr, REG_CONVERT, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 0x7FFF:
            raw -= 0x10000
        return raw

    def read_voltage(self, channel):
        raw = self.read_raw(channel)
        return raw * FS_VOLTAGE[self.pga] / 32768.0


def read_channel(adcs, name):
    """קריאת מתח (לאחר תיקון מחלק) ורמה יחסית עבור ערוץ בודד."""
    chip, ch = SENSORS[name]
    v = adcs[chip].read_voltage(ch) * DIVIDER_SCALE.get(name, 1.0)
    pct = max(0.0, min(100.0, v / SUPPLY * 100.0))
    return {"voltage": v, "percent": pct}


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="קריאה אנלוגית דרך שני ממירי ADS1115 (U10 על i2c-1, U8 על i2c-0).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 analog_read.py read              # כל הערוצים, פעם אחת
  python3 analog_read.py read SENSOR1_A1   # ערוץ בודד
  python3 analog_read.py raw               # מתח גולמי בלבד (לאימות)
  python3 analog_read.py monitor           # ניטור רציף
  python3 analog_read.py list              # רשימת הערוצים והמיפוי
""")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="קריאת ערוץ אנלוגי")
    p_read.add_argument("channel", nargs="?", default="all")

    sub.add_parser("raw", help="מתח גולמי בלבד (לאימות)")
    sub.add_parser("list", help="רשימת הערוצים")

    p_mon = sub.add_parser("monitor", help="ניטור רציף")
    p_mon.add_argument("--interval", type=float, default=1.0)

    args = parser.parse_args()

    if args.cmd == "list":
        for name, (chip, ch) in SENSORS.items():
            cfg = ADCS[chip]
            scale = DIVIDER_SCALE.get(name)
            extra = f"  (מחלק ×{scale:g})" if scale else ""
            print(f"  {name:<11} →  {chip} (i2c-{cfg['bus']}, 0x{cfg['addr']:02X}), AIN{ch}{extra}")
        return

    # פתיחת כל באס ייחודי פעם אחת, ובניית הממירים מעליו
    buses = {}
    for cfg in ADCS.values():
        if cfg["bus"] not in buses:
            buses[cfg["bus"]] = SMBus(cfg["bus"])
    adcs = {chip: ADS1115(buses[cfg["bus"]], cfg["addr"]) for chip, cfg in ADCS.items()}
    try:
        if args.cmd == "raw":
            for name, (chip, ch) in SENSORS.items():
                print(f"  {name}: {adcs[chip].read_voltage(ch):.4f} V")

        elif args.cmd == "read":
            names = list(SENSORS) if args.channel == "all" else [args.channel.upper()]
            for name in names:
                if name not in SENSORS:
                    raise SystemExit(f"ערוץ לא מוכר: {name}")
                d = read_channel(adcs, name)
                print(f"  {name:<11} {d['voltage']:.3f} V   ({d['percent']:.0f}%)")

        elif args.cmd == "monitor":
            print("ניטור רציף (Ctrl+C ליציאה)\n")
            try:
                while True:
                    line = [f"{name}={read_channel(adcs, name)['voltage']:.2f}V"
                            for name in SENSORS]
                    print("  " + "  ".join(line))
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nניטור הופסק.")
    finally:
        for b in buses.values():
            b.close()


if __name__ == "__main__":
    main()
