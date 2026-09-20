from PySide6.QtGui import QKeySequence

from korvoice.settings_dialog import SettingsDialog


def test_hotkey_type_defaults_to_custom_combination(config, qapp):
    dialog = SettingsDialog(config)
    assert dialog.hotkey_type_combo.currentData() == ""
    assert not dialog.hotkey_combo_row.isHidden()
    assert dialog.hotkey_record.keySequence() == QKeySequence(config.hotkey("record"))


def test_hotkey_type_preselects_known_single_key(config, qapp):
    config.set_hotkey("record", "Control_R")
    dialog = SettingsDialog(config)
    assert dialog.hotkey_type_combo.currentData() == "Control_R"
    assert dialog.hotkey_combo_row.isHidden()


def test_saving_single_key_hotkey_persists_to_config(config, qapp):
    dialog = SettingsDialog(config)
    index = dialog.hotkey_type_combo.findData("Control_R")
    assert index > 0
    dialog.hotkey_type_combo.setCurrentIndex(index)
    assert dialog.hotkey_combo_row.isHidden()

    dialog._save()

    assert config.hotkey("record") == "Control_R"


def test_saving_custom_combination_persists_to_config(config, qapp):
    dialog = SettingsDialog(config)
    dialog.hotkey_record.setKeySequence(QKeySequence("Ctrl+Alt+V"))

    dialog._save()

    assert config.hotkey("record") == QKeySequence("Ctrl+Alt+V").toString(
        QKeySequence.SequenceFormat.PortableText
    )


def test_switching_back_to_custom_combination_shows_row(config, qapp):
    config.set_hotkey("record", "Control_R")
    dialog = SettingsDialog(config)
    assert dialog.hotkey_combo_row.isHidden()

    dialog.hotkey_type_combo.setCurrentIndex(0)

    assert dialog.hotkey_type_combo.currentData() == ""
    assert not dialog.hotkey_combo_row.isHidden()
