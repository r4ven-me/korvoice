"""Shared fixtures: isolated config and headless Qt."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import korvoice.config as config_mod
from korvoice.config import Config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Redirects the korvoice config into a temporary directory."""
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    return tmp_path


@pytest.fixture
def config(config_dir):
    return Config()


@pytest.fixture(autouse=True)
def _release_python_clipboard_data():
    """Leaves only C++-created clipboard data behind after each test.

    Under QT_QPA_PLATFORM=offscreen the clipboard contents live in a Qt
    global static destroyed by exit() — after Python has finalized. A
    QMimeData constructed from Python (the "secret" hint, a restored
    snapshot) calls back into shiboken from its destructor and segfaults
    the process there, after every test has passed (seen in CI, and
    locally under CPU load). Real xcb/wayland clipboards are owned by the
    platform integration and torn down earlier, so the app is unaffected.
    """
    yield
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is not None and QGuiApplication.clipboard() is not None:
        QGuiApplication.clipboard().setText("")


@pytest.fixture(autouse=True)
def _isolate_autostart(tmp_path, monkeypatch):
    """Settings/app must not touch the real ~/.config/autostart,
    ~/.local/share/applications or ~/.local/share/icons."""
    import korvoice.app as app_mod
    import korvoice.settings_dialog as settings_dialog
    import korvoice.theme as theme_mod

    monkeypatch.setattr(
        settings_dialog, "AUTOSTART_FILE", tmp_path / "autostart" / "korvoice.desktop"
    )
    monkeypatch.setattr(app_mod, "DESKTOP_FILE", tmp_path / "applications" / "korvoice.desktop")
    monkeypatch.setattr(theme_mod, "ICON_FILE", tmp_path / "icons" / "korvoice.png")
