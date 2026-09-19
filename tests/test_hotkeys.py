import pytest

from korvoice.hotkeys import parse_sequence, to_portal_trigger


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
