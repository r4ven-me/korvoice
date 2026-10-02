import numpy as np

import korvoice.sound as sound_mod


def test_tone_length_matches_duration_and_sample_rate():
    wave = sound_mod._tone(440.0, 0.1)
    assert len(wave) == int(0.1 * sound_mod._SAMPLE_RATE)


def test_tone_fades_in_and_out_to_avoid_clicks():
    wave = sound_mod._tone(440.0, 0.1)
    assert wave[0] == 0.0
    assert wave[-1] == 0.0
    assert abs(wave[0]) < abs(wave[len(wave) // 2])


def test_tone_amplitude_is_bounded():
    wave = sound_mod._tone(440.0, 0.1)
    assert np.max(np.abs(wave)) <= 0.2


def test_play_wake_word_started_plays_at_module_sample_rate(monkeypatch):
    calls = []
    monkeypatch.setattr(sound_mod.sd, "play", lambda samples, samplerate: calls.append(samplerate))

    sound_mod.play_wake_word_started()

    assert calls == [sound_mod._SAMPLE_RATE]


def test_play_wake_word_stopped_plays_at_module_sample_rate(monkeypatch):
    calls = []
    monkeypatch.setattr(sound_mod.sd, "play", lambda samples, samplerate: calls.append(samplerate))

    sound_mod.play_wake_word_stopped()

    assert calls == [sound_mod._SAMPLE_RATE]


def test_play_failure_does_not_raise(monkeypatch):
    def raise_error(*_args, **_kwargs):
        raise RuntimeError("no output device")

    monkeypatch.setattr(sound_mod.sd, "play", raise_error)

    sound_mod.play_wake_word_started()  # must not raise
    sound_mod.play_wake_word_stopped()  # must not raise
