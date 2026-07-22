# Raspberry Pi GPIO Dashboard

מערכת שליטה ב־GPIO ו־PWM עבור Raspberry Pi CM5.

## מה יש פה
- `dashboard.py` — ממשק Tkinter להצגת פיני ה־GPIO בטבלה
- `gpio_manager.py` — לוגיקה לקריאה/כתיבה ו־PWM על גבי `RPi.GPIO`
- `config.py` — מיפוי פינים פיזיים/BCM ותמיכה ב־PWM

## הפעלה
1. העבר את התיקייה ל־Raspberry Pi שלך.
2. התקן את התלות אם צריך:
   ```bash
   pip install RPi.GPIO
   ```
3. הפעל את המערכת:
   ```bash
   python3 dashboard.py
   ```

## איך להשתמש
- בחר פין בטבלה כדי לראות את המספר הפיזי ואת השם שלו.
- עבור פינים מסוג GPIO תוכל:
  - לקרוא את המצב
  - לכתוב HIGH / LOW
  - להפעיל PWM אם הפין תומך
- יש לוח לוג שמראה את הפעולות והקריאות של המערכת.

## הערות
- מערכת זו מיועדת לריצה מקומית על ה־Raspberry Pi.
- פינים לא גמישים (כמו 3.3V, 5V ו־GND) מוצגים אך לא ניתנים לשינוי.
