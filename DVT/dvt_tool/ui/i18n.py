"""Minimal i18n: English source strings → Hebrew. `tr(s)` returns the
translation when the active language is Hebrew, otherwise `s` unchanged.
Catalog content (test titles, procedures, criteria) stays in the language
it was written in — only the application's own UI is translated.
"""

from __future__ import annotations

LANG = "en"           # "en" | "he"
LANGUAGES = {"en": "English", "he": "עברית"}


def set_language(code: str) -> None:
    global LANG
    LANG = code if code in LANGUAGES else "en"


def is_rtl() -> bool:
    return LANG == "he"


def tr(s: str) -> str:
    if LANG == "he":
        return HE.get(s, s)
    return s


HE = {
    # ---- shell / header
    "sCure / CureBox — DVT Qualification & Acceptance Test Console": "sCure / CureBox — קונסולת בדיקות DVT (Qualification & Acceptance)",
    "DUT": "מכונה נבדקת (DUT)", "UNIT UNDER TEST": "יחידה נבדקת", "OPERATOR": "מפעיל", "CAMPAIGN": "קמפיין", "TEST PLAN": "תוכנית בדיקות",
    "SYSTEM STATUS": "מצב מערכת", "DATE / TIME (UTC)": "תאריך / שעה (UTC)", "TEST SUBSYSTEMS": "תתי-מערכות",
    "Dashboard": "לוח מחוונים", "Test Plans": "תוכניות בדיקה", "Test Console": "קונסולת בדיקות", "DUT Control": "שליטה במכונה",
    "Instruments": "מכשירים", "Statistics": "סטטיסטיקה", "Reports": "דוחות", "Settings": "הגדרות",
    "System Health": "תקינות המערכת", "All systems nominal": "כל המערכות תקינות",
    "Simulation mode: ON": "מצב סימולציה: פעיל", "Simulation mode: OFF": "מצב סימולציה: כבוי",
    "◉  SIMULATION MODE — you are connected to the built-in simulated machine. Nothing here touches real hardware. Inject faults from DUT Control.":
        "◉  מצב סימולציה — אתה מחובר למכונה המדומה המובנית. שום דבר כאן לא נוגע בחומרה אמיתית. הזרקת תקלות מתוך 'שליטה במכונה'.",
    "OFFLINE": "מנותק", "IDLE": "במנוחה", "HEATING": "מחמם", "COOLING": "מקרר", "CURING": "קיור", "FAULT": "תקלה", "RUNNING": "פעיל",
    "Drive: —": "Drive: —", "Drive: OFF": "Drive: כבוי",
    # ---- dashboard
    "Tests": "בדיקות", "Running": "פעילות", "Failed": "נכשלו", "Complete": "הושלמו", "Runs done": "ריצות שבוצעו",
    "Blocked": "חסום", "Pending": "ממתין", "Title": "כותרת",
    "Test distribution by subsystem": "התפלגות בדיקות לפי תת-מערכת", "click a slice or a subsystem to filter the matrix": "לחץ על פלח או על תת-מערכת לסינון המטריצה",
    "Progress by subsystem": "התקדמות לפי תת-מערכת", "% of applicable runs committed": "% מהריצות הרלוונטיות שבוצעו",
    "Test matrix — grouped by subsystem": "מטריצת בדיקות — לפי תת-מערכת", "Live telemetry": "טלמטריה חיה", "Safety & interlocks": "בטיחות ומנעולים",
    "What is left": "מה נשאר", "pending runs per test · double-click to open": "ריצות ממתינות לכל בדיקה · לחיצה כפולה לפתיחה",
    "Door closed / locked": "דלת סגורה / נעולה", "UV off": "UV כבוי", "Heater off": "הייטר כבוי", "No active fault": "אין תקלה פעילה",
    "Campaign": "קמפיין", "Test": "בדיקה", "Pending runs": "ריצות ממתינות", "Est (min)": "משוער (דק')",
    "ID / Subsystem": "מזהה / תת-מערכת", "Test name": "שם הבדיקה", "Method": "שיטה", "Appl.": "תחולה", "Status": "סטטוס", "Result": "תוצאה", "Runs": "ריצות", "Reps": "חזרות",
    "Nothing left — every applicable run is committed.": "לא נשאר כלום — כל הריצות הרלוונטיות בוצעו.",
    "waiting for the machine…": "ממתין למכונה…",
    # ---- console
    "Units under test": "יחידות נבדקות", "Freeze config": "הקפא קונפיגורציה", "Sign phase TRR": "חתום על מוכנות שלב (TRR)",
    "Open NCRs": "אי-התאמות (NCR) פתוחות", "Close selected NCR…": "סגור NCR נבחר…", "Search": "חיפוש",
    "run, value, error code, NCR text…": "ריצה, ערך, קוד שגיאה, טקסט NCR…", "Next action": "הפעולה הבאה",
    "Start guided run →": "התחל ריצה מודרכת →", "Resume guided run →": "המשך ריצה מודרכת →", "Start anyway (supervisor)": "התחל בכל זאת (מפקח)",
    "Runs of this test": "ריצות של בדיקה זו", "double-click a NOT_STARTED / IN_PROGRESS run to open it": "לחיצה כפולה על ריצה שלא התחילה / בתהליך פותחת אותה",
    "Unit": "יחידה", "Variant": "וריאנט", "Rep": "חזרה", "Verdict": "פסק-דין", "Operator": "מפעיל",
    "Freeze configuration now": "הקפא קונפיגורציה עכשיו", "Sign phase readiness now": "חתום על מוכנות השלב עכשיו",
    "Record calibrations…": "רשום כיולים…", "Go to ELE-001 (earth first)": "עבור ל-ELE-001 (הארקה קודם)",
    "Blocked:": "חסום:", "Enter the operator name in the header first.": "הזן קודם שם מפעיל בכותרת.",
    # ---- wizard
    "Overview": "סקירה", "Safety plan": "תוכנית בטיחות", "Equipment": "ציוד", "Preconditions": "תנאים מוקדמים", "Done": "סיום", "Step": "צעד",
    "What this run verifies": "מה הריצה הזו מאמתת", "Run": "ריצה", "Phase": "שלב", "Applicability": "תחולה", "Repetition": "חזרה",
    "Estimated": "משוער", "Requirements": "דרישות", "Dependencies": "תלויות", "none": "אין",
    "Press Next to begin. The wizard will tell you what to do at every stage; nothing is submitted until the verdict page.":
        "לחץ 'הבא' כדי להתחיל. האשף יגיד לך מה לעשות בכל שלב; שום דבר לא נשלח עד עמוד פסק-הדין.",
    "Safety plan — read before touching the unit": "תוכנית בטיחות — לקרוא לפני שנוגעים ביחידה",
    "I have read the safety plan; the area, PPE and remote controls are prepared": "קראתי את תוכנית הבטיחות; האזור, הציוד המגן והשליטה מרחוק מוכנים",
    "Equipment and calibration": "ציוד וכיול",
    "Put these instruments on the bench. A missing or expired calibration record blocks the run (SRS-DVT-085).": "הנח את המכשירים האלה על השולחן. רשומת כיול חסרה או פגה חוסמת את הריצה (SRS-DVT-085).",
    "Record calibration…": "רשום כיול…", "NO CALIBRATION RECORD": "אין רשומת כיול",
    "Preconditions — confirm each one": "תנאים מוקדמים — אשר כל אחד",
    "The data fields stay locked until every precondition is ticked (SRS-DVT-083). Use DUT Control to bring the machine to the required state.":
        "שדות הנתונים נשארים נעולים עד שכל התנאים מסומנים (SRS-DVT-083). השתמש ב'שליטה במכונה' כדי להביא אותה למצב הנדרש.",
    "Record now": "רשום עכשיו", "⇩ from DUT": "⇩ מהמכונה",
    "No data to record for this step — perform it, then press Next.": "אין נתונים לרשום בצעד הזה — בצע אותו ולחץ 'הבא'.",
    "Review and verdict": "סקירה ופסק-דין", "Recorded values": "ערכים שנרשמו", "Pass criteria": "קריטריון מעבר", "not evaluated": "לא הוערך",
    "Evaluate": "הערך", "Finish run — commit verdict": "סיים ריצה — קבע פסק-דין", "Waive…": "ויתור (Waive)…", "Reject run…": "פסול ריצה…",
    "Witness (optional — name, role)": "עד (אופציונלי — שם, תפקיד)",
    "Leave wizard (keeps progress)": "צא מהאשף (ההתקדמות נשמרת)", "Redline this step": "Redline לצעד הזה", "Attach file…": "צרף קובץ…",
    "← Back": "→ חזרה", "Next →": "הבא ←",
    "Acknowledge the safety plan to continue.": "אשר את תוכנית הבטיחות כדי להמשיך.", "Tick every precondition first.": "סמן קודם את כל התנאים המוקדמים.",
    "Acknowledge the safety plan first.": "אשר קודם את תוכנית הבטיחות.",
    "No machine connected — set the DUT address in the header.": "אין מכונה מחוברת — הגדר כתובת DUT בכותרת.",
    "Run finished — PASS": "הריצה הסתיימה — PASS", "Run finished — FAIL": "הריצה הסתיימה — FAIL", "Run finished — BLOCKED": "הריצה הסתיימה — BLOCKED", "Run finished — WAIVED": "הריצה הסתיימה — WAIVED",
    "All pass criteria met. The result is committed and exported.": "כל קריטריוני המעבר התקיימו. התוצאה נשמרה ויוצאה.",
    "Pass criteria not met. An NCR was opened automatically — describe the anomaly in the NCR list.": "קריטריון המעבר לא התקיים. נפתח NCR אוטומטית — תאר את החריגה ברשימת ה-NCR.",
    "Next for this unit: ": "הבא ליחידה זו: ",
    # ---- DUT
    "Device under test": "המכונה הנבדקת", "Machine address": "כתובת המכונה", "Connect": "התחבר", "Discover": "גלה",
    "Live state": "מצב חי", "Controls": "פקדים", "every action is confirmed and logged": "כל פעולה מאושרת ונרשמת",
    "Used between wizard steps to bring the machine to the state a step needs (e.g. 'chamber in HEAT mode at 80 °C, steady').":
        "משמש בין צעדי האשף כדי להביא את המכונה למצב שצעד דורש (למשל 'תא במצב חימום ב-80°C, יציב').",
    "Target °C": "יעד °C", "Heat to target": "חמם ליעד", "Cool to target": "קרר ליעד", "UV %": "UV %", "UV on (405 nm)": "UV פעיל (405 nm)", "UV off": "UV כבוי",
    "Open door": "פתח דלת", "STOP — all off": "עצור — הכל כבוי", "Diagnostics": "אבחון", "LED test": "בדיקת LED", "Fan test": "בדיקת מאווררים",
    "Simulator — fault injection": "סימולטור — הזרקת תקלות", "exercise the SAF tests without hardware": "תרגול בדיקות SAF בלי חומרה",
    "Mains voltage": "מתח רשת", "Close door": "סגור דלת", "Acknowledge alarms": "אשר אזעקות", "Not connected to a machine.": "אין חיבור למכונה.",
    "Door closed": "דלת סגורה",
    # ---- instruments / reports / settings
    "Instruments & calibration records": "מכשירים ורשומות כיול", "Instrument": "מכשיר", "Calibration id": "מזהה כיול", "Valid until": "בתוקף עד", "Used by": "בשימוש ע\"י",
    "Record calibration for selected…": "רשום כיול למכשיר הנבחר…",
    "Reports & exports": "דוחות וייצוא", "Export + sync now": "ייצא וסנכרן עכשיו", "Open Drive folder": "פתח תיקיית Drive", "Open local export folder": "פתח תיקיית ייצוא מקומית",
    "Campaign events (latest)": "אירועי קמפיין (אחרונים)",
    "Google Drive sync": "סנכרון Google Drive", "Mode": "מצב", "Synced folder (mode=folder)": "תיקייה מסונכרנת (מצב folder)", "Browse…": "עיון…",
    "OAuth client (mode=api)": "OAuth client (מצב api)", "Select credentials.json…": "בחר credentials.json…", "Apply": "החל",
    "Motion": "הנפשות", "animations on": "הנפשות פעילות", "reduced motion": "הנפשה מופחתת", "About": "אודות",
    "Work mode": "מצב עבודה", "Normal — real machine": "רגיל — מכונה אמיתית", "Simulation — built-in simulated machine": "סימולציה — מכונה מדומה מובנית",
    "Language": "שפה", "Language / mode changes apply after the console restarts.": "שינוי שפה / מצב נכנס לתוקף אחרי הפעלה מחדש של הקונסולה.",
    "Restart console now": "הפעל מחדש עכשיו",
    # ---- start dialog
    "Welcome — choose how to work": "ברוך הבא — בחר איך לעבוד",
    "Work mode:": "מצב עבודה:", "Machine address:": "כתובת המכונה:", "Unit under test:": "יחידה נבדקת:", "Operator:": "מפעיל:", "Language:": "שפה:",
    "Start": "התחל", "You can change all of this later in Settings and in the header.": "אפשר לשנות את כל זה אחר כך בהגדרות ובכותרת.",
    # ---- statistics
    "All machines — verdict per test": "כל המכונות — פסק-דין לכל בדיקה",
    "rolled-up verdict of each test on each unit · N/A = not applicable to that unit": "פסק-דין מגולגל של כל בדיקה בכל יחידה · N/A = לא רלוונטי ליחידה",
    "Comparison across units": "השוואה בין יחידות", "SRS-DVT-095 — one curve per unit, x = sweep value (or repetition)": "SRS-DVT-095 — עקומה לכל יחידה, x = ערך sweep (או חזרה)",
    "Field": "שדה", "Values": "ערכים", "Subsystem": "תת-מערכת",
    "No recorded values yet for this field": "עדיין אין ערכים לשדה הזה",
}
