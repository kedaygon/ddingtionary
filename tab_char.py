from PySide6.QtWidgets import (
    QComboBox, QLineEdit, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

import analysis
import modes
import quickswap
import tab_browse
import skilldata
import theme
import ui

CAT_COLORS = {
    "공명 해방": "#c9a2ff",
    "공명 스킬": "#6ea8fe",
    "강공격": "#e8c56a",
    "일반 공격": "#7fd6f5",
    "회피 반격": "#5fd3a0",
    "공중 공격": "#8b93a5",
    "에코 어빌리티": "#f0a0c0",
    "조화 파동": "#a0e0d0",
    "변주 스킬": "#e06c75",
    "반주 스킬": "#e0b054",
    "조화도 파괴": "#8b93a5",
    "협동 공격": "#9fd08a",
    "해킹": "#6fd0c8",
    "판정 불명확": "#9aa0ad",
    "판정 미기재": "#6b7280",
}


def bar(share, color, width=26):
    n = max(1, round(width * share / 100.0))
    return ("<span style='color:%s'>%s</span>"
            "<span style='color:%s'>%s</span>") % (
        color, "█" * n, theme.BORDER, "─" * max(0, width - n))


class CharTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._modes = []

        self.tree = tab_browse.CharacterTree()
        self.tree.setMaximumWidth(200)
        self.level = QComboBox()
        for i in range(1, 11):
            self.level.addItem("Lv %d" % i, i)
        self.level.setCurrentIndex(9)
        self.mode = QComboBox()
        self.mode.hide()
        self.mode_label = ui.label("모드", "hint")
        self.mode_label.hide()
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("캐릭터 이름")
        self.element = ui.element_box()

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(ui.label("캐릭터", "section"))
        left.addWidget(self.filter)
        left.addWidget(self.element)
        left.addWidget(self.tree, 1)
        leftw = ui.wrap(left)
        leftw.setMaximumWidth(210)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(ui.row(None, self.mode_label, self.mode,
                               ui.label("스킬 레벨", "hint"), self.level))
        right.addWidget(self.body, 1)

        split = QSplitter()
        split.addWidget(leftw)
        split.addWidget(ui.wrap(right, (10, 0, 0, 0)))
        split.setSizes([210, 900])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split)

        self.tree.currentItemChanged.connect(self.on_char)
        self.filter.textChanged.connect(self.refilter)
        self.element.currentIndexChanged.connect(self.refilter)
        self.level.currentIndexChanged.connect(self.render)
        self.mode.currentIndexChanged.connect(self.render)

    def refilter(self, *_):
        cur = self.tree.current_id()
        self.tree.load(self.win.con, self.element.currentData(), self.filter.text())
        if cur is not None and self.tree.select_id(cur):
            return
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def reload(self):
        cur = self.tree.current_id()
        self.tree.load(self.win.con, self.element.currentData(), self.filter.text())
        if cur is not None and self.tree.select_id(cur):
            return
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def show_character(self, cid):
        if not self.tree.select_id(cid):
            self.filter.clear()
            self.element.setCurrentIndex(0)
            self.tree.load(self.win.con)
            self.tree.select_id(cid)

    def on_char(self, *_):
        cid = self.tree.current_id()
        if cid is None or not self.win.con:
            self.body.clear()
            self.mode.hide()
            self.mode_label.hide()
            self._modes = []
            return
        self._modes = modes.character_modes(self.win.con, cid)
        self.mode.blockSignals(True)
        self.mode.clear()
        for m in self._modes:
            self.mode.addItem(m, m)
        self.mode.blockSignals(False)
        show = bool(self._modes)
        self.mode.setVisible(show)
        self.mode_label.setVisible(show)
        self.render()

    def current_mode(self):
        return self.mode.currentData() if self._modes else None

    def render(self, *_):
        cid = self.tree.current_id()
        if cid is None or not self.win.con:
            self.body.clear()
            return
        con = self.win.con
        level = self.level.currentData()
        mode = self.current_mode()

        prof = analysis.damage_profile(con, cid, level, mode)
        recl = analysis.reclassified(con, cid, level, mode)
        prio = analysis.level_priority(con, cid, mode)
        outro = quickswap.outro_profile(con, cid, mode)

        p = []
        head = ui.esc(prof["name"])
        if mode:
            head += ("<span style='color:%s;font-size:10pt'> · 공명 모드 %s</span>"
                     % (theme.ACCENT, ui.esc(mode)))
        ecolor = skilldata.name_colors(con).get(prof["name"], theme.TEXT)
        p.append("<div style='font-size:13pt;font-weight:600;color:%s'>%s</div>"
                 % (ecolor, head))
        if self._modes:
            p.append("<div style='color:%s;font-size:9pt'>이 캐릭터는 모드에 따라 "
                     "피해 판정과 반주 효과가 달라집니다. 오른쪽 위에서 모드를 "
                     "바꿔 비교할 수 있습니다.</div>" % theme.TEXT_DIM)

        p.append(self._section("피해 구성",
                               "스킬 배율이 실제로 어떤 피해 판정으로 들어가는지(게임 피해 데이터 기준). "
                               "어떤 피해 보너스를 받아야 이득인지를 결정합니다."))
        p.append("<table style='margin:4px 0 0 4px'>")
        for r in prof["rows"]:
            c = CAT_COLORS.get(r["category"], theme.TEXT)
            p.append("<tr>"
                     "<td style='padding:2px 12px 2px 0;color:%s'>%s</td>"
                     "<td style='padding:2px 10px 2px 0'>%s</td>"
                     "<td style='padding:2px 10px 2px 0;color:%s;text-align:right'>"
                     "%.1f%%</td>"
                     "<td style='padding:2px 0;color:%s;text-align:right'>%.0f%%</td>"
                     "</tr>" % (c, ui.esc(r["category"]),
                                bar(r["share"], c), theme.TEXT, r["share"],
                                theme.TEXT_DIM, r["total"]))
        p.append("</table>")
        p.append("<div style='margin:4px 0 0 4px;color:%s;font-size:9pt'>공중 공격·회피 반격은 따로 "
                 "판정이 없고 게임 데이터상 판정(대부분 일반 공격, 일부 강공격 등)에 합산했습니다. "
                 "반주 스킬 피해는 스킬 레벨과 무관한 고정 배율이라 아래 반주 항목에 따로 적었습니다.</div>"
                 % theme.TEXT_DIM)
        if prof.get("coop_share"):
            p.append("<div style='margin:4px 0 0 4px;color:%s;font-size:9pt'>"
                     "이 중 <span style='color:%s'>협동 공격 %.1f%%</span> · "
                     "판정과 별개로 협동 공격 버프도 받습니다.</div>"
                     % (theme.TEXT_DIM, CAT_COLORS["협동 공격"], prof["coop_share"]))

        if recl:
            p.append(self._section(
                "판정 전환 %d건" % len(recl),
                "스킬 분류와 실제 피해 판정이 다른 항목입니다. "
                "게임 피해 데이터로 판정을 확인했고, 데이터로 하나로 좁혀지지 않을 때만 원문을 참고했습니다."))
            p.append("<table style='margin:4px 0 0 4px'>")
            for r in recl:
                p.append("<tr><td style='padding:2px 14px 2px 0;color:%s'>%s</td>"
                         "<td style='padding:2px 14px 2px 0;color:%s'>%s → "
                         "<span style='color:%s'>%s</span>"
                         "<span style='color:%s'> (%.0f%%%s)</span></td>"
                         "<td style='padding:2px 0;color:%s;font-size:9pt'>%s</td></tr>"
                         % (theme.TEXT, ui.esc(r["attr"]), theme.TEXT_DIM,
                            ui.esc(r["from"]),
                            CAT_COLORS.get(r["to"], theme.HIGHLIGHT), ui.esc(r["to"]),
                            theme.TEXT_DIM, r["pct"], " · 일부" if r.get("partial") else "",
                            theme.TEXT_DIM, ui.esc(r["reason"])))
            p.append("</table>")

        unc = [e for e in prof["char"]["entries"] if e["category"] == "판정 불명확"]
        if unc:
            p.append(self._section(
                "판정 불명확 %d건" % len(unc),
                "같은 배율을 쓰는 피해가 게임 데이터에 여럿 있어 하나로 확정할 수 없는 항목입니다. "
                "가능한 판정을 모두 적었고, 판정 한정 버프 계산에서는 빠집니다."))
            for e in unc:
                p.append("<div style='margin:2px 0 0 4px;color:%s'>%s "
                         "<span style='color:%s'>· %s · %.0f%% · %s 중 하나</span></div>"
                         % (theme.TEXT, ui.esc(e["attr"]), theme.TEXT_DIM,
                            ui.esc(e["skill_name"]), e["pct"],
                            ui.esc(" / ".join(e.get("options") or []))))

        unk = [e for e in prof["char"]["entries"] if e["category"] == "판정 미기재"]
        if unk:
            p.append(self._section(
                "판정 미기재 %d건" % len(unk),
                "원문에 어떤 피해로 적용되는지 적혀 있지 않은 항목입니다. "
                "추측하지 않고 따로 표시하며, 판정 한정 버프 계산에서는 빠집니다."))
            for e in unk:
                p.append("<div style='margin:2px 0 0 4px;color:%s'>%s "
                         "<span style='color:%s'>· %s · %.0f%%</span></div>"
                         % (theme.TEXT, ui.esc(e["attr"]), theme.TEXT_DIM,
                            ui.esc(e["skill_name"]), e["pct"]))

        p.append(self._section("반주", "다음 등장 캐릭터 또는 파티에게 넘기는 버프와 반주 스킬 피해입니다."))
        for od in prof["char"].get("outro_damage") or []:
            c = CAT_COLORS.get(od["category"], theme.TEXT)
            p.append("<div style='margin:4px 0 0 4px;color:%s'><span style='color:%s'>%s 피해%s</span> · %s</div>"
                     % (theme.TEXT_DIM, c, ui.esc(od["category"]),
                        " (협동 공격)" if od.get("coop") else "", ui.esc(od["text"][:200])))
        if outro:
            target = "파티 전체" if outro["party_wide"] else "다음 등장 캐릭터"
            what, val = quickswap.describe(outro)
            note = []
            if outro.get("stacking"):
                note.append("스택 최대치")
            if outro.get("conditional"):
                note.append("조건부")
            p.append("<div style='margin:4px 0 0 4px;color:%s'>"
                     "<b style='color:%s'>%s %+g%%</b> · %s · %s%s</div>"
                     % (theme.TEXT_DIM, theme.HIGHLIGHT, ui.esc(what), val,
                        ("%g초" % outro["duration"]) if outro["duration"] else "지속시간 표기 없음",
                        target, (" · " + ", ".join(note)) if note else ""))
            for ex in outro.get("extras") or []:
                w2, v2 = quickswap.describe(ex)
                tgt = "파티" if ex.get("holder") in ("party", "on_field") else "다음 등장 캐릭터"
                n2 = []
                if ex.get("stacking"):
                    n2.append("스택 최대치")
                if ex.get("conditional"):
                    n2.append("조건부")
                p.append("<div style='margin-left:4px;color:%s'>%s %+g%% · %s%s%s</div>"
                         % (theme.TEXT_DIM, ui.esc(w2), v2,
                            ("%g초 · " % ex["duration"]) if ex.get("duration") else "", tgt,
                            (" · " + ", ".join(n2)) if n2 else ""))
            p.append("<div style='margin-left:4px;color:%s;font-size:9pt'>%s</div>"
                     % (theme.TEXT_DIM, ui.esc(outro["source_line"][:180])))
        else:
            p.append("<div style='margin:4px 0 0 4px;color:%s'>"
                     "버프 없음 (피해만)</div>" % theme.TEXT_DIM)

        if prio:
            p.append(self._section("스킬 레벨 투자 우선순위",
                                   "Lv1 → Lv10 으로 올렸을 때 배율이 얼마나 오르는지. "
                                   "판정 전환을 반영한 결과입니다."))
            top = prio[0]["gain"] or 1
            p.append("<table style='margin:4px 0 0 4px'>")
            for r in prio:
                cats = " · ".join(
                    "<span style='color:%s'>%s</span> +%.0f%%"
                    % (CAT_COLORS.get(c, theme.TEXT_DIM), ui.esc(c), v)
                    for c, v in r["cats"][:3])
                p.append("<tr>"
                         "<td style='padding:2px 12px 2px 0;color:%s'>%s</td>"
                         "<td style='padding:2px 10px 2px 0'>%s</td>"
                         "<td style='padding:2px 14px 2px 0;color:%s;"
                         "text-align:right'>+%.0f%%</td>"
                         "<td style='padding:2px 0;color:%s;font-size:9pt'>%s</td>"
                         "</tr>"
                         % (theme.TEXT, ui.esc(r["skill"]),
                            bar(r["gain"] / top * 100, theme.ACCENT, 16),
                            theme.TEXT, r["gain"], theme.TEXT_DIM, cats))
            p.append("</table>")

        self.body.setHtml(ui.doc("".join(p)))

    def _section(self, title, hint=""):
        s = ("<div style='margin-top:18px;color:%s;font-weight:600;font-size:11pt'>"
             "%s</div>" % (theme.TEXT, ui.esc(title)))
        if hint:
            s += ("<div style='color:%s;font-size:9pt;margin-bottom:2px'>%s</div>"
                  % (theme.TEXT_DIM, ui.esc(hint)))
        return s
