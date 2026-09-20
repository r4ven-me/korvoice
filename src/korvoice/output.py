"""Delivers recognized text to clipboard, autotype and/or the history
window — independently, per Settings → Output (all on by default)."""

from __future__ import annotations

import logging
import shutil
import subprocess

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication

from .config import Config

log = logging.getLogger(__name__)

_AUTOTYPE_TIMEOUT = 10  # seconds — a stuck xdotool/ydotool must not hang forever


class _AutotypeWorker(QThread):
    """Runs the blocking xdotool/ydotool subprocess off the GUI thread —
    dispatch() used to call this inline, which froze the tray/UI for the
    ~1s+ a longer sentence takes to type out synthetically."""

    failed = Signal(str)

    def __init__(self, command: list[str], parent=None) -> None:
        super().__init__(parent)
        self._command = command

    def run(self) -> None:
        try:
            subprocess.run(self._command, check=True, timeout=_AUTOTYPE_TIMEOUT)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            self.failed.emit(str(exc))


class OutputDispatcher(QObject):
    delivered = Signal(str)             # text to show in the history window
    autotype_unavailable = Signal(str)  # human-readable reason, for the tray tooltip

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        # Keeps running _AutotypeWorker instances referenced until they
        # finish — letting the last reference drop while the underlying
        # QThread is still alive is a use-after-free waiting to happen.
        self._autotype_workers: list[_AutotypeWorker] = []

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
        command = self._autotype_command(text)
        if command is None:
            return  # _autotype_command already emitted the "unavailable" reason
        worker = _AutotypeWorker(command, self)
        worker.failed.connect(self._on_autotype_failed)
        worker.finished.connect(lambda w=worker: self._forget_worker(w))
        self._autotype_workers.append(worker)
        worker.start()

    def _on_autotype_failed(self, message: str) -> None:
        log.warning("autotype failed: %s", message)
        self.autotype_unavailable.emit(message)

    def _forget_worker(self, worker: _AutotypeWorker) -> None:
        if worker in self._autotype_workers:
            self._autotype_workers.remove(worker)

    def _autotype_command(self, text: str) -> list[str] | None:
        """Builds the subprocess command for the current session type, or
        emits autotype_unavailable and returns None. Both backends are
        external system tools, not pip dependencies (see README):
        - X11: `xdotool type` — pynput's alternative was tried first and
          dropped, it raised InvalidCharacterException on Cyrillic (X11
          keymap-remap limits reached mid-string), confirmed against real
          Russian text; xdotool has no such issue.
        - Wayland: `ydotool type`, needs its ydotoold daemon running with
          uinput access — a real setup step beyond pipx install.
        `--delay`/`--key-delay` trimmed from each tool's slower default to
        speed up longer insertions."""
        if QGuiApplication.platformName() == "xcb":
            tool = shutil.which("xdotool")
            if not tool:
                self.autotype_unavailable.emit(
                    "xdotool not found — install it for autotype on X11 "
                    "(e.g. sudo apt install xdotool)"
                )
                return None
            return [tool, "type", "--clearmodifiers", "--delay", "3", "--", text]

        tool = shutil.which("ydotool")
        if not tool:
            self.autotype_unavailable.emit(
                "ydotool not found — install it and run ydotoold for autotype on Wayland"
            )
            return None
        return [tool, "type", "--key-delay", "3", "--", text]
