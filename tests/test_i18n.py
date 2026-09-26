import pytest

from korvoice.i18n import current_language, set_language, system_language, tr


@pytest.fixture(autouse=True)
def reset_language_override():
    set_language("system")
    yield
    set_language("system")


def test_system_language_detects_russian_locale():
    assert system_language({"LANG": "ru_RU.UTF-8"}) == "ru"
    assert system_language({"LANGUAGE": "ru:en"}) == "ru"


def test_system_language_falls_back_to_english():
    assert system_language({"LANG": "en_US.UTF-8"}) == "en"
    assert system_language({"LANG": "de_DE.UTF-8"}) == "en"


def test_translation_uses_system_locale(monkeypatch):
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")

    assert tr("Settings") == "Настройки"
    assert tr("Version {version}", version="1.2") == "Версия 1.2"


def test_manual_language_override_wins_over_system(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "en")
    set_language("ru")

    assert current_language() == "ru"
    assert tr("Settings") == "Настройки"


def test_unknown_text_is_left_unchanged(monkeypatch):
    monkeypatch.setenv("LANGUAGE", "ru")
    assert tr("korvoice") == "korvoice"
