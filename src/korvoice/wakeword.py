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
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QThread, Signal

from .audio import SAMPLE_RATE, resolve_samplerate
from .config import Config

log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
DEFAULT_MODEL_DIR = DATA_DIR / "korvoice" / "vosk-model-small-ru"
MODEL_DOWNLOAD_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"

_BLOCK_SECONDS = 0.05  # read granularity while listening — lower = quicker
                       # to notice a finished phrase, at the cost of more
                       # (still cheap) AcceptWaveform calls per second


def _normalize(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def vosk_importable() -> tuple[bool, str]:
    """(ok, reason) — whether the `vosk` package itself is importable.
    Unlike a missing model directory, this can't be fixed automatically
    from inside the app — needs `pipx inject korvoice vosk` (see README)."""
    try:
        import vosk  # noqa: F401
    except ImportError as exc:
        return False, f"vosk not installed: {exc}"
    return True, ""


def model_present() -> bool:
    """Whether the wake-word model directory already exists. False is the
    normal, expected state before the feature's first use — the model
    downloads automatically on demand, see _download_and_extract_model."""
    return DEFAULT_MODEL_DIR.is_dir()


def _download_and_extract_model(model_dir: Path) -> None:
    """Downloads and extracts the wake-word model into place at model_dir.
    Raises on any failure (network error, corrupt zip, unexpected archive
    layout) — the caller (_VoskModelLoadWorker.run()) is responsible for
    catching and reporting via its `failed` signal.

    Downloads/extracts under a temp sibling of model_dir so the final move
    into place is a same-filesystem, atomic os.replace() — same principle
    as Config.save()'s temp-file-then-replace. Assumes model_dir does not
    already exist (only called when model_present() is False); os.replace()
    onto a non-empty existing directory would raise, which is fine since
    that's not a supported call pattern here."""
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=model_dir.parent, prefix=".vosk-download-") as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / "model.zip"
        response = urllib.request.urlopen(MODEL_DOWNLOAD_URL, timeout=30)
        with open(archive_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)

        extract_dir = tmp_path / "extracted"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)

        top_level = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(top_level) != 1:
            raise RuntimeError(
                f"expected exactly one top-level directory in the model "
                f"archive, found {len(top_level)}"
            )
        os.replace(top_level[0], model_dir)


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
    status = Signal(str)  # "downloading" | "loading" — non-terminal, informational only

    def __init__(self, model_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._model_dir = model_dir

    def run(self) -> None:
        if not self._model_dir.is_dir():
            self.status.emit("downloading")
            try:
                _download_and_extract_model(self._model_dir)
            except Exception as exc:  # noqa: BLE001 — report, don't crash the app
                log.exception("failed to download wake-word model to %s", self._model_dir)
                self.failed.emit(f"failed to download the wake-word model: {exc}")
                return
        self.status.emit("loading")
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
                    log.debug("vosk finalized recognition: %r", text)
                    if text == self._phrase:
                        self.detected.emit()
                        return


class WakeWordDetector(QObject):
    """Mirrors asr.Engine's and hotkeys.GlobalHotkeys's conventions: a
    background QThread does the work, a Qt signal reports back to the main
    thread (Qt auto-queues delivery across threads)."""

    detected = Signal()
    # "" | "downloading" | "loading" | "ready" | "listening" |
    # "error: <msg>" | "unavailable: <msg>"
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
        self._start_load()

    def _start_load(self) -> None:
        worker = _VoskModelLoadWorker(DEFAULT_MODEL_DIR, self)
        worker.loaded.connect(self._on_loaded)
        worker.failed.connect(self._on_load_failed)
        worker.status.connect(self.status_changed)
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
    mechanism already relied on for GlobalHotkeys.activated).

    Tracks elapsed seconds, not chunk counts: sounddevice.InputStream's
    buffer size isn't fixed (no explicit blocksize= is passed when opening
    it), so a fixed number of chunks can be a wildly different amount of
    real time depending on what PortAudio picks — confirmed live as the
    cause of auto-stop firing after well under a second of actual
    silence."""

    silence_detected = Signal()

    def __init__(self, threshold: float = 0.015, min_speech_seconds: float = 0.3,
                 required_silence_seconds: float = 1.2, samplerate: int = SAMPLE_RATE,
                 parent=None) -> None:
        super().__init__(parent)
        self._threshold = threshold
        self._min_speech_seconds = min_speech_seconds
        self._required_silence_seconds = required_silence_seconds
        self._samplerate = samplerate
        self._speech_seconds = 0.0
        self._low_seconds = 0.0
        self._done = False

    def reset(self, samplerate: int, required_silence_seconds: float) -> None:
        """Called once per wake-word-triggered recording — after
        Recorder.start() has resolved this session's real device sample
        rate, not before (feed() needs the current rate to convert chunk
        sizes to seconds correctly). required_silence_seconds is read from
        config at this point, so a Settings change takes effect on the
        very next wake-word recording."""
        self._samplerate = samplerate
        self._required_silence_seconds = required_silence_seconds
        self._speech_seconds = 0.0
        self._low_seconds = 0.0
        self._done = False

    def feed(self, chunk: np.ndarray) -> None:
        if self._done or chunk.size == 0:
            return
        duration = chunk.size / self._samplerate
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        if rms >= self._threshold:
            self._speech_seconds += duration
            self._low_seconds = 0.0
            return
        if self._speech_seconds < self._min_speech_seconds:
            return
        self._low_seconds += duration
        if self._low_seconds >= self._required_silence_seconds:
            self._done = True
            self.silence_detected.emit()
