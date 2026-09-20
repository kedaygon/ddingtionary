from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QPushButton, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)

import config
import modes
import party
import skilldata
import synergy
import theme
import ui

MAX_MEMBERS = 3

STAT_LABEL = {
    "atk": "공격력",
    "dmg_bonus": "피해 보너스",
    "dmg_boost": "피해 부스트",
    "damage_taken": "받는 피해",
    "res_shred": "저항 감소",
    "def_ignore": "방어 무시",
    "crit_dmg": "크리티컬 피해",
    "crit_rate": "크리티컬",
}
SLOTS = ["A", "B"]


def buff_label(scope, stat):
    word = STAT_LABEL.get(stat, "")
    if scope in ("전체", "전체 피해", None, ""):
        return "전체 속성 " + word if word.startswith("피해") else word
    if scope.endswith(" 피해") and word.startswith("피해"):
        return scope + word[2:]
    return ("%s %s" % (scope, word)).strip()


def gauge(pct, color, width=22, cap=60.0):
    n = max(0, min(width, round(width * pct / cap)))
    return ("<span style='color:%s'>%s</span>"
            "<span style='color:%s'>%s</span>") % (
        color, "█" * n, theme.BORDER, "─" * (width - n))


class SlotCard(QFrame):
    def __init__(self, tab, index):
        super().__init__()
        self.tab = tab
        self.index = index
        self.cid = None
        self.setObjectName("card")
        self.setMinimumWidth(190)
        self.num = ui.label("%d번 슬롯" % (index + 1), "hint")
        self.left_btn = QPushButton("◀")
        self.right_btn = QPushButton("▶")
        self.del_btn = QPushButton("✕")
        for b, tip in ((self.left_btn, "앞 슬롯과 순서 바꾸기"),
                       (self.right_btn, "뒤 슬롯과 순서 바꾸기"),
                       (self.del_btn, "파티에서 빼기")):
            b.setObjectName("mini")
            b.setToolTip(tip)
        self.del_btn.setProperty("danger", True)
        self.name = QLabel("")
        self.name.setStyleSheet("font-size:12pt;font-weight:700")
        self.empty = ui.label("비어 있음 · 왼쪽 목록에서 더블클릭", "hint")
        self.mode = QComboBox()
        self.mode.setToolTip("공명 모드. 모드에 따라 피해 판정과 반주가 달라집니다.")
        self.chain = QComboBox()
        for i in range(7):
            self.chain.addItem("%d체인" % i, i)
        self.chain.setToolTip("공명 체인 단계. 파티 버프가 있는 체인이 계산에 들어갑니다.")
        head = QHBoxLayout()
        head.setSpacing(4)
        head.addWidget(self.num)
        head.addStretch(1)
        head.addWidget(self.left_btn)
        head.addWidget(self.right_btn)
        head.addWidget(self.del_btn)
        opts = QHBoxLayout()
        opts.setSpacing(6)
        opts.addWidget(self.mode, 1)
        opts.addWidget(self.chain)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.name)
        lay.addWidget(self.empty)
        lay.addLayout(opts)
        self.left_btn.clicked.connect(lambda: tab.move_slot(self.index, -1))
        self.right_btn.clicked.connect(lambda: tab.move_slot(self.index, 1))
        self.del_btn.clicked.connect(lambda: tab.remove_slot(self.index))
        self.mode.currentIndexChanged.connect(self._mode)
        self.chain.currentIndexChanged.connect(self._chain)

    def set(self, cid, count):
        self.cid = cid
        filled = cid is not None
        self.name.setVisible(filled)
        self.empty.setVisible(not filled)
        self.chain.setVisible(filled)
        self.left_btn.setEnabled(filled and self.index > 0)
        self.right_btn.setEnabled(filled and self.index < count - 1)
        self.del_btn.setEnabled(filled)
        self.mode.blockSignals(True)
        self.chain.blockSignals(True)
        self.mode.clear()
        if filled:
            con = self.tab.win.con
            name = skilldata.character_name(con, cid)
            self.name.setText(name)
            self.name.setStyleSheet("font-size:12pt;font-weight:700;color:%s"
                                    % self.tab.nc(name))
            ms = modes.character_modes(con, cid)
            for m in ms:
                self.mode.addItem("모드: %s" % m, m)
            cur = self.tab.modes_by_id.get(cid)
            if cur in ms:
                self.mode.setCurrentIndex(ms.index(cur))
            self.mode.setVisible(bool(ms))
            self.chain.setCurrentIndex(self.tab.chains_by_id.get(cid, 0))
        else:
            self.mode.setVisible(False)
        self.mode.blockSignals(False)
        self.chain.blockSignals(False)

    def _mode(self, *_):
        if self.cid is not None:
            self.tab.set_mode(self.cid, self.mode.currentData())

    def _chain(self, *_):
        if self.cid is not None:
            self.tab.set_chain(self.cid, self.chain.currentData() or 0)


class PartyTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.teams = {"A": [], "B": []}
        self.active = "A"
        self.modes_by_id = {}
        self.chains_by_id = {}
        self.compare = False
        self.colors = {}

        self.search = QLineEdit()
        self.search.setPlaceholderText("캐릭터 이름")
        self.element = ui.element_box()
        self.pool = QListWidget()
        self.pool.setToolTip("더블클릭하거나 선택 후 [파티에 넣기]")
        self.add_btn = QPushButton("파티에 넣기 ▶")
        self.add_btn.setObjectName("primary")

        self.team_a = QPushButton("파티 A")
        self.team_b = QPushButton("파티 B")
        for b in (self.team_a, self.team_b):
            b.setCheckable(True)
            b.setToolTip("두 파티를 따로 저장해두고 전환합니다")
        self.team_a.setChecked(True)
        self.cmp_btn = QPushButton("A ↔ B 비교")
        self.cmp_btn.setCheckable(True)
        self.cmp_btn.setToolTip("파티 A와 B의 버프 실효를 나란히 비교합니다")
        self.clear_btn = QPushButton("파티 비우기")
        self.clear_btn.setToolTip("지금 보고 있는 파티의 슬롯을 모두 비웁니다")
        self.level = QComboBox()
        for i in range(1, 11):
            self.level.addItem("스킬 Lv %d" % i, i)
        self.level.setCurrentIndex(9)
        self.level.setToolTip("배율 계산에 쓸 스킬 레벨")

        self.cards = [SlotCard(self, i) for i in range(MAX_MEMBERS)]
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(ui.label("캐릭터", "section"))
        left.addWidget(self.search)
        left.addWidget(self.element)
        left.addWidget(self.pool, 1)
        left.addWidget(self.add_btn)
        leftw = ui.wrap(left)
        leftw.setMinimumWidth(170)
        leftw.setMaximumWidth(230)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self.team_a)
        bar.addWidget(self.team_b)
        bar.addWidget(self.cmp_btn)
        bar.addStretch(1)
        bar.addWidget(self.level)
        bar.addWidget(self.clear_btn)

        cards = QHBoxLayout()
        cards.setSpacing(8)
        for c in self.cards:
            cards.addWidget(c, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(bar)
        right.addWidget(ui.label("순환은 1번 → 2번 → 3번 → 다시 1번 순서입니다. "
                                 "앞 캐릭터의 반주가 다음 캐릭터에게 걸립니다.", "hint"))
        right.addLayout(cards)
        right.addWidget(self.body, 1)

        split = QSplitter()
        split.addWidget(leftw)
        split.addWidget(ui.wrap(right, (10, 0, 0, 0)))
        split.setSizes([200, 900])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split)

        self.pool.itemDoubleClicked.connect(self.add_member)
        self.add_btn.clicked.connect(self.add_selected)
        self.search.textChanged.connect(self.fill_pool)
        self.element.currentIndexChanged.connect(self.fill_pool)
        self.team_a.clicked.connect(lambda: self.switch_team("A"))
        self.team_b.clicked.connect(lambda: self.switch_team("B"))
        self.cmp_btn.toggled.connect(self.toggle_compare)
        self.clear_btn.clicked.connect(self.clear)
        self.level.currentIndexChanged.connect(self.render)
        self.body.anchorClicked.connect(self.on_link)

    @property
    def members(self):
        return self.teams[self.active]

    def nc(self, name):
        return self.colors.get(name, theme.TEXT)

    def nm(self, name):
        return ui.colored(name, self.nc(name))

    def fill_pool(self, *_):
        self.pool.clear()
        if not self.win.con:
            return
        want = self.element.currentData()
        q = self.search.text().strip()
        for cid, name, _b, _v, elem in skilldata.characters(self.win.con):
            if want and elem != want:
                continue
            if q and q not in name:
                continue
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, cid)
            it.setToolTip(skilldata.ELEMENTS.get(elem, ""))
            it.setForeground(QColor(self.nc(name)))
            self.pool.addItem(it)

    def reload(self):
        self.pool.clear()
        if not self.win.con:
            return
        self.colors = skilldata.name_colors(self.win.con)
        self.fill_pool()
        valid = {r[0] for r in skilldata.characters(self.win.con)}
        cfg = self.win.cfg

        def ids(key):
            out = []
            for c in cfg.get(key) or []:
                try:
                    c = int(c)
                except (TypeError, ValueError):
                    continue
                if c in valid and c not in out:
                    out.append(c)
            return out[:MAX_MEMBERS]

        self.teams["A"] = ids("party")
        self.teams["B"] = ids("party_b")
        self.chains_by_id = {}
        for k, v in (cfg.get("party_chains") or {}).items():
            try:
                self.chains_by_id[int(k)] = max(0, min(6, int(v)))
            except (TypeError, ValueError):
                pass
        self.modes_by_id = {}
        for k, v in (cfg.get("party_modes") or {}).items():
            try:
                self.modes_by_id[int(k)] = v
            except (TypeError, ValueError):
                pass
        self.refresh_slots()

    def on_show(self):
        self.render()

    def switch_team(self, key):
        self.active = key
        self.team_a.setChecked(key == "A")
        self.team_b.setChecked(key == "B")
        self.refresh_slots()

    def toggle_compare(self, on):
        self.compare = on
        self.render()

    def add_selected(self):
        it = self.pool.currentItem()
        if it:
            self.add_member(it)

    def add_member(self, item):
        cid = item.data(Qt.UserRole)
        if cid in self.members:
            return
        if len(self.members) >= MAX_MEMBERS:
            self.win.statusBar().showMessage("슬롯이 가득 찼습니다. ✕로 한 명을 빼고 넣으세요", 4000)
            return
        self.members.append(cid)
        self.save()
        self.refresh_slots()

    def remove_slot(self, i):
        if 0 <= i < len(self.members):
            del self.members[i]
            self.save()
            self.refresh_slots()

    def move_slot(self, i, delta):
        j = i + delta
        if i < 0 or j < 0 or j >= len(self.members):
            return
        self.members[i], self.members[j] = self.members[j], self.members[i]
        self.save()
        self.refresh_slots()

    def set_mode(self, cid, mode):
        self.modes_by_id[cid] = mode
        self.save()
        self.render()

    def set_chain(self, cid, ch):
        self.chains_by_id[cid] = ch
        self.save()
        self.render()

    def clear(self):
        self.teams[self.active] = []
        self.save()
        self.refresh_slots()

    def save(self):
        self.win.cfg["party"] = list(self.teams["A"])
        self.win.cfg["party_b"] = list(self.teams["B"])
        self.win.cfg["party_chains"] = {str(k): v for k, v in self.chains_by_id.items() if v}
        self.win.cfg["party_modes"] = {str(k): v for k, v in self.modes_by_id.items() if v}
        config.save(self.win.cfg)

    def refresh_slots(self):
        if not self.win.con:
            return
        for cid in self.members:
            if self.modes_by_id.get(cid):
                continue
            available = modes.character_modes(self.win.con, cid)
            if available:
                self.modes_by_id[cid] = available[0]
        for i, card in enumerate(self.cards):
            card.set(self.members[i] if i < len(self.members) else None, len(self.members))
        self.render()


    def render(self, *_):
        if not self.win.con:
            return
        level = self.level.currentData()
        if self.compare:
            self.render_compare(level)
            return
        if not self.members:
            self.body.setHtml(ui.doc(EMPTY_HTML))
            return
        if len(self.members) == 1:
            self.render_single(self.members[0], level)
            return
        self.body.setHtml(ui.doc(self.team_html(self.members, level)))

    def team_html(self, cids, level):
        p = party.plan(self.win.con, cids, level, self.modes_by_id, self.chains_by_id)
        best = p["best"]
        s = p["summary"]
        h = []

        names = "  →  ".join(self.nm(m["name"]) for m in best["order"])
        h.append("<div style='font-size:12pt;font-weight:600;color:%s'>"
                 "%s  →  (반복)</div>" % (theme.TEXT, names))

        h.append("<div style='margin-top:8px;color:%s'>"
                 "파티 합계 <b style='color:%s;font-size:12pt'>+%.1f%%</b>"
                 "<span style='font-size:9pt'> · 1인 평균 +%.1f%%</span></div>"
                 % (theme.TEXT_DIM, theme.GOOD, s["total"], s["avg"]))
        h.append("<div style='color:%s;font-size:9pt'>서로의 반주 버프를 받았을 때 "
                 "각자의 피해가 몇 퍼센트 오르는지를 더한 값입니다. "
                 "높을수록 셋이 서로 잘 맞습니다.</div>" % theme.TEXT_DIM)

        for leg in best["legs"]:
            m = leg["receiver"]
            o = leg["outro"]
            title = ui.esc(m["name"])
            if m.get("mode"):
                title += ("<span style='color:%s'> [%s]</span>"
                          % (theme.ACCENT, ui.esc(m["mode"])))
            h.append("<div style='margin-top:14px'>"
                     "<a href='char:%d' style='color:%s;font-weight:600;"
                     "text-decoration:none'>%s</a>"
                     "<span style='color:%s'> ← %s 반주</span></div>"
                     % (m["id"], self.nc(m["name"]), title,
                        theme.TEXT_DIM, self.nm(leg["giver"]["name"])))

            if o and leg["coverage"] is not None:
                if leg["coverage"] <= 0:
                    if leg.get("element_mismatch"):
                        why = "속성이 달라 적용되지 않습니다 (%s → %s)" % (
                            o.get("element") or "-",
                            m["profile"].get("element") or "-")
                    else:
                        why = "이 캐릭터에게는 %s 판정 피해가 없습니다" % leg["scope"]
                    h.append("<div style='margin-left:14px;color:%s'>"
                             "<span style='color:%s'>%s %+g%%</span> · %s초 · %s</div>"
                             % (theme.TEXT_DIM, theme.HIGHLIGHT,
                                ui.esc(leg["scope"]), o["value"],
                                o["duration"] or "-", ui.esc(why)))
                else:
                    h.append("<div style='margin-left:14px;color:%s'>"
                             "<span style='color:%s'>%s %+g%%</span> · %s초 · "
                             "이 캐릭터 피해의 %.0f%%에 적용</div>"
                             % (theme.TEXT_DIM, theme.HIGHLIGHT,
                                ui.esc(leg["scope"]), o["value"],
                                o["duration"] or "-", leg["coverage"]))
            elif o:
                u = leg.get("unknown") or {}
                if u.get("tag_match"):
                    h.append("<div style='margin-left:14px;color:%s'>"
                             "<span style='color:%s'>%s %+g%%</span> · "
                             "<span style='color:%s'>%s</span> 를 함께 쓰므로 "
                             "실전에서 적용됩니다 (배율로는 환산되지 않음)</div>"
                             % (theme.TEXT_DIM, theme.HIGHLIGHT,
                                ui.esc(leg["scope"]), o["value"], theme.TERM,
                                ui.esc(" · ".join(u["tag_match"]))))
                else:
                    h.append("<div style='margin-left:14px;color:%s'>"
                             "%s %+g%% · 적용 범위를 자동 판정하지 못했습니다</div>"
                             % (theme.WARN, ui.esc(leg["scope"]), o["value"]))
            elif leg.get("giver_party_wide"):
                h.append("<div style='margin-left:14px;color:%s;font-size:9pt'>"
                         "%s 반주는 파티 전체에 걸리므로 아래에 함께 표시됩니다</div>"
                         % (theme.TEXT_DIM, self.nm(leg["giver"]["name"])))
            else:
                h.append("<div style='margin-left:14px;color:%s'>"
                         "%s 반주는 이 캐릭터에게 넘기는 버프가 없습니다</div>"
                         % (theme.TEXT_DIM, self.nm(leg["giver"]["name"])))

            for e in leg.get("bonus") or []:
                h.append("<div style='margin-left:14px;color:%s'>"
                         "<span style='color:%s'>%s %+g%%</span> · 적용 %.0f%%</div>"
                         % (theme.TEXT_DIM, theme.HIGHLIGHT, ui.esc(e["scope"]),
                            e["value"], e["coverage"]))

            for e in leg["shared"]:
                if e["coverage"] is None:
                    if e["tag_match"]:
                        tail = ("<span style='color:%s'>%s</span> 를 함께 쓰므로 "
                                "실전에서 적용됩니다 (배율로는 환산되지 않음)"
                                % (theme.TERM, ui.esc(" · ".join(e["tag_match"]))))
                    else:
                        tail = "적용 범위를 자동 판정하지 못했습니다"
                    h.append("<div style='margin-left:14px;color:%s'>"
                             "<span style='color:%s'>[파티 전체]</span> %s "
                             "<span style='color:%s'>%s %+g%%</span> · %s</div>"
                             % (theme.TEXT_DIM, theme.ACCENT, self.nm(e["from"]),
                                theme.HIGHLIGHT, ui.esc(e["scope"]), e["value"],
                                tail))
                    continue
                h.append("<div style='margin-left:14px;color:%s'>"
                         "<span style='color:%s'>[파티 전체]</span> %s "
                         "<span style='color:%s'>%s %+g%%</span> · %s초 · "
                         "적용 %.0f%%</div>"
                         % (theme.TEXT_DIM, theme.ACCENT, self.nm(e["from"]),
                            theme.HIGHLIGHT, ui.esc(e["scope"]), e["value"],
                            e["duration"] or "-", e["coverage"]))

            for c in leg.get("chains") or []:
                if not c["gain"]:
                    continue
                h.append("<div style='margin-left:14px;color:%s'>"
                         "<span style='color:%s'>[%d체인]</span> %s "
                         "<span style='color:%s'>%s %+g%%</span> · 적용 %.0f%%</div>"
                         % (theme.TEXT_DIM, theme.TITLE, c["idx"] or 0,
                            self.nm(c["from"]), theme.HIGHLIGHT,
                            ui.esc(buff_label(c["scope"], c["stat"])), c["value"],
                            c["coverage"]))

            h.append("<div style='margin-left:14px;margin-top:3px;color:%s'>"
                     "%s &nbsp;<b style='color:%s'>피해 +%.1f%%</b>"
                     "<span style='font-size:9pt;color:%s'> "
                     "(버프 없을 때 100 → %.0f)</span></div>"
                     % (theme.TEXT_DIM, gauge(leg["gain"], theme.GOOD),
                        theme.GOOD, leg["gain"], theme.TEXT_DIM,
                        100 + leg["gain"]))

            top = m["profile"]["rows"][:3]
            share = " · ".join("%s %.0f%%" % (r["category"], r["share"])
                               for r in top)
            h.append("<div style='margin-left:14px;color:%s;font-size:9pt'>"
                     "피해 구성 %s</div>" % (theme.TEXT_DIM, ui.esc(share)))

        notes = {}
        for leg in best["legs"]:
            for c in leg.get("chains") or []:
                if c["counted"] and c["coverage"] is not None:
                    continue
                notes[(c["from"], c["idx"], c["scope"], c["value"])] = c
        if notes:
            h.append(self._h("배율로 환산 안 된 공명 체인 효과",
                             "크리티컬 계열이거나 적용 판정을 자동으로 정하지 못한 효과입니다."))
            for c in notes.values():
                h.append("<div style='margin-left:4px;color:%s'>"
                         "<span style='color:%s'>[%d체인]</span> %s %s %+g%%</div>"
                         % (theme.TEXT_DIM, theme.TITLE, c["idx"] or 0,
                            self.nm(c["from"]),
                            ui.esc(buff_label(c["scope"], c["stat"])), c["value"]))

        links = synergy.pairs(self.win.con, cids)
        if links:
            h.append(self._h("공유 기믹",
                             "같은 상태나 표기를 함께 쓰는 관계입니다. "
                             "배율에는 잡히지 않지만 실전에서 서로를 받쳐줍니다."))
            for l in links:
                who = " · ".join("%s<span style='color:%s'>(%s)</span>"
                                 % (self.nm(n), theme.TEXT_DIM, r)
                                 for n, r in l["members"])
                h.append("<div style='margin-left:4px;color:%s'>"
                         "<span style='color:%s'>%s</span> &nbsp; %s</div>"
                         % (theme.TEXT_DIM, theme.TERM, ui.esc(l["tag"]), who))

        alt = p.get("best_alt")
        if alt and alt["score"] > best["score"] + 0.5:
            h.append(self._h("참고"))
            h.append("<div style='margin-left:4px;color:%s'>"
                     "<span style='color:%s'>%s</span> 순서가 합계 "
                     "<b style='color:%s'>+%.1f%%</b>로 더 높습니다 "
                     "(현재 +%.1f%%)</div>"
                     % (theme.TEXT_DIM, theme.TEXT,
                        " → ".join(self.nm(m["name"]) for m in alt["order"]),
                        theme.GOOD, alt["score"], best["score"]))

        return "".join(h)

    def render_compare(self, level):
        a, b = self.teams["A"], self.teams["B"]
        if len(a) < 2 or len(b) < 2:
            self.body.setHtml(ui.doc(
                "<div style='line-height:1.8'>"
                "비교하려면 <b style='color:%s'>파티 A</b> 와 "
                "<b style='color:%s'>파티 B</b> 에 각각 두 명 이상 넣어주세요.<br>"
                "위쪽 드롭다운에서 파티를 전환해 구성할 수 있습니다.</div>"
                % (theme.ACCENT, theme.ACCENT)))
            return

        pa = party.plan(self.win.con, a, level, self.modes_by_id, self.chains_by_id)
        pb = party.plan(self.win.con, b, level, self.modes_by_id, self.chains_by_id)
        sa, sb = pa["summary"], pb["summary"]

        diff = sa["avg"] - sb["avg"]
        if abs(diff) < 0.5:
            verdict = "두 파티의 1인 평균 버프 실효가 거의 같습니다"
            vcolor = theme.TEXT
        elif diff > 0:
            verdict = "파티 A 가 1인 평균 +%.1f%%p 높습니다" % diff
            vcolor = theme.GOOD
        else:
            verdict = "파티 B 가 1인 평균 +%.1f%%p 높습니다" % (-diff)
            vcolor = theme.GOOD

        h = ["<div style='font-size:13pt;font-weight:600;color:%s'>%s</div>"
             % (vcolor, ui.esc(verdict))]

        for key, pp, ss in (("A", pa, sa), ("B", pb, sb)):
            names = " → ".join(self.nm(m["name"]) for m in pp["best"]["order"])
            h.append("<div style='margin-top:12px;color:%s'>"
                     "<b style='color:%s'>파티 %s</b> &nbsp; %s</div>"
                     % (theme.TEXT_DIM, theme.ACCENT, key, names))
            h.append("<div style='margin-left:4px;color:%s'>%s &nbsp;"
                     "<b style='color:%s'>합계 +%.1f%%</b>"
                     "<span style='font-size:9pt'> · 평균 +%.1f%%</span></div>"
                     % (theme.TEXT_DIM,
                        gauge(ss["total"], theme.GOOD, 26, 90.0),
                        theme.GOOD, ss["total"], ss["avg"]))

        h.append(self._h("캐릭터별 상승폭"))
        h.append("<table style='margin:4px 0 0 4px'>")
        for key, pp in (("A", pa), ("B", pb)):
            for leg in pp["best"]["legs"]:
                h.append("<tr>"
                         "<td style='padding:2px 10px 2px 0;color:%s'>%s</td>"
                         "<td style='padding:2px 12px 2px 0;color:%s'>%s</td>"
                         "<td style='padding:2px 10px 2px 0'>%s</td>"
                         "<td style='padding:2px 0;color:%s;text-align:right'>"
                         "+%.1f%%</td></tr>"
                         % (theme.TEXT_DIM, key,
                            theme.TEXT, self.nm(leg["receiver"]["name"]),
                            gauge(leg["gain"], theme.GOOD, 18),
                            theme.GOOD, leg["gain"]))
        h.append("</table>")

        for key, cids in (("A", a), ("B", b)):
            links = synergy.pairs(self.win.con, cids)
            if not links:
                continue
            h.append(self._h("파티 %s 공유 기믹" % key))
            for l in links:
                who = " · ".join("%s(%s)" % (self.nm(n), ui.esc(r))
                                 for n, r in l["members"])
                h.append("<div style='margin-left:4px;color:%s'>"
                         "<span style='color:%s'>%s</span> &nbsp; %s</div>"
                         % (theme.TEXT_DIM, theme.TERM, ui.esc(l["tag"]),
                            who))

        self.body.setHtml(ui.doc("".join(h)))

    def render_single(self, cid, level):
        target, sug = party.suggest_partners(
            self.win.con, cid, level, 10, self.modes_by_id.get(cid))
        h = ["<div style='font-size:12pt;font-weight:600;color:%s'>%s 에게 "
             "맞는 반주 제공자</div>" % (theme.TEXT, self.nm(target["name"]))]
        top = target["profile"]["rows"][:3]
        h.append("<div style='color:%s;font-size:9pt'>피해 구성 %s</div>"
                 % (theme.TEXT_DIM,
                    ui.esc(" · ".join("%s %.0f%%" % (r["category"], r["share"])
                                      for r in top))))
        h.append("<div style='color:%s;font-size:9pt;margin-top:2px'>"
                 "반주 수치에 이 캐릭터의 피해 구성을 곱해, 실제로 피해가 몇 퍼센트 "
                 "오르는지를 냅니다. 한 명을 더 추가하면 순환 분석으로 바뀝니다.</div>"
                 % theme.TEXT_DIM)
        h.append("<table style='margin:12px 0 0 4px'>")
        for s in sug:
            h.append("<tr>"
                     "<td style='padding:3px 14px 3px 0'>"
                     "<a href='add:%d' style='color:%s;text-decoration:none'>%s</a>"
                     "</td>"
                     "<td style='padding:3px 12px 3px 0;color:%s'>%s %+g%%</td>"
                     "<td style='padding:3px 12px 3px 0;color:%s'>적용 %.0f%%</td>"
                     "<td style='padding:3px 12px 3px 0;color:%s'>%s</td>"
                     "<td style='padding:3px 8px 3px 0'>%s</td>"
                     "<td style='padding:3px 0;color:%s;text-align:right'>"
                     "피해 +%.1f%%</td></tr>"
                     % (s["id"], self.nc(s["name"]), ui.esc(s["name"]),
                        theme.TEXT_DIM, ui.esc(s["scope"]), s["value"],
                        theme.TEXT_DIM, s["coverage"],
                        theme.ACCENT if s["party_wide"] else theme.TEXT_DIM,
                        "파티 전체" if s["party_wide"] else "다음 등장",
                        gauge(s["gain"], theme.GOOD, 14),
                        theme.GOOD, s["gain"]))
        h.append("</table>")

        extra = synergy.suggest(self.win.con, [cid], 6)
        if extra:
            h.append(self._h("기믹이 겹치는 캐릭터",
                             "같은 상태나 표기를 함께 쓰는 캐릭터입니다."))
            for e in extra:
                h.append("<div style='margin-left:4px;color:%s'>"
                         "<a href='add:%d' style='color:%s;text-decoration:none'>"
                         "%s</a> &nbsp;<span style='color:%s'>%s</span></div>"
                         % (theme.TEXT_DIM, e["id"], self.nc(e["name"]),
                            ui.esc(e["name"]), theme.TERM,
                            ui.esc(" · ".join(e["tags"][:3]))))

        self.body.setHtml(ui.doc("".join(h)))

    def _h(self, title, hint=""):
        s = ("<div style='margin-top:18px;color:%s;font-weight:600;font-size:11pt'>"
             "%s</div>" % (theme.TEXT, ui.esc(title)))
        if hint:
            s += ("<div style='color:%s;font-size:9pt'>%s</div>"
                  % (theme.TEXT_DIM, ui.esc(hint)))
        return s

    def on_link(self, url):
        s = url.toString()
        if s.startswith("char:"):
            self.win.open_character(int(s[5:]))
        elif s.startswith("add:"):
            cid = int(s[4:])
            if cid not in self.members and len(self.members) < MAX_MEMBERS:
                self.members.append(cid)
                self.save()
                self.refresh_slots()


EMPTY_HTML = """<div style="line-height:1.85">
<b style="color:%s">1. 캐릭터 넣기</b><br>
왼쪽 목록에서 더블클릭(또는 선택 후 [파티에 넣기])으로 최대 3명까지 넣습니다.
슬롯의 ◀ ▶ 로 순서를, ✕ 로 빼기를 합니다.<br><br>
<b style="color:%s">2. 한 명만 넣으면</b> 그 캐릭터에게 잘 맞는 반주 제공자를 순위로 보여줍니다.<br><br>
<b style="color:%s">3. 두 명 이상 넣으면</b> 반주와 공명 체인 파티 버프가 누구에게 걸려
각자의 피해가 몇 퍼센트 오르는지 계산합니다.<br><br>
<b style="color:%s">4. 파티 A / B</b> 를 따로 짜두고 [A ↔ B 비교]로 나란히 봅니다.
</div>""" % (theme.ACCENT, theme.ACCENT, theme.ACCENT, theme.ACCENT)
