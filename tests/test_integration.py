"""The main user flow end to end: hotkey -> recorder -> ASR -> output, with a
fake microphone and a fake model but the real app, Qt signals and worker
threads."""

import threading
import uuid

import numpy as np
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

import korvoice.app as app_mod
from korvoice.audio import SAMPLE_RATE


class FakeRecorder:
    samplerate = SAMPLE_RATE
    used_default_fallback = False

    def __init__(self, device=None):
        self.device = device

    def start(self):
        pass

    def stop(self):
        return np.full(SAMPLE_RATE, 0.1, dtype=np.float32)  # one second


class FakeHotkeys(QObject):
    activated = Signal(str, bool)
    backend = "fake"
    error = ""

    def apply(self, _bindings):
        pass

    def stop(self):
        pass


class FakeModel:
    def __init__(self, gate: threading.Event | None = None):
        self.gate = gate

    def transcribe(self, _path):
        if self.gate is not None:
            self.gate.wait(5)
        return type("Result", (), {"text": "привет мир"})()


@pytest.fixture
def korvoice(config, qapp, monkeypatch):
    monkeypatch.setattr(app_mod, "SOCKET_NAME", f"korvoice-test-{uuid.uuid4().hex}")
    monkeypatch.setattr(app_mod, "Recorder", FakeRecorder)
    monkeypatch.setattr(app_mod, "GlobalHotkeys", FakeHotkeys)
    monkeypatch.setattr(app_mod.Engine, "preload", lambda self: None)
    config.set("output_clipboard", True)
    config.set("output_autotype", False)
    config.set("output_window", True)
    instance = app_mod.KorvoiceApp(qapp, config)
    instance.engine._model = FakeModel()
    instance.engine._model_key = instance.engine._configured_key()
    yield instance
    instance.engine.shutdown()
    instance.output.shutdown()
    instance.server.close()
    instance.tray.hide()


def _wait_until(predicate, timeout_ms=5000):
    waited = 0
    while not predicate() and waited < timeout_ms:
        QTest.qWait(20)
        waited += 20
    assert predicate()


def test_push_to_talk_flow_delivers_text_and_returns_to_idle(korvoice):
    korvoice.config.set("mode", "push_to_talk")
    delivered = []
    korvoice.output.delivered.connect(delivered.append)

    korvoice.hotkeys.activated.emit("record", True)
    assert korvoice.state == "recording"
    korvoice.hotkeys.activated.emit("record", False)
    assert korvoice.state == "transcribing"
    _wait_until(lambda: korvoice.state == "idle")
    _wait_until(lambda: bool(delivered))

    assert delivered == ["привет мир"]
    assert QGuiApplication.clipboard().text() == "привет мир"


def test_toggle_mode_flow(korvoice):
    korvoice.config.set("mode", "toggle")
    delivered = []
    korvoice.output.delivered.connect(delivered.append)

    korvoice.hotkeys.activated.emit("record", True)
    korvoice.hotkeys.activated.emit("record", False)  # release is ignored
    assert korvoice.state == "recording"
    korvoice.hotkeys.activated.emit("record", True)
    _wait_until(lambda: bool(delivered))

    assert delivered == ["привет мир"]
    assert korvoice.state == "idle"


def test_quit_during_transcription_waits_for_the_worker(korvoice):
    gate = threading.Event()
    korvoice.engine._model = FakeModel(gate)
    korvoice.hotkeys.activated.emit("record", True)
    korvoice.hotkeys.activated.emit("record", False)
    assert korvoice.state == "transcribing"
    threading.Timer(0.3, gate.set).start()

    korvoice.quit()

    assert korvoice.engine._workers == []
