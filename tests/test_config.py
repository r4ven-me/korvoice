import pytest

from korvoice.config import GENERAL_DEFAULTS, HOTKEY_DEFAULTS, Config


def test_defaults_populated_on_first_load(config):
    for key, value in GENERAL_DEFAULTS.items():
        assert config.get(key) == value
    for action, value in HOTKEY_DEFAULTS.items():
        assert config.hotkey(action) == value


def test_config_file_written_on_first_load(config, config_dir):
    assert (config_dir / "config.yaml").exists()


def test_set_persists_across_instances(config_dir, config):
    config.set("mode", "toggle")
    config.set("output_autotype", False)
    config.set_hotkey("record", "Ctrl+Alt+V")

    reloaded = Config()
    assert reloaded.get("mode") == "toggle"
    assert reloaded.get("output_autotype") is False
    assert reloaded.hotkey("record") == "Ctrl+Alt+V"


def test_wake_word_phrase_roundtrips_cyrillic_text(config_dir, config):
    config.set("wake_word_enabled", True)
    config.set("wake_word_phrase", "привет корвойс")

    reloaded = Config()
    assert reloaded.get("wake_word_enabled") is True
    assert reloaded.get("wake_word_phrase") == "привет корвойс"


def test_get_coerces_int_type(config):
    config.set("chunk_max_seconds", "15")
    assert config.get("chunk_max_seconds") == 15
    assert isinstance(config.get("chunk_max_seconds"), int)


def test_get_coerces_bool_type(config):
    config.set("output_window", 0)
    assert config.get("output_window") is False


def test_broken_yaml_falls_back_to_defaults(config_dir):
    (config_dir / "config.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    config = Config()
    assert config.get("mode") == GENERAL_DEFAULTS["mode"]


def test_config_file_permissions_restricted(config, config_dir):
    mode = (config_dir / "config.yaml").stat().st_mode & 0o777
    assert mode == 0o600


def test_non_mapping_sections_fall_back_to_defaults(config_dir):
    (config_dir / "config.yaml").write_text("general: null\nhotkeys: [1, 2]\n", encoding="utf-8")
    config = Config()
    assert config.get("mode") == GENERAL_DEFAULTS["mode"]
    assert config.hotkey("record") == "Ctrl+Alt+Space"


def test_non_mapping_document_falls_back_to_defaults(config_dir):
    (config_dir / "config.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    config = Config()
    assert config.get("mode") == GENERAL_DEFAULTS["mode"]


def test_save_leaves_no_temporary_files(config, config_dir):
    config.set("mode", "toggle")
    assert sorted(p.name for p in config_dir.iterdir()) == ["config.yaml"]


def test_failed_save_keeps_previous_file(config, config_dir, monkeypatch):
    config.set("mode", "toggle")
    before = (config_dir / "config.yaml").read_text(encoding="utf-8")

    def broken_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr("korvoice.config.os.replace", broken_replace)
    with pytest.raises(OSError):
        config.set("mode", "push_to_talk")

    assert (config_dir / "config.yaml").read_text(encoding="utf-8") == before
    assert sorted(p.name for p in config_dir.iterdir()) == ["config.yaml"]
