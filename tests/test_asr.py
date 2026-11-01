import numpy as np

import korvoice.asr as asr_mod
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


class _FakeModel:
    def __init__(self, results):
        self._results = list(results)

    def transcribe(self, _path):
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _WithText:
    def __init__(self, text):
        self.text = text


def _run_transcribe(model, monkeypatch, chunks=1):
    monkeypatch.setattr(
        asr_mod, "split_on_silence", lambda audio, _max: [audio] * chunks
    )
    worker = asr_mod._TranscribeWorker(model, np.zeros(16000, dtype=np.float32), 20.0)
    done, failed = [], []
    worker.finished_ok.connect(done.append)
    worker.failed.connect(failed.append)
    worker.run()  # synchronously: the thread itself is not under test
    return done, failed


def test_transcribe_worker_joins_chunks_in_order(monkeypatch):
    model = _FakeModel([_WithText(" first "), "  ", _WithText("second")])

    done, failed = _run_transcribe(model, monkeypatch, chunks=3)

    assert done == ["first second"]
    assert failed == []


def test_transcribe_worker_accepts_plain_string_results(monkeypatch):
    done, _ = _run_transcribe(_FakeModel(["legacy text"]), monkeypatch)

    assert done == ["legacy text"]


def test_transcribe_worker_empty_result_is_empty_string(monkeypatch):
    done, failed = _run_transcribe(_FakeModel([_WithText("")]), monkeypatch)

    assert done == [""]
    assert failed == []


def test_transcribe_worker_reports_model_exceptions(monkeypatch):
    done, failed = _run_transcribe(_FakeModel([RuntimeError("boom")]), monkeypatch)

    assert done == []
    assert failed == ["boom"]


def test_load_worker_reports_load_failure(monkeypatch):
    import sys
    import types

    def fail(*_args, **_kwargs):
        raise RuntimeError("no weights")

    monkeypatch.setitem(sys.modules, "gigaam", types.SimpleNamespace(load_model=fail))
    monkeypatch.setattr(asr_mod, "_configure_torch_threads", lambda: None)
    worker = asr_mod._ModelLoadWorker("v3_e2e_ctc", "auto")
    failed, loaded = [], []
    worker.failed.connect(failed.append)
    worker.loaded.connect(loaded.append)

    worker.run()

    assert failed == ["no weights"]
    assert loaded == []


def test_load_failure_clears_pending_audio_and_reports_error(config, qapp):
    engine = Engine(config)
    engine._pending_audio = np.zeros(MIN_TRANSCRIBE_SAMPLES, dtype=np.float32)
    errors, statuses = [], []
    engine.error.connect(errors.append)
    engine.status_changed.connect(statuses.append)

    engine._on_load_failed("broken")

    assert engine._pending_audio is None
    assert errors == ["broken"]
    assert statuses == ["error: broken"]


def test_shutdown_stops_accepting_work_and_drops_pending_audio(config, qapp, monkeypatch):
    engine = Engine(config)
    loads = _recording_loads(engine, monkeypatch)
    started = []
    monkeypatch.setattr(engine, "_start_transcribe", started.append)
    engine._pending_audio = np.zeros(MIN_TRANSCRIBE_SAMPLES, dtype=np.float32)

    engine.shutdown()
    engine.preload()
    engine.transcribe(np.zeros(MIN_TRANSCRIBE_SAMPLES, dtype=np.float32))
    engine._on_loaded(object(), ("v3_e2e_ctc", "auto"))

    assert loads == []
    assert started == []
    assert engine._pending_audio is None
    assert engine._model is None


def test_shutdown_waits_for_running_workers(config, qapp):
    class FakeWorker:
        def __init__(self, finishes):
            self.finishes = finishes
            self.waited = None
            self.parent_cleared = False

        def wait(self, timeout):
            self.waited = timeout
            return self.finishes

        def setParent(self, parent):
            self.parent_cleared = parent is None

    engine = Engine(config)
    quick, stuck = FakeWorker(True), FakeWorker(False)
    engine._workers = [quick, stuck]

    engine.shutdown(timeout_ms=50)

    assert quick.waited == 50 and not quick.parent_cleared
    assert stuck.parent_cleared  # abandoned, kept alive instead of destroyed
    assert stuck in asr_mod._abandoned_workers
    asr_mod._abandoned_workers.remove(stuck)
    assert engine._workers == []
