"""History window: one of the three output sinks (Settings → Output →
"History window") — shows each recognized utterance as it arrives."""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path

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
from .config import Config
from .i18n import tr

log = logging.getLogger(__name__)

HISTORY_FILE = (
    Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    / "korvoice" / "history.jsonl"
)
_MAX_HISTORY_ENTRIES = 1000


class HistoryWindow(QMainWindow):
    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._entries: list[dict[str, str]] = []
        self.setWindowTitle(tr("korvoice — History"))
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
        copy_btn = QPushButton(tr("Copy all"))
        copy_btn.clicked.connect(self._copy_all)
        btn_row.addWidget(copy_btn)
        clear_btn = QPushButton(tr("Clear"))
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        self.setCentralWidget(central)
        if bool(self.config.get("history_persistent")):
            self._load_history()

    def _display_entry(self, entry: dict[str, str]) -> None:
        try:
            timestamp = datetime.datetime.fromisoformat(entry["timestamp"])
            shown_at = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except (KeyError, TypeError, ValueError):
            shown_at = "?"
        self.text.appendPlainText(f"[{shown_at}] {entry.get('text', '')}")

    def _load_history(self) -> None:
        try:
            lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return
        except OSError as exc:
            log.warning("failed to load history: %s", exc)
            return

        for line in lines[-_MAX_HISTORY_ENTRIES:]:
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict) or not isinstance(entry.get("text"), str):
                    continue
                if not isinstance(entry.get("timestamp"), str):
                    continue
            except (json.JSONDecodeError, TypeError):
                continue
            self._entries.append(entry)
            self._display_entry(entry)

    def _save_history(self) -> None:
        self._entries = self._entries[-_MAX_HISTORY_ENTRIES:]
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary = HISTORY_FILE.with_suffix(".tmp")
            temporary.write_text(
                "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in self._entries),
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            temporary.replace(HISTORY_FILE)
        except OSError as exc:
            log.warning("failed to save history: %s", exc)

    def append_text(self, text: str) -> None:
        entry = {
            "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "text": text,
        }
        self._entries.append(entry)
        self._display_entry(entry)
        if bool(self.config.get("history_persistent")):
            self._save_history()

    def _clear(self) -> None:
        self.text.clear()
        self._entries.clear()
        try:
            HISTORY_FILE.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("failed to clear saved history: %s", exc)

    def _copy_all(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text.toPlainText())

    def refresh_theme(self) -> None:
        theme.apply_window_theme(self)
        self.setWindowIcon(theme.make_tray_icon())
