import socket
import uuid
from typing import Any, cast

import pytest
from PySide6.QtNetwork import QLocalServer

import korvoice.app as app_mod
from korvoice.app import KorvoiceApp, args_to_command, build_arg_parser


def _parse(argv):
    return build_arg_parser().parse_args(argv)


def test_forced_tray_refresh_resends_icon_without_hiding(config, monkeypatch):
    icons = []
    callbacks = []

    class FakeTray:
        def setIcon(self, icon):
            icons.append(icon)

        def setToolTip(self, _text):
            pass

    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    app.tray = FakeTray()
    app._autotype_note = ""
    icon = object()
    monkeypatch.setattr(app_mod.theme, "make_tray_icon", lambda *args, **kwargs: icon)
    monkeypatch.setattr(app_mod.theme, "tray_icon_color", lambda _setting: None)
    monkeypatch.setattr(
        app_mod.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )

    app._update_tray_visuals(force_refresh=True)

    assert icons == [icon]
    assert len(callbacks) == 1
    callbacks[0]()
    assert icons == [icon, icon]


def test_delayed_tray_refresh_does_not_overwrite_new_state(config, monkeypatch):
    icons = []
    callbacks = []

    class FakeTray:
        def setIcon(self, icon):
            icons.append(icon)

        def setToolTip(self, _text):
            pass

    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    app.tray = FakeTray()
    app._autotype_note = ""
    monkeypatch.setattr(app_mod.theme, "make_tray_icon", lambda *args, **kwargs: object())
    monkeypatch.setattr(app_mod.theme, "tray_icon_color", lambda _setting: None)
    monkeypatch.setattr(
        app_mod.QTimer,
        "singleShot",
        staticmethod(lambda _delay, callback: callbacks.append(callback)),
    )

    app._update_tray_visuals(force_refresh=True)
    app.state = "recording"
    callbacks[0]()

    assert len(icons) == 1


def test_default_is_daemon():
    assert args_to_command(_parse([])) == {"action": "daemon"}


def test_settings_flag():
    assert args_to_command(_parse(["--settings"])) == {"action": "settings"}


def test_history_flag():
    assert args_to_command(_parse(["--history"])) == {"action": "history"}


def test_quit_flag():
    assert args_to_command(_parse(["--quit"])) == {"action": "quit"}


def test_quit_takes_priority_over_settings():
    assert args_to_command(_parse(["--quit", "--settings"])) == {"action": "quit"}


@pytest.fixture
def socket_name(monkeypatch):
    name = f"korvoice-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(app_mod, "SOCKET_NAME", name)
    yield name
    QLocalServer.removeServer(name)


def test_try_send_to_running_reports_no_instance(socket_name, qapp):
    assert app_mod.try_send_to_running({"action": "noop"}) == "none"


def test_listen_exclusively_does_not_displace_a_live_instance(socket_name, qapp):
    owner = QLocalServer()
    assert owner.listen(socket_name)

    with pytest.raises(RuntimeError, match="already running"):
        app_mod._listen_exclusively(QLocalServer())

    assert owner.isListening()
    owner.close()


def test_listen_exclusively_replaces_a_stale_socket_file(socket_name, qapp):
    probe = QLocalServer()
    assert probe.listen(socket_name)
    path = probe.fullServerName()
    probe.close()
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(path)
    stale.close()  # the file stays behind, nobody listens on it

    server = QLocalServer()
    app_mod._listen_exclusively(server)

    assert server.isListening()
    server.close()
