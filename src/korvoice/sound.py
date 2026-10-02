"""Short synthesized beeps for wake-word start/stop feedback — no audio
asset files, just a sine tone played through sounddevice's output
stream."""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_FADE_SECONDS = 0.01  # avoids an audible click at tone start/end


def _tone(frequency: float, duration: float) -> np.ndarray:
    t = np.linspace(0, duration, int(duration * _SAMPLE_RATE), endpoint=False)
    wave = 0.2 * np.sin(2 * np.pi * frequency * t).astype(np.float32)
    fade = min(max(1, int(_FADE_SECONDS * _SAMPLE_RATE)), len(wave) // 2)
    envelope = np.ones(len(wave), dtype=np.float32)
    envelope[:fade] = np.linspace(0, 1, fade, dtype=np.float32)
    envelope[-fade:] = np.linspace(1, 0, fade, dtype=np.float32)
    return wave * envelope


def _play(samples: np.ndarray) -> None:
    try:
        sd.play(samples, _SAMPLE_RATE)
    except Exception as exc:  # noqa: BLE001 — a failed beep must not break recording
        log.debug("could not play notification sound: %s", exc)


def play_wake_word_started() -> None:
    """Higher, shorter tone — "the wake phrase matched, recording"."""
    _play(_tone(880.0, 0.1))


def play_wake_word_stopped() -> None:
    """Lower, longer tone — "auto-stopped on trailing silence"."""
    _play(_tone(440.0, 0.15))
