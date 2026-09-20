from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QProgressBar, QPushButton, QTextBrowser,
    QVBoxLayout, QWidget,
)

import config
import importer
import pipeline
import theme
import ui


class ImportWorker(QThread):
    progress = Signal(str, str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, version, force):
        super().__init__()
        self.version = version
        self.force = force

    def run(self):
        try:
            s = pipeline.do_import(
                version=self.version,
                cache_root=config.data_root(),
                force=self.force,
                progress=lambda st, m: self.progress.emit(st, m),
            )
            self.finished_ok.emit(s)
        except Exception as e:
            self.failed.emit(str(e))


class DataTab(QWidget):
    imported = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.worker = None

        self.version_box = QComboBox()
        self.refresh_btn = QPushButton("버전 목록 새로고침")
        self.force_chk = QCheckBox("이미 받은 데이터도 다시 받기")
        self.import_btn = QPushButton("데이터 가져오기")
        self.import_btn.setObjectName("primary")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.hide()
        self.status = ui.label("", "hint")
        self.report = QTextBrowser()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(ui.label(
            "명조 클라이언트 데이터에서 한국어 스킬 원문, 용어, 배율표를 받아옵니다. "
            "최초 1회 약 52MB를 내려받고 이후에는 저장된 데이터를 씁니다.", "hint"))
        lay.addWidget(ui.card(
            ui.row(ui.label("게임 버전"), self.version_box, self.refresh_btn,
                   stretch_last=False),
            ui.row(self.force_chk, None, self.import_btn),
            self.bar, self.status))
        lay.addWidget(ui.label("가져오기 결과", "h2"))
        lay.addWidget(self.report, 1)

        self.version_box.setMinimumWidth(240)
        self.refresh_btn.clicked.connect(self.load_versions)
        self.import_btn.clicked.connect(self.start_import)
        self.load_local_versions()

    def reload(self):
        self.load_local_versions()

    def load_local_versions(self):
        self.version_box.clear()
        local = importer.cached_versions(config.data_root())
        for v in reversed(local):
            self.version_box.addItem("%s (받음)" % v, v)
        if not local:
            self.version_box.addItem("목록을 새로고침하세요", "")

    def load_versions(self):
        self.status.setText("버전 목록 조회 중...")
        QApplication.processEvents()
        try:
            versions = importer.list_versions()
        except Exception as e:
            self.status.setText("조회 실패: %s" % e)
            return
        local = set(importer.cached_versions(config.data_root()))
        self.version_box.clear()
        for v in reversed(versions):
            self.version_box.addItem(
                "%s%s" % (v, " (받음)" if v in local else ""), v)
        self.status.setText("최신 버전 %s" % versions[-1])

    def start_import(self):
        version = self.version_box.currentData()
        if not version:
            self.status.setText("먼저 버전 목록을 새로고침하세요")
            return
        self.import_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.win.release_db()
        self.bar.show()
        self.report.clear()
        self.worker = ImportWorker(version, self.force_chk.isChecked())
        self.worker.progress.connect(
            lambda st, m: self.status.setText("[%s] %s" % (st, m)))
        self.worker.finished_ok.connect(self.done)
        self.worker.failed.connect(self.fail)
        self.worker.start()

    def done(self, s):
        self.bar.hide()
        self.import_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.status.setText("완료 (%.1f초)" % s["elapsed"])
        issues = s["param_unresolved"] + s["scaling_unparsed"] + s["link_dangling"]
        color = theme.GOOD if issues == 0 else theme.WARN
        self.report.setHtml(ui.doc(
            "버전 <b>%s</b><br>캐릭터 %d명 · 스킬 %d개<br>"
            "배율 %d행 · 용어 %d개 · 용어링크 %d개<br>"
            "<span style='color:%s'>미해결 파라미터 %d · 미파싱 배율 %d · "
            "끊어진 링크 %d</span>"
            % (s["version"], s["distinct"], s["skills"], s["scalings"],
               s["terms"], s["links"], color, s["param_unresolved"],
               s["scaling_unparsed"], s["link_dangling"])))
        self.win.cfg["version"] = s["version"]
        config.save(self.win.cfg)
        self.load_local_versions()
        self.imported.emit()

    def fail(self, msg):
        self.win.reopen_and_reload()
        self.bar.hide()
        self.import_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.status.setText("실패: %s" % msg)
