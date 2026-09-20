BG = "#15171c"
BG_ALT = "#1b1e25"
PANEL = "#21252e"
BORDER = "#2e333f"
TEXT = "#e2e6ee"
TEXT_DIM = "#8b93a5"
ACCENT = "#6ea8fe"
ACCENT_DIM = "#3c5a8a"
GOOD = "#5fd3a0"
WARN = "#e0b054"
BAD = "#e06c75"

HIGHLIGHT = "#e8c56a"
LIGHT = "#7fd6f5"
TITLE = "#c9a2ff"
TERM = "#6ee7a8"

ELEMENT_COLORS = {
    "응결": "#7fc8f8",
    "용융": "#f08a5d",
    "전도": "#b98cff",
    "기류": "#5fd3a0",
    "회절": "#f2d36b",
    "인멸": "#e070b8",
}


def element_color(name):
    return ELEMENT_COLORS.get(name or "", TEXT)

QSS = """
* { font-family: 'Malgun Gothic', 'Segoe UI', sans-serif; }
QWidget { background: %(BG)s; color: %(TEXT)s; font-size: 10pt; }
QMainWindow, QDialog { background: %(BG)s; }
QLabel, QCheckBox, QRadioButton, QProgressBar, QSplitter, QTabWidget, QStackedWidget {
    background: transparent;
}
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }

QTabWidget::pane { border: 1px solid %(BORDER)s; background: %(BG_ALT)s; top: -1px; }
QTabBar::tab {
    background: %(BG)s; color: %(TEXT_DIM)s;
    padding: 8px 18px; border: 1px solid %(BORDER)s; border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:selected { background: %(BG_ALT)s; color: %(TEXT)s; }
QTabBar::tab:hover { color: %(TEXT)s; }

QPushButton {
    background: %(PANEL)s; border: 1px solid %(BORDER)s;
    padding: 7px 16px; border-radius: 4px; color: %(TEXT)s;
}
QPushButton:hover { border-color: %(ACCENT_DIM)s; }
QPushButton:pressed { background: %(BG_ALT)s; }
QPushButton:disabled { color: %(TEXT_DIM)s; border-color: %(BORDER)s; }
QPushButton:checked { background: %(ACCENT_DIM)s; border-color: %(ACCENT)s; color: %(TEXT)s; }
QPushButton#mini { padding: 2px 8px; min-width: 22px; font-size: 9pt; }
QPushButton#danger:hover { border-color: %(BAD)s; color: %(BAD)s; }
QListWidget#nav {
    background: %(BG_ALT)s; border: none; border-right: 1px solid %(BORDER)s;
    padding-top: 8px; font-size: 10.5pt;
}
QListWidget#nav::item { padding: 9px 16px; border-radius: 0; }
QListWidget#nav::item:selected {
    background: %(PANEL)s; color: %(TEXT)s; border-left: 3px solid %(ACCENT)s;
}
QListWidget#nav::item:disabled {
    color: %(ACCENT)s; padding: 14px 12px 5px 12px; margin-top: 6px;
    border-top: 1px solid %(BORDER)s; background: transparent;
}
QLabel#pagetitle { font-size: 15pt; font-weight: 700; }
QLabel#pagedesc { color: %(TEXT_DIM)s; font-size: 9.5pt; }
QFrame#pagehead { background: %(BG)s; border-bottom: 1px solid %(BORDER)s; }
QLabel#section { color: %(TEXT_DIM)s; font-size: 9pt; font-weight: 600; }
QPushButton#primary { background: %(ACCENT_DIM)s; border-color: %(ACCENT)s; }
QPushButton#primary:hover { background: %(ACCENT)s; color: #10131a; }

QDoubleSpinBox[auto="true"] { color: %(TEXT_DIM)s; font-style: italic; }
QSpinBox, QDoubleSpinBox { padding-right: 30px; }
QSpinBox#compact, QDoubleSpinBox#compact { padding-right: 8px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    width: 26px; border-left: 1px solid %(BORDER)s; border-bottom: 1px solid %(BORDER)s;
    border-top-right-radius: 4px; background: %(PANEL)s;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 26px; border-left: 1px solid %(BORDER)s;
    border-bottom-right-radius: 4px; background: %(PANEL)s;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: %(ACCENT_DIM)s; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: %(ACCENT)s; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {
    background: %(BG_ALT)s; border: 1px solid %(BORDER)s;
    padding: 6px 8px; border-radius: 4px; selection-background-color: %(ACCENT_DIM)s;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: %(ACCENT)s; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: %(PANEL)s; border: 1px solid %(BORDER)s;
    selection-background-color: %(ACCENT_DIM)s; outline: none;
}

QTreeWidget, QListWidget, QTableWidget {
    background: %(BG_ALT)s; border: 1px solid %(BORDER)s;
    alternate-background-color: %(PANEL)s; outline: none;
}
QTreeWidget::item, QListWidget::item { padding: 5px 4px; border: none; }
QTreeWidget::item:selected, QListWidget::item:selected,
QTableWidget::item:selected { background: %(ACCENT_DIM)s; color: %(TEXT)s; }
QTreeWidget::item:hover, QListWidget::item:hover { background: %(PANEL)s; }
QHeaderView::section {
    background: %(PANEL)s; color: %(TEXT_DIM)s; border: none;
    border-right: 1px solid %(BORDER)s; border-bottom: 1px solid %(BORDER)s; padding: 6px;
}

QProgressBar {
    background-color: %(BG_ALT)s; border: 1px solid %(BORDER)s;
    border-radius: 4px; text-align: center; height: 18px; color: %(TEXT)s;
}
QProgressBar::chunk { background: %(ACCENT_DIM)s; border-radius: 3px; }

QScrollBar:vertical { background: %(BG)s; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: %(BORDER)s; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(ACCENT_DIM)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: %(BG)s; height: 10px; }
QScrollBar::handle:horizontal { background: %(BORDER)s; border-radius: 5px; min-width: 30px; }

QLabel#hint { color: %(TEXT_DIM)s; font-size: 9pt; }
QLabel#h1 { font-size: 13pt; font-weight: 600; }
QLabel#h2 { font-size: 11pt; font-weight: 600; color: %(TEXT)s; }
QLabel#stat { color: %(TEXT_DIM)s; font-size: 9pt; }
QPushButton[chip="true"] {
    padding: 4px 10px; font-size: 9pt; color: %(TEXT_DIM)s;
    background: %(BG_ALT)s; border-radius: 10px;
}
QPushButton[chip="true"]:hover { color: %(TEXT)s; border-color: %(ACCENT_DIM)s; }
QTextBrowser { background: %(BG_ALT)s; border: 1px solid %(BORDER)s; padding: 10px; }
QFrame#card {
    background: %(PANEL)s; border: 1px solid %(BORDER)s; border-radius: 6px;
}
QFrame#sep { background: %(BORDER)s; max-height: 1px; border: none; }
QSplitter::handle { background: %(BORDER)s; width: 1px; }
QStatusBar { background: %(BG_ALT)s; color: %(TEXT_DIM)s; border-top: 1px solid %(BORDER)s; }
QCheckBox::indicator {
    width: 15px; height: 15px; border: 1px solid %(BORDER)s;
    border-radius: 3px; background: %(BG_ALT)s;
}
QCheckBox::indicator:checked { background: %(ACCENT)s; border-color: %(ACCENT)s; }
QToolTip {
    background: %(PANEL)s; color: %(TEXT)s;
    border: 1px solid %(ACCENT_DIM)s; padding: 6px;
}
""" % {
    "BG": BG, "BG_ALT": BG_ALT, "PANEL": PANEL, "BORDER": BORDER,
    "TEXT": TEXT, "TEXT_DIM": TEXT_DIM, "ACCENT": ACCENT, "ACCENT_DIM": ACCENT_DIM,
    "BAD": BAD,
}

SPAN_COLORS = {
    "highlight": HIGHLIGHT,
    "light": LIGHT,
    "title": TITLE,
    "te": TERM,
}


def _arrow(path, up):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygonF
    pm = QPixmap(20, 12)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(TEXT))
    pts = [QPointF(4, 10), QPointF(16, 10), QPointF(10, 2)] if up else \
        [QPointF(4, 2), QPointF(16, 2), QPointF(10, 10)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    pm.save(path)


def full_qss():
    import os
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "ddinggwasajeon_ui")
    try:
        os.makedirs(d, exist_ok=True)
        up = os.path.join(d, "up.png")
        down = os.path.join(d, "down.png")
        _arrow(up, True)
        _arrow(down, False)
    except Exception:
        return QSS
    up = up.replace("\\", "/")
    down = down.replace("\\", "/")
    return QSS + (
        "\nQSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%s); width: 10px; height: 6px; }"
        "\nQSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%s); width: 10px; height: 6px; }"
        % (up, down))
