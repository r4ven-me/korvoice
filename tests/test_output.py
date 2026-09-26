import shutil

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from korvoice.output import OutputDispatcher, remove_fillers


def test_remove_fillers_cleans_common_hesitation_variants():
    assert remove_fillers("Я хотел, э-э, проверить это.") == "Я хотел проверить это."
    assert remove_fillers("Эм, это ээ хороший результат") == "это хороший результат"
    assert remove_fillers("Ну, м-м, возможно") == "Ну возможно"


def test_remove_fillers_does_not_change_parts_of_words():
    text = "Это поэма про Эмму и ММА."
    assert remove_fillers(text) == text


def test_autotype_command_x11_uses_xdotool(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "xdotool" else None
    )
    dispatcher = OutputDispatcher(config)

    command = dispatcher._autotype_command("привет")

    assert command == ["/usr/bin/xdotool", "key", "--clearmodifiers", "ctrl+v"]


def test_autotype_command_x11_missing_xdotool_emits_unavailable(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    dispatcher = OutputDispatcher(config)
    messages = []
    dispatcher.autotype_unavailable.connect(messages.append)

    command = dispatcher._autotype_command("hello")

    assert command is None
    assert len(messages) == 1
    assert "xdotool" in messages[0]


def test_autotype_command_wayland_uses_ydotool(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "ydotool" else None
    )
    dispatcher = OutputDispatcher(config)

    command = dispatcher._autotype_command("hello")

    assert command == ["/usr/bin/ydotool", "type", "--key-delay", "3", "--", "hello"]


def test_autotype_command_wayland_missing_ydotool_emits_unavailable(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    dispatcher = OutputDispatcher(config)
    messages = []
    dispatcher.autotype_unavailable.connect(messages.append)

    command = dispatcher._autotype_command("hello")

    assert command is None
    assert len(messages) == 1
    assert "ydotool" in messages[0]


def test_dispatch_clipboard_only(config, qapp):
    config.set("output_clipboard", True)
    config.set("output_autotype", False)
    config.set("output_window", False)
    dispatcher = OutputDispatcher(config)

    dispatcher.dispatch("test text")

    assert QGuiApplication.clipboard().text() == "test text"


def test_unavailable_x11_autotype_does_not_change_clipboard(config, qapp, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    config.set("output_clipboard", False)
    dispatcher = OutputDispatcher(config)
    monkeypatch.setattr(dispatcher, "_autotype_command", lambda _text: None)
    QGuiApplication.clipboard().setText("previous")

    dispatcher._autotype("recognized")

    assert QGuiApplication.clipboard().text() == "previous"


def test_autotype_restores_all_previous_clipboard_formats(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    original.setHtml("<b>previous</b>")
    dispatcher._temporary_clipboard_original = dispatcher._clone_mime_data(original)
    dispatcher._clipboard_generation = 1
    QGuiApplication.clipboard().setText("recognized")

    dispatcher._restore_clipboard("recognized", 1)

    restored = QGuiApplication.clipboard().mimeData()
    assert restored.text() == "previous"
    assert restored.html() == "<b>previous</b>"


def test_autotype_does_not_overwrite_new_user_clipboard_text(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    dispatcher._temporary_clipboard_original = original
    dispatcher._clipboard_generation = 1
    QGuiApplication.clipboard().setText("copied by user")

    dispatcher._restore_clipboard("recognized", 1)

    assert QGuiApplication.clipboard().text() == "copied by user"


def test_stale_autotype_operation_cannot_restore_clipboard(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    dispatcher._temporary_clipboard_original = original
    dispatcher._clipboard_generation = 2
    QGuiApplication.clipboard().setText("newer autotype")

    dispatcher._restore_clipboard("older autotype", 1)

    assert QGuiApplication.clipboard().text() == "newer autotype"


def test_dispatch_removes_fillers_before_suffix(config, qapp):
    config.set("remove_fillers", True)
    config.set("output_suffix", " ")
    config.set("output_clipboard", True)
    config.set("output_autotype", False)
    config.set("output_window", False)
    dispatcher = OutputDispatcher(config)

    dispatcher.dispatch("Проверяю, э-э, результат")

    assert QGuiApplication.clipboard().text() == "Проверяю результат "


def test_dispatch_appends_configured_suffix_to_every_sink(config, qapp, monkeypatch):
    config.set("output_suffix", "\n")
    config.set("output_clipboard", True)
    config.set("output_autotype", True)
    config.set("output_window", True)
    dispatcher = OutputDispatcher(config)
    autotyped = []
    delivered = []
    monkeypatch.setattr(dispatcher, "_autotype", autotyped.append)
    dispatcher.delivered.connect(delivered.append)

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized\n"
    assert autotyped == ["recognized\n"]
    assert delivered == ["recognized\n"]


def test_dispatch_window_only_emits_delivered(config, qapp):
    config.set("output_clipboard", False)
    config.set("output_autotype", False)
    config.set("output_window", True)
    dispatcher = OutputDispatcher(config)
    delivered = []
    dispatcher.delivered.connect(delivered.append)

    dispatcher.dispatch("test text")

    assert delivered == ["test text"]


def test_dispatch_empty_text_is_noop(config, qapp):
    config.set("output_clipboard", True)
    dispatcher = OutputDispatcher(config)
    QGuiApplication.clipboard().setText("unchanged")

    dispatcher.dispatch("")

    assert QGuiApplication.clipboard().text() == "unchanged"
