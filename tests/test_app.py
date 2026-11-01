from typing import Any, cast

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
