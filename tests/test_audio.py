import wave

import numpy as np

from korvoice.audio import SAMPLE_RATE, split_on_silence, write_wav


def test_split_on_silence_empty():
    assert split_on_silence(np.zeros(0, dtype=np.float32), max_seconds=20) == []


def test_split_on_silence_short_audio_unchanged():
    audio = np.random.default_rng(0).uniform(-0.5, 0.5, size=SAMPLE_RATE * 5).astype(np.float32)
    chunks = split_on_silence(audio, max_seconds=20)
    assert len(chunks) == 1
    np.testing.assert_array_equal(chunks[0], audio)


def test_split_on_silence_cuts_within_a_silent_gap():
    rng = np.random.default_rng(1)
    total_seconds = 45
    audio = rng.uniform(-0.5, 0.5, size=SAMPLE_RATE * total_seconds).astype(np.float32)
    # Silence between 19.0s and 19.3s — inside the search window the
    # algorithm looks at for a 20s target cut (target - 2s .. target).
    silence_start, silence_end = int(19.0 * SAMPLE_RATE), int(19.3 * SAMPLE_RATE)
    audio[silence_start:silence_end] = 0.0

    chunks = split_on_silence(audio, max_seconds=20)

    assert len(chunks) >= 2
    first_cut = len(chunks[0])
    assert silence_start <= first_cut <= silence_end


def test_split_on_silence_chunks_never_exceed_max_seconds():
    rng = np.random.default_rng(2)
    audio = rng.uniform(-0.5, 0.5, size=SAMPLE_RATE * 63).astype(np.float32)
    max_seconds = 20
    chunks = split_on_silence(audio, max_seconds=max_seconds)
    for chunk in chunks:
        assert len(chunk) <= max_seconds * SAMPLE_RATE


def test_split_on_silence_chunks_reconstruct_original():
    rng = np.random.default_rng(3)
    audio = rng.uniform(-0.5, 0.5, size=SAMPLE_RATE * 47).astype(np.float32)
    chunks = split_on_silence(audio, max_seconds=20)
    np.testing.assert_array_equal(np.concatenate(chunks), audio)


def test_write_wav_roundtrip(tmp_path):
    audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    path = tmp_path / "chunk.wav"
    write_wav(path, audio, sample_rate=SAMPLE_RATE)

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == SAMPLE_RATE
        frames = wav_file.readframes(wav_file.getnframes())

    pcm16 = np.frombuffer(frames, dtype=np.int16)
    restored = pcm16.astype(np.float32) / 32767.0
    np.testing.assert_allclose(restored, audio, atol=1e-3)


def test_write_wav_clips_out_of_range_values(tmp_path):
    audio = np.array([2.0, -2.0], dtype=np.float32)
    path = tmp_path / "clip.wav"
    write_wav(path, audio, sample_rate=SAMPLE_RATE)

    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    pcm16 = np.frombuffer(frames, dtype=np.int16)
    assert pcm16[0] == 32767
    assert pcm16[1] == -32767
