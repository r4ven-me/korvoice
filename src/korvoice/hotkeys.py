"""Global hotkey inside the application, no external tools.

X11: XGrabKey via ctypes (libX11) + a dedicated X event reading thread —
except a bare modifier key (Control_R and the like, see
config.SINGLE_KEY_CHOICES), which is tracked by polling XQueryKeymap
instead: confirmed live that XGrabKey on a modifier keycode delivers its
KeyPress but never delivers the matching KeyRelease at all, a quirk of the
X11 core protocol around grabbing modifier keycodes specifically, not
something fixable in the press/release matching logic. Wayland: XDG
Desktop Portal (org.freedesktop.portal.GlobalShortcuts) via QtDBus — the
compositor itself shows the binding confirmation dialog.

Adapted from kortalk's hotkeys.py (~/Cloud/Projects/public/kortalk), with
one addition: korvoice's push-to-talk mode needs to know when the key is
*released*, not just pressed, so both backends here report press AND
release (kortalk only ever needed "activated", i.e. press). That in turn
surfaced a second issue kortalk never hit either: X11 key auto-repeat
sends a synthetic KeyRelease immediately before every repeated KeyPress
while a key is held, which read as the hotkey being released and
re-pressed dozens of times over one real hold — see
XkbSetDetectableAutoRepeat and should_emit_key_event below.

If no backend is available the application keeps working — the tray menu
offers "Start recording" as a fallback (see app.py).
"""

from __future__ import annotations

import ctypes
import logging
import os

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

# -- parsing strings like "Ctrl+Alt+C" ----------------------------------------

X11_MODMASK = {"ctrl": 1 << 2, "shift": 1 << 0, "alt": 1 << 3, "meta": 1 << 6}
_NUMLOCK, _CAPSLOCK = 1 << 4, 1 << 1  # Mod2Mask, LockMask
_RELEVANT_MODS = sum(X11_MODMASK.values())

# A bare modifier used as the whole hotkey (config.SINGLE_KEY_CHOICES) is
# tracked by polling XQueryKeymap instead of XGrabKey — see
# _X11HotkeyThread.run()'s "polled" branch for why.
_MODIFIER_KEYSYM_NAMES = {
    "Control_L", "Control_R", "Shift_L", "Shift_R",
    "Alt_L", "Alt_R", "Super_L", "Super_R",
}

# Qt key names -> X11 keysym names (XStringToKeysym)
_KEYSYM_NAMES = {
    "space": "space", "return": "Return", "enter": "Return", "tab": "Tab",
    "esc": "Escape", "escape": "Escape", "backspace": "BackSpace",
    "ins": "Insert", "del": "Delete", "home": "Home", "end": "End",
    "pgup": "Prior", "pgdown": "Next", "print": "Print", "pause": "Pause",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    **{f"f{i}": f"F{i}" for i in range(1, 25)},
    # Punctuation: letters/digits resolve via XStringToKeysym as-is (their
    # keysym value equals their ASCII code), but punctuation keysyms have
    # their own symbolic names — the raw character is NoSymbol to Xlib, so
    # without this a binding on one of these keys silently fails to grab.
    "`": "grave", "~": "asciitilde",
    "-": "minus", "_": "underscore",
    "=": "equal", "+": "plus",
    "[": "bracketleft", "{": "braceleft",
    "]": "bracketright", "}": "braceright",
    ";": "semicolon", ":": "colon",
    "'": "apostrophe", '"': "quotedbl",
    ",": "comma", "<": "less",
    ".": "period", ">": "greater",
    "/": "slash", "?": "question",
    "\\": "backslash", "|": "bar",
    "!": "exclam", "@": "at", "#": "numbersign", "$": "dollar",
    "%": "percent", "^": "asciicircum", "&": "ampersand", "*": "asterisk",
    "(": "parenleft", ")": "parenright",
}


def parse_sequence(sequence: str) -> tuple[int, str] | None:
    """'Ctrl+Alt+C' -> (X11 modifier mask, keysym name). None — unparseable."""
    parts = [p.strip() for p in sequence.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for part in parts[:-1]:
        mask = X11_MODMASK.get(part.lower())
        if mask is None:
            return None
        mods |= mask
    key = parts[-1]
    keysym_name = _KEYSYM_NAMES.get(key.lower(), key.lower() if len(key) == 1 else key)
    return mods, keysym_name


def to_portal_trigger(sequence: str) -> str:
    """'Ctrl+Alt+C' -> 'CTRL+ALT+c' (the portal's preferred_trigger format)."""
    parts = [p.strip() for p in sequence.split("+") if p.strip()]
    if not parts:
        return ""
    mods = [p.upper() for p in parts[:-1]]
    key = parts[-1]
    return "+".join(mods + [key.lower() if len(key) == 1 else key])


def should_emit_key_event(key: object, is_press: bool, held: set) -> bool:
    """Backstop against X11 key auto-repeat, alongside
    XkbSetDetectableAutoRepeat in _X11HotkeyThread.run() (belt and
    suspenders: that call should already stop the server from re-sending
    KeyPress/KeyRelease pairs while a key auto-repeats, this just also
    drops anything that slips through). `held` is mutated in place —
    tracks which grabbed keys are currently down. A press for a key
    that's already in `held` is a repeat, not a new press: dropped
    (returns False) instead of re-triggering push-to-talk's start.

    A push-to-talk hold without this fired start/stop/transcribe dozens
    of times over one held key (confirmed live) — each repeated KeyPress
    arrived with a synthetic KeyRelease immediately before it, and
    without deduplication every one of those pairs looked like a
    legitimate release-then-repress."""
    if is_press:
        if key in held:
            return False
        held.add(key)
    else:
        held.discard(key)
    return True


# -- X11 backend --------------------------------------------------------------

class _X11HotkeyThread(QThread):
    """A separate Xlib connection: grab keys on the root window and read
    events. Qt talks over its own xcb connection, so our Xlib error handler
    and event loop do not interfere with it."""

    activated = Signal(str, bool)  # action, is_press

    def __init__(self, bindings: list[tuple[int, str, str]]):
        # bindings: (modifier mask, keysym name, action)
        super().__init__()
        self._bindings = bindings
        self._stop = False
        self.grabbed: list[str] = []   # actions that were bound successfully
        self.failed: list[str] = []

    def stop(self) -> None:
        self._stop = True
        self.wait(2000)

    def run(self) -> None:  # noqa: C901
        try:
            xlib = ctypes.CDLL("libX11.so.6")
        except OSError:
            self.failed = [action for _m, _k, action in self._bindings]
            return

        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XStringToKeysym.argtypes = [ctypes.c_char_p]
        xlib.XStringToKeysym.restype = ctypes.c_ulong
        xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        xlib.XKeysymToKeycode.restype = ctypes.c_ubyte
        xlib.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint,
                                  ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        xlib.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        xlib.XPending.argtypes = [ctypes.c_void_p]
        xlib.XPending.restype = ctypes.c_int
        xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        # A combination taken by another client yields BadAccess; the default
        # Xlib handler kills the process — install a silent one (Xlib only,
        # Qt lives on xcb and is not affected).
        handler_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        silent = handler_t(lambda *_a: 0)
        xlib.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        xlib.XSetErrorHandler(ctypes.cast(silent, ctypes.c_void_p))

        display = xlib.XOpenDisplay(None)
        if not display:
            self.failed = [action for _m, _k, action in self._bindings]
            return
        root = xlib.XDefaultRootWindow(display)

        # Without this, holding a grabbed key down makes X11's keyboard
        # auto-repeat synthesize a KeyRelease immediately before every
        # repeated KeyPress — confirmed live: push-to-talk with a held
        # combination fired start/stop/transcribe dozens of times over the
        # hold (visible as the tray icon and text cursor flickering, no
        # usable audio ever captured, and — since each cycle spins up a
        # real torch inference call — the burst of back-to-back
        # transcriptions was enough to make the whole desktop stutter for
        # the entire time the key was held). XkbSetDetectableAutoRepeat
        # makes the server send exactly one KeyRelease, on the actual
        # physical release, regardless of how long the key auto-repeats —
        # this is what mainstream toolkits (Qt/GTK) already do on their
        # own xcb connection, which is a separate connection from this
        # thread's own raw Xlib one, so it has to be requested here too.
        xlib.XkbSetDetectableAutoRepeat.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        xlib.XkbSetDetectableAutoRepeat.restype = ctypes.c_int
        xlib.XkbSetDetectableAutoRepeat(display, 1, None)

        class XKeyEvent(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
                ("state", ctypes.c_uint), ("keycode", ctypes.c_uint),
                ("same_screen", ctypes.c_int),
            ]

        class XEvent(ctypes.Union):
            _fields_ = [("type", ctypes.c_int), ("xkey", XKeyEvent),
                        ("pad", ctypes.c_long * 24)]

        xlib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]

        GRAB_MODE_ASYNC, KEY_PRESS, KEY_RELEASE = 1, 2, 3
        registered: dict[tuple[int, int], str] = {}  # (keycode, mods) -> action
        # (keycode, action) for a bare modifier used as the whole hotkey —
        # tracked by polling instead of XGrabKey. Confirmed live: grabbing
        # a modifier keycode itself delivers its KeyPress fine but *never*
        # delivers the matching KeyRelease at all (reproduced directly —
        # push-to-talk recording started and then simply never stopped,
        # confirmed still actively capturing a full second-plus later).
        # This is a known-quirky corner of the X11 core protocol around
        # grabbing modifier keycodes, not a bug in the press/release
        # matching above — XQueryKeymap sidesteps grabbing for this one
        # case entirely, just sampling whether the key is currently down.
        polled: list[tuple[int, str]] = []
        for mods, keysym_name, action in self._bindings:
            keysym = xlib.XStringToKeysym(keysym_name.encode())
            keycode = xlib.XKeysymToKeycode(display, keysym) if keysym else 0
            if not keycode:
                self.failed.append(action)
                continue
            if mods == 0 and keysym_name in _MODIFIER_KEYSYM_NAMES:
                polled.append((keycode, action))
                self.grabbed.append(action)
                continue
            # grab all NumLock/CapsLock combinations
            for extra in (0, _NUMLOCK, _CAPSLOCK, _NUMLOCK | _CAPSLOCK):
                xlib.XGrabKey(display, keycode, mods | extra, root,
                              1, GRAB_MODE_ASYNC, GRAB_MODE_ASYNC)
            registered[(keycode, mods)] = action
            self.grabbed.append(action)
        xlib.XSync(display, 0)
        log.info("X11 hotkeys: grabbed %s%s", self.grabbed,
                 f", failed {self.failed}" if self.failed else "")

        held: set[tuple[int, int]] = set()  # see should_emit_key_event
        polled_down: dict[int, bool] = dict.fromkeys((kc for kc, _a in polled), False)
        keymap_buf = ctypes.create_string_buffer(32)

        event = XEvent()
        while not self._stop:
            while xlib.XPending(display):
                xlib.XNextEvent(display, ctypes.byref(event))
                if event.type in (KEY_PRESS, KEY_RELEASE):
                    key = (event.xkey.keycode, event.xkey.state & _RELEVANT_MODS)
                    action = registered.get(key)
                    if not action:
                        continue
                    is_press = event.type == KEY_PRESS
                    if should_emit_key_event(key, is_press, held):
                        self.activated.emit(action, is_press)
            if polled:
                xlib.XQueryKeymap(display, keymap_buf)
                raw = keymap_buf.raw
                for keycode, action in polled:
                    is_down = bool(raw[keycode // 8] & (1 << (keycode % 8)))
                    if is_down != polled_down[keycode]:
                        polled_down[keycode] = is_down
                        self.activated.emit(action, is_down)
            self.msleep(30)

        for (keycode, mods), _action in registered.items():
            for extra in (0, _NUMLOCK, _CAPSLOCK, _NUMLOCK | _CAPSLOCK):
                xlib.XUngrabKey(display, keycode, mods | extra, root)
        xlib.XSync(display, 0)
        xlib.XCloseDisplay(display)


# -- Wayland backend (XDG Desktop Portal) -------------------------------------

_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"


class _PortalHotkeys(QObject):
    activated = Signal(str, bool)  # action, is_press

    def __init__(self, bindings: dict[str, str], parent=None):
        # bindings: action -> "Ctrl+Alt+C"
        super().__init__(parent)
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        self._bindings = bindings
        self._bus = QDBusConnection.sessionBus()
        self._iface = QDBusInterface(_PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE, self._bus)
        if not self._iface.isValid():
            raise RuntimeError("GlobalShortcuts portal is unavailable")

        token = f"korvoice{os.getpid()}"
        sender = self._bus.baseService()[1:].replace(".", "_")
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        self._bus.connect(_PORTAL_SERVICE, request_path, "org.freedesktop.portal.Request",
                          "Response", self._on_session_created)
        reply = self._iface.call("CreateSession", {
            "handle_token": token,
            "session_handle_token": f"korvoice_{os.getpid()}",
        })
        if reply.errorName():
            raise RuntimeError(f"CreateSession: {reply.errorMessage()}")

    @Slot("uint", "QVariantMap")
    def _on_session_created(self, code: int, results: dict) -> None:
        from PySide6.QtDBus import QDBusObjectPath

        if code != 0:
            return
        session = results.get("session_handle", "")
        shortcuts = [
            [action, {"description": f"korvoice: {action}",
                      "preferred_trigger": to_portal_trigger(seq)}]
            for action, seq in self._bindings.items() if seq
        ]
        reply = self._iface.call("BindShortcuts", QDBusObjectPath(session), shortcuts, "",
                                 {"handle_token": f"korvoice_bind{os.getpid()}"})
        if reply.errorName():
            log.warning("portal BindShortcuts: %s", reply.errorMessage())
        else:
            log.info("portal GlobalShortcuts: requested bindings %s",
                     [a for a, _s in self._bindings.items()])
        # "Activated" fires on key-down, "Deactivated" on key-up — both are
        # part of the portal's own spec (it's how a compositor supports
        # hold-to-activate shortcuts), kortalk just never needed the second
        # one since it has no push-to-talk-style mode.
        self._bus.connect(_PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE,
                          "Activated", self._on_activated)
        self._bus.connect(_PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE,
                          "Deactivated", self._on_deactivated)

    @Slot("QDBusObjectPath", "QString", "qulonglong", "QVariantMap")
    def _on_activated(self, _session, shortcut_id: str, _ts, _opts) -> None:
        self.activated.emit(shortcut_id, True)

    @Slot("QDBusObjectPath", "QString", "qulonglong", "QVariantMap")
    def _on_deactivated(self, _session, shortcut_id: str, _ts, _opts) -> None:
        self.activated.emit(shortcut_id, False)


# -- facade -------------------------------------------------------------------

class GlobalHotkeys(QObject):
    """Registers the global hotkey in whatever way suits the session."""

    activated = Signal(str, bool)  # action: "record"; is_press: True/False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x11: _X11HotkeyThread | None = None
        self._portal: _PortalHotkeys | None = None
        self.backend = "none"
        self.error = ""

    def apply(self, bindings: dict[str, str]) -> None:
        """bindings: action -> 'Ctrl+Alt+C' (empty string = unassigned)."""
        self.stop()
        bindings = {a: s for a, s in bindings.items() if s}
        if not bindings:
            return

        platform = QGuiApplication.platformName()
        if platform == "xcb":
            parsed = []
            for action, seq in bindings.items():
                result = parse_sequence(seq)
                if result:
                    parsed.append((result[0], result[1], action))
            if not parsed:
                self.error = "failed to parse the key sequences"
                return
            self._x11 = _X11HotkeyThread(parsed)
            self._x11.activated.connect(self.activated)
            self._x11.start()
            self.backend = "x11"
        else:
            try:
                self._portal = _PortalHotkeys(bindings, self)
                self._portal.activated.connect(self.activated)
                self.backend = "portal"
            except Exception as exc:  # noqa: BLE001 — hotkeys must not kill the app
                self.backend = "none"
                self.error = str(exc)
                log.warning("hotkeys unavailable: %s", exc)

    def stop(self) -> None:
        if self._x11 is not None:
            self._x11.stop()
            self._x11 = None
        self._portal = None
        self.backend = "none"
        self.error = ""
