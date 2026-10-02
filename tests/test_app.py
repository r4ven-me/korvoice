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


def test_start_recording_stops_wake_word_listening_first(config):
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    calls = []

    class FakeWakeWord:
        def stop_listening(self):
            calls.append("stop_listening")

    class FakeRecorder:
        used_default_fallback = False

        def start(self, on_chunk=None):
            calls.append("recorder_start")

    app.wake_word = FakeWakeWord()
    app.recorder = FakeRecorder()
    app._wake_word_silence_watcher = None
    app._resolve_input_device = lambda: None
    app._update_tray_visuals = lambda: None

    app._start_recording()

    assert calls == ["stop_listening", "recorder_start"]
    assert app.state == "recording"


def test_start_recording_auto_stop_wires_silence_watcher(config):
    config.set("wake_word_silence_seconds", 2.0)
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    calls = []

    class FakeWakeWord:
        def stop_listening(self):
            pass

    class FakeRecorder:
        used_default_fallback = False
        on_chunk = "unset"
        samplerate = 48000

        def start(self, on_chunk=None):
            self.on_chunk = on_chunk
            calls.append("recorder_start")

    class FakeWatcher:
        reset_args = None

        def reset(self, samplerate, required_silence_seconds):
            self.reset_args = (samplerate, required_silence_seconds)
            calls.append("watcher_reset")

        def feed(self, chunk):
            pass

    recorder = FakeRecorder()
    watcher = FakeWatcher()
    app.wake_word = FakeWakeWord()
    app.recorder = recorder
    app._wake_word_silence_watcher = watcher
    app._resolve_input_device = lambda: None
    app._update_tray_visuals = lambda: None

    app._start_recording(auto_stop=True)

    # reset() must come after recorder.start() — only then is
    # recorder.samplerate the real, resolved rate for this session.
    assert calls == ["recorder_start", "watcher_reset"]
    assert watcher.reset_args == (48000, 2.0)
    assert recorder.on_chunk == watcher.feed


def test_maybe_start_wake_word_listening_starts_when_idle_and_enabled(config):
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    config.set("wake_word_enabled", True)
    calls = []

    class FakeWakeWord:
        def start_listening(self):
            calls.append("start_listening")

    app.wake_word = FakeWakeWord()

    app._maybe_start_wake_word_listening()

    assert calls == ["start_listening"]


def test_maybe_start_wake_word_listening_noop_when_disabled(config):
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "idle"
    config.set("wake_word_enabled", False)
    calls = []

    class FakeWakeWord:
        def start_listening(self):
            calls.append("start_listening")

    app.wake_word = FakeWakeWord()

    app._maybe_start_wake_word_listening()

    assert calls == []


def test_maybe_start_wake_word_listening_noop_when_not_idle(config):
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app.state = "recording"
    config.set("wake_word_enabled", True)
    calls = []

    class FakeWakeWord:
        def start_listening(self):
            calls.append("start_listening")

    app.wake_word = FakeWakeWord()

    app._maybe_start_wake_word_listening()

    assert calls == []


def test_wake_word_detected_triggers_start_recording_with_auto_stop(config, monkeypatch):
    config.set("wake_word_sound_enabled", False)
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    calls = []
    app._start_recording = lambda auto_stop=False: calls.append(auto_stop)
    sound_calls = []
    monkeypatch.setattr(app_mod.sound, "play_wake_word_started", lambda: sound_calls.append(True))

    app._on_wake_word_detected()

    assert calls == [True]
    assert sound_calls == []  # sound disabled


def test_wake_word_detected_plays_sound_when_enabled(config, monkeypatch):
    config.set("wake_word_sound_enabled", True)
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app._start_recording = lambda auto_stop=False: None
    sound_calls = []
    monkeypatch.setattr(app_mod.sound, "play_wake_word_started", lambda: sound_calls.append(True))

    app._on_wake_word_detected()

    assert sound_calls == [True]


def test_wake_word_silence_timeout_stops_recording(config, monkeypatch):
    config.set("wake_word_sound_enabled", False)
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    calls = []
    app._stop_recording = lambda: calls.append(True)
    sound_calls = []
    monkeypatch.setattr(app_mod.sound, "play_wake_word_stopped", lambda: sound_calls.append(True))

    app._on_wake_word_silence_timeout()

    assert calls == [True]
    assert sound_calls == []  # sound disabled


def test_wake_word_silence_timeout_plays_sound_when_enabled(config, monkeypatch):
    config.set("wake_word_sound_enabled", True)
    app = cast(Any, KorvoiceApp.__new__(KorvoiceApp))
    app.config = config
    app._stop_recording = lambda: None
    sound_calls = []
    monkeypatch.setattr(app_mod.sound, "play_wake_word_stopped", lambda: sound_calls.append(True))

    app._on_wake_word_silence_timeout()

    assert sound_calls == [True]


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
