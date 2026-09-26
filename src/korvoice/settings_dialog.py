"""Settings dialog: General, Output, Model, About — same structure as
kortalk's settings_dialog.py (~/Cloud/Projects/public/kortalk), trimmed to
the fields korvoice actually has (no providers/prompts)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import (
    __author__,
    __chat__,
    __description__,
    __homepage__,
    __license__,
    __repository__,
    __telegram__,
    __version__,
    theme,
)
from .audio import list_input_devices
from .config import (
    DEVICE_CHOICES,
    MODE_CHOICES,
    MODEL_CHOICES,
    OUTPUT_SUFFIX_CHOICES,
    SINGLE_KEY_CHOICES,
    Config,
)
from .i18n import set_language, tr

AUTOSTART_FILE = Path.home() / ".config" / "autostart" / "korvoice.desktop"

# Exec must be an absolute path: with a pipx install ~/.local/bin may not be
# in PATH yet when the session starts.
AUTOSTART_DESKTOP = """\
[Desktop Entry]
Type=Application
Name=korvoice
Comment=Push-to-talk Russian voice input (GigaAM)
Comment[ru]=Голосовой ввод на русском языке (GigaAM)
Exec={exec_path}
Icon={icon_path}
X-GNOME-Autostart-enabled=true
"""

_KEY_FMT = QKeySequence.SequenceFormat.PortableText


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(tr("Settings — korvoice"))
        self.resize(560, 460)
        theme.apply_window_theme(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), tr("General"))
        tabs.addTab(self._build_output_tab(), tr("Output"))
        tabs.addTab(self._build_model_tab(), tr("Model"))
        tabs.addTab(_build_about_widget(), tr("About"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        for role, label in (
            (QDialogButtonBox.StandardButton.Save, "Save"),
            (QDialogButtonBox.StandardButton.Cancel, "Cancel"),
        ):
            button = buttons.button(role)
            if button is not None:
                button.setIcon(QIcon())
                button.setText(tr(label))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # -- "General" tab ---------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(tr("System"), "system")
        self.theme_combo.addItem(tr("Nord Dark"), "nord-dark")
        self.theme_combo.addItem(tr("Nord Light"), "nord-light")
        index = self.theme_combo.findData(str(self.config.get("theme")))
        self.theme_combo.setCurrentIndex(max(0, index))
        form.addRow(tr("Theme:"), self.theme_combo)

        self.language_combo = QComboBox()
        self.language_combo.addItem(tr("System language"), "system")
        self.language_combo.addItem("Русский", "ru")
        self.language_combo.addItem("English", "en")
        language_index = self.language_combo.findData(str(self.config.get("language")))
        self.language_combo.setCurrentIndex(max(0, language_index))
        form.addRow(tr("Language:"), self.language_combo)

        self.tray_icon_combo = QComboBox()
        self.tray_icon_combo.addItem(tr("Auto (theme)"), "auto")
        self.tray_icon_combo.addItem(tr("Dark"), "dark")
        self.tray_icon_combo.addItem(tr("Light"), "light")
        tray_index = self.tray_icon_combo.findData(str(self.config.get("tray_icon")))
        self.tray_icon_combo.setCurrentIndex(max(0, tray_index))
        self.tray_icon_combo.setToolTip(tr(
            "The system tray's own background isn't always the same as the "
            "app's theme — pick a fixed icon colour if \"Auto\" is hard to see."
        ))
        form.addRow(tr("Tray icon:"), self.tray_icon_combo)

        self.mode_combo = QComboBox()
        for value, label in MODE_CHOICES:
            self.mode_combo.addItem(tr(label), value)
        mode_index = self.mode_combo.findData(str(self.config.get("mode")))
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        self.mode_combo.setToolTip(tr(
            "Push-to-talk: hold the hotkey while speaking, release to transcribe.\n"
            "Toggle: press once to start recording, press again to stop."
        ))
        form.addRow(tr("Recording mode:"), self.mode_combo)

        # Two alternative ways to set the hotkey, both always visible (one
        # greys out rather than disappearing) — a lone modifier press (e.g.
        # Right Ctrl) typed straight into "...or combination" below doesn't
        # register at all (Qt's QKeySequenceEdit has no representation for
        # "just a modifier, nothing else"), which used to silently save an
        # *empty* hotkey with no feedback. "Single key" is the explicit,
        # working way to bind one — see _save()'s guard against saving
        # nothing at all.
        self.hotkey_type_combo = QComboBox()
        self.hotkey_type_combo.addItem(tr("Use the combination below"), "")
        for value, label in SINGLE_KEY_CHOICES:
            self.hotkey_type_combo.addItem(tr(label), value)
        self.hotkey_type_combo.setToolTip(tr(
            "A lone modifier key (Ctrl/Shift/Alt/Super) can't be captured by "
            "pressing it into the combination field below — pick it here."
        ))
        form.addRow(tr("Single key:"), self.hotkey_type_combo)

        self.hotkey_combo_row = QWidget()
        combo_row_layout = QHBoxLayout(self.hotkey_combo_row)
        combo_row_layout.setContentsMargins(0, 0, 0, 0)
        self.hotkey_record = QKeySequenceEdit(QKeySequence(self.config.hotkey("record")))
        combo_row_layout.addWidget(self.hotkey_record, 1)
        clear_hotkey = QPushButton(tr("Clear"))
        clear_hotkey.clicked.connect(self.hotkey_record.clear)
        combo_row_layout.addWidget(clear_hotkey)
        form.addRow(tr("...or combination:"), self.hotkey_combo_row)

        current_hotkey = self.config.hotkey("record")
        single_key_index = self.hotkey_type_combo.findData(current_hotkey)
        if single_key_index > 0:
            self.hotkey_type_combo.setCurrentIndex(single_key_index)
        self.hotkey_combo_row.setEnabled(single_key_index <= 0)
        self.hotkey_type_combo.currentIndexChanged.connect(self._hotkey_type_changed)

        self.autostart = QCheckBox(tr("Start at login"))
        self.autostart.setChecked(AUTOSTART_FILE.exists())
        form.addRow("", self.autostart)

        hotkey_note = QLabel(tr("X11 hotkey note"))
        hotkey_note.setWordWrap(True)
        form.addRow("", hotkey_note)

        settings_path_label = QLabel(tr("Settings file: {path}", path=self.config.file_path()))
        settings_path_label.setWordWrap(True)
        form.addRow("", settings_path_label)
        return page

    def _hotkey_type_changed(self, _index: int) -> None:
        self.hotkey_combo_row.setEnabled(not self.hotkey_type_combo.currentData())

    # -- "Output" tab ------------------------------------------------------------

    def _build_output_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(tr("Deliver recognized text to (any combination):")))

        self.output_clipboard = QCheckBox(tr("Keep recognized text in the clipboard"))
        self.output_clipboard.setChecked(bool(self.config.get("output_clipboard")))
        self.output_clipboard.setToolTip(tr(
                    "X11 autotype uses the clipboard temporarily. When this option is off, "
                    "the previous contents are restored after pasting. A clipboard history "
                    "manager may still capture the temporary text."
                ))
        layout.addWidget(self.output_clipboard)

        self.output_autotype = QCheckBox(tr("Autotype into the focused window"))
        self.output_autotype.setChecked(bool(self.config.get("output_autotype")))
        self.output_autotype.setToolTip(tr("Autotype requirements"))
        layout.addWidget(self.output_autotype)

        self.output_window = QCheckBox(tr("History window"))
        self.output_window.setChecked(bool(self.config.get("output_window")))
        layout.addWidget(self.output_window)

        self.history_persistent = QCheckBox(tr("Keep history between restarts"))
        self.history_persistent.setChecked(bool(self.config.get("history_persistent")))
        layout.addWidget(self.history_persistent)

        self.remove_fillers = QCheckBox(tr("Remove hesitation sounds (eh, eh-eh, um, mm)"))
        self.remove_fillers.setChecked(bool(self.config.get("remove_fillers")))
        layout.addWidget(self.remove_fillers)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(QLabel(tr("After recognized text:")))
        self.output_suffix_combo = QComboBox()
        for value, label in OUTPUT_SUFFIX_CHOICES:
            self.output_suffix_combo.addItem(tr(label), value)
        self.output_suffix_combo.addItem(tr("Custom…"), None)
        suffix_row.addWidget(self.output_suffix_combo)
        self.output_suffix_custom = QLineEdit()
        self.output_suffix_custom.setPlaceholderText(tr("Text appended verbatim"))
        suffix_row.addWidget(self.output_suffix_custom, 1)
        layout.addLayout(suffix_row)

        suffix = str(self.config.get("output_suffix"))
        suffix_index = self.output_suffix_combo.findData(suffix)
        if suffix_index < 0:
            suffix_index = self.output_suffix_combo.count() - 1
            self.output_suffix_custom.setText(suffix)
        self.output_suffix_combo.setCurrentIndex(suffix_index)
        self.output_suffix_combo.currentIndexChanged.connect(self._output_suffix_changed)
        self._output_suffix_changed(suffix_index)

        layout.addStretch(1)
        return page

    def _output_suffix_changed(self, _index: int) -> None:
        self.output_suffix_custom.setEnabled(self.output_suffix_combo.currentData() is None)

    # -- "Model" tab ---------------------------------------------------------

    def _build_model_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.model_combo = QComboBox()
        for value, label in MODEL_CHOICES:
            self.model_combo.addItem(tr(label), value)
        model_index = self.model_combo.findData(str(self.config.get("model")))
        self.model_combo.setCurrentIndex(max(0, model_index))
        form.addRow(tr("Model:"), self.model_combo)

        self.device_combo = QComboBox()
        for value, label in DEVICE_CHOICES:
            self.device_combo.addItem(tr(label), value)
        device_index = self.device_combo.findData(str(self.config.get("device")))
        self.device_combo.setCurrentIndex(max(0, device_index))
        form.addRow(tr("Inference device:"), self.device_combo)

        self.chunk_seconds = QSpinBox()
        self.chunk_seconds.setRange(5, 24)
        self.chunk_seconds.setValue(int(self.config.get("chunk_max_seconds")))
        self.chunk_seconds.setToolTip(tr("GigaAM chunk note"))
        form.addRow(tr("Max chunk length, s:"), self.chunk_seconds)

        self.input_device_combo = QComboBox()
        self.input_device_combo.addItem(tr("System default"), "")
        for index, name in list_input_devices():
            self.input_device_combo.addItem(name, str(index))
        current_device = str(self.config.get("input_device"))
        device_idx = self.input_device_combo.findData(current_device)
        self.input_device_combo.setCurrentIndex(max(0, device_idx))
        form.addRow(tr("Microphone:"), self.input_device_combo)

        model_note = QLabel(tr("GigaAM model note"))
        model_note.setWordWrap(True)
        form.addRow("", model_note)
        return page

    # -- saving ---------------------------------------------------------------

    def _save(self) -> None:
        single_key = self.hotkey_type_combo.currentData()
        sequence = single_key or self.hotkey_record.keySequence().toString(_KEY_FMT)
        if not sequence:
            # A lone modifier tap into "...or combination" produces an
            # empty QKeySequence — used to save silently as no hotkey at
            # all, with zero feedback, breaking recording entirely.
            proceed = QMessageBox.question(
                self, "korvoice",
                tr("No hotkey is set — recording would only start from the "
                   "tray menu (or its left-click). Save without a hotkey?"),
            ) == QMessageBox.StandardButton.Yes
            if not proceed:
                return

        self.config.set("theme", self.theme_combo.currentData())
        language = str(self.language_combo.currentData())
        self.config.set("language", language)
        set_language(language)
        self.config.set("tray_icon", self.tray_icon_combo.currentData())
        self.config.set("mode", self.mode_combo.currentData())
        self.config.set("output_clipboard", self.output_clipboard.isChecked())
        self.config.set("output_autotype", self.output_autotype.isChecked())
        self.config.set("output_window", self.output_window.isChecked())
        self.config.set("history_persistent", self.history_persistent.isChecked())
        self.config.set("remove_fillers", self.remove_fillers.isChecked())
        suffix = self.output_suffix_combo.currentData()
        if suffix is None:
            suffix = self.output_suffix_custom.text()
        self.config.set("output_suffix", suffix)
        self.config.set("model", self.model_combo.currentData())
        self.config.set("device", self.device_combo.currentData())
        self.config.set("chunk_max_seconds", self.chunk_seconds.value())
        self.config.set("input_device", self.input_device_combo.currentData())
        self.config.set_hotkey("record", sequence)

        try:
            if self.autostart.isChecked():
                AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
                exec_path = shutil.which("korvoice") or str(Path(sys.argv[0]).resolve())
                icon_path = theme.install_icon_file()
                AUTOSTART_FILE.write_text(
                    AUTOSTART_DESKTOP.format(exec_path=exec_path, icon_path=icon_path),
                    encoding="utf-8",
                )
            elif AUTOSTART_FILE.exists():
                AUTOSTART_FILE.unlink()
        except OSError as exc:
            QMessageBox.warning(
                self,
                "korvoice",
                tr("Failed to configure autostart: {message}", message=exc),
            )

        self.saved.emit()
        self.accept()


def _build_about_widget() -> QWidget:
    """Icon, name, version, description/author/license/website (from
    pyproject.toml's [project] table via importlib.metadata, see
    korvoice/__init__.py) — shared between Settings → About and the
    standalone About dialog reached from the tray menu."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(28, 24, 28, 20)
    layout.setSpacing(6)

    icon_label = QLabel()
    icon_label.setPixmap(theme.make_tray_icon().pixmap(64, 64))
    icon_label.setFixedSize(64, 64)
    icon_label.setScaledContents(True)
    layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignHCenter)

    title = QLabel("korvoice")
    title.setStyleSheet("font-size: 18px; font-weight: 600;")
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(title)

    version_label = QLabel(tr("Version {version}", version=__version__))
    version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    layout.addWidget(version_label)

    if __description__:
        layout.addSpacing(6)
        desc = QLabel(tr(__description__))
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

    facts = [(tr("Author:"), __author__), (tr("License:"), __license__)]
    if any(value for _, value in facts):
        layout.addSpacing(6)
        for label_text, value in facts:
            if not value:
                continue
            row = QLabel(f"{label_text} {value}")
            row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(row)

    links = (
        (tr("Website:"), __homepage__),
        (tr("GitHub:"), __repository__),
        (tr("Telegram channel:"), __telegram__),
        (tr("Telegram chat:"), __chat__),
    )
    if any(url for _, url in links):
        layout.addSpacing(6)
    for label_text, url in links:
        if not url:
            continue
        link = QLabel(f'{label_text} <a href="{url}">{url}</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

    layout.addStretch(1)
    return widget


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("About korvoice"))
        theme.apply_window_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(_build_about_widget())

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(28, 0, 28, 20)
        btn_row.addStretch(1)
        close_btn = QPushButton(tr("Close"))
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
