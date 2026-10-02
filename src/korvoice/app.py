"""korvoice entry point: CLI, single instance, tray, global hotkey.

Architecture mirrors the author's kortalk project's app.py:
`korvoice` with no arguments starts the resident application (tray +
QLocalServer + global hotkey). CLI flags are delivered to the running
instance over a local socket and return immediately.

Recording state machine: idle -> recording -> transcribing -> idle.
push_to_talk mode drives it from hotkey press/release; toggle mode and the
tray's "Start/Stop recording" action both drive it from press-only clicks.
"""

from __future__ import annotations

import argparse
import ctypes
import getpass
import json
import logging
import logging.handlers
import os
import shutil
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, theme, wakeword
from .asr import Engine
from .audio import MIN_TRANSCRIBE_SAMPLES, SAMPLE_RATE, Recorder, list_input_devices
from .config import Config
from .hotkeys import GlobalHotkeys
from .i18n import set_language, tr
from .output import OutputDispatcher
from .settings_dialog import AboutDialog, SettingsDialog
from .wakeword import WakeWordDetector, WakeWordSilenceWatcher
from .windows import HistoryWindow

SOCKET_NAME = f"korvoice-{getpass.getuser()}"
LOG_DIR = Path(os.environ.get("XDG_STATE_HOME",
                              str(Path.home() / ".local" / "state"))) / "korvoice"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
DESKTOP_FILE = DATA_DIR / "applications" / "korvoice.desktop"

_RECORD_ACTION = "record"

log = logging.getLogger(__name__)


def augment_path_from_login_shell() -> None:
    """Merges the user's login-shell PATH into this process's PATH — apps
    launched from the applications menu or autostart usually inherit a
    minimal PATH that skips shell startup files (~/.local/bin among them,
    where pipx puts `korvoice` itself). Best-effort: any failure just
    leaves PATH as is. (Same rationale and implementation as kortalk's
    augment_path_from_login_shell.)"""
    shell = os.environ.get("SHELL") or "/bin/sh"
    try:
        import subprocess
        result = subprocess.run(
            [shell, "-ilc", 'echo -n "$PATH"'],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, ValueError):
        return
    if result.returncode != 0:
        return
    shell_path = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
    if not shell_path:
        return
    current_dirs = os.environ.get("PATH", "").split(os.pathsep)
    added = [d for d in shell_path.split(os.pathsep) if d and d not in current_dirs]
    if added:
        os.environ["PATH"] = os.pathsep.join(current_dirs + added)


DESKTOP_ENTRY = """\
[Desktop Entry]
Type=Application
Name=korvoice
Comment=Push-to-talk Russian voice input (GigaAM)
Comment[ru]=Голосовой ввод на русском языке (GigaAM)
Exec={exec_path}
Icon={icon_path}
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=false
"""


def ensure_desktop_entry() -> None:
    """Installs an applications-menu launcher entry with the app icon —
    pip/pipx only puts the `korvoice` binary on PATH, there is no install
    hook for a per-user XDG menu entry."""
    try:
        icon_path = theme.install_icon_file()
        exec_path = shutil.which("korvoice") or str(Path(sys.argv[0]).resolve())
        DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(
            DESKTOP_ENTRY.format(exec_path=exec_path, icon_path=icon_path), encoding="utf-8"
        )
    except OSError:
        pass  # non-critical: the app still runs fine from the tray/CLI


def setup_logging(debug: bool) -> None:
    root = logging.getLogger("korvoice")
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "korvoice.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass
    if debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korvoice",
        description="Push-to-talk / toggle Russian voice input, powered by GigaAM. "
                    "With no arguments starts the tray daemon; recording is driven by "
                    "the hotkey (configured in Settings) or the tray menu.",
    )
    parser.add_argument("--settings", action="store_true", help="Open settings.")
    parser.add_argument("--history", action="store_true", help="Open the history window.")
    parser.add_argument("--quit", action="store_true", dest="quit_",
                        help="Quit the running instance.")
    parser.add_argument("--check", action="store_true", help="Environment diagnostics.")
    parser.add_argument("--debug", action="store_true", help="Verbose log and full tracebacks.")
    parser.add_argument("--version", action="version", version=f"korvoice {__version__}")
    return parser


def args_to_command(args) -> dict:
    if args.quit_:
        action = "quit"
    elif args.settings:
        action = "settings"
    elif args.history:
        action = "history"
    else:
        action = "daemon"
    return {"action": action}


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------

def run_selftest(config: Config) -> int:
    ok = True

    def report(label: str, passed: bool, remedy: str = "") -> None:
        nonlocal ok
        print(f"{'✅' if passed else '❌'} {label}")
        if not passed:
            ok = False
            if remedy:
                print(f"   → {remedy}")

    report(f"PySide6 (Qt {__import__('PySide6').QtCore.qVersion()})", True)
    report("System tray", QSystemTrayIcon.isSystemTrayAvailable(),
           "tray unavailable — use --settings/--history instead")

    platform = QGuiApplication.platformName()
    print(f"ℹ️  Platform: {platform} → hotkey backend: "
          + ("XGrabKey (X11)" if platform == "xcb" else "XDG portal GlobalShortcuts"))

    report("ffmpeg in PATH", shutil.which("ffmpeg") is not None,
           "install ffmpeg — GigaAM decodes audio through it")

    try:
        import gigaam  # noqa: F401
        report("gigaam importable", True)
    except ImportError as exc:
        report(
            "gigaam importable",
            False,
            "install the current GigaAM GitHub version into the korvoice pipx "
            f"environment (see README): {exc}",
        )

    devices = list_input_devices()
    report(f"microphone input device(s) found: {len(devices)}", len(devices) > 0,
           "no input device seen by sounddevice/PortAudio")

    if platform == "xcb":
        report("xdotool in PATH (X11 autotype)", shutil.which("xdotool") is not None,
               "autotype will be unavailable on X11 without xdotool")
    else:
        report("ydotool in PATH (Wayland autotype)", shutil.which("ydotool") is not None,
               "autotype will be unavailable on Wayland without ydotool + ydotoold")
        report("wl-copy/wl-paste in PATH (Wayland clipboard and autotype)",
               bool(shutil.which("wl-copy") and shutil.which("wl-paste")),
               "install wl-clipboard — autotype needs it, and without it the "
               "clipboard output may not work while korvoice has no focus")

    vosk_ok, vosk_reason = wakeword.vosk_importable()
    report(
        "vosk importable", vosk_ok,
        f"{vosk_reason} — install it with `pipx inject korvoice vosk` (only needed "
        "if wake word is enabled), see README" if not vosk_ok else "",
    )
    if wakeword.model_present():
        print(f"ℹ️  wake-word model present at {wakeword.DEFAULT_MODEL_DIR}")
    else:
        print("ℹ️  wake-word model not downloaded yet — downloads automatically "
              "(~45 MB) the first time wake word is enabled")

    print(f"\nMode: {config.get('mode')}, hotkey: {config.hotkey('record') or '—'}")
    print(f"Model: {config.get('model')}, device: {config.get('device')}")
    print(f"Settings file: {config.file_path()}")
    print("All good." if ok else "Issues found, see the recommendations above.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------

def try_send_to_running(command: dict) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(QByteArray(json.dumps(command).encode("utf-8")))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


# ---------------------------------------------------------------------------
# xcb platform plugin preflight
# ---------------------------------------------------------------------------

def _will_use_xcb_platform() -> bool:
    platform = os.environ.get("QT_QPA_PLATFORM", "")
    if platform:
        return platform.split(":")[0] == "xcb"
    return bool(os.environ.get("DISPLAY")) and not os.environ.get("WAYLAND_DISPLAY")


def _xcb_cursor_library_missing() -> bool:
    try:
        ctypes.CDLL("libxcb-cursor.so.0")
        return False
    except OSError:
        return True


def check_xcb_cursor_dependency() -> str:
    """Since Qt 6.5, the xcb platform plugin needs libxcb-cursor0 — without
    it Qt calls qFatal() and the process is killed outright rather than
    raising a catchable exception. Checked before ever constructing a
    QApplication, turning that crash into a normal startup error. (Same
    check as kortalk's app.py — verified there against the same Qt bug.)"""
    if not _will_use_xcb_platform() or not _xcb_cursor_library_missing():
        return ""
    return (
        "the Qt xcb platform plugin needs libxcb-cursor0, which isn't "
        "installed — install it and try again "
        "(Debian/Ubuntu/Mint: sudo apt install libxcb-cursor0)"
    )


class KorvoiceApp:
    """Resident application: tray + command server + hotkey + recording
    state machine."""

    def __init__(self, app: QApplication, config: Config) -> None:
        self.app = app
        self.config = config
        self.state = "idle"  # idle | recording | transcribing
        self.settings_dialog: SettingsDialog | None = None
        self.history_window: HistoryWindow | None = None
        self._autotype_note = ""
        self._record_started_at = 0.0
        self._transcribe_started_at = 0.0

        theme.apply_theme(app, str(config.get("theme")))
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(theme.make_tray_icon())

        self.recorder = Recorder(self._resolve_input_device())
        self.engine = Engine(config)
        self.engine.result_ready.connect(self._on_result)
        self.engine.error.connect(self._on_engine_error)
        self.engine.status_changed.connect(self._on_engine_status)

        self.wake_word = WakeWordDetector(config)
        self.wake_word.detected.connect(self._on_wake_word_detected)
        self.wake_word.status_changed.connect(self._on_wake_word_status)
        self._wake_word_status = ""
        self._wake_word_silence_watcher = WakeWordSilenceWatcher()
        self._wake_word_silence_watcher.silence_detected.connect(self._stop_recording)

        self.output = OutputDispatcher(config)
        self.output.delivered.connect(self._on_output_window)
        self.output.autotype_unavailable.connect(self._on_autotype_unavailable)
        self.output.autotype_succeeded.connect(self._on_autotype_succeeded)

        self.server = QLocalServer()
        # Qt's default socket permissions let any local user connect and
        # send commands (force --quit, open windows) — restrict to the
        # owning user, same as kortalk.
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(SOCKET_NAME)  # clean up the socket after a crash
        self.server.listen(SOCKET_NAME)
        self.server.newConnection.connect(self._on_connection)

        # IMPORTANT: keep the menu in an attribute — setContextMenu does
        # not take ownership, and a local QMenu would be garbage collected.
        self.tray = QSystemTrayIcon(
            theme.make_tray_icon(theme.tray_icon_color(str(config.get("tray_icon")))))
        self.menu = QMenu()
        self._rebuild_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        self.hotkeys = GlobalHotkeys()
        self.hotkeys.activated.connect(self._hotkey_activated)
        self._apply_hotkeys()

        # Warms the model now instead of on the first hotkey press — cold
        # load (torch import + weights) measured at ~3-5s on this
        # project's dev host, which otherwise landed entirely on the
        # user's first-ever recording with no feedback why it's slow.
        self.engine.preload()
        if config.get("wake_word_enabled"):
            self.wake_word.preload()

    # -- input device -----------------------------------------------------------

    def _resolve_input_device(self) -> int | None:
        raw = str(self.config.get("input_device"))
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    # -- tray ---------------------------------------------------------------

    def _rebuild_menu(self) -> None:
        self.menu.clear()

        self.record_action = QAction(self._record_action_label())
        self.record_action.triggered.connect(self._on_record_action)
        self.menu.addAction(self.record_action)

        self.menu.addSeparator()
        mode_menu = QMenu(tr("Mode"), self.menu)
        mode_group = QActionGroup(mode_menu)
        mode_group.setExclusive(True)
        current_mode = str(self.config.get("mode"))
        for value, label in (("push_to_talk", "Push-to-talk"), ("toggle", "Toggle")):
            action = QAction(tr(label), mode_menu, checkable=True)
            action.setChecked(value == current_mode)
            action.triggered.connect(lambda _checked=False, v=value: self._set_mode(v))
            mode_group.addAction(action)
            mode_menu.addAction(action)
        self.menu.addMenu(mode_menu)

        self.menu.addAction(tr("Open history"), self.open_history)
        self.menu.addSeparator()
        self.menu.addAction(tr("Settings"), self.open_settings)
        self.menu.addAction(tr("About"), self.open_about)
        self.menu.addSeparator()
        self.menu.addAction(tr("Quit"), self.quit)
        self._update_tooltip()

    def _record_action_label(self) -> str:
        return tr({"idle": "Start recording", "recording": "Stop recording",
                   "transcribing": "Recognizing…"}[self.state])

    def _on_record_action(self) -> None:
        if self.state == "idle":
            self._start_recording()
        elif self.state == "recording":
            self._stop_recording()
        # "transcribing": busy, ignore

    def _set_mode(self, mode: str) -> None:
        self.config.set("mode", mode)
        self._update_tooltip()

    def _update_tray_visuals(self, force_refresh: bool = False) -> None:
        icon = theme.make_tray_icon(
            theme.tray_icon_color(str(self.config.get("tray_icon"))), state=self.state
        )
        self.tray.setIcon(icon)
        if force_refresh:
            # Cinnamon can miss one StatusNotifierItem icon-property update
            # after a long idle/suspend period. Never hide/re-register the
            # item: that can make it disappear entirely. Re-send the fresh
            # pixmap after the event loop has had time to flush the first
            # update, but only if the state has not changed in the meantime.
            expected_state = self.state
            QTimer.singleShot(
                150,
                lambda refreshed=icon, expected=expected_state: (
                    self.tray.setIcon(refreshed) if self.state == expected else None
                ),
            )
        if hasattr(self, "record_action"):
            self.record_action.setText(self._record_action_label())
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        mode = str(self.config.get("mode"))
        hotkey = self.config.hotkey("record") or "—"
        state_label = tr({"idle": "idle", "recording": "recording…",
                          "transcribing": "recognizing…"}[self.state])
        mode_label = tr("Push-to-talk" if mode == "push_to_talk" else "Toggle")
        lines = [f"korvoice — {state_label}",
                 tr("Mode: {mode}, hotkey: {hotkey}", mode=mode_label, hotkey=hotkey)]
        note = self.hotkeys_note()
        if note:
            lines.append(note)
        if self._autotype_note:
            lines.append(self._autotype_note)
        wake_word_note = self._wake_word_tooltip_line()
        if wake_word_note:
            lines.append(wake_word_note)
        self.tray.setToolTip("\n".join(lines))

    def _wake_word_tooltip_line(self) -> str:
        if not self.config.get("wake_word_enabled"):
            return ""
        if self.wake_word.is_listening():
            return tr('Wake word armed: listening for "{phrase}"',
                       phrase=self.config.get("wake_word_phrase"))
        if self._wake_word_status == "downloading":
            return tr("Wake word: downloading model (~45 MB, one-time)…")
        if self._wake_word_status == "loading":
            return tr("Wake word: loading model…")
        if self._wake_word_status.startswith(("error", "unavailable")):
            message = self._wake_word_status.split(": ", 1)[-1]
            return tr("Wake word unavailable: {message}", message=message)
        return ""

    def hotkeys_note(self) -> str:
        if getattr(self, "hotkeys", None) and self.hotkeys.backend == "none" and self.hotkeys.error:
            return tr("Hotkey unavailable: {message}", message=self.hotkeys.error)
        return ""

    def _apply_hotkeys(self) -> None:
        self.hotkeys.apply({_RECORD_ACTION: self.config.hotkey("record")})
        self._update_tooltip()

    # -- recording state machine ---------------------------------------------

    def _hotkey_activated(self, action: str, is_press: bool) -> None:
        if action != _RECORD_ACTION:
            return
        log.debug("hotkey %s: %s", action, "press" if is_press else "release")
        mode = str(self.config.get("mode"))
        if mode == "push_to_talk":
            if is_press:
                self._start_recording()
            else:
                self._stop_recording()
        elif is_press:  # toggle: react on press only, ignore release
            self._on_record_action()

    def _start_recording(self, auto_stop: bool = False) -> None:
        if self.state != "idle":
            return
        self.wake_word.stop_listening()
        try:
            self.recorder.device = self._resolve_input_device()
            on_chunk = None
            if auto_stop:
                self._wake_word_silence_watcher.reset()
                on_chunk = self._wake_word_silence_watcher.feed
            self.recorder.start(on_chunk=on_chunk)
            if self.recorder.used_default_fallback:
                self.config.set("input_device", "")
                self.tray.showMessage(
                    "korvoice",
                    tr("Selected microphone is unavailable; using the system default."),
                    QSystemTrayIcon.MessageIcon.Information,
                )
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the daemon
            log.warning("failed to start recording: %s", exc)
            self.tray.showMessage(
                "korvoice", tr("Could not start recording: {message}", message=exc),
                                  QSystemTrayIcon.MessageIcon.Warning)
            self._maybe_start_wake_word_listening()
            return
        self.state = "recording"
        self._record_started_at = time.monotonic()
        self._update_tray_visuals()

    def _stop_recording(self) -> None:
        if self.state != "recording":
            return
        audio = self.recorder.stop()
        held_for = time.monotonic() - self._record_started_at
        log.debug("recording stopped: held %.2fs, captured %.2fs of audio",
                 held_for, len(audio) / SAMPLE_RATE)
        if len(audio) < MIN_TRANSCRIBE_SAMPLES:
            log.debug(
                "recording ignored: only %.3fs (minimum %.3fs)",
                len(audio) / SAMPLE_RATE,
                MIN_TRANSCRIBE_SAMPLES / SAMPLE_RATE,
            )
            self.state = "idle"
            self._update_tray_visuals(force_refresh=True)
            self._maybe_start_wake_word_listening()
            return
        self.state = "transcribing"
        self._transcribe_started_at = time.monotonic()
        self._update_tray_visuals()
        self.engine.transcribe(audio)

    def _on_engine_status(self, status: str) -> None:
        if status.startswith("error"):
            self.state = "idle"
            self._update_tray_visuals()

    def _on_result(self, text: str) -> None:
        elapsed = time.monotonic() - self._transcribe_started_at
        log.info("transcription finished in %.2fs", elapsed)
        log.debug("transcription result: %r", text)
        self.state = "idle"
        self._update_tray_visuals(force_refresh=True)
        self._maybe_start_wake_word_listening()
        if text:
            self.output.dispatch(text)

    def _on_engine_error(self, message: str) -> None:
        self.state = "idle"
        self._update_tray_visuals(force_refresh=True)
        self._maybe_start_wake_word_listening()
        self.tray.showMessage(
            "korvoice", tr("Recognition failed: {message}", message=message),
                              QSystemTrayIcon.MessageIcon.Warning)

    # -- wake word ------------------------------------------------------------

    def _maybe_start_wake_word_listening(self) -> None:
        if self.state == "idle" and self.config.get("wake_word_enabled"):
            self.wake_word.start_listening()

    def _on_wake_word_detected(self) -> None:
        log.debug("wake word detected")
        self._start_recording(auto_stop=True)

    def _on_wake_word_status(self, status: str) -> None:
        self._wake_word_status = status
        if status == "ready":
            self._maybe_start_wake_word_listening()
        self._update_tooltip()

    def _on_output_window(self, text: str) -> None:
        self._show_history_window().append_text(text)

    def _on_autotype_unavailable(self, message: str) -> None:
        self._autotype_note = tr("Autotype unavailable: {message}", message=message)
        self._update_tooltip()

    def _on_autotype_succeeded(self) -> None:
        if self._autotype_note:
            self._autotype_note = ""
            self._update_tooltip()

    # -- tray click / windows -------------------------------------------------

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # left click
            self._on_record_action()

    def _show_history_window(self) -> HistoryWindow:
        if self.history_window is None:
            self.history_window = HistoryWindow(self.config)
        return self.history_window

    def open_history(self) -> None:
        window = self._show_history_window()
        window.show()
        window.raise_()
        window.activateWindow()

    def open_settings(self) -> None:
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.settings_dialog = SettingsDialog(self.config)
        self.settings_dialog.saved.connect(self._settings_saved)
        self.settings_dialog.finished.connect(
            lambda _r: setattr(self, "settings_dialog", None)
        )
        self.settings_dialog.show()

    def open_about(self) -> None:
        AboutDialog().exec()

    def _settings_saved(self) -> None:
        theme.apply_theme(self.app, str(self.config.get("theme")))
        self.app.setWindowIcon(theme.make_tray_icon())
        self._rebuild_menu()
        self._apply_hotkeys()
        self.recorder.device = self._resolve_input_device()
        # A newly selected model/device starts loading right away, not on
        # the next dictation; a no-op when neither changed.
        self.engine.preload()
        self.wake_word.stop_listening()
        self.wake_word.preload()
        self._maybe_start_wake_word_listening()
        if not self.config.get("output_autotype"):
            self._autotype_note = ""
            self._update_tooltip()
        if self.history_window is not None:
            self.history_window.refresh_theme()

    # -- commands ---------------------------------------------------------------

    def handle(self, command: dict) -> None:
        action = command.get("action", "daemon")
        log.debug("command: %s", command)
        if action == "quit":
            self.quit()
        elif action == "settings":
            self.open_settings()
        elif action == "history":
            self.open_history()
        # "daemon" — just keep running

    def quit(self) -> None:
        self.tray.hide()
        self.server.close()
        QLocalServer.removeServer(SOCKET_NAME)
        self.hotkeys.stop()
        self.wake_word.stop_listening()
        if self.state == "recording":
            self.recorder.stop()
        self.output.shutdown()
        self.app.quit()

    # -- IPC ----------------------------------------------------------------

    def _on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._read_command(socket))

    def _read_command(self, socket) -> None:
        data = bytes(socket.readAll()).decode("utf-8", errors="replace")
        socket.disconnectFromServer()
        try:
            command = json.loads(data)
        except json.JSONDecodeError:
            command = {"action": "noop"}
        self.handle(command)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def install_signal_handlers(korvoice: KorvoiceApp) -> QTimer:
    """Ctrl+C/SIGTERM quit cleanly — app.exec() runs in C++ and never
    executes Python bytecode on its own, so an empty timer wakes the
    interpreter periodically for the signal handler to actually run."""
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)

    def handler(signum, _frame) -> None:
        log.info("received %s, quitting", signal.Signals(signum).name)
        korvoice.quit()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    return timer


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    command = args_to_command(args)
    setup_logging(args.debug)
    augment_path_from_login_shell()
    ensure_desktop_entry()

    if not args.check:
        if try_send_to_running(command):
            if command["action"] == "daemon":
                print("korvoice is already running.", file=sys.stderr)
            return 0
        if args.quit_:
            print("korvoice is not running.", file=sys.stderr)
            return 1

    xcb_issue = check_xcb_cursor_dependency()
    if xcb_issue:
        print(f"Error: {xcb_issue}", file=sys.stderr)
        return 1

    try:
        app = QApplication(sys.argv[:1])
        app.setApplicationName("korvoice")
        config = Config()
        set_language(str(config.get("language")))

        if args.check:
            return run_selftest(config)

        korvoice = KorvoiceApp(app, config)
        _signal_timer = install_signal_handlers(korvoice)  # noqa: F841 — keep a reference
        log.info("korvoice %s started: platform=%s, hotkeys=%s",
                 __version__, QGuiApplication.platformName(), korvoice.hotkeys.backend)
        if command["action"] != "daemon":
            korvoice.handle(command)
        code = app.exec()
        log.info("korvoice exited (code %d)", code)
        return code
    except Exception as exc:  # noqa: BLE001
        log.exception("unhandled error")
        if args.debug:
            raise
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
