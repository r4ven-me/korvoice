"""Delivers recognized text to clipboard, autotype and/or the history
window — independently, per Settings → Output (all on by default)."""

from __future__ import annotations

import logging
import shutil
import subprocess

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication

from .config import Config

log = logging.getLogger(__name__)


class OutputDispatcher(QObject):
    delivered = Signal(str)             # text to show in the history window
    autotype_unavailable = Signal(str)  # human-readable reason, for the tray tooltip

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def dispatch(self, text: str) -> None:
        if not text:
            return
        if bool(self.config.get("output_clipboard")):
            self._to_clipboard(text)
        if bool(self.config.get("output_autotype")):
            self._autotype(text)
        if bool(self.config.get("output_window")):
            self.delivered.emit(text)

    def _to_clipboard(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _autotype(self, text: str) -> None:
        if QGuiApplication.platformName() == "xcb":
            self._autotype_x11(text)
        else:
            self._autotype_wayland(text)

    def _autotype_x11(self, text: str) -> None:
        try:
            from pynput.keyboard import Controller
        except ImportError as exc:
            self.autotype_unavailable.emit(f"pynput not installed: {exc}")
            return
        try:
            Controller().type(text)
        except Exception as exc:  # noqa: BLE001 — autotype must not crash the app
            log.warning("autotype (X11) failed: %s", exc)
            self.autotype_unavailable.emit(str(exc))

    def _autotype_wayland(self, text: str) -> None:
        # ydotool needs a running ydotoold with uinput access — a real setup
        # step beyond pipx install. Best-effort: fail quietly into the tray
        # tooltip (see app.py's status text), never block clipboard/window
        # output, which always work regardless of session type.
        ydotool = shutil.which("ydotool")
        if not ydotool:
            self.autotype_unavailable.emit(
                "ydotool not found — install it and run ydotoold for autotype on Wayland"
            )
            return
        try:
            subprocess.run([ydotool, "type", "--", text], check=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("autotype (Wayland/ydotool) failed: %s", exc)
            self.autotype_unavailable.emit(str(exc))
