import os

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)

import config
import db
import importer
import patch
import pipeline
import skilldata
import theme
import ui

QUALITY_COLORS = {5: "#e8c56a", 4: "#c9a2ff", 3: "#6ea8fe", 2: "#5fd3a0", 1: "#8b93a5"}
WEAPON_TYPES = {1: "대검", 2: "직검", 3: "권총", 4: "권갑", 5: "증폭기"}


class VersionWorker(QThread):
    done = Signal(list)

    def run(self):
        try:
            self.done.emit(importer.list_versions())
        except Exception:
            self.done.emit([])


class FetchWorker(QThread):
    progress = Signal(str)
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, version):
        super().__init__()
        self.version = version

    def run(self):
        try:
            path = os.path.join(config.data_root(), self.version, "skills.sqlite")
            if not os.path.isfile(path):
                pipeline.do_import(version=self.version, cache_root=config.data_root(),
                                   progress=lambda st, m: self.progress.emit(str(m)))
            self.ok.emit(path)
        except Exception as e:
            self.failed.emit(str(e))


def vkey(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


class PatchTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.result = None
        self.worker = None
        self.vworker = None
        self.remote = []

        self.base = QComboBox()
        self.base.setMinimumWidth(160)
        self.run_btn = QPushButton("비교하기")
        self.run_btn.setObjectName("primary")
        self.status = ui.label("", "hint")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setMaximumWidth(160)
        self.bar.hide()
        self.cats = QListWidget()
        self.cats.setMaximumWidth(220)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("캐릭터·무기 이름으로 거르기")
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.filter)
        right.addWidget(self.body, 1)
        split = QSplitter()
        split.addWidget(self.cats)
        split.addWidget(ui.wrap(right, (8, 0, 0, 0)))
        split.setSizes([200, 900])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.addLayout(ui.row(ui.label("이전 버전", "hint"), self.base, ui.label("→ 지금 버전", "hint"),
                             self.run_btn, self.bar, self.status, None))
        lay.addWidget(split, 1)

        self.run_btn.clicked.connect(self.run)
        self.cats.currentRowChanged.connect(self.render)
        self.filter.textChanged.connect(self.render)

    def current_version(self):
        return self.win.cfg.get("version") or ""

    def reload(self):
        self.fill_versions()
        if self.vworker is None:
            self.vworker = VersionWorker()
            self.vworker.done.connect(self.on_versions)
            self.vworker.start()
        self.render()

    def on_versions(self, versions):
        self.remote = versions or []
        self.fill_versions()

    def fill_versions(self):
        cur = self.current_version()
        have = set(importer.cached_versions(config.data_root()))
        vs = sorted({v for v in list(have) + self.remote if vkey(v) < vkey(cur)}, key=vkey, reverse=True)
        keep = self.base.currentData()
        self.base.blockSignals(True)
        self.base.clear()
        for v in vs:
            self.base.addItem("%s%s" % (v, " (받음)" if v in have else ""), v)
        i = self.base.findData(keep)
        self.base.setCurrentIndex(i if i >= 0 else 0)
        self.base.blockSignals(False)
        self.run_btn.setEnabled(bool(vs))
        if not vs:
            self.status.setText("비교할 이전 버전을 찾는 중이거나, 받을 수 있는 이전 버전이 없습니다")
        elif not self.result:
            self.status.setText("이전 버전을 고르고 [비교하기]를 누르세요. 처음 한 번은 그 버전 데이터를 받습니다")

    def run(self):
        v = self.base.currentData()
        if not v or not self.win.con:
            return
        self.run_btn.setEnabled(False)
        self.bar.show()
        self.status.setText("%s 데이터 준비 중…" % v)
        self.worker = FetchWorker(v)
        self.worker.progress.connect(lambda m: self.status.setText("%s 받는 중 · %s" % (v, m)))
        self.worker.ok.connect(lambda path: self.on_ready(v, path))
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def on_fail(self, msg):
        self.bar.hide()
        self.run_btn.setEnabled(True)
        self.status.setText("실패: %s" % msg)

    def on_ready(self, v, path):
        self.bar.hide()
        self.run_btn.setEnabled(True)
        try:
            old = db.connect(path)
            self.result = patch.compare(old, self.win.con)
            old.close()
        except Exception as e:
            self.status.setText("비교 실패: %s" % e)
            return
        self.base_version = v
        total = sum(len(x) for x in self.result.values())
        self.status.setText("%s → %s · 변경 %d건" % (v, self.current_version(), total))
        self.fill_versions()
        self.cats.blockSignals(True)
        self.cats.clear()
        all_it = QListWidgetItem("전체 보기  (%d)" % total)
        all_it.setData(Qt.UserRole, None)
        self.cats.addItem(all_it)
        for key, name in patch.CATEGORIES:
            n = len(self.result[key])
            it = QListWidgetItem("%s  (%d)" % (name, n))
            it.setData(Qt.UserRole, key)
            if not n:
                it.setForeground(QColor(theme.TEXT_DIM))
            self.cats.addItem(it)
        self.cats.blockSignals(False)
        self.cats.setCurrentRow(0)
        self.render()

    def render(self, *_):
        if not self.result:
            self.body.setHtml(ui.doc(
                "<div style='color:%s;line-height:1.9'>이전 버전과 지금 데이터를 비교해 이번 패치에서 바뀐 것을 "
                "정리합니다.<br>· 새로 나온 캐릭터·무기<br>· 스킬·공명 체인·무기·에코 세트 설명이 바뀐 부분 "
                "(<span style='color:%s;text-decoration:line-through'>지운 글자</span> → "
                "<span style='color:%s;font-weight:600'>새 글자</span>)<br>· 스킬 배율 수치 변경<br><br>"
                "공식 패치노트에 없는 조용한 수정도 잡힙니다.</div>"
                % (theme.TEXT_DIM, theme.BAD, theme.GOOD)))
            return
        it = self.cats.currentItem()
        key = it.data(Qt.UserRole) if it else None
        q = self.filter.text().strip()
        colors = skilldata.name_colors(self.win.con)
        out = []
        for k, name in patch.CATEGORIES:
            if key and k != key:
                continue
            rows = [r for r in self.result[k] if not q or q in (r.get("name") or "")]
            if not rows:
                continue
            out.append("<div style='margin-top:14px;font-size:12pt;font-weight:700'>%s "
                       "<span style='color:%s;font-size:10pt;font-weight:400'>%d</span></div>"
                       % (ui.esc(name), theme.TEXT_DIM, len(rows)))
            for r in rows:
                out.append(self.row_html(k, r, colors))
        if not out:
            out.append("<div style='color:%s'>해당하는 변경이 없습니다</div>" % theme.TEXT_DIM)
        self.body.setHtml(ui.doc("".join(out)))

    def row_html(self, k, r, colors):
        name = r.get("name") or ""
        if k == "new_chars":
            return ("<div style='margin-top:6px'><span style='color:%s;font-weight:600'>%s</span> "
                    "<span style='color:%s'>새로 추가</span></div>"
                    % (colors.get(name, theme.TEXT), ui.esc(name), theme.GOOD))
        if k == "new_weapons":
            return ("<div style='margin-top:8px'><span style='color:%s;font-weight:600'>%s %s</span> "
                    "<span style='color:%s'>%s · 새로 추가</span><div style='color:%s;font-size:9pt'>%s"
                    "</div></div>" % (QUALITY_COLORS.get(r["quality"], theme.TEXT), "★" * (r["quality"] or 0),
                                      ui.esc(name), theme.TEXT_DIM, WEAPON_TYPES.get(r["type"], ""),
                                      theme.TEXT_DIM, ui.esc(r["text"])))
        col = colors.get(name) or QUALITY_COLORS.get(r.get("quality"), theme.TEXT)
        if k == "skill_values":
            return ("<div style='margin-top:6px'><span style='color:%s;font-weight:600'>%s</span> "
                    "<span style='color:%s'>%s · Lv%s</span><br>&nbsp;&nbsp;%s</div>"
                    % (col, ui.esc(name), theme.TEXT_DIM, ui.esc(r["what"]), r["level"],
                       patch.diff_html(r["old"], r["new"])))
        return ("<div style='margin-top:10px'><span style='color:%s;font-weight:600'>%s</span> "
                "<span style='color:%s'>%s</span><div style='margin-left:8px'>%s</div></div>"
                % (col, ui.esc(name), theme.TEXT_DIM, ui.esc(r.get("what") or ""),
                   patch.diff_html(r.get("old"), r.get("new"))))
