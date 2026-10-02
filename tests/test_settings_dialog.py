import pytest
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLabel, QMessageBox

import korvoice.settings_dialog as settings_dialog_mod
from korvoice.i18n import current_language, set_language
from korvoice.settings_dialog import SettingsDialog


def test_about_lists_telegram_channel_and_chat(qapp, monkeypatch):
    set_language("en")
    monkeypatch.setattr(settings_dialog_mod, "__telegram__", "https://t.me/r4ven_me")
    monkeypatch.setattr(settings_dialog_mod, "__chat__", "https://t.me/r4ven_me_chat")

    widget = settings_dialog_mod._build_about_widget()
    texts = [label.text() for label in widget.findChildren(QLabel)]

    assert any("Telegram channel:" in text and "https://t.me/r4ven_me" in text for text in texts)
    assert any("Telegram chat:" in text and "https://t.me/r4ven_me_chat" in text for text in texts)
    set_language("system")


def test_russian_locale_localizes_settings_window(config, qapp, monkeypatch):
    monkeypatch.setenv("LANGUAGE", "ru")

    dialog = SettingsDialog(config)

    assert dialog.windowTitle() == "Настройки — korvoice"
    assert dialog.output_clipboard.text() == "Оставлять распознанный текст в буфере обмена"
    assert dialog.output_suffix_combo.itemText(0) == "Ничего"
    assert dialog.remove_fillers.text() == "Удалять слова-паразиты (э, э-э, эм, м-м)"


def test_english_filler_option_uses_latin_examples(config, qapp):
    set_language("en")

    dialog = SettingsDialog(config)

    assert dialog.remove_fillers.text() == "Remove hesitation sounds (eh, eh-eh, um, mm)"
    set_language("system")


def test_saving_manual_language_applies_immediately(config, qapp):
    set_language("system")
    dialog = SettingsDialog(config)
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ru"))

    dialog._save()

    assert config.get("language") == "ru"
    assert current_language() == "ru"
    set_language("system")


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


def test_saving_history_persistence_option_persists(config, qapp):
    dialog = SettingsDialog(config)
    dialog.history_persistent.setChecked(True)

    dialog._save()

    assert config.get("history_persistent") is True


def test_saving_remove_fillers_option_persists(config, qapp):
    dialog = SettingsDialog(config)
    dialog.remove_fillers.setChecked(True)

    dialog._save()

    assert config.get("remove_fillers") is True


def test_output_suffix_preselects_standard_value(config, qapp):
    config.set("output_suffix", "\n")

    dialog = SettingsDialog(config)

    assert dialog.output_suffix_combo.currentData() == "\n"
    assert not dialog.output_suffix_custom.isEnabled()


def test_saving_custom_output_suffix_persists(config, qapp):
    dialog = SettingsDialog(config)
    dialog.output_suffix_combo.setCurrentIndex(dialog.output_suffix_combo.count() - 1)
    dialog.output_suffix_custom.setText(" → ")

    dialog._save()

    assert config.get("output_suffix") == " → "


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


def test_wake_word_phrase_disabled_until_checkbox_checked(config, qapp):
    dialog = SettingsDialog(config)
    assert not dialog.wake_word_enabled.isChecked()
    assert not dialog.wake_word_phrase.isEnabled()
    assert not dialog.wake_word_silence_seconds.isEnabled()

    dialog.wake_word_enabled.setChecked(True)

    assert dialog.wake_word_phrase.isEnabled()
    assert dialog.wake_word_silence_seconds.isEnabled()


def test_saving_wake_word_settings_persists(config, qapp, monkeypatch):
    monkeypatch.setattr(settings_dialog_mod, "vosk_importable", lambda: (True, ""))
    dialog = SettingsDialog(config)
    dialog.wake_word_enabled.setChecked(True)
    dialog.wake_word_phrase.setText("привет корвойс")
    dialog.wake_word_silence_seconds.setValue(2.3)

    dialog._save()

    assert config.get("wake_word_enabled") is True
    assert config.get("wake_word_phrase") == "привет корвойс"
    assert config.get("wake_word_silence_seconds") == pytest.approx(2.3)


def test_saving_wake_word_enabled_without_phrase_warns_but_saves(config, qapp, monkeypatch):
    dialog = SettingsDialog(config)
    dialog.wake_word_enabled.setChecked(True)
    warned = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: warned.append(True))

    dialog._save()

    assert warned == [True]
    assert config.get("wake_word_enabled") is True
    assert config.get("wake_word_phrase") == ""


def test_wake_word_status_label_reports_vosk_unavailable(config, qapp, monkeypatch):
    set_language("en")
    monkeypatch.setattr(
        settings_dialog_mod, "vosk_importable", lambda: (False, "vosk not installed")
    )

    dialog = SettingsDialog(config)

    assert "vosk not installed" in dialog.wake_word_status.text()
    set_language("system")


def test_wake_word_status_label_reports_model_not_downloaded_yet(config, qapp, monkeypatch):
    set_language("en")
    monkeypatch.setattr(settings_dialog_mod, "vosk_importable", lambda: (True, ""))
    monkeypatch.setattr(settings_dialog_mod, "model_present", lambda: False)

    dialog = SettingsDialog(config)

    assert "downloaded yet" in dialog.wake_word_status.text()
    set_language("system")


def test_wake_word_status_label_reports_model_found(config, qapp, monkeypatch):
    set_language("en")
    monkeypatch.setattr(settings_dialog_mod, "vosk_importable", lambda: (True, ""))
    monkeypatch.setattr(settings_dialog_mod, "model_present", lambda: True)

    dialog = SettingsDialog(config)

    assert dialog.wake_word_status.text() == "Wake-word model found."
    set_language("system")


def test_clipboard_hide_history_defaults_to_temporary(config, qapp):
    dialog = SettingsDialog(config)

    assert dialog.clipboard_hide_combo.currentData() == "temporary"


def test_saving_clipboard_hide_history_persists(config, qapp):
    dialog = SettingsDialog(config)
    dialog.clipboard_hide_combo.setCurrentIndex(dialog.clipboard_hide_combo.findData("all"))

    dialog._save()

    assert config.get("clipboard_hide_history") == "all"


def test_english_notes_show_text_not_ids(config, qapp):
    set_language("en")
    try:
        dialog = SettingsDialog(config)
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        tooltips = [dialog.output_autotype.toolTip(), dialog.chunk_seconds.toolTip(),
                    dialog.clipboard_hide_combo.toolTip(),
                    dialog.wake_word_silence_seconds.toolTip()]
    finally:
        set_language("system")

    ids = {"X11 hotkey note", "GigaAM model note", "GigaAM chunk note",
           "Autotype requirements", "Clipboard history note", "Wake word silence note"}
    assert not ids & set(texts)
    assert not ids & set(tooltips)
    assert any("GlobalShortcuts" in text for text in texts)


def test_autostart_file_follows_xdg_config_home(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = importlib.reload(settings_dialog_mod)
    try:
        assert module.AUTOSTART_FILE == tmp_path / "xdg" / "autostart" / "korvoice.desktop"
    finally:
        monkeypatch.delenv("XDG_CONFIG_HOME")
        importlib.reload(settings_dialog_mod)
