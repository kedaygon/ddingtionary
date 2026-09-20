import math

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout,
    QWidget,
)

import config
import library
import skilldata
import theme
import ui

QUALITY_COLORS = {5: "#e8c56a", 4: "#c9a2ff", 3: "#6ea8fe", 2: "#5fd3a0", 1: "#8b93a5"}
SKILL_TYPES = {1: "일반 공격", 2: "공명 스킬", 3: "공명 해방", 5: "변주 스킬", 6: "공명 회로"}
WEAPON_TYPES = {1: "대검", 2: "직검", 3: "권총", 4: "권갑", 5: "증폭기"}
CREDIT = "2"


def states(breach):
    out = [(1, 0)]
    bl = sorted(breach, key=lambda x: x[0])
    for i, (b, cap, _c) in enumerate(bl):
        if cap not in (s[0] for s in out) or out[-1] != (cap, b):
            out.append((cap, b))
        if i + 1 < len(bl):
            out.append((cap, bl[i + 1][0]))
    seen = []
    for s in out:
        if s not in seen:
            seen.append(s)
    return seen


def state_label(s, breach):
    lv, b = s
    caps = {x[0]: x[1] for x in breach}
    if b and caps.get(b - 1) == lv and caps.get(b, 0) > lv:
        return "Lv %d · 돌파 완료" % lv
    return "Lv %d" % lv


def add(total, key, n):
    if n:
        total[str(key)] = total.get(str(key), 0) + n


def exp_split(exp, items):
    out = []
    left = exp
    for iid, val, cost in sorted(items, key=lambda x: -x[1]):
        n = left // val
        if n:
            out.append((iid, n, cost))
            left -= n * val
    if left > 0 and items:
        iid, val, cost = min(items, key=lambda x: x[1])
        n = int(math.ceil(left / float(val)))
        for i, (a, m, c) in enumerate(out):
            if a == iid:
                out[i] = (a, m + n, c)
                break
        else:
            out.append((iid, n, cost))
    return out


class PlanTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._busy = False

        self.add_char = QComboBox()
        self.add_char.setMinimumWidth(150)
        self.add_char_btn = QPushButton("캐릭터 추가")
        self.add_char_btn.setObjectName("primary")
        self.add_weapon = QComboBox()
        self.add_weapon.setMinimumWidth(150)
        self.add_weapon_btn = QPushButton("무기 추가")
        self.add_weapon_btn.setObjectName("primary")
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(False)
        self.rm_btn = QPushButton("선택 항목 삭제")
        self.rm_btn.setObjectName("danger")

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(ui.label("육성 계획", "section"))
        left.addWidget(ui.label("체크한 항목만 합계에 들어갑니다", "hint"))
        left.addWidget(self.list, 1)
        left.addWidget(self.rm_btn)
        left.addWidget(ui.separator())
        left.addWidget(self.add_char)
        left.addWidget(self.add_char_btn)
        left.addWidget(self.add_weapon)
        left.addWidget(self.add_weapon_btn)
        leftw = ui.wrap(left)
        leftw.setMinimumWidth(220)
        leftw.setMaximumWidth(260)

        self.form = QVBoxLayout()
        self.form.setSpacing(8)
        self.formw = ui.wrap(self.form, (6, 0, 6, 0))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.formw)
        scroll.setMinimumWidth(380)

        self.scope = QComboBox()
        self.scope.addItem("체크한 항목 전체 합계", "all")
        self.scope.addItem("선택한 항목만", "one")
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addLayout(ui.row(ui.label("필요 재료", "section"), None, self.scope))
        right.addWidget(self.body, 1)

        split = QSplitter()
        split.addWidget(leftw)
        split.addWidget(scroll)
        split.addWidget(ui.wrap(right, (8, 0, 0, 0)))
        split.setSizes([240, 440, 520])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split)

        self.add_char_btn.clicked.connect(self.on_add_char)
        self.add_weapon_btn.clicked.connect(self.on_add_weapon)
        self.rm_btn.clicked.connect(self.on_remove)
        self.list.currentRowChanged.connect(self.on_select)
        self.list.itemChanged.connect(self.on_check)
        self.scope.currentIndexChanged.connect(self.render)

    def lib(self, name):
        return library.get(self.win.con, name) if self.win.con else {}

    def plan(self):
        return self.win.cfg.setdefault("plan", [])

    def save(self):
        config.save(self.win.cfg)

    def reload(self):
        if not self.win.con:
            return
        self.add_char.clear()
        roles = self.lib("roles")
        for cid, name, _b, _v, elem in skilldata.characters(self.win.con):
            if str(cid) in roles and roles[str(cid)]["skills"]:
                self.add_char.addItem(name, cid)
                self.add_char.setItemData(self.add_char.count() - 1,
                                          QColor(theme.element_color(skilldata.ELEMENTS.get(elem))),
                                          Qt.ForegroundRole)
        self.add_weapon.clear()
        ws = self.lib("weapons")
        for wid, w in sorted(ws.items(), key=lambda kv: (kv[1]["type"] or 0, -(kv[1]["quality"] or 0),
                                                          kv[1]["name"])):
            if (w["quality"] or 0) < 3 or not w["breach"]:
                continue
            self.add_weapon.addItem("%s · %s %s" % (WEAPON_TYPES.get(w["type"], ""), "★" * w["quality"],
                                                    w["name"]), int(wid))
            self.add_weapon.setItemData(self.add_weapon.count() - 1,
                                        QColor(QUALITY_COLORS.get(w["quality"], theme.TEXT)),
                                        Qt.ForegroundRole)
        valid = []
        for e in self.plan():
            if (e.get("kind") == "role" and str(e.get("id")) in roles) or \
                    (e.get("kind") == "weapon" and str(e.get("id")) in ws):
                valid.append(e)
        self.win.cfg["plan"] = valid
        self.refresh_list(0 if valid else None)

    def entry_name(self, e):
        if e["kind"] == "role":
            return skilldata.character_name(self.win.con, e["id"])
        w = self.lib("weapons").get(str(e["id"])) or {}
        return "%s %s" % ("★" * (w.get("quality") or 0), w.get("name", "?"))

    def refresh_list(self, select=None):
        self._busy = True
        self.list.clear()
        colors = skilldata.name_colors(self.win.con) if self.win.con else {}
        for e in self.plan():
            name = self.entry_name(e)
            summary = self.summary(e)
            it = QListWidgetItem("%s\n%s" % (name, summary))
            it.setSizeHint(QSize(0, 46))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if e.get("on", True) else Qt.Unchecked)
            if e["kind"] == "role":
                it.setForeground(QColor(colors.get(name, theme.TEXT)))
            else:
                w = self.lib("weapons").get(str(e["id"])) or {}
                it.setForeground(QColor(QUALITY_COLORS.get(w.get("quality"), theme.TEXT)))
            self.list.addItem(it)
        self._busy = False
        if select is not None and 0 <= select < self.list.count():
            self.list.setCurrentRow(select)
        else:
            self.build_form(None)
        self.render()

    def summary(self, e):
        src = self.lib("roles" if e["kind"] == "role" else "weapons").get(str(e["id"])) or {}
        br = src.get("breach") or []
        s = "Lv %d → %d" % (e["from"][0], e["to"][0])
        if e["kind"] == "role":
            ups = sum(1 for c, t in e.get("skills") or [] if t > c)
            if ups:
                s += " · 스킬 %d개" % ups
            n = sum(1 for x in e.get("nodes") or [] if x)
            if n:
                s += " · 노드 %d" % n
        return s if br else "데이터 없음"

    def new_role(self, cid):
        r = self.lib("roles").get(str(cid)) or {}
        st = states(r.get("breach") or [])
        return {"kind": "role", "id": cid, "on": True, "from": list(st[0]), "to": list(st[-1]),
                "skills": [[1, 10] for _ in r.get("skills") or []],
                "nodes": [True] * (len(r.get("inherent") or []) + len(r.get("stats") or []))}

    def new_weapon(self, wid):
        w = self.lib("weapons").get(str(wid)) or {}
        st = states(w.get("breach") or [])
        return {"kind": "weapon", "id": wid, "on": True, "from": list(st[0]), "to": list(st[-1])}

    def on_add_char(self):
        cid = self.add_char.currentData()
        if cid is None:
            return
        self.plan().append(self.new_role(cid))
        self.save()
        self.refresh_list(len(self.plan()) - 1)

    def on_add_weapon(self):
        wid = self.add_weapon.currentData()
        if wid is None:
            return
        self.plan().append(self.new_weapon(wid))
        self.save()
        self.refresh_list(len(self.plan()) - 1)

    def on_remove(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.plan()):
            del self.plan()[row]
            self.save()
            self.refresh_list(min(row, len(self.plan()) - 1) if self.plan() else None)

    def on_check(self, item):
        if self._busy:
            return
        row = self.list.row(item)
        if 0 <= row < len(self.plan()):
            self.plan()[row]["on"] = item.checkState() == Qt.Checked
            self.save()
            self.render()

    def on_select(self, row):
        if self._busy:
            return
        self.build_form(self.plan()[row] if 0 <= row < len(self.plan()) else None)
        self.render()

    def current(self):
        row = self.list.currentRow()
        return self.plan()[row] if 0 <= row < len(self.plan()) else None

    def clear_form(self):
        while self.form.count():
            it = self.form.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif it.layout():
                lay = it.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget():
                        sub.widget().hide()
                        sub.widget().setParent(None)
                        sub.widget().deleteLater()

    def level_box(self, breach, value):
        cb = QComboBox()
        cb.setMinimumHeight(30)
        for s in states(breach):
            cb.addItem(state_label(s, breach), list(s))
        i = cb.findData(list(value))
        cb.setCurrentIndex(i if i >= 0 else 0)
        return cb

    def build_form(self, e):
        self.clear_form()
        if e is None:
            self.form.addWidget(ui.label(
                "왼쪽 아래에서 캐릭터나 무기를 골라 [추가]하세요. 현재 상태와 목표를 정하면 오른쪽에 "
                "필요한 재료 합계가 나옵니다. 여러 명을 넣어 한 번에 계산할 수 있습니다.", "hint"))
            self.form.addStretch(1)
            return
        src = self.lib("roles" if e["kind"] == "role" else "weapons").get(str(e["id"])) or {}
        breach = src.get("breach") or []
        title = ui.label(self.entry_name(e), "h1")
        if e["kind"] == "role":
            title.setStyleSheet("color:%s" % skilldata.name_colors(self.win.con).get(
                self.entry_name(e), theme.TEXT))
        self.form.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        cur = self.level_box(breach, e["from"])
        tgt = self.level_box(breach, e["to"])
        grid.addWidget(ui.label("레벨", "hint"), 0, 0)
        grid.addWidget(cur, 0, 1)
        grid.addWidget(QLabel("→"), 0, 2)
        grid.addWidget(tgt, 0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        cur.currentIndexChanged.connect(lambda _i: self.set_level(e, "from", cur.currentData()))
        tgt.currentIndexChanged.connect(lambda _i: self.set_level(e, "to", tgt.currentData()))
        self.form.addLayout(grid)
        if e["kind"] == "role":
            skills = src.get("skills") or []
            sg = QGridLayout()
            sg.setHorizontalSpacing(8)
            sg.setVerticalSpacing(6)
            self.form.addWidget(ui.label("스킬 레벨 (현재 → 목표)", "section"))
            while len(e["skills"]) < len(skills):
                e["skills"].append([1, 10])
            for i, s in enumerate(skills):
                lab = ui.label("%s · %s" % (SKILL_TYPES.get(s["type"], ""), s["name"]))
                a = QSpinBox()
                b = QSpinBox()
                for sp, v in ((a, e["skills"][i][0]), (b, e["skills"][i][1])):
                    sp.setRange(1, 10)
                    sp.setValue(v)
                    sp.setMinimumHeight(30)
                    sp.setMinimumWidth(80)
                a.valueChanged.connect(lambda v, k=i: self.set_skill(e, k, 0, v))
                b.valueChanged.connect(lambda v, k=i: self.set_skill(e, k, 1, v))
                sg.addWidget(lab, i, 0)
                sg.addWidget(a, i, 1)
                sg.addWidget(QLabel("→"), i, 2)
                sg.addWidget(b, i, 3)
            sg.setColumnStretch(0, 1)
            self.form.addLayout(sg)
            nodes = [("고유 스킬", n["name"]) for n in src.get("inherent") or []] + \
                    [("능력치", n["name"]) for n in src.get("stats") or []]
            while len(e["nodes"]) < len(nodes):
                e["nodes"].append(True)
            self.form.addWidget(ui.label("스킬트리 노드 (새로 찍을 것만 체크)", "section"))
            ng = QGridLayout()
            ng.setHorizontalSpacing(12)
            for i, (kind, name) in enumerate(nodes):
                box = QCheckBox("%s · %s" % (kind, name))
                box.setChecked(bool(e["nodes"][i]))
                box.toggled.connect(lambda on, k=i: self.set_node(e, k, on))
                ng.addWidget(box, i, 0)
            self.form.addLayout(ng)
            quick = QHBoxLayout()
            b1 = QPushButton("전부 최대로")
            b1.setToolTip("레벨 90, 스킬 10, 스킬트리 전부")
            b2 = QPushButton("스킬·노드 비우기")
            b1.clicked.connect(lambda: self.preset(e, True))
            b2.clicked.connect(lambda: self.preset(e, False))
            quick.addWidget(b1)
            quick.addWidget(b2)
            quick.addStretch(1)
            self.form.addLayout(quick)
        self.form.addStretch(1)

    def touch(self, e):
        self.save()
        row = self.list.currentRow()
        it = self.list.item(row)
        if it:
            self._busy = True
            it.setText("%s\n%s" % (self.entry_name(e), self.summary(e)))
            self._busy = False
        self.render()

    def set_level(self, e, key, value):
        if value is None:
            return
        e[key] = list(value)
        if tuple(e["to"]) < tuple(e["from"]):
            other = "to" if key == "from" else "from"
            e[other] = list(value)
            self.build_form(e)
        self.touch(e)

    def set_skill(self, e, k, which, v):
        e["skills"][k][which] = v
        if e["skills"][k][1] < e["skills"][k][0]:
            e["skills"][k][1 - which] = v
            self.build_form(e)
        self.touch(e)

    def set_node(self, e, k, on):
        e["nodes"][k] = on
        self.touch(e)

    def preset(self, e, full):
        r = self.lib("roles").get(str(e["id"])) or {}
        if full:
            e["to"] = list(states(r.get("breach") or [])[-1])
            e["skills"] = [[c, 10] for c, _t in e["skills"]]
            e["nodes"] = [True] * len(e["nodes"])
        else:
            e["skills"] = [[c, c] for c, _t in e["skills"]]
            e["nodes"] = [False] * len(e["nodes"])
        self.build_form(e)
        self.touch(e)

    def cost(self, e):
        total = {}
        exp = 0
        src = self.lib("roles" if e["kind"] == "role" else "weapons").get(str(e["id"])) or {}
        shift = 1 if e["kind"] == "weapon" else 0
        breach = {b + shift: c for b, _cap, c in src.get("breach") or []}
        (l0, b0), (l1, b1) = e["from"], e["to"]
        for b in range(b0 + 1, b1 + 1):
            for k, n in breach.get(b, []):
                add(total, k, n)
        if e["kind"] == "role":
            table = self.lib("role_exp").get(str(src.get("exp_group"))) or {}
            exp = sum(table.get(str(l), 0) for l in range(l0 + 1, l1 + 1))
            items = self.lib("exp_items").get("role") or []
            for s, (c, t) in zip(src.get("skills") or [], e.get("skills") or []):
                for lv in range(c + 1, t + 1):
                    for k, n in s["levels"].get(str(lv), []):
                        add(total, k, n)
            nodes = (src.get("inherent") or []) + (src.get("stats") or [])
            for n, on in zip(nodes, e.get("nodes") or []):
                if on:
                    for k, v in n["consume"]:
                        add(total, k, v)
        else:
            table = self.lib("weapon_exp").get(str(src.get("level_group"))) or {}
            exp = sum(table.get(str(l), 0) for l in range(l0, l1))
            items = self.lib("exp_items").get("weapon") or []
        potions = exp_split(exp, items) if exp else []
        for iid, n, c in potions:
            add(total, iid, n)
            add(total, CREDIT, n * c)
        return total, exp

    def table(self, rows):
        h = ["<table cellspacing='0' cellpadding='0' style='margin-top:4px'>"]
        for _q, name, _k, v, it in rows:
            col = QUALITY_COLORS.get(it["quality"], theme.TEXT)
            where = " · ".join(it["access"][:3])
            h.append("<tr><td style='padding:4px 14px 4px 0;color:%s;font-weight:600'>%s</td>"
                     "<td style='padding:4px 14px 4px 0;text-align:right;color:%s;font-weight:700'>%s</td>"
                     "<td style='padding:4px 0;color:%s;font-size:9pt'>%s</td></tr>"
                     % (col, ui.esc(name), theme.TEXT, "{:,}".format(v), theme.TEXT_DIM,
                        ui.esc(where or it.get("use") or "")))
        h.append("</table>")
        return "".join(h)

    def render(self, *_):
        if not self.win.con:
            return
        items = self.lib("items")
        if self.scope.currentData() == "one":
            e = self.current()
            entries = [e] if e else []
        else:
            entries = [e for e in self.plan() if e.get("on", True)]
        if not entries:
            self.body.setHtml(ui.doc("<span style='color:%s'>계획에 항목을 추가하면 여기에 필요한 재료가 "
                                     "나옵니다.</span>" % theme.TEXT_DIM))
            return
        total = {}
        exp_role = exp_weapon = 0
        for e in entries:
            t, ex = self.cost(e)
            for k, v in t.items():
                total[k] = total.get(k, 0) + v
            if e["kind"] == "role":
                exp_role += ex
            else:
                exp_weapon += ex
        exp_ids = {str(i) for kind in (self.lib("exp_items") or {}).values() for i, _e, _c in kind}
        credit = total.pop(CREDIT, 0)
        rows = []
        exp_rows = []
        for k, v in total.items():
            it = items.get(k) or {"name": "아이템 %s" % k, "quality": 1, "use": "", "access": []}
            (exp_rows if k in exp_ids else rows).append((-(it["quality"] or 0), it["name"], k, v, it))
        rows.sort()
        exp_rows.sort()
        h = ["<div style='color:%s;font-size:9pt'>%d개 항목 기준</div>" % (theme.TEXT_DIM, len(entries))]
        h.append("<div style='margin-top:6px;font-size:13pt;font-weight:700'>코인 "
                 "<span style='color:%s'>%s</span></div>" % (theme.HIGHLIGHT, "{:,}".format(credit)))
        h.append("<div style='color:%s;font-size:9pt'>돌파·스킬·스킬트리·무기 강화에 드는 코인입니다. "
                 "캐릭터 레벨업에 드는 코인은 게임 데이터에 값이 없어 넣지 않았습니다.</div>" % theme.TEXT_DIM)
        if exp_rows:
            h.append("<div style='margin-top:10px;font-weight:600'>경험치 재료</div>"
                     "<div style='color:%s;font-size:9pt'>캐릭터 경험치 %s · 무기 경험치 %s를 큰 재료부터 "
                     "채운 개수</div>" % (theme.TEXT_DIM, "{:,}".format(exp_role), "{:,}".format(exp_weapon)))
            h.append(self.table(exp_rows))
        if rows:
            h.append("<div style='margin-top:10px;font-weight:600'>돌파·스킬 재료</div>")
            h.append(self.table(rows))
        self.body.setHtml(ui.doc("".join(h)))
