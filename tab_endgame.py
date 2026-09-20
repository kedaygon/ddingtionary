import re

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

import library
import theme
import ui

TOWER_ZONES = {1: "안정 구역", 2: "실험 구역", 3: "심경 구역", 4: "과부하 구역"}
MODES = [("tower", "역경의 탑"), ("matrix", "종말 매트릭스"), ("ruins", "바닷속 폐허")]
MODE_HINTS = {
    "tower": "탑(구역)마다 접혀 있습니다. 제목을 누르면 층별 적·추천 속성·층 효과가 펼쳐집니다.",
    "matrix": "높은 단계가 위에 있습니다. 제목을 누르면 라운드별 적·레벨·태그·위기 진화 효과와 선택 버프가 펼쳐집니다.",
    "ruins": "1~6단계는 상시, 7~12단계는 시즌마다 바뀝니다. 제목을 누르면 효과와 파티별 상대가 펼쳐집니다.",
}


def mon_html(m, count=1):
    el = m.get("elements") or []
    col = theme.element_color(el[0]) if el else theme.TEXT
    tail = (" <span style='color:%s;font-size:9pt'>%s</span>" % (theme.TEXT_DIM, "·".join(el))) \
        if el else ""
    n = (" <span style='color:%s'>×%d</span>" % (theme.TEXT_DIM, count)) if count > 1 else ""
    return "<span style='color:%s'>%s</span>%s%s" % (col, ui.esc(m["name"] or "?"), n, tail)


def team_html(team):
    seen = {}
    for m in team:
        key = m.get("name") or "?"
        if key in seen:
            seen[key][1] += 1
        else:
            seen[key] = [m, 1]
    return " &nbsp;·&nbsp; ".join(mon_html(m, c) for m, c in seen.values())


def element_dots(elems):
    return " ".join("<span style='color:%s'>%s</span>" % (theme.element_color(e), e) for e in elems)


def text_html(s):
    return "<br>".join(ui.esc(x) for x in (s or "").split("\n") if x.strip())


def lines(s):
    return [x.strip() for x in (s or "").split("\n") if x.strip()]


def common_lines(descs):
    descs = [lines(d) for d in descs if d]
    if len(descs) < 2:
        return []
    return [x for x in descs[0] if all(x in d for d in descs[1:])]


def plain(html_text):
    return re.sub(r"<[^>]+>", " ", html_text)


class EndgameTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.mode = "tower"
        self.opened = {}
        self.keys = []
        self.group = QButtonGroup(self)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.buttons = {}
        for key, name in MODES:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setMinimumWidth(120)
            self.group.addButton(b)
            self.buttons[key] = b
            bar.addWidget(b)
            b.clicked.connect(lambda _c=False, k=key: self.set_mode(k))
        self.buttons["tower"].setChecked(True)
        self.season = QComboBox()
        self.season.setMinimumWidth(220)
        bar.addStretch(1)
        bar.addWidget(ui.label("시즌", "hint"))
        bar.addWidget(self.season)

        self.query = QLineEdit()
        self.query.setPlaceholderText("적 이름·효과로 찾기 (예: 드레이크, 공명 해방)")
        self.query.setClearButtonEnabled(True)
        self.expand_btn = QPushButton("모두 펼치기")
        self.collapse_btn = QPushButton("모두 접기")
        tools = QHBoxLayout()
        tools.setSpacing(6)
        tools.addWidget(self.query, 1)
        tools.addWidget(self.expand_btn)
        tools.addWidget(self.collapse_btn)

        self.hint = ui.label("", "hint")
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self.on_anchor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addLayout(bar)
        lay.addLayout(tools)
        lay.addWidget(self.hint)
        lay.addWidget(self.body, 1)
        self.season.currentIndexChanged.connect(lambda *_: self.render(reset_scroll=True))
        self.expand_btn.clicked.connect(lambda: self.set_all(True))
        self.collapse_btn.clicked.connect(lambda: self.set_all(False))
        self.qtimer = QTimer(self)
        self.qtimer.setSingleShot(True)
        self.qtimer.setInterval(200)
        self.qtimer.timeout.connect(lambda: self.render(reset_scroll=True))
        self.query.textChanged.connect(lambda *_: self.qtimer.start())

    def lib(self, name):
        return library.get(self.win.con, name) if self.win.con else {}

    def reload(self):
        self.set_mode(self.mode)

    def state_key(self):
        return (self.mode, self.season.currentData())

    def open_set(self):
        return self.opened.setdefault(self.state_key(), set())

    def on_anchor(self, url):
        s = url.toString()
        if not s.startswith("toggle:"):
            return
        key = s[len("toggle:"):]
        st = self.open_set()
        if key in st:
            st.discard(key)
        else:
            st.add(key)
        self.render()

    def set_all(self, on):
        st = self.open_set()
        st.clear()
        if on:
            st.update(self.keys)
        self.render()

    def set_mode(self, key):
        self.mode = key
        self.buttons[key].setChecked(True)
        self.hint.setText(MODE_HINTS[key])
        self.season.blockSignals(True)
        self.season.clear()
        if key == "tower":
            data = self.lib("tower")
            seasons = sorted((int(s) for s in data), reverse=True)
            for s in seasons:
                if s == 0:
                    continue
                self.season.addItem("심경 구역 시즌 %d%s" % (s, " · 데이터상 최신" if s == seasons[0] else ""), s)
            if 0 in seasons:
                self.season.addItem("상시 구역 (안정·실험·과부하)", 0)
        elif key == "ruins":
            data = self.lib("ruins")
            seasons = sorted((int(s) for s in data if int(s) > 0), reverse=True)
            for s in seasons:
                self.season.addItem("시즌 %d%s" % (s, " · 데이터상 최신" if s == seasons[0] else ""), s)
        else:
            seasons = self.lib("matrix").get("seasons") or []
            for i, s in enumerate(seasons):
                self.season.addItem("%s (%s~%s)" % (s["name"], s["start"], s["end"]), i)
            ver = self.win.cfg.get("version") or ""
            pick = len(seasons) - 1
            for i, s in enumerate(seasons):
                if _ver(s["start"]) <= _ver(ver) <= _ver(s["end"]):
                    pick = i
            if pick >= 0:
                self.season.setCurrentIndex(pick)
        self.season.blockSignals(False)
        self.render(reset_scroll=True)

    def render(self, *_a, reset_scroll=False):
        if not self.win.con:
            return
        if not self.season.count():
            self.keys = []
            self.body.setHtml(ui.doc("<span style='color:%s'>데이터가 없습니다. 데이터 화면에서 다시 "
                                     "받아 주세요.</span>" % theme.TEXT_DIM))
            return
        fn = {"tower": self.tower_sections, "matrix": self.matrix_sections,
              "ruins": self.ruins_sections}[self.mode]
        intro, sections = fn(self.season.currentData())
        q = self.query.text().strip()
        st = self.open_set()
        self.keys = [s["key"] for s in sections if s.get("key")]
        out = [intro] if intro else []
        shown = 0
        for s in sections:
            if not s.get("key"):
                if not q:
                    out.append(s["html"])
                continue
            if q and q not in plain(s["title"] + " " + s["sub"] + " " + s["body"]):
                continue
            shown += 1
            opened = bool(q) or s["key"] in st
            out.append(self.header(s, opened))
            if opened:
                out.append("<div style='margin:2px 0 10px 18px'>%s</div>" % s["body"])
        if q and not shown:
            out.append("<div style='color:%s;margin-top:12px'>'%s'이(가) 들어간 구역이 없습니다</div>"
                       % (theme.TEXT_DIM, ui.esc(q)))
        sb = self.body.verticalScrollBar()
        pos = 0 if reset_scroll else sb.value()
        self.body.setHtml(ui.doc("".join(out)))
        sb.setValue(pos)

    def header(self, s, opened):
        return ("<table width='100%%' cellspacing='0' cellpadding='6' style='margin-top:6px;"
                "background-color:%s'><tr><td><a href='toggle:%s' style='text-decoration:none;color:%s'>"
                "<span style='color:%s'>%s</span>&nbsp; <b style='font-size:11pt'>%s</b></a>"
                "&nbsp;&nbsp;<span style='color:%s;font-size:9pt'>%s</span></td></tr></table>"
                % (theme.PANEL, s["key"], theme.TEXT, theme.ACCENT, "▾" if opened else "▸",
                   s["title"], theme.TEXT_DIM, s["sub"]))

    def group_html(self, title, note=""):
        return ("<div style='margin-top:18px;font-size:12pt;font-weight:700;color:%s'>%s</div>%s"
                % (theme.HIGHLIGHT, ui.esc(title), note))

    def tower_sections(self, season):
        floors = self.lib("tower").get(str(season)) or []
        groups = {}
        for f in floors:
            groups.setdefault((f["difficulty"], f["area"], f["area_name"]), []).append(f)
        sections = []
        last_diff = None
        for (diff, area, name), fl in sorted(groups.items()):
            if diff != last_diff:
                sections.append({"html": self.group_html(TOWER_ZONES.get(diff, "구역"))})
                last_diff = diff
            fl = sorted(fl, key=lambda x: x["floor"])
            rec = []
            for f in fl:
                rec += [e for e in f["recommend"] if e not in rec]
            rows = ["<table cellspacing='0' cellpadding='0'>"]
            for f in fl:
                r = element_dots(f["recommend"])
                rows.append(
                    "<tr><td style='padding:5px 14px 5px 0;vertical-align:top;color:%s;"
                    "font-weight:600;white-space:nowrap'>%d층</td><td style='padding:5px 0'>"
                    "<div>%s</div>%s%s</td></tr>"
                    % (theme.ACCENT, f["floor"], team_html(f["monsters"]) or "-",
                       ("<div style='color:%s;font-size:9pt'>추천 속성 %s</div>" % (theme.TEXT_DIM, r))
                       if r else "",
                       "".join("<div style='color:%s;font-size:9pt'>▸ %s</div>" % (theme.TERM, text_html(b))
                               for b in f["buffs"])))
            rows.append("</table>")
            sub = "%d~%d층" % (fl[0]["floor"], fl[-1]["floor"])
            if rec:
                sub += " · 추천 " + element_dots(rec)
            sections.append({"key": "t%d_%d" % (diff, area), "title": ui.esc(name), "sub": sub,
                             "body": "".join(rows)})
        return "", sections

    def matrix_sections(self, idx):
        data = self.lib("matrix")
        levels = {lv["id"]: lv for lv in data.get("levels") or []}
        waves = {}
        for w in data.get("waves") or []:
            waves.setdefault(w["level"], []).append(w)
        intro = ""
        seasons = data.get("seasons") or []
        ver = self.win.cfg.get("version") or ""
        if seasons and idx is not None and 0 <= idx < len(seasons):
            s = seasons[idx]
            if not (_ver(s["start"]) <= _ver(ver) <= _ver(s["end"])):
                intro = ("<div style='color:%s'>데이터에는 지금 버전(%s)의 단계 구성만 들어 있어서, 다른 시즌을 "
                         "골라도 아래 내용은 지금 버전 기준입니다</div>" % (theme.WARN, ui.esc(ver)))
        sections = []
        for lid in sorted(levels, key=lambda i: (-levels[i]["stage"], levels[i]["hard"])):
            lv = levels[lid]
            body = []
            if lv["buffs"]:
                body.append("<div style='color:%s;font-size:9pt'>선택 버프</div>" % theme.TEXT_DIM)
                for b in lv["buffs"]:
                    body.append("<div style='margin-left:8px'><span style='color:%s'>%s</span> "
                                "<span style='color:%s;font-size:9pt'>%s</span></div>"
                                % (theme.TERM, ui.esc(b["name"]), theme.TEXT_DIM, text_html(b["desc"])))
            rounds = {}
            for w in sorted(waves.get(lid, []), key=lambda x: (x["round"], x["wave"])):
                rounds.setdefault(w["round"], []).append(w)
            elems, top_lv = [], 0
            for r, ws in sorted(rounds.items()):
                body.append("<div style='margin:6px 0 0 0;color:%s;font-weight:600'>%d라운드</div>"
                            % (theme.ACCENT, r))
                for w in ws:
                    if w["element"] and w["element"] not in elems:
                        elems.append(w["element"])
                    top_lv = max(top_lv, w["monster_level"] or 0)
                    col = theme.element_color(w["element"]) if w["element"] else theme.TEXT
                    tags = "".join(" <span style='color:%s;font-size:9pt'>[%s]</span>" % (theme.WARN, ui.esc(t))
                                   for t in w["tags"])
                    meta = " · ".join(x for x in (("Lv%d" % w["monster_level"]) if w["monster_level"] else "",
                                                  w["element"] or "") if x)
                    body.append("<div style='margin-left:8px'><span style='color:%s'>%s</span> "
                                "<span style='color:%s;font-size:9pt'>%s</span>%s</div>"
                                % (col, ui.esc(w["name"]), theme.TEXT_DIM, meta, tags))
                    for sk in w["skills"]:
                        body.append("<div style='margin-left:22px;font-size:9pt'><span style='color:%s'>%s"
                                    "</span> <span style='color:%s'>%s</span></div>"
                                    % (theme.HIGHLIGHT, ui.esc(sk["title"]), theme.TEXT_DIM,
                                       text_html(sk["desc"])))
            score = [v for _k, v in lv["score"] if v]
            sub = []
            if top_lv:
                sub.append("적 Lv%d" % top_lv)
            if elems:
                sub.append(element_dots(elems))
            if score:
                sub.append("점수 " + " / ".join("{:,}".format(v) for v in score))
            title = "%d단계%s" % (lv["stage"], " · <span style='color:%s'>고난도</span>" % theme.BAD
                                 if lv["hard"] else "")
            sections.append({"key": "m%d" % lid, "title": title, "sub": " · ".join(sub),
                             "body": "".join(body) or "-"})
        return intro, sections

    def ruins_sections(self, season):
        stages = self.lib("ruins").get(str(season)) or []
        sections = []
        for base in (True, False):
            group = [s for s in stages if s.get("base") == base]
            if not group:
                continue
            common = common_lines([s["desc"] for s in group])
            note = ""
            if common:
                note = ("<div style='color:%s;font-size:9pt;margin-top:2px'>%s 모든 단계 공통</div>"
                        "<div style='color:%s;margin-left:8px'>%s</div>"
                        % (theme.TEXT_DIM, "상시" if base else "이번 시즌", theme.TERM,
                           "<br>".join(ui.esc(x) for x in common)))
            lo, hi = group[0]["order"], group[-1]["order"]
            sections.append({"html": self.group_html(
                "%s  %d~%d단계" % ("상시 단계" if base else "시즌 단계", lo, hi), note)})
            for st in group:
                own = [x for x in lines(st["desc"]) if x not in common]
                body = []
                if own:
                    body.append("<div style='color:%s'>%s</div>"
                                % (theme.TERM, "<br>".join(ui.esc(x) for x in own)))
                for j, team in enumerate(st["teams"], 1):
                    if team:
                        body.append("<div style='margin-top:4px'><span style='color:%s'>%d파티 상대</span>"
                                    " &nbsp;%s</div>" % (theme.TEXT_DIM, j, team_html(team)))
                target = " / ".join("{:,}".format(v) for v in st["target"] if v)
                sub = ("목표 점수 " + target) if target else ""
                title = "%d단계 · %s%s" % (st["order"], ui.esc(st["title"] or "스테이지"),
                                          " · <span style='color:%s'>무한</span>" % theme.WARN
                                          if st["endless"] else "")
                sections.append({"key": "r%d" % st["order"], "title": title, "sub": sub,
                                 "body": "".join(body) or "-"})
        return "", sections


def _ver(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)
