"""korvoice configuration: YAML in ~/.config/korvoice/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "korvoice"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# (model id, label) — CTC lines are faster, RNNT more accurate; "e2e" lines
# add punctuation/case restoration on top of the same encoder. See
# https://github.com/salute-developers/GigaAM — v3_e2e_ctc is the default:
# CTC for speed, e2e because raw CTC output has no punctuation or capital
# letters at all, which reads poorly once dictated into a text field.
MODEL_CHOICES = [
    ("v3_e2e_ctc", "v3 CTC + punctuation (default, fastest with punctuation)"),
    ("v3_e2e_rnnt", "v3 RNNT + punctuation (more accurate, slower)"),
    ("v3_ctc", "v3 CTC, no punctuation (fastest)"),
    ("v3_rnnt", "v3 RNNT, no punctuation"),
]

DEVICE_CHOICES = [
    ("auto", "Auto (GPU if available, else CPU)"),
    ("cpu", "CPU"),
    ("cuda", "GPU (NVIDIA CUDA)"),
]

MODE_CHOICES = [
    ("push_to_talk", "Push-to-talk (hold the key)"),
    ("toggle", "Toggle (press to start/stop)"),
]

# X11 keysym names for the bare modifier keys, used as-is as the whole
# hotkey string (no "+"-joined combination) — hotkeys.parse_sequence's
# fallback already passes an unrecognised multi-character key name through
# verbatim, and XStringToKeysym resolves "Control_R" etc. as a normal,
# distinct keysym, so the X11/portal backends need no changes to support
# these (see settings_dialog.py's "Hotkey type" selector, the only place
# that actually offers them).
SINGLE_KEY_CHOICES = [
    ("Control_R", "Right Ctrl"),
    ("Control_L", "Left Ctrl"),
    ("Shift_R", "Right Shift"),
    ("Shift_L", "Left Shift"),
    ("Alt_R", "Right Alt"),
    ("Alt_L", "Left Alt"),
    ("Super_R", "Right Super"),
    ("Super_L", "Left Super"),
]

GENERAL_DEFAULTS = {
    "theme": "system",          # system | nord-dark | nord-light
    # auto = follow the app's own theme; dark/light pin a specific icon
    # colour regardless of it — the system tray's own background isn't
    # necessarily the same as the app's theme (see theme.tray_icon_color).
    "tray_icon": "auto",
    "mode": "push_to_talk",     # push_to_talk | toggle
    "model": "v3_e2e_ctc",
    "device": "auto",           # auto | cpu | cuda
    # Recorded audio longer than this is split at the nearest silence
    # before transcription — GigaAM.transcribe() rejects anything over 25s
    # outright; the margin below that is deliberate headroom, not exact.
    "chunk_max_seconds": 20,
    "input_device": "",         # "" = system default input device
    "output_clipboard": True,
    "output_autotype": True,
    "output_window": True,
}

HOTKEY_DEFAULTS = {
    "record": "Ctrl+Alt+Space",
}


class Config:
    """YAML config with sections general / hotkeys. Written to disk on
    every change (write-through)."""

    def __init__(self) -> None:
        self._data: dict = {}
        if CONFIG_FILE.exists():
            try:
                self._data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                # a broken file must not block startup — fall back to defaults
                self._data = {}
        changed = self._ensure_defaults()
        if changed or not CONFIG_FILE.exists():
            self.save()

    def _ensure_defaults(self) -> bool:
        changed = False
        general = self._data.setdefault("general", {})
        for key, value in GENERAL_DEFAULTS.items():
            if key not in general:
                general[key] = value
                changed = True
        hotkeys = self._data.setdefault("hotkeys", {})
        for key, value in HOTKEY_DEFAULTS.items():
            if key not in hotkeys:
                hotkeys[key] = value
                changed = True
        return changed

    # -- general settings -----------------------------------------------------

    def get(self, key: str):
        default = GENERAL_DEFAULTS[key]
        value = self._data["general"].get(key, default)
        if isinstance(default, bool):
            return bool(value)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value

    def set(self, key: str, value) -> None:
        self._data["general"][key] = value
        self.save()

    # -- hotkeys --------------------------------------------------------------

    def hotkey(self, action: str) -> str:
        return str(self._data["hotkeys"].get(action, "") or "")

    def set_hotkey(self, action: str, sequence: str) -> None:
        self._data["hotkeys"][action] = sequence
        self.save()

    # -- persistence ----------------------------------------------------------

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            yaml.safe_dump(self._data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass

    def file_path(self) -> str:
        return str(CONFIG_FILE)
