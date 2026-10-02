"""Short synthesized chimes for wake-word start/stop feedback — no audio
asset files, just a couple of sine-wave notes played through
sounddevice's output stream."""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000


def _note(frequency: float, duration: float) -> np.ndarray:
    """A single bell-like note: fundamental plus a quiet octave overtone,
    with a soft attack and an exponential decay — reads as a gentle chime
    rather than a flat, harsh beep."""
    t = np.linspace(0, duration, int(duration * _SAMPLE_RATE), endpoint=False)
    wave = np.sin(2 * np.pi * frequency * t) + 0.3 * np.sin(2 * np.pi * frequency * 2 * t)
    decay = np.exp(-t * (6.0 / duration))
    attack = max(1, int(0.003 * _SAMPLE_RATE))
    envelope = decay.copy()
    envelope[:attack] *= np.linspace(0, 1, attack)
    return (0.18 * wave * envelope).astype(np.float32)


def _chime(frequencies: list[float], note_duration: float = 0.09, gap: float = 0.03) -> np.ndarray:
    silence = np.zeros(int(gap * _SAMPLE_RATE), dtype=np.float32)
    parts: list[np.ndarray] = []
    for i, frequency in enumerate(frequencies):
        parts.append(_note(frequency, note_duration))
        if i < len(frequencies) - 1:
            parts.append(silence)
    return np.concatenate(parts)


def _play(samples: np.ndarray) -> None:
    try:
        sd.play(samples, _SAMPLE_RATE)
    except Exception as exc:  # noqa: BLE001 — a failed chime must not break recording
        log.debug("could not play notification sound: %s", exc)


def play_wake_word_started() -> None:
    """Rising two-note chime — "the wake phrase matched, recording"."""
    _play(_chime([660.0, 880.0]))


def play_wake_word_stopped() -> None:
    """Falling two-note chime — "auto-stopped on trailing silence"."""
    _play(_chime([660.0, 440.0]))
