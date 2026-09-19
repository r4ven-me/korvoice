"""History window: one of the three output sinks (Settings → Output →
"History window") — shows each recognized utterance as it arrives."""

from __future__ import annotations

import datetime

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme


class HistoryWindow(QMainWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("korvoice — History")
        self.resize(520, 420)
        self.setWindowIcon(theme.make_tray_icon())
        theme.apply_window_theme(self)

        central = QWidget()
        layout = QVBoxLayout(central)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        copy_btn = QPushButton("Copy all")
        copy_btn.clicked.connect(self._copy_all)
        btn_row.addWidget(copy_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.text.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        self.setCentralWidget(central)

    def append_text(self, text: str) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText(f"[{timestamp}] {text}")

    def _copy_all(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text.toPlainText())

    def refresh_theme(self) -> None:
        theme.apply_window_theme(self)
        self.setWindowIcon(theme.make_tray_icon())
