import wave

import numpy as np

import korvoice.audio as audio_mod
from korvoice.audio import SAMPLE_RATE, Recorder, resample_linear, split_on_silence, write_wav


def test_recorder_falls_back_when_selected_device_is_unavailable(monkeypatch):
    opened_devices = []

    class FakeStream:
        def start(self):
            return None

        def close(self):
            return None

    def open_stream(**kwargs):
        device = kwargs["device"]
        opened_devices.append(device)
        if device == 0:
            raise audio_mod.sd.PortAudioError("device unavailable")
        return FakeStream()

    monkeypatch.setattr(
        audio_mod.sd, "query_devices", lambda *args, **kwargs: {"default_samplerate": 48000}
    )
    monkeypatch.setattr(audio_mod.sd, "InputStream", open_stream)
    recorder = Recorder(device=0)

    recorder.start()

    assert opened_devices == [0, None]
    assert recorder.device is None
    assert recorder.used_default_fallback is True


def test_resample_linear_same_rate_returns_input_unchanged():
    audio = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    result = resample_linear(audio, 16000, 16000)
    np.testing.assert_array_equal(result, audio)


def test_resample_linear_empty():
    result = resample_linear(np.zeros(0, dtype=np.float32), 48000, 16000)
    assert len(result) == 0


def test_resample_linear_downsamples_to_expected_length():
    # 1 second of audio at 48kHz (the native rate of a real USB mic on
    # this project's dev host) should become ~1 second at 16kHz.
    audio = np.zeros(48000, dtype=np.float32)
    result = resample_linear(audio, 48000, 16000)
    assert abs(len(result) - 16000) <= 1


def test_resample_linear_upsamples_to_expected_length():
    audio = np.zeros(16000, dtype=np.float32)
    result = resample_linear(audio, 16000, 48000)
    assert abs(len(result) - 48000) <= 1


def test_resample_linear_preserves_frequency_content():
    # A 440Hz tone at 48kHz resampled to 16kHz should still look like a
    # ~440Hz tone — cheap sanity check via zero-crossing count rather than
    # a full FFT comparison.
    sr_in, sr_out, freq, duration = 48000, 16000, 440.0, 0.5
    t = np.arange(int(sr_in * duration)) / sr_in
    tone = np.sin(2 * np.pi * freq * t).astype(np.float32)
    resampled = resample_linear(tone, sr_in, sr_out)
    zero_crossings = int(np.sum(np.diff(np.sign(resampled)) != 0))
    expected_crossings = 2 * freq * duration  # two crossings per cycle
    assert abs(zero_crossings - expected_crossings) < expected_crossings * 0.05


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
