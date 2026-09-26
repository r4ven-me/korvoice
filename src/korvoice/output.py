"""Delivers recognized text to clipboard, autotype and/or the history
window — independently, per Settings → Output (all on by default)."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time

from PySide6.QtCore import QMimeData, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from .config import Config
from .i18n import tr

log = logging.getLogger(__name__)

_AUTOTYPE_TIMEOUT = 10  # seconds — a stuck xdotool/ydotool must not hang forever
_FILLER_RE = re.compile(
    r"(?:[ \t]*,[ \t]*)?"
    r"(?<!\w)(?:э(?:[ \t-]*э)*|эм|м(?:[ \t-]*м)+)(?!\w)"
    r"(?:[ \t]*,[ \t]*)?",
    re.IGNORECASE,
)


def remove_fillers(text: str) -> str:
    """Removes standalone Russian hesitation sounds without touching words."""
    text = _FILLER_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]+([,.!?;:])", r"\1", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


class _AutotypeWorker(QThread):
    """Runs the blocking xdotool/ydotool subprocess off the GUI thread."""

    failed = Signal(str)

    def __init__(self, command: list[str], parent=None) -> None:
        super().__init__(parent)
        self._command = command

    def run(self) -> None:
        t0 = time.monotonic()
        try:
            subprocess.run(self._command, check=True, timeout=_AUTOTYPE_TIMEOUT)
            log.debug("autotype finished in %.2fs", time.monotonic() - t0)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.debug("autotype failed after %.2fs", time.monotonic() - t0)
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
        self._clipboard_generation = 0
        self._temporary_clipboard_original: QMimeData | None = None

    def dispatch(self, text: str) -> None:
        if not text:
            return
        if bool(self.config.get("remove_fillers")):
            text = remove_fillers(text)
            if not text:
                return
        text += str(self.config.get("output_suffix"))
        if bool(self.config.get("output_clipboard")):
            self._to_clipboard(text)
        if bool(self.config.get("output_autotype")):
            self._autotype(text)
        if bool(self.config.get("output_window")):
            self.delivered.emit(text)

    @staticmethod
    def _clone_mime_data(source: QMimeData) -> QMimeData:
        clone = QMimeData()
        for mime_type in source.formats():
            clone.setData(mime_type, source.data(mime_type))
        return clone

    def _to_clipboard(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            # An intentional clipboard output supersedes any pending restore
            # from an earlier temporary autotype operation.
            self._clipboard_generation += 1
            self._temporary_clipboard_original = None
            clipboard.setText(text)

    def _autotype(self, text: str) -> None:
        # `xdotool type` handles Cyrillic by repeatedly changing the X11
        # keymap.  Those synchronous X server operations can freeze the
        # entire desktop for tens of seconds, not merely this process.  A
        # single paste shortcut avoids keymap mutation altogether.
        command = self._autotype_command(text)
        if command is None:
            return  # _autotype_command already emitted the "unavailable" reason

        restore_clipboard = False
        clipboard_generation = self._clipboard_generation
        if QGuiApplication.platformName() == "xcb":
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                restore_clipboard = not bool(self.config.get("output_clipboard"))
                if restore_clipboard:
                    if self._temporary_clipboard_original is None:
                        self._temporary_clipboard_original = self._clone_mime_data(
                            clipboard.mimeData()
                        )
                    self._clipboard_generation += 1
                    clipboard_generation = self._clipboard_generation
                clipboard.setText(text)

        worker = _AutotypeWorker(command, self)
        worker.failed.connect(self._on_autotype_failed)
        worker.finished.connect(
            lambda w=worker, inserted=text, restore=restore_clipboard,
            generation=clipboard_generation: self._finish_autotype(
                w, inserted, restore, generation
            )
        )
        self._autotype_workers.append(worker)
        worker.start()

    def _on_autotype_failed(self, message: str) -> None:
        log.warning("autotype failed: %s", message)
        self.autotype_unavailable.emit(message)

    def _finish_autotype(
        self, worker: _AutotypeWorker, inserted: str, restore: bool, generation: int
    ) -> None:
        self._forget_worker(worker)
        if restore:
            # Let the focused application handle Ctrl+V before replacing the
            # temporary clipboard contents.  Never overwrite a value the user
            # copied while autotype was running.
            QTimer.singleShot(
                150, lambda: self._restore_clipboard(inserted, generation)
            )

    def _restore_clipboard(self, inserted: str, generation: int) -> None:
        clipboard = QGuiApplication.clipboard()
        original = self._temporary_clipboard_original
        if generation != self._clipboard_generation:
            return
        if clipboard is not None and original is not None and clipboard.text() == inserted:
            clipboard.setMimeData(original)
        self._temporary_clipboard_original = None

    def _forget_worker(self, worker: _AutotypeWorker) -> None:
        if worker in self._autotype_workers:
            self._autotype_workers.remove(worker)

    def _autotype_command(self, text: str) -> list[str] | None:
        """Builds the subprocess command for the current session type, or
        emits autotype_unavailable and returns None. Both backends are
        external system tools, not pip dependencies (see README):
        - X11: the text is first put in Qt's clipboard and `xdotool key`
          sends one Ctrl+V.  Do not use `xdotool type` here: for Cyrillic it
          repeatedly mutates the X keymap and can synchronously freeze Xorg
          for tens of seconds.  Consequently X11 autotype uses the clipboard
          temporarily; when clipboard output is disabled, its previous text
          is restored immediately after the paste.
        - Wayland: `ydotool type`, needs its ydotoold daemon running with
          uinput access — a real setup step beyond pipx install.
        `--key-delay` trims ydotool's slower default."""
        if QGuiApplication.platformName() == "xcb":
            tool = shutil.which("xdotool")
            if not tool:
                self.autotype_unavailable.emit(
                    tr("xdotool not found — install it for autotype on X11 "
                       "(e.g. sudo apt install xdotool)")
                )
                return None
            return [tool, "key", "--clearmodifiers", "ctrl+v"]

        tool = shutil.which("ydotool")
        if not tool:
            self.autotype_unavailable.emit(
                tr("ydotool not found — install it and run ydotoold for autotype on Wayland")
            )
            return None
        return [tool, "type", "--key-delay", "3", "--", text]
