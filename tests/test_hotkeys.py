import pytest
from PySide6.QtCore import QObject

from korvoice.config import SINGLE_KEY_CHOICES
from korvoice.hotkeys import (
    _MODIFIER_KEYSYM_NAMES,
    GlobalHotkeys,
    _PortalHotkeys,
    next_portal_tokens,
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


def test_portal_tokens_are_unique_per_session():
    first, second = next_portal_tokens(), next_portal_tokens()
    assert len(set(first)) == 3
    assert not set(first) & set(second)


class _FakeBus:
    def __init__(self):
        self.disconnected = []

    def disconnect(self, *args):
        self.disconnected.append(args[3])
        return True


def _bare_portal(session_handle="/org/freedesktop/portal/desktop/session/1_2/mine"):
    """A _PortalHotkeys past its D-Bus setup, without a real session bus."""
    portal = _PortalHotkeys.__new__(_PortalHotkeys)
    QObject.__init__(portal)
    portal._bus = _FakeBus()
    portal._request_path = "/org/freedesktop/portal/desktop/request/1_2/token"
    portal._session_handle = session_handle
    portal._closed = False
    return portal


class _Path:
    def __init__(self, path):
        self._path = path

    def path(self):
        return self._path


def test_portal_ignores_other_sessions(qapp):
    portal = _bare_portal()
    events = []
    portal.activated.connect(lambda action, press: events.append((action, press)))

    portal._on_activated(_Path("/org/freedesktop/portal/desktop/session/1_2/other"),
                         "record", 0, {})
    portal._on_activated(_Path(portal._session_handle), "record", 0, {})
    portal._on_deactivated(portal._session_handle, "record", 0, {})

    assert events == [("record", True), ("record", False)]


def test_closed_portal_stops_emitting_and_disconnects(qapp):
    portal = _bare_portal(session_handle="")  # session never created: no Close call
    events = []
    portal.activated.connect(lambda action, press: events.append((action, press)))

    portal.close()
    portal._on_activated(portal._session_handle, "record", 0, {})

    assert events == []
    assert {"Response", "Activated", "Deactivated"} <= set(portal._bus.disconnected)


def test_global_hotkeys_stop_closes_portal_session(qapp):
    class FakePortal:
        closed = False

        def close(self):
            self.closed = True

    hotkeys = GlobalHotkeys()
    portal = FakePortal()
    hotkeys._portal = portal
    hotkeys.backend = "portal"

    hotkeys.stop()

    assert portal.closed
    assert hotkeys._portal is None
    assert hotkeys.backend == "none"
