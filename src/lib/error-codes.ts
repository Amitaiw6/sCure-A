/**
 * Per-component error codes (firmware 1.0.106, 2026-10-21): every thermistor, fan and LED panel has its own code so the
 * service team can give each its own text and repair video. The grouped codes of older machines (9001-9005, 9050, 9051)
 * are their "family" - code that reacts to a KIND of fault compares families, never the exact code.
 * Mirror of sCureBox-CS ErrorCodes.Family.
 */
export const TEMP_SENSOR = 9001          // 9010 chamber, 9011 left, 9012 right
export const FAN_FAILURE = 9002          // 9020-9025 one per fan
export const FAN_STOPPED = 9003          // 9030-9033 LED fans, 9034 chamber cooling fan
export const LED_NOT_HEATING = 9004      // 9040 left, 9041 right, 9044 back, 9045 door
export const LED_TEMP_DROP = 9005        // 9042 left, 9043 right
export const LED_TEMP_SENSOR = 9050      // 9013 back, 9014 door
export const FAN_WEAR = 9051             // 9060-9065 one per fan
export const CHAMBER_SENSOR = 9010

export function errorFamily(code: number): number {
  if (code >= 9010 && code <= 9012) return TEMP_SENSOR
  if (code >= 9013 && code <= 9014) return LED_TEMP_SENSOR
  if (code >= 9020 && code <= 9025) return FAN_FAILURE
  if (code >= 9030 && code <= 9034) return FAN_STOPPED
  if ((code >= 9040 && code <= 9041) || (code >= 9044 && code <= 9045)) return LED_NOT_HEATING
  if (code >= 9042 && code <= 9043) return LED_TEMP_DROP
  if (code >= 9060 && code <= 9065) return FAN_WEAR
  return code
}

export const isA = (code: number | undefined | null, family: number): boolean => code != null && errorFamily(code) === family

/** The not-heating code of an LED panel ("left" / "right" / "back" / "door"); the grouped 9004 for anything else. */
export function ledNotHeatingCode(panel: string): number {
  return ({ left: 9040, right: 9041, back: 9044, door: 9045 } as Record<string, number>)[panel.toLowerCase()] ?? LED_NOT_HEATING
}
