import json

import korvoice.windows as windows_mod
from korvoice.windows import HistoryWindow


def test_history_persists_and_reloads(config, qapp, tmp_path, monkeypatch):
    history_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(windows_mod, "HISTORY_FILE", history_file)
    config.set("history_persistent", True)
    first = HistoryWindow(config)

    first.append_text("Первая строка\nи продолжение")

    assert history_file.exists()
    stored = json.loads(history_file.read_text(encoding="utf-8").strip())
    assert stored["text"] == "Первая строка\nи продолжение"

    restored = HistoryWindow(config)
    assert "Первая строка\nи продолжение" in restored.text.toPlainText()


def test_history_is_not_written_when_persistence_is_disabled(config, qapp, tmp_path, monkeypatch):
    history_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(windows_mod, "HISTORY_FILE", history_file)
    config.set("history_persistent", False)
    window = HistoryWindow(config)

    window.append_text("temporary")

    assert not history_file.exists()


def test_clear_removes_saved_history(config, qapp, tmp_path, monkeypatch):
    history_file = tmp_path / "history.jsonl"
    monkeypatch.setattr(windows_mod, "HISTORY_FILE", history_file)
    config.set("history_persistent", True)
    window = HistoryWindow(config)
    window.append_text("saved")

    window._clear()

    assert window.text.toPlainText() == ""
    assert not history_file.exists()


def test_history_loader_skips_corrupt_lines(config, qapp, tmp_path, monkeypatch):
    history_file = tmp_path / "history.jsonl"
    history_file.write_text(
        'not json\n{"timestamp":"2026-09-22T12:00:00+03:00","text":"valid"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(windows_mod, "HISTORY_FILE", history_file)
    config.set("history_persistent", True)

    window = HistoryWindow(config)

    assert "valid" in window.text.toPlainText()
