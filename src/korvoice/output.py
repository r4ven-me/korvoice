"""Delivers recognized text to clipboard, autotype and/or the history
window — independently, per Settings → Output (all on by default)."""

from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
import time

from PySide6.QtCore import QMimeData, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from .clipboard import QtClipboard, WlClipboard
from .config import Config
from .i18n import tr

log = logging.getLogger(__name__)

_AUTOTYPE_TIMEOUT = 10  # seconds — a stuck xdotool/ydotool must not hang forever

# How long the focused application gets to request the pasted text before
# the previous clipboard contents come back. Wayland is slower: the paste
# request travels app -> compositor -> the forked wl-copy process.
_RESTORE_DELAY_MS = {"x11": 150, "wayland": 300}

# ydotool >= 1.0 takes raw evdev keycodes (KEY_LEFTCTRL=29, KEY_LEFTSHIFT=42,
# KEY_V=47) as code:state pairs; 0.1.x (still what Debian/Ubuntu ship) takes
# key names.
_YDOTOOL_PASTE = ["29:1", "47:1", "47:0", "29:0"]
_YDOTOOL_PASTE_SHIFT = ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]
_YDOTOOL_LEGACY_PASTE = ["ctrl+v"]
_YDOTOOL_LEGACY_PASTE_SHIFT = ["ctrl+shift+v"]
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

    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, command: list[str], parent=None) -> None:
        super().__init__(parent)
        self._command = command

    def run(self) -> None:
        t0 = time.monotonic()
        try:
            subprocess.run(self._command, check=True, timeout=_AUTOTYPE_TIMEOUT)
            log.debug("autotype finished in %.2fs", time.monotonic() - t0)
            self.succeeded.emit()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.debug("autotype failed after %.2fs", time.monotonic() - t0)
            self.failed.emit(str(exc))


def _is_wayland() -> bool:
    return QGuiApplication.platformName().startswith("wayland")


@functools.lru_cache(maxsize=4)
def ydotool_is_legacy(tool: str) -> bool:
    """True for ydotool 0.1.x, whose command list (printed when run with no
    arguments) still includes "recorder" — dropped in the 1.0 rewrite."""
    try:
        result = subprocess.run([tool], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "recorder" in (result.stdout + result.stderr)


class OutputDispatcher(QObject):
    delivered = Signal(str)             # text to show in the history window
    autotype_unavailable = Signal(str)  # human-readable reason, for the tray tooltip
    autotype_succeeded = Signal()       # clears a stale "unavailable" reason

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        # Keeps running _AutotypeWorker instances referenced until they
        # finish — letting the last reference drop while the underlying
        # QThread is still alive is a use-after-free waiting to happen.
        self._autotype_workers: list[_AutotypeWorker] = []
        self._qt_clipboard = QtClipboard()
        self._clipboard_generation = 0
        self._temporary_clipboard_original = None

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

    def _clipboard_backend(self) -> QtClipboard | WlClipboard:
        if _is_wayland():
            wl_copy, wl_paste = shutil.which("wl-copy"), shutil.which("wl-paste")
            if wl_copy and wl_paste:
                return WlClipboard(wl_copy, wl_paste)
        return self._qt_clipboard

    def _hide_mode(self) -> str:
        return str(self.config.get("clipboard_hide_history"))

    def _to_clipboard(self, text: str) -> None:
        # An intentional clipboard output supersedes any pending restore
        # from an earlier temporary autotype operation.
        self._clipboard_generation += 1
        self._temporary_clipboard_original = None
        self._clipboard_backend().set_text(text, hide_from_history=self._hide_mode() == "all")

    def _autotype(self, text: str) -> None:
        # Typing the text key by key is not an option: `xdotool type`
        # handles Cyrillic by repeatedly changing the X11 keymap, and those
        # synchronous X server operations can freeze the entire desktop for
        # tens of seconds; `ydotool type` only knows the US layout and
        # can't produce Cyrillic at all. Both sessions therefore put the
        # text in the clipboard and send a single paste shortcut.
        command = self._autotype_command(text)
        if command is None:
            return  # _autotype_command already emitted the "unavailable" reason

        backend = self._clipboard_backend()
        restore_clipboard = not bool(self.config.get("output_clipboard"))
        clipboard_generation = self._clipboard_generation
        if restore_clipboard:
            if self._temporary_clipboard_original is None:
                self._temporary_clipboard_original = backend.snapshot()
            self._clipboard_generation += 1
            clipboard_generation = self._clipboard_generation
            backend.set_text(text, hide_from_history=self._hide_mode() in ("temporary", "all"))
        # Otherwise dispatch() has just put this same text in the clipboard
        # via _to_clipboard(); setting it again would only add a duplicate
        # entry to clipboard managers.

        worker = _AutotypeWorker(command, self)
        worker.succeeded.connect(self.autotype_succeeded)
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
            # Let the focused application handle the paste before replacing
            # the temporary clipboard contents.  Never overwrite a value the
            # user copied while autotype was running.
            delay = _RESTORE_DELAY_MS["wayland" if _is_wayland() else "x11"]
            # Use the two-argument overload supported by every PySide6
            # version in our >=6.5 range. The callback closes over `self`, so
            # the dispatcher stays alive until the restore has run.
            QTimer.singleShot(delay, lambda: self._restore_clipboard(inserted, generation))

    def _restore_clipboard(self, inserted: str, generation: int) -> None:
        if generation != self._clipboard_generation:
            return
        original = self._temporary_clipboard_original
        self._temporary_clipboard_original = None
        if original is None:
            return
        backend = self._clipboard_backend()
        if backend.text() != inserted:
            return
        if isinstance(backend, QtClipboard) and isinstance(original, QMimeData):
            backend.restore(original)
        elif isinstance(backend, WlClipboard) and isinstance(original, tuple):
            backend.restore(original)

    def shutdown(self, timeout_ms: int = (_AUTOTYPE_TIMEOUT + 1) * 1000) -> None:
        """Waits for running autotype subprocesses before the dispatcher
        goes away — destroying a QThread that is still running crashes the
        process. Bounded by the subprocess timeout, so it can't hang."""
        for worker in list(self._autotype_workers):
            worker.wait(timeout_ms)
        self._autotype_workers.clear()

    def _forget_worker(self, worker: _AutotypeWorker) -> None:
        if worker in self._autotype_workers:
            self._autotype_workers.remove(worker)

    def _autotype_command(self, text: str) -> list[str] | None:
        """Builds the paste-shortcut command for the current session type,
        or emits autotype_unavailable and returns None. Both backends are
        external system tools, not pip dependencies (see README):
        - X11: `xdotool key` sends the configured shortcut.
        - Wayland: `ydotool key` sends it — needs its ydotoold daemon
          running with uinput access — and wl-clipboard puts the text in
          the clipboard first (see clipboard.py for why not Qt).
        Most applications paste with Ctrl+V, but terminals usually expect
        Ctrl+Shift+V instead — configurable via Settings → Output →
        "Paste shortcut" (output_autotype_shortcut)."""
        shortcut = str(self.config.get("output_autotype_shortcut"))
        if QGuiApplication.platformName() == "xcb":
            tool = shutil.which("xdotool")
            if not tool:
                self.autotype_unavailable.emit(
                    tr("xdotool not found — install it for autotype on X11 "
                       "(e.g. sudo apt install xdotool)")
                )
                return None
            return [tool, "key", "--clearmodifiers", shortcut]

        tool = shutil.which("ydotool")
        if not tool:
            self.autotype_unavailable.emit(
                tr("ydotool not found — install it and run ydotoold for autotype on Wayland")
            )
            return None
        if not (shutil.which("wl-copy") and shutil.which("wl-paste")):
            self.autotype_unavailable.emit(
                tr("wl-copy not found — install wl-clipboard for autotype on Wayland")
            )
            return None
        legacy = ydotool_is_legacy(tool)
        if shortcut == "ctrl+shift+v":
            keys = _YDOTOOL_LEGACY_PASTE_SHIFT if legacy else _YDOTOOL_PASTE_SHIFT
        else:
            keys = _YDOTOOL_LEGACY_PASTE if legacy else _YDOTOOL_PASTE
        return [tool, "key", *keys]
