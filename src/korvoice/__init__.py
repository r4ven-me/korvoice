"""korvoice — push-to-talk / toggle Russian voice input for Linux.

PySide6 tray application: records from the microphone on a global hotkey,
transcribes with the local GigaAM speech model (no cloud), delivers the
text to the clipboard, autotype and/or a small history window.
"""

from importlib.metadata import PackageNotFoundError, metadata, version


def _project_url(all_urls: list[str], name: str) -> str:
    """Picks one entry out of importlib.metadata's "Project-URL" list
    (each formatted "Name, https://..."), matching pyproject.toml's
    [project.urls] table by key."""
    return next(
        (
            url.split(",", 1)[1].strip()
            for url in all_urls
            if url.split(",", 1)[0].strip() == name
        ),
        "",
    )


try:
    # Single source of truth: pyproject.toml's [project] table, read back
    # from the installed package's metadata (populated from it at build
    # time) — hardcoding copies of these here would drift the moment
    # pyproject.toml changes and this file doesn't.
    __version__ = version("korvoice")
    _metadata = metadata("korvoice")
    __description__ = _metadata.get("Summary", "")
    __author__ = _metadata.get("Author", "")
    __license__ = _metadata.get("License", "")
    _urls = _metadata.get_all("Project-URL", [])
    __homepage__ = _project_url(_urls, "Homepage")
    __repository__ = _project_url(_urls, "Repository")
    __telegram__ = _project_url(_urls, "Telegram")
    __chat__ = _project_url(_urls, "Chat")
except PackageNotFoundError:
    # Running from a source checkout, not installed.
    __version__ = "0.0.0+unknown"
    __description__ = ""
    __author__ = ""
    __license__ = ""
    __homepage__ = ""
    __repository__ = ""
    __telegram__ = ""
    __chat__ = ""
