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
