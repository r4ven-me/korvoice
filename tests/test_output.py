import shutil

from PySide6.QtGui import QGuiApplication

from korvoice.output import OutputDispatcher


def test_autotype_command_x11_uses_xdotool(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "xdotool" else None
    )
    dispatcher = OutputDispatcher(config)

    command = dispatcher._autotype_command("привет")

    assert command == [
        "/usr/bin/xdotool", "type", "--clearmodifiers", "--delay", "3", "--", "привет",
    ]


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
