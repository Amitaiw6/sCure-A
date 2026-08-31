"""Design tokens + the single Qt stylesheet for the sCure DVT application.

Palette: deep navy ground with cool-grey text, one teal accent for actions,
semantic colours only for state (ok / warn / bad / info). Subsystems keep
their own hue (used in the dashboard donut, matrix groups and nav counters).
"""

BG = "#0b111a"          # window ground
BG_2 = "#0f1724"        # sidebar / header
CARD = "#141d2b"        # cards
CARD_2 = "#1a2536"      # nested / hover
LINE = "#243144"
INK = "#e7edf5"
MUTED = "#8ea0b5"
ACCENT = "#22b8c8"
ACCENT_INK = "#06282d"
OK = "#3ecf8e"
WARN = "#f2b544"
BAD = "#ff6b6b"
INFO = "#4f9cf9"
PURPLE = "#b39ddb"

SUBSYSTEM = {"Safety": "#ff5c4d", "Thermal": "#ff9f43", "Electrical": "#4f9cf9", "Environmental": "#3ecf8e"}
SUBSYSTEM_ICON = {"Safety": "⚠", "Thermal": "🌡", "Electrical": "⚡", "Environmental": "🚚"}
STATUS = {"Complete": OK, "Running": WARN, "Failed": BAD, "Pending": MUTED, "Blocked": WARN}
VERDICT = {"PASS": OK, "FAIL": BAD, "BLOCKED": WARN, "WAIVED": PURPLE}

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {INK}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QToolTip {{ background: {CARD_2}; color: {INK}; border: 1px solid {LINE}; padding: 6px; }}
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG}; border: 1px solid {LINE}; border-radius: 8px; padding: 8px 10px; selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[state="error"] {{ border: 1px solid {BAD}; }}
QLineEdit[state="ok"] {{ border: 1px solid {OK}; }}
QLineEdit[state="fromdut"] {{ border: 1px solid {INFO}; background: #0f1a2c; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; selection-background-color: {CARD_2}; }}
QPushButton {{ background: {ACCENT}; color: {ACCENT_INK}; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 700; }}
QPushButton:hover {{ background: #33c8d8; }}
QPushButton:pressed {{ background: #189aa8; }}
QPushButton:disabled {{ background: {CARD_2}; color: #5d6d80; }}
QPushButton[kind="ghost"] {{ background: transparent; color: {INK}; border: 1px solid {LINE}; }}
QPushButton[kind="ghost"]:hover {{ background: {CARD_2}; }}
QPushButton[kind="danger"] {{ background: #5a2320; color: #ffd6d2; }}
QPushButton[kind="nav"] {{ background: transparent; color: {MUTED}; text-align: left; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QPushButton[kind="nav"]:hover {{ background: {CARD}; color: {INK}; }}
QPushButton[kind="nav"]:checked {{ background: {CARD_2}; color: {ACCENT}; }}
QPushButton[kind="big"] {{ padding: 14px 26px; font-size: 15px; border-radius: 10px; }}
QListWidget, QTableWidget, QTreeWidget {{ background: {BG}; border: 1px solid {LINE}; border-radius: 8px; font-size: 12.5px; outline: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 4px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{ background: {CARD_2}; color: {INK}; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: 0; border-bottom: 1px solid {LINE}; padding: 6px; font-size: 11px; letter-spacing: .6px; text-transform: uppercase; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollArea {{ border: 0; }}
QCheckBox {{ spacing: 10px; padding: 6px 0; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {LINE}; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QProgressBar {{ background: {CARD_2}; border: 0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QSplitter::handle {{ background: {LINE}; width: 1px; }}
QGroupBox {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; margin-top: 16px; padding: 12px 14px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 4px; color: {MUTED}; font-size: 10.5px; letter-spacing: 1.2px; font-weight: 700; }}
QFrame[card="true"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame[card="raised"] {{ background: {CARD_2}; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame[card="sidebar"] {{ background: {BG_2}; border: 0; border-right: 1px solid {LINE}; }}
QFrame[card="header"] {{ background: {BG_2}; border: 0; border-bottom: 1px solid {LINE}; }}
QLabel[role="h1"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 16px; font-weight: 700; }}
QLabel[role="eyebrow"] {{ color: {MUTED}; font-size: 10.5px; letter-spacing: 1.2px; font-weight: 700; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="mono"] {{ font-family: Consolas, 'Cascadia Mono', monospace; }}
QLabel[role="pill"] {{ border-radius: 10px; padding: 3px 10px; font-weight: 700; font-size: 11.5px; }}
QLabel[role="banner-warn"] {{ background: #4a3608; color: #ffd98a; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QLabel[role="banner-bad"] {{ background: #4a1f1b; color: #ffb4ad; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QLabel[role="banner-info"] {{ background: #16283f; color: #cfe1fb; padding: 10px 14px; border-radius: 8px; }}
QLabel[role="instruction"] {{ font-size: 17px; line-height: 1.5; }}
"""
