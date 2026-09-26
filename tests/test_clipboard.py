import subprocess

import pytest

from korvoice.clipboard import WlClipboard


class FakeWlClipboard:
    """Stands in for wl-copy/wl-paste: records calls, keeps one selection."""

    def __init__(self, selection=None):
        self.selection = selection  # (mime type, bytes) or None
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append((args, kwargs))
        tool, *rest = args
        if tool == "wl-copy":
            if rest == ["--clear"]:
                self.selection = None
            else:
                self.selection = (rest[rest.index("--type") + 1], kwargs["input"])
            return subprocess.CompletedProcess(args, 0)
        if self.selection is None:
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"Nothing is copied")
        mime_type, data = self.selection
        if rest == ["--list-types"]:
            return subprocess.CompletedProcess(args, 0, stdout=f"{mime_type}\n".encode())
        return subprocess.CompletedProcess(args, 0, stdout=data)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeWlClipboard()
    monkeypatch.setattr(subprocess, "run", fake.run)
    return fake


def test_set_text_does_not_pipe_wl_copy_output(fake):
    # wl-copy forks a background server; piped stdout would make run()
    # wait for that server to exit.
    WlClipboard("wl-copy", "wl-paste").set_text("привет")

    args, kwargs = fake.calls[0]
    assert args == ["wl-copy", "--type", "text/plain;charset=utf-8"]
    assert kwargs["input"] == "привет".encode()
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_snapshot_and_restore_round_trip(fake):
    clipboard = WlClipboard("wl-copy", "wl-paste")
    fake.selection = ("image/png", b"\x89PNG")

    snapshot = clipboard.snapshot()
    clipboard.set_text("recognized")
    assert clipboard.text() == "recognized"
    clipboard.restore(snapshot)

    assert fake.selection == ("image/png", b"\x89PNG")


def test_restoring_empty_snapshot_clears_clipboard(fake):
    clipboard = WlClipboard("wl-copy", "wl-paste")

    snapshot = clipboard.snapshot()
    clipboard.set_text("recognized")
    clipboard.restore(snapshot)

    assert fake.selection is None


def test_text_is_none_when_wl_paste_is_missing(monkeypatch):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("wl-paste")

    monkeypatch.setattr(subprocess, "run", missing)

    assert WlClipboard("wl-copy", "wl-paste").text() is None
