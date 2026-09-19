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
