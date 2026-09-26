# korvoice

**Push-to-talk (or toggle) Russian voice input for Linux, powered by the
local [GigaAM](https://github.com/salute-developers/GigaAM) speech model.**
Hold a hotkey, speak, release — the recognized text lands in the clipboard,
gets typed into whatever window has focus, and/or shows up in a small
history window. Everything runs on-device; nothing is sent anywhere.

## Features

- **Push-to-talk or toggle** — hold the hotkey to record and release to
  transcribe, or press once to start and again to stop. One mode is active
  at a time, switchable from Settings or the tray menu, on the same hotkey.
- **Three independent output sinks** — clipboard, autotype into the
  focused window, and a history window, any combination at once.
- **Local GigaAM recognition** — `v3_e2e_ctc` by default (fast, with
  punctuation and case restoration); switch to an RNNT or non-punctuated
  variant in Settings → Model. CPU/CUDA device is auto-detected.
- **Long recordings handled without an external VAD model** — GigaAM
  refuses audio over ~25s in one call; longer recordings are split at the
  nearest detected pause instead of a hard mid-word cut.
- **Tray + Nord GUI settings** — system / Nord dark / Nord light theme,
  same visual language across the settings dialog and history window.
- **X11 and Wayland** — global hotkey via direct `XGrabKey` on X11, the
  `GlobalShortcuts` portal on Wayland. Autotype shells out to `xdotool`
  (X11) or `ydotool` (Wayland) — see Configuration below — clipboard and
  the history window always work regardless of session type or whether
  either tool is installed.
- **Autostart** — optional login autostart entry, toggled from Settings.

## Quick start

```bash
pipx install korvoice

# Required ASR backend. The GigaAM release currently on PyPI lacks the v3/e2e
# models used by korvoice, so install its current GitHub version into the same
# pipx environment. The extra index selects CPU-only PyTorch wheels.
pipx runpip korvoice install \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  "gigaam[torch] @ git+https://github.com/salute-developers/GigaAM.git"

korvoice          # starts the tray daemon
korvoice --check  # environment diagnostics (mic, ffmpeg, hotkey backend, gigaam)
```

The GigaAM model (weights ~1 GB, cached in `~/.cache/gigaam/`) downloads
and loads in the background as soon as the daemon starts, not on first
use — the first hotkey press only has to wait for that warm-up if you
press it within the first few seconds of starting korvoice.

## Usage / Configuration / CLI

```bash
korvoice              # start (or, if already running, no-op) the tray daemon
korvoice --settings   # open settings in the running instance
korvoice --history    # open the history window in the running instance
korvoice --quit       # quit the running instance
korvoice --check      # diagnostics: tray, hotkey backend, mic, ffmpeg, gigaam
korvoice --debug      # verbose logging (also to ~/.local/state/korvoice/korvoice.log)
```

Settings (`~/.config/korvoice/config.yaml`, YAML, written on every change):

| Setting | Values | Default |
| --- | --- | --- |
| Theme | `system` / `nord-dark` / `nord-light` | `system` |
| Interface language | `system` / `ru` / `en` | `system` |
| Tray icon colour | `auto` / `dark` / `light` | `auto` |
| Recording mode | `push_to_talk` / `toggle` | `push_to_talk` |
| Record hotkey | `Ctrl+Alt+...`-style combination, or a single modifier (Right/Left Ctrl/Shift/Alt/Super) | `Ctrl+Alt+Space` |
| Model | `v3_e2e_ctc` / `v3_e2e_rnnt` / `v3_ctc` / `v3_rnnt` | `v3_e2e_ctc` |
| Inference device | `auto` / `cpu` / `cuda` | `auto` |
| Max chunk length | 5-24 seconds | `20` |
| Microphone | any input device PortAudio reports | system default |
| Output: keep in clipboard / autotype / history window | on/off, independently | all on |
| Text ending | nothing / space / new line / blank line / custom text | nothing |
| Keep history between restarts | on/off (last 1000 entries) | off |
| Autostart at login | on/off | off |

### GPU acceleration

For NVIDIA CUDA, omit the PyTorch CPU index when installing GigaAM:

```bash
pipx runpip korvoice install \
  "gigaam[torch] @ git+https://github.com/salute-developers/GigaAM.git"
```

Then set Settings → Model → Inference device to `cuda` (or leave `auto`).

AMD is **not supported**: the RX580 and similar Polaris-generation cards
(`gfx803`) were dropped from official ROCm support in ROCm 6.0+, and the
only path back is a third-party patched ROCm/PyTorch Docker image — out of
scope for this project for now.

### Autotype

Both backends are external system tools, not pip dependencies:

- **X11**: [`xdotool`](https://github.com/jordansissel/xdotool)
  (`sudo apt install xdotool` or your distro's equivalent). Korvoice puts
  the text in Qt's clipboard and asks `xdotool` to send one `Ctrl+V` rather
  than emulating every character: `xdotool type` repeatedly changes the X11
  keymap for Cyrillic and can freeze the whole desktop. Therefore X11
  autotype uses the clipboard temporarily; when “keep in clipboard” is off,
  the previous MIME contents are restored after pasting (clipboard-history
  managers may still record the temporary text).
- **Wayland**: [`ydotool`](https://github.com/ktr0731/ydotool), whose
  daemon (`ydotoold`) needs to be running with access to `/dev/uinput`.

If the relevant tool isn't set up, autotype silently fails and the reason
shows up in the tray tooltip — clipboard and the history window are
unaffected either way.

## Development

```bash
make install
make check     # lint + test
```

No `make typecheck`/mypy here — see the comment in `pyproject.toml`'s
`[project.optional-dependencies]`: strict typechecking is this author's
convention for server/backend projects, optional for a small GUI utility.

### Publishing to PyPI

`.github/workflows/publish.yml` tests and builds the package on pull requests,
`main` pushes and manual runs. Pushing a tag matching the version in
`pyproject.toml` (for example, `v0.1.0`) additionally publishes the wheel and
source distribution to PyPI using trusted publishing — no API token is stored
in GitHub.

Configure a PyPI trusted publisher with owner `r4ven-me`, repository
`korvoice`, workflow `publish.yml`, and environment `pypi`. The required
GigaAM Git installation remains a documented second step because PyPI rejects
direct Git dependencies and its `gigaam` 0.1.0 package lacks the v3/e2e models.

## Links

Project presentation convention: whenever project contacts are listed, keep
all four links together:

- Website: [r4ven.me](https://r4ven.me)
- GitHub: [github.com/r4ven-me/korvoice](https://github.com/r4ven-me/korvoice)
- Telegram channel: [t.me/r4ven_me](https://t.me/r4ven_me)
- Telegram chat: [t.me/r4ven_me_chat](https://t.me/r4ven_me_chat)

## Author

[Ivan Cherniy](https://r4ven.me).

## Credits

Speech recognition by [GigaAM](https://github.com/salute-developers/GigaAM)
(Sber/SberDevices), MIT licensed — not affiliated with korvoice.

## License

GNU General Public License v3.0 or later (GPL-3.0-or-later), see
[LICENSE](LICENSE).
