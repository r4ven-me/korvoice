import numpy as np

from korvoice.asr import Engine
from korvoice.audio import MIN_TRANSCRIBE_SAMPLES


def test_engine_ignores_audio_shorter_than_minimum(config, qapp, monkeypatch):
    engine = Engine(config)
    engine._model = object()
    engine._model_key = (str(config.get("model")), str(config.get("device")))
    started = []
    monkeypatch.setattr(engine, "_start_transcribe", started.append)

    engine.transcribe(np.zeros(MIN_TRANSCRIBE_SAMPLES - 1, dtype=np.float32))

    assert started == []


def test_engine_accepts_audio_at_minimum_duration(config, qapp, monkeypatch):
    engine = Engine(config)
    engine._model = object()
    engine._model_key = (str(config.get("model")), str(config.get("device")))
    started = []
    monkeypatch.setattr(engine, "_start_transcribe", started.append)
    audio = np.zeros(MIN_TRANSCRIBE_SAMPLES, dtype=np.float32)

    engine.transcribe(audio)

    assert len(started) == 1
    assert started[0] is audio


def _recording_loads(engine, monkeypatch):
    loads = []

    def fake_start_load(key):
        engine._loading_key = key
        loads.append(key)

    monkeypatch.setattr(engine, "_start_load", fake_start_load)
    return loads


def test_preload_after_model_change_starts_background_load(config, qapp, monkeypatch):
    engine = Engine(config)
    engine._model = object()
    engine._model_key = ("v3_e2e_ctc", "auto")
    loads = _recording_loads(engine, monkeypatch)
    config.set("model", "v3_e2e_rnnt")

    engine.preload()

    assert loads == [("v3_e2e_rnnt", "auto")]


def test_preload_does_nothing_when_model_is_current(config, qapp, monkeypatch):
    engine = Engine(config)
    engine._model = object()
    engine._model_key = engine._configured_key()
    loads = _recording_loads(engine, monkeypatch)

    engine.preload()

    assert loads == []


def test_stale_load_is_replaced_by_configured_model(config, qapp, monkeypatch):
    engine = Engine(config)
    loads = _recording_loads(engine, monkeypatch)
    started = []
    monkeypatch.setattr(engine, "_start_transcribe", started.append)
    engine.preload()
    audio = np.zeros(MIN_TRANSCRIBE_SAMPLES, dtype=np.float32)
    config.set("model", "v3_rnnt")
    engine.transcribe(audio)  # waits for the load already in progress

    engine._on_loaded(object(), loads[0])  # the old model finishes loading

    assert loads == [("v3_e2e_ctc", "auto"), ("v3_rnnt", "auto")]
    assert engine._model is None
    assert started == []

    new_model = object()
    engine._on_loaded(new_model, loads[1])

    assert engine._model is new_model
    assert started == [audio]
