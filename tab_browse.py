import json
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QSplitter, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

import skilldata
import theme
import ui


class CharacterTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setMinimumWidth(150)

    def load(self, con, element_filter=None, name_filter=""):
        self.clear()
        if not con:
            return
        rows = skilldata.characters(con)
        nf = (name_filter or "").strip()
        groups = {}
        for cid, name, base, vlabel, elem in rows:
            if element_filter and elem != element_filter:
                continue
            if nf and nf not in name:
                continue
            groups.setdefault(base, []).append((cid, name, vlabel, elem))

        for base in sorted(groups, key=lambda b: groups[b][0][1]):
            kids = groups[base]
            if len(kids) == 1:
                cid, name, _v, elem = kids[0]
                it = QTreeWidgetItem([name])
                it.setData(0, Qt.UserRole, cid)
                it.setToolTip(0, skilldata.ELEMENTS.get(elem, ""))
                it.setForeground(0, QColor(theme.element_color(skilldata.ELEMENTS.get(elem))))
                self.addTopLevelItem(it)
            else:
                stem = kids[0][1].split(" · ")[0]
                parent = QTreeWidgetItem([stem])
                parent.setData(0, Qt.UserRole, None)
                for cid, name, vlabel, elem in sorted(kids, key=lambda k: k[2] or ""):
                    ch = QTreeWidgetItem([vlabel or name])
                    ch.setData(0, Qt.UserRole, cid)
                    ch.setToolTip(0, skilldata.ELEMENTS.get(elem, ""))
                    ch.setForeground(0, QColor(theme.element_color(skilldata.ELEMENTS.get(elem))))
                    parent.addChild(ch)
                parent.setExpanded(True)
                self.addTopLevelItem(parent)

    def current_id(self):
        it = self.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def select_id(self, cid):
        def walk(item):
            if item.data(0, Qt.UserRole) == cid:
                return item
            for i in range(item.childCount()):
                hit = walk(item.child(i))
                if hit:
                    return hit
            return None
        for i in range(self.topLevelItemCount()):
            hit = walk(self.topLevelItem(i))
            if hit:
                self.setCurrentItem(hit)
                return True
        return False


class BrowseTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._last_skill = None

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("캐릭터 검색")
        self.element = QComboBox()
        self.element.addItem("전체 속성", None)
        for k, v in skilldata.ELEMENTS.items():
            self.element.addItem(v, k)

        self.tree = CharacterTree()
        self.skills = QListWidget()
        self.skills.setMinimumWidth(190)
        self.skills.setMaximumWidth(250)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.terms = QTextBrowser()
        self.terms.setMaximumHeight(190)

        self.level = QComboBox()
        for i in range(1, 11):
            self.level.addItem("Lv %d" % i, i)
        self.level.setCurrentIndex(9)

        self.title = ui.label("", "h2")

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self.filter)
        left.addWidget(self.element)
        left.addWidget(self.tree, 1)
        leftw = ui.wrap(left)
        leftw.setMaximumWidth(210)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(ui.row(self.title, None,
                               ui.label("스킬 레벨", "hint"), self.level))
        right.addWidget(self.detail, 1)
        right.addWidget(ui.label("등장 용어", "h2"))
        right.addWidget(self.terms)

        split = QSplitter()
        split.addWidget(leftw)
        split.addWidget(self.skills)
        split.addWidget(ui.wrap(right))
        split.setSizes([210, 230, 640])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(split)

        self.filter.textChanged.connect(self.reload)
        self.element.currentIndexChanged.connect(self.reload)
        self.tree.currentItemChanged.connect(self.on_char)
        self.skills.currentItemChanged.connect(self.on_skill)
        self.level.currentIndexChanged.connect(self.on_level)

    def reload(self, *_):
        cur = self.tree.current_id()
        self.tree.load(self.win.con, self.element.currentData(), self.filter.text())
        if cur is not None:
            self.tree.select_id(cur)
        if self.tree.current_id() is None:
            self.skills.blockSignals(True)
            self.skills.clear()
            self.skills.blockSignals(False)
            self.clear_detail()

    def show_character(self, cid, skill_id=None):
        if not self.tree.select_id(cid):
            self.filter.clear()
            self.element.setCurrentIndex(0)
            self.tree.load(self.win.con)
            self.tree.select_id(cid)
        if skill_id is not None:
            for i in range(self.skills.count()):
                if self.skills.item(i).data(Qt.UserRole) == skill_id:
                    self.skills.setCurrentRow(i)
                    break

    def clear_detail(self):
        self.title.setText("")
        self.detail.clear()
        self.terms.clear()
        self._last_skill = None

    def on_char(self, cur, _prev=None):
        self.skills.blockSignals(True)
        self.skills.clear()
        self.skills.blockSignals(False)
        if not cur or not self.win.con:
            self.clear_detail()
            return
        cid = cur.data(0, Qt.UserRole)
        if cid is None:
            self.clear_detail()
            return
        rows = skilldata.load_skills(self.win.con, cid)
        rows = sorted(rows, key=lambda r: (skilldata.TYPE_ORDER.get(r[1], 9), r[0]))
        for sid, stype, name, _t in rows:
            it = QListWidgetItem("%s\n%s" % (
                skilldata.TYPE_NAMES.get(stype, "기타"), name or "-"))
            it.setData(Qt.UserRole, sid)
            self.skills.addItem(it)
        for chid, idx, cname in skilldata.load_chains(self.win.con, cid):
            it = QListWidgetItem("공명 체인 %d\n%s" % (idx, cname or "-"))
            it.setData(Qt.UserRole, -chid)
            it.setForeground(QColor(theme.TITLE))
            self.skills.addItem(it)
        if rows:
            self.skills.setCurrentRow(0)

    def on_level(self, *_):
        self.on_skill(keep_scroll=True)

    def on_skill(self, *_args, **kw):
        keep = kw.get("keep_scroll", False)
        it = self.skills.currentItem()
        if not it or not self.win.con:
            return
        sid = it.data(Qt.UserRole)
        con = self.win.con
        if sid is not None and sid < 0:
            self.show_chain(-sid)
            return
        row = con.execute(
            "SELECT name, describe_text, spans, skill_level_group_id "
            "FROM skills WHERE id=?", (sid,)).fetchone()
        if not row:
            return
        name, text, spans_json, group = row
        self.title.setText(name or "")
        bar = self.detail.verticalScrollBar()
        pos = bar.value() if (keep and sid == self._last_skill) else 0
        self._last_skill = sid

        level = self.level.currentData()
        body = ui.render_spans(text or "", json.loads(spans_json or "[]"))

        scal = con.execute(
            "SELECT sc.attribute_name, sl.raw, sc.scale_kind FROM skill_scalings sc "
            "JOIN scaling_levels sl ON sl.scaling_id=sc.id "
            "WHERE sc.skill_level_group_id=? AND sl.level=? ORDER BY sc.sort_order",
            (group, level)).fetchall()
        table = ""
        if scal:
            cells = "".join(
                "<tr><td style='padding:3px 16px 3px 0;color:%s'>%s</td>"
                "<td style='padding:3px 0;color:%s'>%s</td></tr>" % (
                    theme.TEXT_DIM, ui.esc(a), theme.TEXT,
                    ui.esc(v) + ({"hp": " HP", "def": " 방어력"}.get(k, "")))
                for a, v, k in scal)
            table = ("<div style='margin-top:16px;color:%s;font-weight:600'>"
                     "배율 (Lv %d)</div><table style='margin-top:6px'>%s</table>"
                     % (theme.TEXT, level, cells))

        self.detail.setHtml(ui.doc(body + table))
        if pos:
            bar.setValue(pos)

        links = con.execute(
            "SELECT DISTINCT t.id, t.title, t.desc_text FROM skill_term_links l "
            "JOIN terms t ON t.id=l.term_id WHERE l.skill_id=?", (sid,)).fetchall()
        if links:
            self.terms.setHtml("".join(
                "<div style='margin-bottom:10px'>"
                "<span style='color:%s;font-weight:600'>%s</span><br>"
                "<span style='color:%s;line-height:1.7'>%s</span></div>" % (
                    theme.TERM, ui.esc(t), theme.TEXT_DIM,
                    ui.esc(re.sub(r"\{\d+\}", "N", (d or "")[:700])).replace("\n", "<br>"))
                for _i, t, d in links))
        else:
            self.terms.setHtml(
                "<span style='color:%s'>없음</span>" % theme.TEXT_DIM)

    def show_chain(self, chid):
        row = self.win.con.execute(
            "SELECT idx, name, describe_text FROM chains WHERE id=?", (chid,)).fetchone()
        if not row:
            return
        idx, name, text = row
        self._last_skill = -chid
        self.title.setText("공명 체인 %d · %s" % (idx, name or ""))
        self.detail.setHtml(ui.doc(
            "<div style='line-height:1.8'>%s</div>"
            % ui.esc(text or "").replace("\n", "<br>")))
        self.terms.setHtml("<span style='color:%s'>없음</span>" % theme.TEXT_DIM)
