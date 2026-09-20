"""GigaAM speech recognition: lazy model load + chunked transcription.

Both the model load (weights download to ~/.cache/gigaam on first use,
then torch initialisation) and transcription itself run on background
QThreads — neither should block the tray/hotkey event loop.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from .audio import split_on_silence, write_wav
from .config import Config

log = logging.getLogger(__name__)


class _ModelLoadWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, model_name: str, device: str, parent=None) -> None:
        super().__init__(parent)
        self.model_name = model_name
        self.device = device

    def run(self) -> None:
        try:
            import gigaam
        except ImportError as exc:
            self.failed.emit(f"gigaam is not installed: {exc}")
            return
        try:
            device = None if self.device == "auto" else self.device
            model = gigaam.load_model(self.model_name, device=device)
        except Exception as exc:  # noqa: BLE001 — report, don't crash the app
            log.exception("failed to load GigaAM model %s", self.model_name)
            self.failed.emit(str(exc))
            return
        self.loaded.emit(model)


class _TranscribeWorker(QThread):
    """Splits `audio` at safe cut points (see audio.split_on_silence),
    writes each piece to a temp WAV, runs it through the already-loaded
    model, and joins the results with spaces."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, model, audio: np.ndarray, max_seconds: float, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._audio = audio
        self._max_seconds = max_seconds

    def run(self) -> None:
        try:
            chunks = split_on_silence(self._audio, self._max_seconds)
            texts: list[str] = []
            with tempfile.TemporaryDirectory(prefix="korvoice-") as tmp_dir:
                for i, chunk in enumerate(chunks):
                    wav_path = Path(tmp_dir) / f"chunk-{i}.wav"
                    write_wav(wav_path, chunk)
                    # transcribe() returns a TranscriptionResult (.text,
                    # .words), not a plain string — confirmed against the
                    # actually-installed GigaAM (git main, 0.2.0); the
                    # README/PyPI 0.1.0 examples that show a bare string
                    # are out of date.
                    result = self._model.transcribe(str(wav_path))
                    text = str(result.text if hasattr(result, "text") else result)
                    if text.strip():
                        texts.append(text.strip())
            self.finished_ok.emit(" ".join(texts).strip())
        except Exception as exc:  # noqa: BLE001 — report, don't crash the app
            log.exception("transcription failed")
            self.failed.emit(str(exc))


class Engine(QObject):
    """Owns the GigaAM model lifecycle: lazy load on first use, reused for
    every later transcription. Reloads automatically if the configured
    model name or device changes between calls (Settings → Model)."""

    status_changed = Signal(str)   # "" | "loading" | "ready" | "error: <message>"
    result_ready = Signal(str)
    error = Signal(str)

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._model = None
        self._model_key: tuple[str, str] | None = None
        self._load_worker: _ModelLoadWorker | None = None
        self._transcribe_worker: _TranscribeWorker | None = None
        self._pending_audio: np.ndarray | None = None

    def preload(self) -> None:
        """Warms the model in the background right after the daemon
        starts (see app.py's KorvoiceApp.__init__), so the first real
        hotkey press doesn't also have to eat the ~3-5s cold load (torch
        import + weights) on top of recording — confirmed that cost is
        real by timing load_model() directly against the cached weights
        on this project's dev host."""
        model_name = str(self.config.get("model"))
        device = str(self.config.get("device"))
        key = (model_name, device)
        if self._model is not None and self._model_key == key:
            return
        if self._load_worker is not None and self._load_worker.isRunning():
            return
        self._start_load(model_name, device, key)

    def transcribe(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        model_name = str(self.config.get("model"))
        device = str(self.config.get("device"))
        key = (model_name, device)
        if self._model is not None and self._model_key == key:
            self._start_transcribe(audio)
            return

        self._pending_audio = audio
        if self._load_worker is not None and self._load_worker.isRunning():
            return  # preload() (or an earlier transcribe()) already started this same load
        self._start_load(model_name, device, key)

    def _start_load(self, model_name: str, device: str, key: tuple[str, str]) -> None:
        self.status_changed.emit("loading")
        self._load_worker = _ModelLoadWorker(model_name, device)
        self._load_worker.loaded.connect(lambda model: self._on_loaded(model, key))
        self._load_worker.failed.connect(self._on_load_failed)
        self._load_worker.start()

    def _on_loaded(self, model, key: tuple[str, str]) -> None:
        self._model = model
        self._model_key = key
        self.status_changed.emit("ready")
        if self._pending_audio is not None:
            audio, self._pending_audio = self._pending_audio, None
            self._start_transcribe(audio)

    def _on_load_failed(self, message: str) -> None:
        self._pending_audio = None
        self.status_changed.emit(f"error: {message}")
        self.error.emit(message)

    def _start_transcribe(self, audio: np.ndarray) -> None:
        max_seconds = float(self.config.get("chunk_max_seconds"))
        self._transcribe_worker = _TranscribeWorker(self._model, audio, max_seconds)
        self._transcribe_worker.finished_ok.connect(self.result_ready)
        self._transcribe_worker.failed.connect(self.error)
        self._transcribe_worker.start()
