import pytest

from korvoice.config import SINGLE_KEY_CHOICES
from korvoice.hotkeys import (
    _MODIFIER_KEYSYM_NAMES,
    parse_sequence,
    should_emit_key_event,
    to_portal_trigger,
)


@pytest.mark.parametrize(
    ("sequence", "expected_mods", "expected_key"),
    [
        ("Ctrl+Alt+Space", (1 << 2) | (1 << 3), "space"),
        ("Ctrl+C", 1 << 2, "c"),
        ("Alt+Shift+F5", (1 << 3) | (1 << 0), "F5"),
        ("Ctrl+-", 1 << 2, "minus"),
        ("Ctrl+.", 1 << 2, "period"),
    ],
)
def test_parse_sequence(sequence, expected_mods, expected_key):
    result = parse_sequence(sequence)
    assert result == (expected_mods, expected_key)


def test_parse_sequence_unknown_modifier():
    assert parse_sequence("Super+X") is None


def test_parse_sequence_empty():
    assert parse_sequence("") is None
    assert parse_sequence("   ") is None


@pytest.mark.parametrize(
    ("sequence", "expected"),
    [
        ("Ctrl+Alt+Space", "CTRL+ALT+Space"),
        ("Ctrl+C", "CTRL+c"),
        ("Alt+Shift+F5", "ALT+SHIFT+F5"),
    ],
)
def test_to_portal_trigger(sequence, expected):
    assert to_portal_trigger(sequence) == expected


def test_to_portal_trigger_empty():
    assert to_portal_trigger("") == ""


def test_should_emit_key_event_first_press_emits():
    held = set()
    assert should_emit_key_event("k", True, held) is True
    assert "k" in held


def test_should_emit_key_event_repeated_press_while_held_is_dropped():
    # This is the auto-repeat scenario: the key never actually released,
    # but the server (or a backstop-worthy edge case) sent another
    # KeyPress anyway — must not look like a new press.
    held = {"k"}
    assert should_emit_key_event("k", True, held) is False
    assert "k" in held  # unchanged, still considered held


def test_should_emit_key_event_release_emits_and_clears():
    held = {"k"}
    assert should_emit_key_event("k", False, held) is True
    assert "k" not in held


def test_should_emit_key_event_release_without_prior_press_is_still_emitted():
    held: set = set()
    assert should_emit_key_event("k", False, held) is True
    assert held == set()


def test_should_emit_key_event_press_release_press_cycle():
    # A real press, real release, then a genuine new press — every one of
    # these must be emitted, unlike the auto-repeat case above.
    held = set()
    assert should_emit_key_event("k", True, held) is True
    assert should_emit_key_event("k", False, held) is True
    assert should_emit_key_event("k", True, held) is True
    assert "k" in held


def test_every_single_key_choice_is_polled_not_grabbed():
    # SINGLE_KEY_CHOICES (config.py, the settings dialog's "Single key"
    # dropdown) and _MODIFIER_KEYSYM_NAMES (hotkeys.py, which decides
    # whether a binding goes through XGrabKey or XQueryKeymap polling)
    # must stay in sync — a value offered in the dropdown but missing
    # here would silently fall back to XGrabKey, which never delivers a
    # KeyRelease for a bare modifier keycode (confirmed live).
    for value, _label in SINGLE_KEY_CHOICES:
        assert value in _MODIFIER_KEYSYM_NAMES
