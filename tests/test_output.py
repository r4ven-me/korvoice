import shutil
import subprocess

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

import korvoice.output as output_mod
from korvoice.clipboard import SECRET_HINT_MIME, QtClipboard
from korvoice.output import OutputDispatcher, remove_fillers


@pytest.fixture(autouse=True)
def _reset_ydotool_cache():
    output_mod.ydotool_is_legacy.cache_clear()


@pytest.fixture(autouse=True)
def _join_autotype_workers(monkeypatch):
    """Tests may end while an autotype subprocess still runs; its QThread
    must finish before the dispatcher owning it is garbage-collected."""
    dispatchers = []
    original_init = OutputDispatcher.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        dispatchers.append(self)

    monkeypatch.setattr(OutputDispatcher, "__init__", tracking_init)
    yield
    for dispatcher in dispatchers:
        dispatcher.shutdown()


def _which_only(*names):
    return lambda name: f"/usr/bin/{name}" if name in names else None


def test_remove_fillers_cleans_common_hesitation_variants():
    assert remove_fillers("Я хотел, э-э, проверить это.") == "Я хотел проверить это."
    assert remove_fillers("Эм, это ээ хороший результат") == "это хороший результат"
    assert remove_fillers("Ну, м-м, возможно") == "Ну возможно"


def test_remove_fillers_does_not_change_parts_of_words():
    text = "Это поэма про Эмму и ММА."
    assert remove_fillers(text) == text


def test_autotype_command_x11_uses_xdotool(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    monkeypatch.setattr(
        shutil, "which", lambda name: f"/usr/bin/{name}" if name == "xdotool" else None
    )
    dispatcher = OutputDispatcher(config)

    command = dispatcher._autotype_command("привет")

    assert command == ["/usr/bin/xdotool", "key", "--clearmodifiers", "ctrl+v"]


def test_autotype_command_x11_missing_xdotool_emits_unavailable(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    dispatcher = OutputDispatcher(config)
    messages = []
    dispatcher.autotype_unavailable.connect(messages.append)

    command = dispatcher._autotype_command("hello")

    assert command is None
    assert len(messages) == 1
    assert "xdotool" in messages[0]


def test_autotype_command_wayland_pastes_with_ydotool_keycodes(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(shutil, "which", _which_only("ydotool", "wl-copy", "wl-paste"))
    monkeypatch.setattr(output_mod, "ydotool_is_legacy", lambda _tool: False)
    dispatcher = OutputDispatcher(config)

    command = dispatcher._autotype_command("привет")

    assert command == ["/usr/bin/ydotool", "key", "29:1", "47:1", "47:0", "29:0"]


def test_autotype_command_wayland_legacy_ydotool_uses_key_names(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(shutil, "which", _which_only("ydotool", "wl-copy", "wl-paste"))
    monkeypatch.setattr(output_mod, "ydotool_is_legacy", lambda _tool: True)
    dispatcher = OutputDispatcher(config)

    assert dispatcher._autotype_command("привет") == ["/usr/bin/ydotool", "key", "ctrl+v"]


def test_autotype_command_wayland_missing_wl_clipboard_emits_unavailable(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(shutil, "which", _which_only("ydotool"))
    dispatcher = OutputDispatcher(config)
    messages = []
    dispatcher.autotype_unavailable.connect(messages.append)

    assert dispatcher._autotype_command("hello") is None
    assert len(messages) == 1
    assert "wl-copy" in messages[0]


@pytest.mark.parametrize(
    ("usage", "legacy"),
    [
        ("Usage: ydotool <cmd> <args>\nAvailable commands:\n  type\n  recorder\n", True),
        ("Usage: ydotool <cmd> <args>\nAvailable commands:\n  click\n  key\n  bakers\n", False),
    ],
)
def test_ydotool_version_detection(monkeypatch, usage, legacy):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=usage, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert output_mod.ydotool_is_legacy("/usr/bin/ydotool") is legacy


def test_autotype_command_wayland_missing_ydotool_emits_unavailable(config, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "wayland"))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    dispatcher = OutputDispatcher(config)
    messages = []
    dispatcher.autotype_unavailable.connect(messages.append)

    command = dispatcher._autotype_command("hello")

    assert command is None
    assert len(messages) == 1
    assert "ydotool" in messages[0]


def test_dispatch_clipboard_only(config, qapp):
    config.set("output_clipboard", True)
    config.set("output_autotype", False)
    config.set("output_window", False)
    dispatcher = OutputDispatcher(config)

    dispatcher.dispatch("test text")

    assert QGuiApplication.clipboard().text() == "test text"


def test_unavailable_x11_autotype_does_not_change_clipboard(config, qapp, monkeypatch):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    config.set("output_clipboard", False)
    dispatcher = OutputDispatcher(config)
    monkeypatch.setattr(dispatcher, "_autotype_command", lambda _text: None)
    QGuiApplication.clipboard().setText("previous")

    dispatcher._autotype("recognized")

    assert QGuiApplication.clipboard().text() == "previous"


def test_autotype_restores_all_previous_clipboard_formats(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    original.setHtml("<b>previous</b>")
    QGuiApplication.clipboard().setMimeData(original)
    dispatcher._temporary_clipboard_original = QtClipboard().snapshot()
    dispatcher._clipboard_generation = 1
    QGuiApplication.clipboard().setText("recognized")

    dispatcher._restore_clipboard("recognized", 1)

    restored = QGuiApplication.clipboard().mimeData()
    assert restored.text() == "previous"
    assert restored.html() == "<b>previous</b>"


def test_autotype_does_not_overwrite_new_user_clipboard_text(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    dispatcher._temporary_clipboard_original = original
    dispatcher._clipboard_generation = 1
    QGuiApplication.clipboard().setText("copied by user")

    dispatcher._restore_clipboard("recognized", 1)

    assert QGuiApplication.clipboard().text() == "copied by user"


def test_stale_autotype_operation_cannot_restore_clipboard(config, qapp):
    dispatcher = OutputDispatcher(config)
    original = QMimeData()
    original.setText("previous")
    dispatcher._temporary_clipboard_original = original
    dispatcher._clipboard_generation = 2
    QGuiApplication.clipboard().setText("newer autotype")

    dispatcher._restore_clipboard("older autotype", 1)

    assert QGuiApplication.clipboard().text() == "newer autotype"


def test_dispatch_removes_fillers_before_suffix(config, qapp):
    config.set("remove_fillers", True)
    config.set("output_suffix", " ")
    config.set("output_clipboard", True)
    config.set("output_autotype", False)
    config.set("output_window", False)
    dispatcher = OutputDispatcher(config)

    dispatcher.dispatch("Проверяю, э-э, результат")

    assert QGuiApplication.clipboard().text() == "Проверяю результат "


def test_dispatch_appends_configured_suffix_to_every_sink(config, qapp, monkeypatch):
    config.set("output_suffix", "\n")
    config.set("output_clipboard", True)
    config.set("output_autotype", True)
    config.set("output_window", True)
    dispatcher = OutputDispatcher(config)
    autotyped = []
    delivered = []
    monkeypatch.setattr(dispatcher, "_autotype", autotyped.append)
    dispatcher.delivered.connect(delivered.append)

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized\n"
    assert autotyped == ["recognized\n"]
    assert delivered == ["recognized\n"]


def test_dispatch_window_only_emits_delivered(config, qapp):
    config.set("output_clipboard", False)
    config.set("output_autotype", False)
    config.set("output_window", True)
    dispatcher = OutputDispatcher(config)
    delivered = []
    dispatcher.delivered.connect(delivered.append)

    dispatcher.dispatch("test text")

    assert delivered == ["test text"]


def test_dispatch_empty_text_is_noop(config, qapp):
    config.set("output_clipboard", True)
    dispatcher = OutputDispatcher(config)
    QGuiApplication.clipboard().setText("unchanged")

    dispatcher.dispatch("")

    assert QGuiApplication.clipboard().text() == "unchanged"


def _hint():
    data = QGuiApplication.clipboard().mimeData()
    return bytes(data.data(SECRET_HINT_MIME))


def _x11_autotype_dispatcher(config, monkeypatch, *, keep: bool, hide: str):
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "xcb"))
    config.set("output_clipboard", keep)
    config.set("output_autotype", True)
    config.set("output_window", False)
    config.set("clipboard_hide_history", hide)
    dispatcher = OutputDispatcher(config)
    monkeypatch.setattr(dispatcher, "_autotype_command", lambda _text: ["true"])
    return dispatcher


def test_temporary_paste_text_is_hidden_from_clipboard_history(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=False, hide="temporary")
    QGuiApplication.clipboard().setText("previous")

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized"
    assert _hint() == b"secret"


def test_kept_text_is_not_hidden_in_temporary_mode(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="temporary")

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized"
    assert _hint() == b""


def test_all_mode_hides_kept_text_too(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="all")

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized"
    assert _hint() == b"secret"


def test_none_mode_never_hides(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=False, hide="none")

    dispatcher.dispatch("recognized")

    assert QGuiApplication.clipboard().text() == "recognized"
    assert _hint() == b""


def test_kept_text_is_put_in_clipboard_only_once(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="none")
    changes = []
    QGuiApplication.clipboard().dataChanged.connect(lambda: changes.append(1))

    dispatcher.dispatch("recognized")

    assert len(changes) == 1


def test_temporary_paste_restores_previous_clipboard(config, qapp, qtbot, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=False, hide="temporary")
    QGuiApplication.clipboard().setText("previous")

    dispatcher.dispatch("recognized")

    qtbot.waitUntil(lambda: QGuiApplication.clipboard().text() == "previous", timeout=3000)
    assert _hint() == b""


def test_successful_autotype_emits_succeeded(config, qapp, qtbot, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="none")

    with qtbot.waitSignal(dispatcher.autotype_succeeded, timeout=3000):
        dispatcher.dispatch("recognized")


def test_failed_autotype_reports_unavailable(config, qapp, qtbot, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="none")
    monkeypatch.setattr(dispatcher, "_autotype_command", lambda _text: ["false"])

    with qtbot.waitSignal(dispatcher.autotype_unavailable, timeout=3000):
        dispatcher.dispatch("recognized")


def test_shutdown_waits_for_running_autotype(config, qapp, monkeypatch):
    dispatcher = _x11_autotype_dispatcher(config, monkeypatch, keep=True, hide="none")
    monkeypatch.setattr(dispatcher, "_autotype_command", lambda _text: ["sleep", "0.3"])
    dispatcher.dispatch("recognized")
    worker = dispatcher._autotype_workers[0]

    dispatcher.shutdown()

    assert worker.isFinished()
    assert dispatcher._autotype_workers == []
