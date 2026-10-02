"""Optional wake-word ("kodovoe slovo") activation: continuously listens to
the microphone for a user-configured Russian phrase via Vosk's
grammar-constrained offline recognizer, and tells app.py when it hears it —
wired to the same _start_recording() path as the hotkey/tray button.

Vosk's grammar mode (KaldiRecognizer(model, samplerate, grammar_json)) is a
closed-vocabulary keyword-spotting technique, not a dedicated acoustic
wake-word model like Porcupine/openWakeWord: it decodes against just the
configured phrase plus "[unk]", so expect more false accepts/rejects than a
purpose-built KWS engine. It is the only practical fully-offline route to an
arbitrary Russian phrase (see README's privacy/tradeoff note) — both
alternatives above are English-first and either need cloud infra or
English-centric training tooling for a custom phrase.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QThread, Signal

from .audio import resolve_samplerate
from .config import Config

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
DEFAULT_MODEL_DIR = DATA_DIR / "korvoice" / "vosk-model-small-ru"

_BLOCK_SECONDS = 0.2  # read granularity while listening


def _normalize(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def availability() -> tuple[bool, str]:
    """(ok, reason) — vosk importable and the model directory present.
    Used by the Settings status label and --check, without requiring a
    model load. Module-level (not model/config dependent) so it can be
    called cheaply from anywhere without constructing a WakeWordDetector."""
    if not DEFAULT_MODEL_DIR.is_dir():
        return False, f"model not found at {DEFAULT_MODEL_DIR}"
    try:
        import vosk  # noqa: F401
    except ImportError as exc:
        return False, f"vosk not installed: {exc}"
    return True, ""


def _resolve_input_device(config: Config) -> str | int | None:
    raw = str(config.get("input_device"))
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class _VoskModelLoadWorker(QThread):
    loaded = Signal(object)  # vosk.Model
    failed = Signal(str)

    def __init__(self, model_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._model_dir = model_dir

    def run(self) -> None:
        if not self._model_dir.is_dir():
            self.failed.emit(
                f"wake-word model not found at {self._model_dir} "
                "(download vosk-model-small-ru, see README)"
            )
            return
        try:
            import vosk
        except ImportError as exc:
            self.failed.emit(
                f"vosk is not installed; install it with `pipx inject korvoice vosk`: {exc}"
            )
            return
        try:
            vosk.SetLogLevel(-1)  # vosk logs straight to stderr otherwise
            model = vosk.Model(str(self._model_dir))
        except Exception as exc:  # noqa: BLE001 — report, don't crash the app
            log.exception("failed to load wake-word model at %s", self._model_dir)
            self.failed.emit(str(exc))
            return
        self.loaded.emit(model)


class _VoskListenWorker(QThread):
    """Owns its own sounddevice.InputStream — a separate stream object from
    Recorder's, never open at the same time (see app.py's state machine)."""

    detected = Signal()
    failed = Signal(str)

    def __init__(self, model, device: str | int | None, phrase: str, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._device = device
        self._phrase = phrase
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        self.wait(2000)

    def run(self) -> None:
        import vosk

        samplerate = resolve_samplerate(self._device)
        grammar = json.dumps([self._phrase, "[unk]"], ensure_ascii=False)
        try:
            recognizer = vosk.KaldiRecognizer(self._model, samplerate, grammar)
        except Exception as exc:  # noqa: BLE001 — report, don't crash the app
            self.failed.emit(str(exc))
            return
        block_frames = max(1, int(samplerate * _BLOCK_SECONDS))

        try:
            stream = sd.InputStream(
                samplerate=samplerate, channels=1, dtype="int16", device=self._device,
            )
        except sd.PortAudioError as exc:
            self.failed.emit(str(exc))
            return

        with stream:
            while not self._stop:
                try:
                    data, _overflowed = stream.read(block_frames)
                except sd.PortAudioError as exc:
                    self.failed.emit(str(exc))
                    return
                if recognizer.AcceptWaveform(data.tobytes()):
                    text = _normalize(json.loads(recognizer.Result()).get("text", ""))
                    if text == self._phrase:
                        self.detected.emit()
                        return


class WakeWordDetector(QObject):
    """Mirrors asr.Engine's and hotkeys.GlobalHotkeys's conventions: a
    background QThread does the work, a Qt signal reports back to the main
    thread (Qt auto-queues delivery across threads)."""

    detected = Signal()
    # "" | "loading" | "ready" | "listening" | "error: <msg>" | "unavailable: <msg>"
    status_changed = Signal(str)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._model = None
        self._load_worker: _VoskModelLoadWorker | None = None
        self._listen_worker: _VoskListenWorker | None = None

    def is_listening(self) -> bool:
        return self._listen_worker is not None

    def preload(self) -> None:
        """Loads the configured wake-word model in the background, unless
        the feature is disabled or it is already loaded/loading."""
        if not self.config.get("wake_word_enabled"):
            return
        if self._model is not None or self._load_worker is not None:
            return
        self.status_changed.emit("loading")
        self._start_load()

    def _start_load(self) -> None:
        worker = _VoskModelLoadWorker(DEFAULT_MODEL_DIR, self)
        worker.loaded.connect(self._on_loaded)
        worker.failed.connect(self._on_load_failed)
        worker.finished.connect(worker.deleteLater)
        self._load_worker = worker
        worker.start()

    def _on_loaded(self, model) -> None:
        self._model = model
        self._load_worker = None
        self.status_changed.emit("ready")

    def _on_load_failed(self, message: str) -> None:
        self._load_worker = None
        self.status_changed.emit(f"unavailable: {message}")

    def start_listening(self) -> None:
        """No-op if already listening, disabled, the model isn't loaded
        yet, or no phrase is configured — safe to call redundantly."""
        if self._listen_worker is not None:
            return
        if not self.config.get("wake_word_enabled") or self._model is None:
            return
        phrase = _normalize(str(self.config.get("wake_word_phrase")))
        if not phrase:
            return
        self.status_changed.emit("listening")
        self._start_listen(phrase)

    def _start_listen(self, phrase: str) -> None:
        device = _resolve_input_device(self.config)
        worker = _VoskListenWorker(self._model, device, phrase, self)
        worker.detected.connect(self._on_detected)
        worker.failed.connect(self._on_listen_failed)
        worker.finished.connect(worker.deleteLater)
        self._listen_worker = worker
        worker.start()

    def _on_detected(self) -> None:
        self._listen_worker = None
        self.detected.emit()

    def _on_listen_failed(self, message: str) -> None:
        self._listen_worker = None
        self.status_changed.emit(f"error: {message}")

    def stop_listening(self) -> None:
        if self._listen_worker is None:
            return
        worker, self._listen_worker = self._listen_worker, None
        worker.stop()


class WakeWordSilenceWatcher(QObject):
    """Auto-stops a wake-word-triggered recording after a trailing pause —
    there is no hotkey "release" event for this trigger. Feeds on
    Recorder's on_chunk hook, which runs on sounddevice's own callback
    thread; this object is constructed on the main thread, so Qt
    auto-queues delivery of `silence_detected` there (the same cross-thread
    mechanism already relied on for GlobalHotkeys.activated)."""

    silence_detected = Signal()

    def __init__(self, threshold: float = 0.015, min_speech_chunks: int = 3,
                 required_low_chunks: int = 12, parent=None) -> None:
        super().__init__(parent)
        self._threshold = threshold
        self._min_speech_chunks = min_speech_chunks
        self._required_low_chunks = required_low_chunks
        self._speech_seen = 0
        self._low_run = 0
        self._done = False

    def reset(self) -> None:
        self._speech_seen = 0
        self._low_run = 0
        self._done = False

    def feed(self, chunk: np.ndarray) -> None:
        if self._done or chunk.size == 0:
            return
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        if rms >= self._threshold:
            self._speech_seen += 1
            self._low_run = 0
            return
        if self._speech_seen < self._min_speech_chunks:
            return
        self._low_run += 1
        if self._low_run >= self._required_low_chunks:
            self._done = True
            self.silence_detected.emit()
