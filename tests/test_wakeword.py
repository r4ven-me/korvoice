import io
import sys
import types
import zipfile

import numpy as np
import pytest

import korvoice.wakeword as wakeword_mod
from korvoice.wakeword import WakeWordDetector, WakeWordSilenceWatcher

# -- WakeWordDetector ---------------------------------------------------------


def test_preload_noop_when_disabled(config, qapp, monkeypatch):
    config.set("wake_word_enabled", False)
    detector = WakeWordDetector(config)
    started = []
    monkeypatch.setattr(detector, "_start_load", lambda: started.append(True))

    detector.preload()

    assert started == []


def test_preload_starts_load_when_enabled(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    detector = WakeWordDetector(config)
    started = []
    monkeypatch.setattr(detector, "_start_load", lambda: started.append(True))

    detector.preload()

    assert started == [True]


def test_preload_noop_when_already_loading(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    detector = WakeWordDetector(config)
    detector._load_worker = object()
    started = []
    monkeypatch.setattr(detector, "_start_load", lambda: started.append(True))

    detector.preload()

    assert started == []


def test_preload_noop_when_model_already_loaded(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    detector = WakeWordDetector(config)
    detector._model = object()
    started = []
    monkeypatch.setattr(detector, "_start_load", lambda: started.append(True))

    detector.preload()

    assert started == []


def test_on_loaded_sets_model_and_status(config, qapp):
    detector = WakeWordDetector(config)
    statuses = []
    detector.status_changed.connect(statuses.append)
    model = object()

    detector._on_loaded(model)

    assert detector._model is model
    assert detector._load_worker is None
    assert statuses == ["ready"]


def test_on_load_failed_sets_status(config, qapp):
    detector = WakeWordDetector(config)
    statuses = []
    detector.status_changed.connect(statuses.append)

    detector._on_load_failed("boom")

    assert detector._load_worker is None
    assert statuses == ["unavailable: boom"]


def test_start_listening_noop_without_loaded_model(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    config.set("wake_word_phrase", "привет корвойс")
    detector = WakeWordDetector(config)
    started = []
    monkeypatch.setattr(detector, "_start_listen", started.append)

    detector.start_listening()

    assert started == []


def test_start_listening_noop_when_already_listening(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    config.set("wake_word_phrase", "привет корвойс")
    detector = WakeWordDetector(config)
    detector._model = object()
    detector._listen_worker = object()
    started = []
    monkeypatch.setattr(detector, "_start_listen", started.append)

    detector.start_listening()

    assert started == []


def test_start_listening_noop_when_phrase_empty(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    config.set("wake_word_phrase", "   ")
    detector = WakeWordDetector(config)
    detector._model = object()
    started = []
    monkeypatch.setattr(detector, "_start_listen", started.append)

    detector.start_listening()

    assert started == []


def test_start_listening_normalizes_phrase_and_reports_status(config, qapp, monkeypatch):
    config.set("wake_word_enabled", True)
    config.set("wake_word_phrase", "  Привет   Корвойс  ")
    detector = WakeWordDetector(config)
    detector._model = object()
    started = []
    monkeypatch.setattr(detector, "_start_listen", started.append)
    statuses = []
    detector.status_changed.connect(statuses.append)

    detector.start_listening()

    assert started == ["привет корвойс"]
    assert statuses == ["listening"]


def test_detected_forwards_signal_and_clears_listen_worker(config, qapp):
    detector = WakeWordDetector(config)
    detector._listen_worker = object()
    events = []
    detector.detected.connect(lambda: events.append(True))

    detector._on_detected()

    assert detector._listen_worker is None
    assert events == [True]


def test_listen_failed_clears_worker_and_sets_status(config, qapp):
    detector = WakeWordDetector(config)
    detector._listen_worker = object()
    statuses = []
    detector.status_changed.connect(statuses.append)

    detector._on_listen_failed("mic busy")

    assert detector._listen_worker is None
    assert statuses == ["error: mic busy"]


def test_stop_listening_noop_when_not_listening(config, qapp):
    detector = WakeWordDetector(config)
    detector.stop_listening()  # must not raise
    assert detector._listen_worker is None


def test_stop_listening_stops_worker_and_clears_it(config, qapp):
    detector = WakeWordDetector(config)

    class FakeWorker:
        stopped = False

        def stop(self):
            self.stopped = True

    worker = FakeWorker()
    detector._listen_worker = worker

    detector.stop_listening()

    assert worker.stopped is True
    assert detector._listen_worker is None


def test_is_listening_reflects_listen_worker_presence(config, qapp):
    detector = WakeWordDetector(config)
    assert detector.is_listening() is False
    detector._listen_worker = object()
    assert detector.is_listening() is True


# -- vosk_importable() / model_present() --------------------------------------


def test_model_present_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeword_mod, "DEFAULT_MODEL_DIR", tmp_path / "missing")
    assert wakeword_mod.model_present() is False


def test_model_present_true_when_dir_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeword_mod, "DEFAULT_MODEL_DIR", tmp_path)
    assert wakeword_mod.model_present() is True


def test_vosk_importable_reports_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "vosk", None)
    ok, reason = wakeword_mod.vosk_importable()
    assert ok is False
    assert "vosk" in reason


def test_vosk_importable_true_when_module_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "vosk", types.ModuleType("vosk"))
    ok, reason = wakeword_mod.vosk_importable()
    assert ok is True
    assert reason == ""


# -- _download_and_extract_model() ---------------------------------------------


def _build_zip(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buf.getvalue()


def _fake_urlopen(payload: bytes):
    return lambda *_args, **_kwargs: io.BytesIO(payload)


def test_download_and_extract_model_moves_single_top_level_dir_into_place(tmp_path, monkeypatch):
    payload = _build_zip({"vosk-model-small-ru-0.22/README": "dummy model file"})
    monkeypatch.setattr(wakeword_mod.urllib.request, "urlopen", _fake_urlopen(payload))
    model_dir = tmp_path / "vosk-model-small-ru"

    wakeword_mod._download_and_extract_model(model_dir)

    assert model_dir.is_dir()
    assert (model_dir / "README").read_text() == "dummy model file"


def test_download_and_extract_model_rejects_zero_top_level_dirs(tmp_path, monkeypatch):
    payload = _build_zip({"loose_file.txt": "no top-level dir"})
    monkeypatch.setattr(wakeword_mod.urllib.request, "urlopen", _fake_urlopen(payload))

    with pytest.raises(RuntimeError, match="found 0"):
        wakeword_mod._download_and_extract_model(tmp_path / "model")


def test_download_and_extract_model_rejects_multiple_top_level_dirs(tmp_path, monkeypatch):
    payload = _build_zip({"a/file.txt": "x", "b/file.txt": "y"})
    monkeypatch.setattr(wakeword_mod.urllib.request, "urlopen", _fake_urlopen(payload))

    with pytest.raises(RuntimeError, match="found 2"):
        wakeword_mod._download_and_extract_model(tmp_path / "model")


def test_download_and_extract_model_does_not_leave_partial_state_on_bad_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeword_mod.urllib.request, "urlopen", _fake_urlopen(b"not a zip file"))
    model_dir = tmp_path / "model"

    with pytest.raises(zipfile.BadZipFile):
        wakeword_mod._download_and_extract_model(model_dir)

    assert not model_dir.exists()
    assert list(tmp_path.iterdir()) == []


# -- WakeWordSilenceWatcher -----------------------------------------------------


def _loud_chunk(n=320):
    return np.full(n, 0.5, dtype=np.float32)


def _quiet_chunk(n=320):
    return np.zeros(n, dtype=np.float32)


def test_silence_watcher_fires_after_speech_then_enough_quiet_chunks(qapp):
    watcher = WakeWordSilenceWatcher(threshold=0.1, min_speech_chunks=2, required_low_chunks=3)
    events = []
    watcher.silence_detected.connect(lambda: events.append(True))

    for _ in range(2):
        watcher.feed(_loud_chunk())
    for _ in range(2):
        watcher.feed(_quiet_chunk())
    assert events == []  # not enough quiet chunks yet
    watcher.feed(_quiet_chunk())
    assert events == [True]


def test_silence_watcher_does_not_fire_before_minimum_speech_seen(qapp):
    watcher = WakeWordSilenceWatcher(threshold=0.1, min_speech_chunks=3, required_low_chunks=2)
    events = []
    watcher.silence_detected.connect(lambda: events.append(True))

    watcher.feed(_loud_chunk())  # only 1 speech chunk, below min_speech_chunks
    for _ in range(5):
        watcher.feed(_quiet_chunk())

    assert events == []


def test_silence_watcher_fires_only_once(qapp):
    watcher = WakeWordSilenceWatcher(threshold=0.1, min_speech_chunks=1, required_low_chunks=2)
    events = []
    watcher.silence_detected.connect(lambda: events.append(True))

    watcher.feed(_loud_chunk())
    for _ in range(5):
        watcher.feed(_quiet_chunk())

    assert events == [True]


def test_silence_watcher_reset_allows_firing_again(qapp):
    watcher = WakeWordSilenceWatcher(threshold=0.1, min_speech_chunks=1, required_low_chunks=2)
    events = []
    watcher.silence_detected.connect(lambda: events.append(True))
    watcher.feed(_loud_chunk())
    for _ in range(2):
        watcher.feed(_quiet_chunk())
    assert events == [True]

    watcher.reset()
    watcher.feed(_loud_chunk())
    for _ in range(2):
        watcher.feed(_quiet_chunk())

    assert events == [True, True]


def test_silence_watcher_ignores_empty_chunk(qapp):
    watcher = WakeWordSilenceWatcher()
    watcher.feed(np.zeros(0, dtype=np.float32))  # must not raise
