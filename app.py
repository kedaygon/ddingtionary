import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

import config
import db
import importer
import appicon
import dmgtype
import library
import pipeline
import tab_browse
import tab_char
import tab_data
import tab_endgame
import tab_lore
import tab_party
import tab_patch
import tab_plan
import tab_search
import theme


PAGES = [
    (None, "찾아보기"),
    ("browse_tab", "스킬 탐색", "캐릭터별 스킬 원문과 레벨별 배율, 공명 체인을 봅니다. "
                              "밑줄 친 용어는 아래 등장 용어 칸에 설명이 나옵니다."),
    ("search_tab", "원문 검색", "모든 캐릭터의 스킬·공명 체인 원문에서 문장을 찾습니다. "
                              "특정 효과를 가진 캐릭터를 추릴 때 씁니다."),
    ("char_tab", "캐릭터 분석", "피해가 어떤 판정(공명 스킬·강공격 등)으로 들어가는지, "
                              "반주 버프, 스킬 레벨 투자 우선순위를 봅니다."),
    ("party_tab", "파티 시너지", "3명을 넣으면 반주·공명 체인 버프가 서로에게 얼마나 먹히는지 봅니다. "
                             "순서와 모드, 체인을 슬롯에서 바로 바꿉니다."),
    ("lore_tab", "캐릭터 백과", "프로필·성우·대사·스토리·소장품을 봅니다. 생일 달력도 있습니다."),
    ("endgame_tab", "엔드 컨텐츠", "역경의 탑·종말 매트릭스·바닷속 폐허의 층별 적과 효과를 봅니다."),
    (None, "도구"),
    ("plan_tab", "육성 재료", "캐릭터·무기의 현재와 목표를 정하면 필요한 재료·코인·경험치를 합산합니다. "
                           "여러 명을 한 번에 계획할 수 있습니다."),
    ("patch_tab", "패치 변경점", "이전 버전 데이터와 비교해 새 캐릭터·무기와 바뀐 스킬·배율·체인·세트를 "
                             "정리합니다."),
    (None, "설정"),
    ("data_tab", "데이터", "게임 데이터를 내려받고 버전을 바꿉니다."),
]


def tab_attrs():
    return [e[0] for e in PAGES if e[0]]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.con = None
        self.db_path = None

        self.setWindowTitle("띵과사전 — 명조 스킬·정보 도구")
        self.resize(1320, 840)

        self.browse_tab = tab_browse.BrowseTab(self)
        self.search_tab = tab_search.SearchTab(self)
        self.char_tab = tab_char.CharTab(self)
        self.party_tab = tab_party.PartyTab(self)
        self.lore_tab = tab_lore.LoreTab(self)
        self.endgame_tab = tab_endgame.EndgameTab(self)
        self.plan_tab = tab_plan.PlanTab(self)
        self.patch_tab = tab_patch.PatchTab(self)
        self.data_tab = tab_data.DataTab(self)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(168)
        self.stack = QStackedWidget()
        self.pages = {}
        for entry in PAGES:
            if entry[0] is None:
                it = QListWidgetItem("▸ " + entry[1])
                it.setFlags(Qt.NoItemFlags)
                f = it.font()
                f.setBold(True)
                f.setPointSizeF(9.5)
                f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
                it.setFont(f)
                it.setForeground(QColor(theme.ACCENT))
                it.setToolTip("%s 메뉴 묶음" % entry[1])
                self.nav.addItem(it)
                continue
            attr, title, desc = entry
            widget = getattr(self, attr)
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            head = QFrame()
            head.setObjectName("pagehead")
            hl = QVBoxLayout(head)
            hl.setContentsMargins(20, 14, 20, 12)
            hl.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("pagetitle")
            d = QLabel(desc)
            d.setObjectName("pagedesc")
            d.setWordWrap(True)
            hl.addWidget(t)
            hl.addWidget(d)
            lay.addWidget(head)
            lay.addWidget(widget, 1)
            idx = self.stack.addWidget(page)
            it = QListWidgetItem(title)
            it.setData(Qt.UserRole, idx)
            it.setToolTip(desc)
            self.nav.addItem(it)
            self.pages[id(widget)] = (idx, it)
        self.nav.currentItemChanged.connect(self.on_nav)

        root = QWidget()
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.nav)
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("준비됨")

        self.data_tab.imported.connect(self.reopen_and_reload)
        self.reopen()
        if self.con:
            self.reload_all()
            self.show_page(self.browse_tab)
        else:
            self.show_page(self.data_tab)
            self.statusBar().showMessage(
                "데이터 메뉴에서 먼저 가져오기를 실행하세요")

    def show_page(self, widget):
        idx, it = self.pages[id(widget)]
        self.nav.setCurrentItem(it)
        self.stack.setCurrentIndex(idx)

    def on_nav(self, cur, _prev=None):
        if not cur or cur.data(Qt.UserRole) is None:
            return
        self.stack.setCurrentIndex(cur.data(Qt.UserRole))
        page = self.stack.currentWidget()
        for attr in tab_attrs():
            w = getattr(self, attr)
            if w.parent() is page and hasattr(w, "on_show") and self.con:
                try:
                    w.on_show()
                except Exception:
                    pass

    def closeEvent(self, event):
        config.save(self.cfg)
        super().closeEvent(event)

    def reopen(self):
        version = self.cfg.get("version")
        local = importer.cached_versions(config.data_root())
        if not version or version not in local:
            version = local[-1] if local else None
        if not version:
            return
        path = config.db_path(version)
        if not os.path.isfile(path):
            return
        if self.con:
            self.con.close()
        con = db.connect(path)
        if not db.has_data(con):
            con.close()
            return
        if not db.has_chains(con):
            self.statusBar().showMessage("공명 체인 데이터 추가하는 중…")
            QApplication.processEvents()
            try:
                pipeline.backfill_chains(con, os.path.dirname(path))
            except Exception:
                pass
        if not db.get_meta(con, "scale_kind"):
            try:
                pipeline.backfill_scale_kinds(con, os.path.dirname(path))
            except Exception:
                pass
        if not db.has_stats(con) or db.get_meta(con, "stats_version") != pipeline.STATS_VERSION:
            self.statusBar().showMessage("무기·에코 데이터 받는 중…")
            QApplication.processEvents()
            try:
                pipeline.backfill_stats(con, os.path.dirname(path))
            except Exception:
                pass
        if not library.ready(con):
            self.statusBar().showMessage("캐릭터 백과·재료·엔드 컨텐츠 데이터 받는 중…")
            QApplication.processEvents()
            try:
                library.backfill(con, os.path.dirname(path))
            except Exception:
                pass
        library.clear()
        if not dmgtype.ready(con):
            self.statusBar().showMessage("스킬 피해 판정 데이터 받는 중…")
            QApplication.processEvents()
            try:
                dmgtype.backfill(con, os.path.dirname(path))
            except Exception:
                pass
        dmgtype.clear()
        self.con = con
        self.db_path = path
        self.cfg["version"] = version
        self.statusBar().showMessage("버전 %s · 데이터 준비됨" % version)

    def release_db(self):
        if self.con:
            try:
                self.con.close()
            except Exception:
                pass
        self.con = None

    def reload_all(self):
        if not self.con:
            return
        for attr in tab_attrs():
            tab = getattr(self, attr)
            if hasattr(tab, "reload"):
                tab.reload()

    def reopen_and_reload(self):
        self.reopen()
        self.reload_all()

    def open_character(self, cid):
        self.show_page(self.char_tab)
        self.char_tab.show_character(cid)

    def open_skill(self, cid, skill_id=None):
        self.show_page(self.browse_tab)
        self.browse_tab.show_character(cid, skill_id)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ddinggwasajeon.app")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_TITLE)
    app.setWindowIcon(appicon.icon())
    app.setStyleSheet(theme.full_qss())
    f = QFont("Malgun Gothic")
    f.setPointSize(10)
    app.setFont(f)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
