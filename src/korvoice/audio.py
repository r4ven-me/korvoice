"""Microphone capture and silence-aware chunking for GigaAM's 25s cap.

GigaAM.transcribe() (see asr.py) hard-rejects audio longer than ~25
seconds and expects mono 16kHz PCM. Rather than pull in an external VAD
model (pyannote — GigaAM's own answer to this, but heavy and needs a
Hugging Face token, see the project plan) split_on_silence() below does a
much simpler thing: look for a locally quiet moment near each cut point
and cut there instead of mid-word.
"""

from __future__ import annotations

import logging
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # GigaAM's fixed expectation (gigaam.preprocess.SAMPLE_RATE)
_DTYPE = "float32"

log = logging.getLogger(__name__)


class Recorder:
    """Captures mono audio from the given input device between start() and
    stop(), at the device's own native sample rate — a raw ALSA hw: device
    (e.g. a USB mic exposed as "hw:0,0") only supports its own fixed rate
    and raises PaInvalidSampleRate for anything else, confirmed against a
    real USB microphone on this project's dev host. stop() resamples the
    result to GigaAM's required 16kHz, so the recorded-at rate stays this
    class's own concern — callers always get 16kHz back, as before.

    sounddevice runs its callback on its own thread; frames are appended
    to a plain list under a lock and concatenated on stop() — recordings
    here are seconds to low tens of seconds, not long enough for a
    queue/ring-buffer to matter."""

    def __init__(self, device: str | int | None = None) -> None:
        self.device: str | int | None = device or None
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._samplerate = SAMPLE_RATE

    def _resolve_samplerate(self) -> int:
        """The device's own default rate — sd.query_devices()'s `kind`
        parameter only applies when `device` is unset (falls back to the
        system default input device in that case)."""
        try:
            info = (sd.query_devices(self.device) if self.device is not None
                    else sd.query_devices(kind="input"))
            rate = int(info["default_samplerate"])
            return rate if rate > 0 else SAMPLE_RATE
        except (sd.PortAudioError, TypeError, ValueError, KeyError) as exc:
            log.debug("could not resolve device sample rate, using %d: %s", SAMPLE_RATE, exc)
            return SAMPLE_RATE

    def start(self) -> None:
        self._frames = []
        self._samplerate = self._resolve_samplerate()
        self._stream = sd.InputStream(
            samplerate=self._samplerate, channels=1, dtype=_DTYPE,
            device=self.device, callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, _frames, _time_info, status) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        with self._lock:
            self._frames.append(indata[:, 0].copy())

    def stop(self) -> np.ndarray:
        """Stops capture and returns the full recording as float32 in
        [-1, 1], resampled to SAMPLE_RATE (16kHz). Safe to call even if
        start() was never called."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            frames, self._frames = self._frames, []
        if not frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(frames)
        if self._samplerate != SAMPLE_RATE:
            audio = resample_linear(audio, self._samplerate, SAMPLE_RATE)
        return audio


def resample_linear(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear-interpolation resample — no scipy/torchaudio dependency just
    for this. Good enough for ASR input: GigaAM's own feature extraction
    (log-mel spectrogram) is tolerant of the mild high-frequency smoothing
    linear interpolation introduces, and this only ever runs once per
    recording, not per-frame."""
    if orig_sr == target_sr or len(audio) == 0:
        return audio
    duration = len(audio) / orig_sr
    target_length = max(1, round(duration * target_sr))
    orig_times = np.linspace(0.0, duration, num=len(audio), endpoint=False)
    target_times = np.linspace(0.0, duration, num=target_length, endpoint=False)
    return np.interp(target_times, orig_times, audio).astype(np.float32)


def split_on_silence(
    audio: np.ndarray,
    max_seconds: float,
    sample_rate: int = SAMPLE_RATE,
    window_seconds: float = 0.02,
    search_seconds: float = 2.0,
) -> list[np.ndarray]:
    """Splits `audio` into chunks no longer than `max_seconds`.

    For each cut point, looks backward up to `search_seconds` for the
    quietest `window_seconds`-wide window (lowest RMS energy) and cuts
    there — a pause between words or sentences almost always sits
    somewhere in that range for normal speech. If the search window is
    shorter than one analysis window (a very short remaining tail), cuts
    exactly at the target instead. Pure NumPy, no VAD model.
    """
    max_samples = int(max_seconds * sample_rate)
    n = len(audio)
    if n == 0:
        return []
    if n <= max_samples:
        return [audio]

    window = max(1, int(window_seconds * sample_rate))
    search = int(search_seconds * sample_rate)

    chunks: list[np.ndarray] = []
    pos = 0
    while n - pos > max_samples:
        target = pos + max_samples
        search_start = max(pos, target - search)
        segment = audio[search_start:target]
        num_windows = len(segment) // window
        if num_windows < 1:
            cut = target
        else:
            energies = np.array([
                np.sqrt(np.mean(segment[i * window:(i + 1) * window].astype(np.float64) ** 2))
                for i in range(num_windows)
            ])
            quietest = int(np.argmin(energies))
            cut = search_start + quietest * window + window // 2
            cut = max(pos + 1, min(cut, target))
        chunks.append(audio[pos:cut])
        pos = cut
    if pos < n:
        chunks.append(audio[pos:n])
    return chunks


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """Writes float32 [-1, 1] mono audio as 16-bit PCM WAV — the format
    GigaAM's own `load_audio` decodes via ffmpeg."""
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def list_input_devices() -> list[tuple[int, str]]:
    """(index, name) for every device with at least one input channel —
    populates the settings dialog's microphone dropdown."""
    devices = []
    try:
        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0:
                devices.append((index, str(info.get("name", f"Device {index}"))))
    except sd.PortAudioError as exc:
        log.warning("could not query audio devices: %s", exc)
    return devices
