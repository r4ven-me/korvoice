"""Clipboard backends used by output.py.

X11 (and any non-Wayland session): Qt's own clipboard. It can attach extra
MIME entries, which is how the "hide from clipboard history" option works:
the "x-kde-passwordManagerHint: secret" entry is the convention password
managers (KeePassXC and others) use so that clipboard managers — Klipper,
CopyQ, cliphist and others that honour it — don't record the value.

Wayland: `wl-copy`/`wl-paste` from wl-clipboard. A tray application
without keyboard focus usually can't set the Wayland selection through Qt
(the compositor wants a recent input serial); wl-clipboard can. wl-copy
offers exactly one MIME type, so it can't carry the history hint, and a
restore brings back one format of the previous contents (text preferred)
rather than all of them.
"""

from __future__ import annotations

import logging
import subprocess

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

SECRET_HINT_MIME = "x-kde-passwordManagerHint"
SECRET_HINT_VALUE = b"secret"

_WL_TIMEOUT = 2  # seconds — wl-copy forks and returns at once; wl-paste is quick
_WL_TEXT_TYPES = ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "TEXT", "STRING")


class QtClipboard:
    supports_history_hint = True

    def set_text(self, text: str, hide_from_history: bool = False) -> bool:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False
        if hide_from_history:
            data = QMimeData()
            data.setText(text)
            data.setData(SECRET_HINT_MIME, QByteArray(SECRET_HINT_VALUE))
            clipboard.setMimeData(data)
        else:
            clipboard.setText(text)
        return True

    def snapshot(self) -> QMimeData | None:
        """A copy of every format currently in the clipboard (the original
        QMimeData belongs to the clipboard and dies with the next change)."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return None
        source = clipboard.mimeData()
        clone = QMimeData()
        if source is not None:
            for mime_type in source.formats():
                clone.setData(mime_type, source.data(mime_type))
        return clone

    def restore(self, snapshot: QMimeData) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setMimeData(snapshot)

    def text(self) -> str | None:
        clipboard = QGuiApplication.clipboard()
        return clipboard.text() if clipboard is not None else None


class WlClipboard:
    supports_history_hint = False

    def __init__(self, wl_copy: str, wl_paste: str) -> None:
        self._wl_copy = wl_copy
        self._wl_paste = wl_paste

    def _copy(self, args: list[str], data: bytes | None = None) -> bool:
        # stdout/stderr must not be pipes: wl-copy forks a background
        # server that inherits them, and run() would wait for it to exit.
        try:
            result = subprocess.run(
                [self._wl_copy, *args], input=data, timeout=_WL_TIMEOUT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("wl-copy failed: %s", exc)
            return False
        return result.returncode == 0

    def _paste(self, args: list[str]) -> bytes | None:
        try:
            result = subprocess.run(
                [self._wl_paste, *args], capture_output=True, timeout=_WL_TIMEOUT, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.debug("wl-paste failed: %s", exc)
            return None
        return result.stdout if result.returncode == 0 else None

    def set_text(self, text: str, hide_from_history: bool = False) -> bool:
        return self._copy(["--type", "text/plain;charset=utf-8"], text.encode("utf-8"))

    def snapshot(self) -> tuple[str | None, bytes] | None:
        """(mime type, data) of the current selection; (None, b"") when it
        is empty — restoring that clears the clipboard again."""
        listed = self._paste(["--list-types"])
        if listed is None:
            return (None, b"")  # wl-paste exits non-zero on an empty clipboard
        types = [t.strip() for t in listed.decode("utf-8", "replace").splitlines() if t.strip()]
        if not types:
            return (None, b"")
        mime_type = next((t for t in _WL_TEXT_TYPES if t in types), types[0])
        data = self._paste(["--no-newline", "--type", mime_type])
        return None if data is None else (mime_type, data)

    def restore(self, snapshot: tuple[str | None, bytes]) -> None:
        mime_type, data = snapshot
        if mime_type is None:
            self._copy(["--clear"])
        else:
            self._copy(["--type", mime_type], data)

    def text(self) -> str | None:
        data = self._paste(["--no-newline"])
        return None if data is None else data.decode("utf-8", "replace")
