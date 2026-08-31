"""Design tokens + the single Qt stylesheet for the sCure DVT application.

Direction: a lab instrument console — dark graphite navigation rail on the
left, a light, quiet work surface (cool paper grey with white cards) on the
right, graphite ink, and one Stratasys signal-orange accent for the primary
action. Semantic colours are reserved for state (ok / warn / bad / info);
subsystems keep their own hue for the donut, matrix groups and counters.
Labels are always transparent — only inputs and cards paint a surface.
"""

# ---- surfaces
RAIL = "#161b22"        # navigation rail / header band
RAIL_2 = "#1f2630"      # rail hover / active
PAPER = "#eef1f5"       # work surface
CARD = "#ffffff"
CARD_2 = "#f5f7fa"      # nested surface / table header
LINE = "#d9dee6"
LINE_2 = "#c3cad5"
# ---- ink
INK = "#1b2430"
INK_2 = "#3c4858"
MUTED = "#6b7a8c"
ON_RAIL = "#c9d1dc"
ON_RAIL_MUTED = "#7f8b9a"
# ---- accent + semantics
ACCENT = "#e8461f"      # Stratasys orange-red
ACCENT_DARK = "#c93a17"
ACCENT_INK = "#ffffff"
OK = "#1f9d61"
WARN = "#d68a0c"
BAD = "#d62839"
INFO = "#2f6fdb"
PURPLE = "#7c5cbf"

SUBSYSTEM = {"Safety": "#d62839", "Thermal": "#e8760c", "Electrical": "#2f6fdb", "Environmental": "#1f9d61"}
SUBSYSTEM_ICON = {"Safety": "⚠", "Thermal": "🌡", "Electrical": "⚡", "Environmental": "🚚"}
STATUS = {"Complete": OK, "Running": WARN, "Failed": BAD, "Pending": MUTED, "Blocked": WARN}
VERDICT = {"PASS": OK, "FAIL": BAD, "BLOCKED": WARN, "WAIVED": PURPLE}
MODE = {"OFFLINE": MUTED, "SIMULATION": PURPLE, "FAULT": BAD, "CURING": WARN, "HEATING": WARN, "COOLING": INFO, "IDLE": OK}

# kept for modules that still import the old names
BG, BG_2 = PAPER, RAIL

QSS = f"""
QMainWindow, QDialog {{ background: {PAPER}; }}
QWidget {{ color: {INK}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {INK}; color: #fff; border: 0; padding: 6px 8px; font-size: 12px; }}

/* ---- inputs */
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {CARD}; color: {INK}; border: 1px solid {LINE_2}; border-radius: 6px; padding: 7px 10px; selection-background-color: {ACCENT}; selection-color: #fff; }}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1.5px solid {ACCENT}; }}
QLineEdit:read-only {{ background: {CARD_2}; color: {INK_2}; }}
QLineEdit[state="error"] {{ border: 1.5px solid {BAD}; background: #fff3f4; }}
QLineEdit[state="fromdut"] {{ border: 1.5px solid {INFO}; background: #f0f5ff; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE_2}; selection-background-color: {CARD_2}; selection-color: {INK}; outline: 0; }}
QPlainTextEdit[role="code"] {{ font-family: Consolas, 'Cascadia Mono', monospace; font-size: 12px; }}

/* ---- buttons */
QPushButton {{ background: {ACCENT}; color: {ACCENT_INK}; border: 0; border-radius: 6px; padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton:pressed {{ background: #a82f11; }}
QPushButton:disabled {{ background: {LINE}; color: {MUTED}; }}
QPushButton[kind="ghost"] {{ background: {CARD}; color: {INK}; border: 1px solid {LINE_2}; }}
QPushButton[kind="ghost"]:hover {{ background: {CARD_2}; border-color: {INK_2}; }}
QPushButton[kind="ghost"]:disabled {{ background: {CARD_2}; color: {MUTED}; border-color: {LINE}; }}
QPushButton[kind="danger"] {{ background: #fdecec; color: {BAD}; border: 1px solid #f3b8be; }}
QPushButton[kind="danger"]:hover {{ background: #fbd9dc; }}
QPushButton[kind="big"] {{ padding: 13px 26px; font-size: 15px; border-radius: 8px; }}
QPushButton[kind="nav"] {{ background: transparent; color: {ON_RAIL}; text-align: left; padding: 10px 14px; border-radius: 8px; font-weight: 600; font-size: 13.5px; }}
QPushButton[kind="nav"]:hover {{ background: {RAIL_2}; color: #fff; }}
QPushButton[kind="nav"]:checked {{ background: {RAIL_2}; color: #fff; border-left: 3px solid {ACCENT}; padding-left: 11px; }}
QPushButton[kind="link"] {{ background: transparent; color: {INFO}; border: 0; padding: 2px 4px; text-align: left; font-weight: 600; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; }}

/* ---- lists / tables */
QListWidget, QTableWidget, QTreeWidget {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; font-size: 12.5px; outline: 0; alternate-background-color: {CARD_2}; }}
QTreeWidget::item, QListWidget::item {{ padding: 5px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{ background: #fdeae4; color: {INK}; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {CARD_2}; }}
QHeaderView::section {{ background: {CARD_2}; color: {MUTED}; border: 0; border-bottom: 1px solid {LINE}; padding: 7px 8px; font-size: 11px; letter-spacing: .6px; font-weight: 700; }}
QTableWidget QTableCornerButton::section {{ background: {CARD_2}; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE_2}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE_2}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QSplitter::handle {{ background: {LINE}; width: 1px; }}

/* ---- controls */
QCheckBox {{ spacing: 10px; padding: 6px 0; font-size: 13.5px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid {LINE_2}; background: {CARD}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: none; }}
QProgressBar {{ background: {LINE}; border: 0; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

/* ---- surfaces */
QFrame[card="true"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; }}
QFrame[card="raised"] {{ background: {CARD}; border: 1px solid {LINE_2}; border-radius: 10px; }}
QFrame[card="tint"] {{ background: #fff6f2; border: 1px solid #f6cfc3; border-radius: 10px; }}
QFrame[card="sidebar"] {{ background: {RAIL}; border: 0; }}
QFrame[card="header"] {{ background: {CARD}; border: 0; border-bottom: 1px solid {LINE}; }}
QFrame[card="sim"] {{ background: #efe9fb; border: 1px solid #cdbdf0; border-radius: 8px; }}
QGroupBox {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; margin-top: 16px; padding: 12px 14px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 4px; color: {MUTED}; font-size: 10.5px; letter-spacing: 1.2px; font-weight: 700; }}

/* ---- text roles */
QLabel[role="h1"] {{ font-size: 24px; font-weight: 700; color: {INK}; }}
QLabel[role="h2"] {{ font-size: 17px; font-weight: 700; color: {INK}; }}
QLabel[role="eyebrow"] {{ color: {MUTED}; font-size: 10.5px; letter-spacing: 1.2px; font-weight: 700; }}
QLabel[role="eyebrow-rail"] {{ color: {ON_RAIL_MUTED}; font-size: 10.5px; letter-spacing: 1.2px; font-weight: 700; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="rail"] {{ color: {ON_RAIL}; }}
QLabel[role="mono"] {{ font-family: Consolas, 'Cascadia Mono', monospace; }}
QLabel[role="pill"] {{ border-radius: 10px; padding: 3px 10px; font-weight: 700; font-size: 11.5px; }}
QLabel[role="banner-warn"] {{ background: #fff4e0; color: #7a4d00; border: 1px solid #f3d59a; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QLabel[role="banner-bad"] {{ background: #fdecec; color: #8a1a25; border: 1px solid #f3b8be; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QLabel[role="banner-info"] {{ background: #eaf1fd; color: #1f3f7a; border: 1px solid #c4d6f5; padding: 10px 14px; border-radius: 8px; }}
QLabel[role="banner-ok"] {{ background: #e8f7ef; color: #135c3a; border: 1px solid #b7e2c9; padding: 10px 14px; border-radius: 8px; font-weight: 600; }}
QLabel[role="instruction"] {{ font-size: 18px; line-height: 1.5; color: {INK}; }}
"""
