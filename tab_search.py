from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QTextBrowser, QVBoxLayout, QWidget

TERM_HEAD = 6
CHAR_HEAD = 5

import analysis
import skilldata
import theme
import ui

class SearchTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.hits = []
        self.expanded = set()
        self.terms_open = False

        self.query = QLineEdit()
        self.query.setPlaceholderText("스킬 원문에서 찾을 말")
        self.element = ui.element_box()
        self.element.setMaximumWidth(130)
        self.scope = QComboBox()
        self.scope.addItem("스킬 + 공명 체인", "all")
        self.scope.addItem("스킬만", "skills")
        self.scope.addItem("공명 체인만", "chains")
        self.result = QTextBrowser()
        self.result.setOpenLinks(False)
        self.count = ui.label("", "stat")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.query, 1)
        top.addWidget(self.scope)
        top.addWidget(self.element)
        lay.addLayout(top)
        lay.addWidget(self.count)
        lay.addWidget(self.result, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self.run)
        self.query.textChanged.connect(lambda _t: self._timer.start())
        self.result.anchorClicked.connect(self.on_link)
        self.element.currentIndexChanged.connect(lambda _i: self.run())
        self.scope.currentIndexChanged.connect(lambda _i: self.run())

    def reload(self):
        if self.query.text().strip():
            self.run()

    def run(self, text=None, keep=False):
        if text is not None:
            self.query.blockSignals(True)
            self.query.setText(text)
            self.query.blockSignals(False)
        if not keep:
            self.expanded = set()
            self.terms_open = False
        q = self.query.text().strip()
        if not self.win.con or len(q) < 2:
            self.result.clear()
            self.count.setText("")
            return

        limit = 5000
        hits = analysis.search(self.win.con, q, limit, self.scope.currentData())
        capped = len(hits) >= limit
        want = self.element.currentData()
        elems = {cid: e for cid, _n, _b, _v, e in skilldata.characters(self.win.con)}
        colors = skilldata.name_colors(self.win.con)
        if want:
            hits = [h for h in hits if elems.get(h["character_id"]) == want]
        terms = analysis.term_search(self.win.con, q, 200)
        self.hits = hits

        by_char = {}
        for h in hits:
            by_char.setdefault((h["character_id"], h["character"]), []).append(h)

        parts = []
        if terms:
            shown = terms if self.terms_open else terms[:TERM_HEAD]
            parts.append("<div style='color:%s;font-weight:600;margin-bottom:6px'>"
                         "용어 %d건</div>" % (theme.TEXT, len(terms)))
            for tid, title, desc in shown:
                parts.append(
                    "<div style='margin-bottom:8px'>"
                    "<span style='color:%s;font-weight:600'>%s</span><br>"
                    "<span style='color:%s'>%s</span></div>" % (
                        theme.TERM, ui.esc(title), theme.TEXT_DIM,
                        ui.esc((desc or "")[:220])))
            if len(terms) > TERM_HEAD:
                parts.append(
                    "<div style='margin-bottom:6px'>"
                    "<a href='terms' style='color:%s;text-decoration:none'>%s</a>"
                    "</div>" % (theme.ACCENT,
                                "접기" if self.terms_open
                                else "더보기 (%d건)" % (len(terms) - TERM_HEAD)))
            parts.append("<div style='height:10px'></div>")

        for (cid, cname), items in sorted(by_char.items(), key=lambda kv: kv[0][1]):
            parts.append(
                "<div style='margin-top:12px'>"
                "<a href='char:%d' style='color:%s;font-weight:600;"
                "text-decoration:none'>%s</a> "
                "<span style='color:%s'>· %d건</span></div>" % (
                    cid, colors.get(cname, theme.ACCENT), ui.esc(cname),
                    theme.TEXT_DIM, len(items)))
            is_open = cid in self.expanded
            shown = items if is_open else items[:CHAR_HEAD]
            for h in shown:
                line = ui.esc(h["line"])
                line = line.replace(ui.esc(q),
                                    "<span style='color:%s'>%s</span>"
                                    % (theme.HIGHLIGHT, ui.esc(q)))
                parts.append(
                    "<div style='margin:3px 0 3px 12px'>"
                    "<span style='color:%s'>[%s] %s</span><br>"
                    "<span style='color:%s'>%s</span></div>" % (
                        theme.TITLE if h.get("chain") else theme.TEXT_DIM,
                        ui.esc(h["type_name"]),
                        ui.esc(h["skill"]), theme.TEXT, line))
            if len(items) > CHAR_HEAD:
                parts.append(
                    "<div style='margin-left:12px'>"
                    "<a href='more:%d' style='color:%s;text-decoration:none'>%s</a>"
                    "</div>" % (cid, theme.ACCENT,
                                "접기" if is_open
                                else "더보기 (외 %d건)" % (len(items) - CHAR_HEAD)))

        self.count.setText("캐릭터 %d명 · 문장 %d건%s%s" % (
            len(by_char), len(hits), "+" if capped else "",
            " · 용어 %d건" % len(terms) if terms else ""))
        self.result.setHtml(ui.doc("".join(parts) if parts
                                   else "<span style='color:%s'>결과 없음</span>"
                                   % theme.TEXT_DIM))

    def on_link(self, url):
        s = url.toString()
        if s.startswith("char:"):
            self.win.open_character(int(s[5:]))
        elif s == "terms":
            self.terms_open = not self.terms_open
            self._rerender()
        elif s.startswith("more:"):
            cid = int(s[5:])
            if cid in self.expanded:
                self.expanded.discard(cid)
            else:
                self.expanded.add(cid)
            self._rerender()

    def _rerender(self):
        bar = self.result.verticalScrollBar()
        pos = bar.value()
        self.run(keep=True)
        bar.setValue(min(pos, bar.maximum()))
