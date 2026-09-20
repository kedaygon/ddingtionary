from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

import tab_browse
import ui


class CharPicker(QWidget):
    changed = Signal(object)

    def __init__(self, title="캐릭터"):
        super().__init__()
        self.con = None
        self.tree = tab_browse.CharacterTree()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("캐릭터 이름")
        self.element = ui.element_box()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(ui.label(title, "section"))
        lay.addWidget(self.filter)
        lay.addWidget(self.element)
        lay.addWidget(self.tree, 1)
        self.setMaximumWidth(210)
        self.tree.currentItemChanged.connect(lambda *_: self.changed.emit(self.tree.current_id()))
        self.filter.textChanged.connect(self.refilter)
        self.element.currentIndexChanged.connect(self.refilter)

    def current(self):
        return self.tree.current_id()

    def load(self, con):
        self.con = con
        self.refilter()

    def refilter(self, *_):
        cur = self.tree.current_id()
        self.tree.blockSignals(True)
        self.tree.load(self.con, self.element.currentData(), self.filter.text())
        self.tree.blockSignals(False)
        if cur is not None and self.tree.select_id(cur):
            self.changed.emit(self.tree.current_id())
            return
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.changed.emit(self.tree.current_id())

    def select(self, cid):
        if not self.tree.select_id(cid):
            self.filter.clear()
            self.element.setCurrentIndex(0)
            self.tree.select_id(cid)
