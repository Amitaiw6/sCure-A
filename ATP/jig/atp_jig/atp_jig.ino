/*
  sCure ATP jig - Arduino Uno firmware
  Turns the StarBright sensor head (on a 270 degree servo) at the chamber centre,
  commanded by the CureBox over USB serial.

  Wiring: servo signal -> D9 (Timer1 OC1A). Servo power from its own 5-6 V supply,
  ground shared with the Uno. The Uno's 5 V pin must not power the servo.

  Serial: 115200 8N1, one command per line (\n or \r\n), one reply line per command.
    ID?             -> ATP-JIG <version> servo=D9 range=0-270 min_us=<a> max_us=<b>
    MOVE <deg>      -> OK MOVE <deg> eta_ms=<n>   ... then DONE <deg> when the travel time has passed
    POS?            -> POS <deg> moving=<0|1> on=<0|1>
    OFF             -> OK OFF          (pulses stop, servo goes limp)
    PULSE <us>      -> OK PULSE <us>   (raw pulse 400-2600 us, for finding the end stops)
    CAL <min> <max> -> OK CAL <min> <max>  (pulse widths for 0 and 270 deg, kept in EEPROM)
    anything else   -> ERR <reason>

  Safety: the servo does not move at power-up or reset - pulses start only on the first MOVE or PULSE.
*/
#include <EEPROM.h>

const char *VERSION = "0.1.0";
const float RANGE_DEG = 270.0;
const uint16_t DEFAULT_MIN_US = 500, DEFAULT_MAX_US = 2500;
const uint16_t ABS_MIN_US = 400, ABS_MAX_US = 2600;
const uint16_t MS_PER_DEG = 4, SETTLE_MS = 300;   // travel estimate, about 0.24 s per 60 deg plus settling
const uint16_t EE_MAGIC = 0xA7A1;

uint16_t minUs = DEFAULT_MIN_US, maxUs = DEFAULT_MAX_US;
float posDeg = -1;          // unknown until the first move
bool pulsesOn = false;
bool moving = false;
unsigned long doneAt = 0;
char line[48];
uint8_t len = 0;

void loadCal() {
  uint16_t m, a, b;
  EEPROM.get(0, m); EEPROM.get(2, a); EEPROM.get(4, b);
  if (m == EE_MAGIC && a >= ABS_MIN_US && b <= ABS_MAX_US && a < b) { minUs = a; maxUs = b; }
}

void saveCal() {
  EEPROM.put(0, EE_MAGIC); EEPROM.put(2, minUs); EEPROM.put(4, maxUs);
}

// Timer1, fast PWM mode 14 (TOP = ICR1), prescaler 8 -> 0.5 us per tick, 20 ms period.
void pulseUs(uint16_t us) {
  if (!pulsesOn) {
    pinMode(9, OUTPUT);
    TCCR1A = _BV(COM1A1) | _BV(WGM11);
    TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS11);
    ICR1 = 40000;
    pulsesOn = true;
  }
  OCR1A = us * 2;
}

void pulsesOff() {
  TCCR1A = 0; TCCR1B = 0;
  digitalWrite(9, LOW);
  pulsesOn = false;
}

void handle(char *cmd) {
  char *arg = strchr(cmd, ' ');
  if (arg) { *arg++ = 0; while (*arg == ' ') arg++; }

  if (!strcmp(cmd, "ID?")) {
    Serial.print(F("ATP-JIG ")); Serial.print(VERSION);
    Serial.print(F(" servo=D9 range=0-270 min_us=")); Serial.print(minUs);
    Serial.print(F(" max_us=")); Serial.println(maxUs);
  } else if (!strcmp(cmd, "MOVE")) {
    if (!arg || !*arg) { Serial.println(F("ERR MOVE needs an angle 0-270")); return; }
    float d = atof(arg);
    if (d < 0 || d > RANGE_DEG) { Serial.println(F("ERR angle out of range 0-270")); return; }
    float travel = posDeg < 0 ? RANGE_DEG : fabs(d - posDeg);
    pulseUs(minUs + (uint16_t)((maxUs - minUs) * d / RANGE_DEG + 0.5));
    uint16_t eta = (uint16_t)(travel * MS_PER_DEG) + SETTLE_MS;
    posDeg = d; moving = true; doneAt = millis() + eta;
    Serial.print(F("OK MOVE ")); Serial.print(d, 1); Serial.print(F(" eta_ms=")); Serial.println(eta);
  } else if (!strcmp(cmd, "POS?")) {
    Serial.print(F("POS ")); if (posDeg < 0) Serial.print(F("unknown")); else Serial.print(posDeg, 1);
    Serial.print(F(" moving=")); Serial.print(moving ? 1 : 0);
    Serial.print(F(" on=")); Serial.println(pulsesOn ? 1 : 0);
  } else if (!strcmp(cmd, "OFF")) {
    pulsesOff(); moving = false;
    Serial.println(F("OK OFF"));
  } else if (!strcmp(cmd, "PULSE")) {
    long us = arg ? atol(arg) : 0;
    if (us < ABS_MIN_US || us > ABS_MAX_US) { Serial.println(F("ERR pulse out of range 400-2600 us")); return; }
    pulseUs((uint16_t)us); posDeg = -1; moving = false;
    Serial.print(F("OK PULSE ")); Serial.println(us);
  } else if (!strcmp(cmd, "CAL")) {
    char *b = arg ? strchr(arg, ' ') : NULL;
    long a = arg ? atol(arg) : 0, c = b ? atol(b) : 0;
    if (a < ABS_MIN_US || c > ABS_MAX_US || a >= c) { Serial.println(F("ERR CAL needs <min_us> <max_us>, 400-2600, min below max")); return; }
    minUs = a; maxUs = c; saveCal();
    Serial.print(F("OK CAL ")); Serial.print(minUs); Serial.print(' '); Serial.println(maxUs);
  } else if (!*cmd) {
    // empty line - ignore
  } else {
    Serial.print(F("ERR unknown command ")); Serial.println(cmd);
  }
}

void setup() {
  digitalWrite(9, LOW); pinMode(9, OUTPUT);
  loadCal();
  Serial.begin(115200);
  Serial.print(F("ATP-JIG ")); Serial.print(VERSION); Serial.println(F(" ready"));
}

void loop() {
  if (moving && (long)(millis() - doneAt) >= 0) {
    moving = false;
    Serial.print(F("DONE ")); Serial.println(posDeg, 1);
  }
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') { line[len] = 0; handle(line); len = 0; }
    else if (len < sizeof(line) - 1) line[len++] = ch;
    else { len = 0; Serial.println(F("ERR line too long")); }
  }
}
