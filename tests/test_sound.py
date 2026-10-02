import numpy as np

import korvoice.sound as sound_mod


def test_note_length_matches_duration_and_sample_rate():
    wave = sound_mod._note(440.0, 0.1)
    assert len(wave) == int(0.1 * sound_mod._SAMPLE_RATE)


def test_note_has_soft_attack_and_decays_towards_the_end():
    wave = sound_mod._note(440.0, 0.1)
    assert wave[0] == 0.0  # soft attack starts silent
    peak = np.max(np.abs(wave))
    assert abs(wave[-1]) < peak  # decayed well below the peak by the end


def test_note_amplitude_is_bounded():
    wave = sound_mod._note(440.0, 0.1)
    assert np.max(np.abs(wave)) <= 0.3


def test_chime_concatenates_notes_with_gaps():
    note_duration, gap = 0.09, 0.03
    chime = sound_mod._chime([660.0, 880.0], note_duration=note_duration, gap=gap)
    expected_len = 2 * int(note_duration * sound_mod._SAMPLE_RATE) + int(
        gap * sound_mod._SAMPLE_RATE
    )
    assert len(chime) == expected_len


def test_chime_single_note_has_no_gap():
    note_duration = 0.09
    chime = sound_mod._chime([660.0], note_duration=note_duration)
    assert len(chime) == int(note_duration * sound_mod._SAMPLE_RATE)


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
