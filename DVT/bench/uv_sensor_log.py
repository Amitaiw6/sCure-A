"""Log thermistor (A0) + photoresistor (A1) from the Arduino Uno to CSV.

Usage:  python uv_sensor_log.py [COM3] [seconds] [out.csv]
Prints each line live and also writes it to the CSV. Ctrl+C stops early.
Sketch: scratchpad/uv_sensors/uv_sensors.ino (115200 baud, "ms,ntc,ldr").
"""
import sys, time, math
import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
out = sys.argv[3] if len(sys.argv) > 3 else time.strftime("uv_sensors_%Y%m%d_%H%M%S.csv")

R_FIXED = 10_000.0   # ohms, resistor from Ax to GND
R0, T0, BETA = 10_000.0, 298.15, 3950.0   # 10k NTC at 25 C, beta 3950 (edit if known)


def ntc_c(counts: int) -> float:
    """Convert a divider reading to degrees C (5V -> NTC -> Ax -> 10k -> GND)."""
    if counts <= 0 or counts >= 1023:
        return float("nan")
    r = R_FIXED * (1023.0 - counts) / counts
    return 1.0 / (1.0 / T0 + math.log(r / R0) / BETA) - 273.15


with serial.Serial(port, 115200, timeout=1) as s, open(out, "w", newline="") as f:
    time.sleep(2)  # the Uno resets when the port opens
    s.reset_input_buffer()
    f.write("host_time,ms,ntc_counts,ldr_counts,ntc_c\n")
    print(f"logging {port} -> {out} for {secs:.0f} s (Ctrl+C to stop)")
    t_end = time.time() + secs
    try:
        while time.time() < t_end:
            line = s.readline().decode(errors="ignore").strip()
            if not line or line.startswith("ms"):
                continue
            try:
                ms, ntc, ldr = (int(x) for x in line.split(","))
            except ValueError:
                continue
            tc = ntc_c(ntc)
            row = f"{time.time():.3f},{ms},{ntc},{ldr},{tc:.2f}"
            f.write(row + "\n")
            print(f"{ms:>8} ms  NTC {ntc:4d} ({tc:5.1f} C)  LDR {ldr:4d}")
    except KeyboardInterrupt:
        pass
print(f"saved {out}")
