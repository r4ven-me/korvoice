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
