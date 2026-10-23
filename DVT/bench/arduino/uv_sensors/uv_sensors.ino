// sCure UV experiment: thermistor on A0, photoresistor on A1.
// Each sensor: 5V -> sensor -> Ax, and a 10k fixed resistor from Ax to GND.
// Prints "millis,ntc,ldr" as CSV every 200 ms at 115200 baud.

const int NTC_PIN = A0;
const int LDR_PIN = A1;
const unsigned long PERIOD_MS = 200;

void setup() {
  Serial.begin(115200);
  Serial.println("ms,ntc,ldr");
}

void loop() {
  static unsigned long last = 0;
  unsigned long now = millis();
  if (now - last >= PERIOD_MS) {
    last = now;
    // Average 8 samples per channel to reduce noise from the LED drivers.
    long ntc = 0, ldr = 0;
    for (int i = 0; i < 8; i++) {
      ntc += analogRead(NTC_PIN);
      ldr += analogRead(LDR_PIN);
    }
    Serial.print(now);
    Serial.print(',');
    Serial.print(ntc / 8);
    Serial.print(',');
    Serial.println(ldr / 8);
  }
}
