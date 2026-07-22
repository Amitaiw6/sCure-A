#!/usr/bin/env python3
"""
מערכת קריאת טמפרטורה עבור לוח ה-CureBox.
שני ממירי ADS1115 על /dev/i2c-0, הקוראים טרמיסטורי NTC.

שרשרת המרה: קוד ADC → מתח → התנגדות NTC → טמפרטורה (משוואת בטא).

⚠️ אמת לפני שימוש:
   - כתובות הממירים מול i2cdetect: U6 על i2c-0, U7 על i2c-1
   - פרמטרי ה-NTC (NTC_R0, NTC_BETA) מהדאטה-שיט של הטרמיסטור
   - הנגד הקבוע במחלק (R_SERIES) וטופולוגיית המחלק (DIVIDER)
"""

from smbus2 import SMBus
import time
import math

# כל ממיר מוגדר עם הבאס והכתובת שלו.
# שמות הרשתות בסכמטיק הפוכים: "I2C1" = /dev/i2c-0, "I2C0" = /dev/i2c-1.
# ⚠️ אמת את הכתובות מול i2cdetect על הבאס המתאים לכל ממיר.
ADCS = {
    "U6": {"bus": 0, "addr": 0x49},   # NTC1-4 — סכמטיק "I2C1" → /dev/i2c-0
    "U7": {"bus": 1, "addr": 0x49},   # NTC5-7 — סכמטיק "I2C0" → /dev/i2c-1
}

# --- רגיסטרים של ADS1115 ---
REG_CONVERT = 0x00
REG_CONFIG  = 0x01

# --- הגדרות ADC ---
# PGA: בחירת טווח מלא. 1 = ±4.096V (מתאים להזנת 3.3V).
PGA = 1
FS_VOLTAGE = {0: 6.144, 1: 4.096, 2: 2.048, 3: 1.024, 4: 0.512, 5: 0.256}

# --- פרמטרי הטרמיסטור (NTC) — Murata NCP21XV103J03RA ---
NTC_R0    = 10000.0    # התנגדות נקובה ב-25°C (אוהם)
NTC_BETA  = 3934.0     # מקדם בטא B25/85 (מהדאטה-שיט של Murata)
NTC_T0    = 298.15     # 25°C בקלווין
R_SERIES  = 10000.0    # ⚠️ נגד קבוע במחלק — אמת מול הסכמטיק
VREF      = 3.3        # מתח הזנת המחלק (V)

# טופולוגיית המחלק:
#   "pullup"   → Vcc—R_SERIES—[מדידה]—NTC—GND  (NTC לכיוון הארקה)
#   "pulldown" → Vcc—NTC—[מדידה]—R_SERIES—GND  (NTC לכיוון המתח)
DIVIDER = "pullup"

# מיפוי חיישנים: שם → (מזהה הממיר, ערוץ אנלוגי 0-3)
SENSORS = {
    "NTC1": ("U6", 0), "NTC2": ("U6", 1),
    "NTC3": ("U6", 2), "NTC4": ("U6", 3),
    "NTC5": ("U7", 0), "NTC6": ("U7", 1),
    "NTC7": ("U7", 2),
}


class ADS1115:
    def __init__(self, bus, addr, pga=PGA):
        self.bus = bus
        self.addr = addr
        self.pga = pga

    def read_raw(self, channel):
        """קריאת ערך גולמי (single-ended) מערוץ 0-3."""
        mux = 0b100 + channel          # single-ended AIN<channel>
        config = (
            (1 << 15) |                # OS: התחל המרה בודדת
            (mux << 12) |              # MUX
            (self.pga << 9) |          # PGA
            (1 << 8) |                 # MODE: single-shot
            (0b100 << 5) |             # DR: 128 SPS
            0b00011                    # COMP_QUE=11 (מבטל את המשווה)
        )
        self.bus.write_i2c_block_data(self.addr, REG_CONFIG,
                                      [(config >> 8) & 0xFF, config & 0xFF])
        # המתנה לסיום ההמרה (poll על ביט ה-OS)
        for _ in range(50):
            time.sleep(0.002)
            cfg = self.bus.read_i2c_block_data(self.addr, REG_CONFIG, 2)
            if (cfg[0] & 0x80):        # OS=1 → ההמרה הסתיימה
                break
        data = self.bus.read_i2c_block_data(self.addr, REG_CONVERT, 2)
        raw = (data[0] << 8) | data[1]
        if raw > 0x7FFF:               # 16-bit signed
            raw -= 0x10000
        return raw

    def read_voltage(self, channel):
        raw = self.read_raw(channel)
        return raw * FS_VOLTAGE[self.pga] / 32768.0


def voltage_to_resistance(v):
    """המרת מתח המחלק להתנגדות הטרמיסטור."""
    if v <= 0 or v >= VREF:
        return None                    # מחוץ לטווח — חיישן מנותק/קצר
    if DIVIDER == "pullup":
        return R_SERIES * v / (VREF - v)
    else:  # pulldown
        return R_SERIES * (VREF - v) / v


def resistance_to_temp(r):
    """משוואת בטא: התנגדות → טמפרטורה ב-°C."""
    if r is None or r <= 0:
        return None
    inv_t = (1.0 / NTC_T0) + (1.0 / NTC_BETA) * math.log(r / NTC_R0)
    return (1.0 / inv_t) - 273.15


def read_sensor(adcs, name):
    """קריאת טמפרטורה, מתח והתנגדות עבור חיישן בודד."""
    chip, ch = SENSORS[name]
    v = adcs[chip].read_voltage(ch)
    r = voltage_to_resistance(v)
    t = resistance_to_temp(r)
    return {"voltage": v, "resistance": r, "temp": t}


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="קריאת טמפרטורה מטרמיסטורי NTC דרך ADS1115 על i2c-0.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""דוגמאות:
  python3 temp_monitor.py read           # כל החיישנים, פעם אחת
  python3 temp_monitor.py read NTC1      # חיישן בודד
  python3 temp_monitor.py raw            # מתח גולמי בלבד (לאימות)
  python3 temp_monitor.py monitor        # ניטור רציף, מתעדכן כל שנייה
  python3 temp_monitor.py list           # רשימת החיישנים והמיפוי
""")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="קריאת טמפרטורה")
    p_read.add_argument("sensor", nargs="?", default="all")

    sub.add_parser("raw", help="מתח גולמי בלבד (לאימות)")
    sub.add_parser("list", help="רשימת החיישנים")

    p_mon = sub.add_parser("monitor", help="ניטור רציף")
    p_mon.add_argument("--interval", type=float, default=1.0)

    args = parser.parse_args()

    if args.cmd == "list":
        for name, (chip, ch) in SENSORS.items():
            cfg = ADCS[chip]
            print(f"  {name}  →  {chip} (i2c-{cfg['bus']}, 0x{cfg['addr']:02X}), AIN{ch}")
        return

    # פתיחת כל באס ייחודי פעם אחת, ובניית הממירים מעליו
    buses = {}
    for cfg in ADCS.values():
        if cfg["bus"] not in buses:
            buses[cfg["bus"]] = SMBus(cfg["bus"])
    adcs = {chip: ADS1115(buses[cfg["bus"]], cfg["addr"]) for chip, cfg in ADCS.items()}
    try:
        if args.cmd == "raw":
            for name in SENSORS:
                chip, ch = SENSORS[name]
                v = adcs[chip].read_voltage(ch)
                print(f"  {name}: {v:.4f} V")

        elif args.cmd == "read":
            names = list(SENSORS) if args.sensor == "all" else [args.sensor.upper()]
            for name in names:
                if name not in SENSORS:
                    raise SystemExit(f"חיישן לא מוכר: {name}")
                d = read_sensor(adcs, name)
                t = f"{d['temp']:.1f}°C" if d["temp"] is not None else "—"
                print(f"  {name}: {t}   ({d['voltage']:.3f} V)")

        elif args.cmd == "monitor":
            print("ניטור רציף (Ctrl+C ליציאה)\n")
            try:
                while True:
                    line = []
                    for name in SENSORS:
                        d = read_sensor(adcs, name)
                        t = f"{d['temp']:.1f}" if d["temp"] is not None else "—"
                        line.append(f"{name}={t}°C")
                    print("  " + "  ".join(line))
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nניטור הופסק.")
    finally:
        for b in buses.values():
            b.close()


if __name__ == "__main__":
    main()
