import datetime
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QLabel, QLineEdit, QPushButton, QSplitter, QStackedWidget, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

import library
import picker
import skilldata
import theme
import ui

RE_DATE = re.compile(r"(\d+)\s*월\s*(\d+)\s*일")
VOICE_TYPES = {1: "일상", 2: "전투"}


def browser():
    b = QTextBrowser()
    b.setOpenLinks(False)
    return b


def para(text):
    return "<br>".join(ui.esc(line) for line in (text or "").split("\n"))


class LoreTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.cid = None
        self.pick = picker.CharPicker()
        self.cal_btn = QPushButton("생일 달력")
        self.cal_btn.setToolTip("모든 캐릭터 생일을 달별로 봅니다")
        self.head = QLabel()
        self.head.setTextFormat(Qt.RichText)
        self.head.setWordWrap(True)
        self.tabs = QTabWidget()
        self.intro = browser()
        self.voice_filter = QLineEdit()
        self.voice_filter.setPlaceholderText("대사 제목·내용 검색")
        self.voice_kind = QComboBox()
        self.voice_kind.addItem("전체 대사", None)
        for k, v in VOICE_TYPES.items():
            self.voice_kind.addItem(v + " 대사", k)
        self.voices = browser()
        vw = QVBoxLayout()
        vw.setSpacing(6)
        vw.addLayout(ui.row(self.voice_kind, self.voice_filter, stretch_last=True))
        vw.addWidget(self.voices, 1)
        self.stories = browser()
        self.goods = browser()
        self.tabs.addTab(self.intro, "소개")
        self.tabs.addTab(ui.wrap(vw, (0, 6, 0, 0)), "대사")
        self.tabs.addTab(self.stories, "스토리")
        self.tabs.addTab(self.goods, "소장품")
        self.calendar = browser()

        page = QVBoxLayout()
        page.setSpacing(8)
        page.addWidget(self.head)
        page.addWidget(self.tabs, 1)
        self.stack = QStackedWidget()
        self.stack.addWidget(ui.wrap(page))
        self.stack.addWidget(self.calendar)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addLayout(ui.row(None, self.cal_btn))
        right.addWidget(self.stack, 1)

        split = QSplitter()
        split.addWidget(self.pick)
        split.addWidget(ui.wrap(right, (10, 0, 0, 0)))
        split.setSizes([200, 900])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split)

        self.pick.changed.connect(self.on_char)
        self.cal_btn.clicked.connect(self.show_calendar)
        self.voice_filter.textChanged.connect(self.render_voices)
        self.voice_kind.currentIndexChanged.connect(self.render_voices)

    def reload(self):
        self.pick.load(self.win.con)

    def show_character(self, cid):
        self.pick.select(cid)

    def lib(self, name):
        return library.get(self.win.con, name) if self.win.con else {}

    def on_char(self, cid):
        self.cid = cid
        if cid is None or not self.win.con:
            return
        self.stack.setCurrentIndex(0)
        self.render()

    def render(self):
        cid = str(self.cid)
        name = skilldata.character_name(self.win.con, self.cid)
        color = skilldata.name_colors(self.win.con).get(name, theme.TEXT)
        p = self.lib("profiles").get(cid)
        if not p:
            self.head.setText("<span style='font-size:15pt;font-weight:700;color:%s'>%s</span>"
                              "<div style='color:%s'>이 캐릭터는 프로필 데이터가 없습니다 "
                              "(방랑자 형태 등)</div>" % (color, ui.esc(name), theme.TEXT_DIM))
            for b in (self.intro, self.stories, self.goods, self.voices):
                b.clear()
            return
        meta = " · ".join(x for x in (p.get("birthday") and "생일 " + p["birthday"],
                                       p.get("sex"), p.get("country"), p.get("influence")) if x)
        cv = []
        for k, lang in (("cv_ko", "한국어"), ("cv_ja", "일본어"), ("cv_en", "영어"), ("cv_zh", "중국어")):
            if p.get(k):
                cv.append("<span style='color:%s'>%s</span> %s" % (theme.TEXT_DIM, lang, ui.esc(p[k])))
        self.head.setText(
            "<span style='font-size:15pt;font-weight:700;color:%s'>%s</span>"
            "&nbsp;&nbsp;<span style='color:%s'>%s</span>"
            "<div style='margin-top:4px'>성우 &nbsp;%s</div>"
            % (color, ui.esc(name), theme.TEXT_DIM, ui.esc(meta), " &nbsp;·&nbsp; ".join(cv)))
        h = []
        if p.get("info"):
            h.append(self.section("소개", para(p["info"])))
        if p.get("talent"):
            h.append(self.section("공명 능력 · " + p["talent"], para(p.get("talent_doc"))))
        if p.get("talent_cert"):
            h.append(self.section("오버클럭 진단", para(p["talent_cert"])))
        self.intro.setHtml(ui.doc("".join(h)))
        self.render_list(self.stories, self.lib("stories").get(cid), "스토리가 없습니다")
        self.render_list(self.goods, self.lib("goods").get(cid), "소장품이 없습니다")
        self.render_voices()

    def section(self, title, body):
        return ("<div style='margin:10px 0 2px 0;color:%s;font-weight:600;font-size:11pt'>%s</div>"
                "<div style='color:%s'>%s</div>" % (theme.ACCENT, ui.esc(title), theme.TEXT, body))

    def render_list(self, box, items, empty):
        if not items:
            box.setHtml(ui.doc("<span style='color:%s'>%s</span>" % (theme.TEXT_DIM, empty)))
            return
        box.setHtml(ui.doc("".join(self.section(e["title"], para(e["content"])) for e in items)))

    def render_voices(self, *_):
        if self.cid is None or not self.win.con:
            return
        items = self.lib("voices").get(str(self.cid)) or []
        kind = self.voice_kind.currentData()
        q = self.voice_filter.text().strip()
        rows = [e for e in items if (kind is None or e["type"] == kind)
                and (not q or q in e["title"] or q in e["content"])]
        if not rows:
            self.voices.setHtml(ui.doc("<span style='color:%s'>조건에 맞는 대사가 없습니다</span>"
                                       % theme.TEXT_DIM))
            return
        h = ["<div style='color:%s;font-size:9pt'>대사 %d개 · 음성 파일은 게임 데이터 저장소에 "
             "없어서 텍스트만 제공합니다</div>" % (theme.TEXT_DIM, len(rows))]
        for e in rows:
            tag = VOICE_TYPES.get(e["type"], "")
            h.append("<div style='margin-top:10px'><span style='color:%s;font-weight:600'>%s</span>"
                     " <span style='color:%s;font-size:9pt'>%s</span></div>"
                     "<div>%s</div>" % (theme.ACCENT, ui.esc(e["title"]), theme.TEXT_DIM, tag,
                                        para(e["content"])))
        self.voices.setHtml(ui.doc("".join(h)))

    def show_calendar(self):
        if not self.win.con:
            return
        self.stack.setCurrentIndex(1)
        profiles = self.lib("profiles")
        colors = skilldata.name_colors(self.win.con)
        today = datetime.date.today()
        by_month = {m: [] for m in range(1, 13)}
        upcoming = []
        for cid, name, _b, _v, _e in skilldata.characters(self.win.con):
            p = profiles.get(str(cid))
            m = RE_DATE.search((p or {}).get("birthday") or "")
            if not m:
                continue
            mo, dy = int(m.group(1)), int(m.group(2))
            if any(n == name for _d, n in by_month[mo]):
                continue
            by_month[mo].append((dy, name))
            try:
                d = datetime.date(today.year, mo, dy)
            except ValueError:
                continue
            if d < today:
                d = datetime.date(today.year + 1, mo, dy)
            upcoming.append(((d - today).days, mo, dy, name))
        upcoming.sort()
        h = ["<div style='font-size:13pt;font-weight:700'>생일 달력</div>"]
        if upcoming:
            h.append("<div style='margin:6px 0 10px 0;color:%s'>다가오는 생일 &nbsp;%s</div>" % (
                theme.TEXT_DIM, " &nbsp;·&nbsp; ".join(
                    "<span style='color:%s'>%s</span> %d/%d%s" % (
                        colors.get(n, theme.TEXT), ui.esc(n), mo, dy,
                        " <b style='color:%s'>오늘!</b>" % theme.HIGHLIGHT if days == 0
                        else " (%d일 뒤)" % days)
                    for days, mo, dy, n in upcoming[:5])))
        h.append("<table cellspacing='0' cellpadding='0'>")
        for mo in range(1, 13):
            names = sorted(by_month[mo])
            cur = mo == today.month
            h.append("<tr><td style='padding:5px 14px 5px 0;vertical-align:top;color:%s;"
                     "font-weight:%s;white-space:nowrap'>%d월</td><td style='padding:5px 0'>%s</td></tr>"
                     % (theme.HIGHLIGHT if cur else theme.TEXT_DIM, "700" if cur else "400", mo,
                        " &nbsp; ".join("<span style='color:%s'>%s</span> <span style='color:%s'>"
                                        "%d일</span>" % (colors.get(n, theme.TEXT), ui.esc(n),
                                                        theme.TEXT_DIM, d)
                                        for d, n in names) or
                        "<span style='color:%s'>-</span>" % theme.TEXT_DIM))
        h.append("</table>")
        self.calendar.setHtml(ui.doc("".join(h)))
