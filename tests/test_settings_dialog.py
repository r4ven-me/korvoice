from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMessageBox

from korvoice.settings_dialog import SettingsDialog


def test_hotkey_type_defaults_to_custom_combination(config, qapp):
    dialog = SettingsDialog(config)
    assert dialog.hotkey_type_combo.currentData() == ""
    assert dialog.hotkey_combo_row.isEnabled()
    assert dialog.hotkey_record.keySequence() == QKeySequence(config.hotkey("record"))


def test_hotkey_type_preselects_known_single_key(config, qapp):
    config.set_hotkey("record", "Control_R")
    dialog = SettingsDialog(config)
    assert dialog.hotkey_type_combo.currentData() == "Control_R"
    assert not dialog.hotkey_combo_row.isEnabled()


def test_saving_single_key_hotkey_persists_to_config(config, qapp):
    dialog = SettingsDialog(config)
    index = dialog.hotkey_type_combo.findData("Control_R")
    assert index > 0
    dialog.hotkey_type_combo.setCurrentIndex(index)
    assert not dialog.hotkey_combo_row.isEnabled()

    dialog._save()

    assert config.hotkey("record") == "Control_R"


def test_saving_custom_combination_persists_to_config(config, qapp):
    dialog = SettingsDialog(config)
    dialog.hotkey_record.setKeySequence(QKeySequence("Ctrl+Alt+V"))

    dialog._save()

    assert config.hotkey("record") == QKeySequence("Ctrl+Alt+V").toString(
        QKeySequence.SequenceFormat.PortableText
    )


def test_switching_back_to_custom_combination_enables_row(config, qapp):
    config.set_hotkey("record", "Control_R")
    dialog = SettingsDialog(config)
    assert not dialog.hotkey_combo_row.isEnabled()

    dialog.hotkey_type_combo.setCurrentIndex(0)

    assert dialog.hotkey_type_combo.currentData() == ""
    assert dialog.hotkey_combo_row.isEnabled()


def test_saving_empty_hotkey_prompts_and_is_blocked_on_no(config, qapp, monkeypatch):
    # A lone modifier tap into the QKeySequenceEdit produces an empty
    # sequence — used to save silently with no hotkey at all. Now it must
    # ask first, and declining must leave the previous hotkey untouched.
    original_hotkey = config.hotkey("record")
    dialog = SettingsDialog(config)
    dialog.hotkey_record.clear()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    dialog._save()

    assert config.hotkey("record") == original_hotkey


def test_saving_empty_hotkey_proceeds_on_yes(config, qapp, monkeypatch):
    dialog = SettingsDialog(config)
    dialog.hotkey_record.clear()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)

    dialog._save()

    assert config.hotkey("record") == ""
