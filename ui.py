import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import theme


def label(text="", kind=None, rich=False):
    l = QLabel(text)
    if kind:
        l.setObjectName(kind)
    l.setWordWrap(True)
    if rich:
        l.setTextFormat(Qt.RichText)
    return l


def card(*widgets, spacing=8, margins=(14, 12, 14, 12)):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QWidget):
            lay.addWidget(w)
        elif w is not None:
            lay.addLayout(w)
    return f


def row(*widgets, stretch_last=False, spacing=8):
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for i, w in enumerate(widgets):
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w, 1 if (stretch_last and i == len(widgets) - 1) else 0)
        else:
            lay.addLayout(w)
    return lay


def separator():
    f = QFrame()
    f.setObjectName("sep")
    f.setFixedHeight(1)
    return f


def wrap(layout, margins=(0, 0, 0, 0)):
    w = QWidget()
    w.setLayout(layout)
    layout.setContentsMargins(*margins)
    return w


def table(headers, stretch_col=None):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    if stretch_col is not None:
        t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


def fill_table(t, rows, aligns=None, colors=None, stretch_col=None):
    t.setRowCount(0)
    for r in rows:
        i = t.rowCount()
        t.insertRow(i)
        for j, v in enumerate(r):
            item = QTableWidgetItem(str(v))
            if aligns and j < len(aligns) and aligns[j] == "r":
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if colors:
                c = colors(i, j, r)
                if c:
                    from PySide6.QtGui import QColor
                    item.setForeground(QColor(c))
            t.setItem(i, j, item)
    t.resizeColumnsToContents()
    if stretch_col is not None:
        t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)


def bar_html(share, color=None, width=120):
    color = color or theme.ACCENT
    filled = max(1, int(width * min(share, 100) / 100.0))
    return ("<span style='background:%s'>%s</span>"
            "<span style='background:%s'>%s</span>") % (
        color, "&nbsp;" * (filled // 6), theme.BORDER,
        "&nbsp;" * max(0, (width - filled) // 6))


def esc(s):
    return html.escape(str(s or ""))


def doc(body, size="10pt"):
    return ("<div style='color:%s;font-size:%s;line-height:1.75'>%s</div>"
            % (theme.TEXT, size, body))


def render_spans(text, spans):
    marks = {}
    for s in spans:
        kind = s.get("kind")
        color = None
        if kind == "te":
            color = theme.TERM
        elif kind == "color":
            color = theme.SPAN_COLORS.get(str(s.get("value", "")).lower())
            if color is None and str(s.get("value", "")).startswith("#"):
                color = s["value"]
        if not color:
            continue
        marks.setdefault(s["start"], []).append(("open", color))
        marks.setdefault(s["end"], []).append(("close", None))

    out = []
    for i, ch in enumerate(text):
        for kind, color in marks.get(i, []):
            out.append("</span>" if kind == "close"
                       else "<span style='color:%s'>" % color)
        out.append("<br>" if ch == "\n" else html.escape(ch))
    for kind, _c in marks.get(len(text), []):
        if kind == "close":
            out.append("</span>")
    return "".join(out)


def element_box(con=None):
    from PySide6.QtWidgets import QComboBox
    import skilldata
    box = QComboBox()
    box.addItem("전체 속성", None)
    from PySide6.QtGui import QColor
    for k, v in skilldata.ELEMENTS.items():
        box.addItem(v, k)
        box.setItemData(box.count() - 1, QColor(theme.element_color(v)),
                        Qt.ForegroundRole)
    return box


def colored(name, color):
    return "<span style='color:%s'>%s</span>" % (color, esc(name))
