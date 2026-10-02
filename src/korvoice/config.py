"""korvoice configuration: YAML in ~/.config/korvoice/config.yaml."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "korvoice"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# (model id, label) — CTC lines are faster, RNNT more accurate; "e2e" lines
# add punctuation/case restoration on top of the same encoder. See
# https://github.com/salute-developers/GigaAM — v3_e2e_ctc is the default:
# CTC for speed, e2e because raw CTC output has no punctuation or capital
# letters at all, which reads poorly once dictated into a text field.
#
# Labels kept short on purpose: a QComboBox sizes itself to its widest
# item by default, and a long label here was the main reason the settings
# dialog couldn't be shrunk smaller than its initial size.
MODEL_CHOICES = [
    ("v3_e2e_ctc", "v3 CTC + punctuation (default)"),
    ("v3_e2e_rnnt", "v3 RNNT + punctuation (more accurate)"),
    ("v3_ctc", "v3 CTC (no punctuation)"),
    ("v3_rnnt", "v3 RNNT (no punctuation)"),
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

OUTPUT_SUFFIX_CHOICES = [
    ("", "Nothing"),
    (" ", "Space"),
    ("\n", "New line"),
    ("\n\n", "Blank line"),
]

# Which clipboard writes carry the "x-kde-passwordManagerHint: secret" MIME
# entry that clipboard managers (Klipper, CopyQ, cliphist, ...) use to skip
# password-manager copies. "temporary" = only the text autotype puts in
# the clipboard just to paste it and then restores the previous contents.
CLIPBOARD_HISTORY_CHOICES = [
    ("temporary", "Only temporary paste text"),
    ("all", "All recognized text"),
    ("none", "Nothing"),
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
    "language": "system",       # system | ru | en
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
    "output_suffix": "",       # appended after every recognized utterance
    "clipboard_hide_history": "temporary",  # temporary | all | none
    "remove_fillers": False,    # remove standalone э / э-э / эм / м-м
    "history_persistent": False,
    "wake_word_enabled": False,  # listen continuously for wake_word_phrase while idle
    "wake_word_phrase": "",      # free-text Russian phrase, e.g. "привет корвойс"
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
                loaded = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                # a broken file must not block startup — fall back to defaults
                loaded = None
            self._data = loaded if isinstance(loaded, dict) else {}
        changed = self._ensure_defaults()
        if changed or not CONFIG_FILE.exists():
            self.save()

    def _ensure_defaults(self) -> bool:
        changed = False
        for section in ("general", "hotkeys"):
            if not isinstance(self._data.get(section), dict):
                self._data[section] = {}
                changed = True
        general = self._data["general"]
        for key, value in GENERAL_DEFAULTS.items():
            if key not in general:
                general[key] = value
                changed = True
        hotkeys = self._data["hotkeys"]
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
        """Writes to a temporary file in the same directory and renames it
        over the config, so a crash mid-write can't leave a truncated file
        (which would silently reset every setting on the next start)."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        content = yaml.safe_dump(self._data, allow_unicode=True, sort_keys=False)
        fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=CONFIG_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, CONFIG_FILE)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def file_path(self) -> str:
        return str(CONFIG_FILE)
