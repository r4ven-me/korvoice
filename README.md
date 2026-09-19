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
  `GlobalShortcuts` portal on Wayland. Autotype on Wayland needs `ydotool`
  (see Configuration below) — clipboard and the history window always work
  regardless of session type.
- **Autostart** — optional login autostart entry, toggled from Settings.

## Quick start

```bash
# CPU-only by default — the plain "torch" wheel from PyPI bundles ~1.5-2 GB
# of CUDA libraries even without a GPU; --pip-args routes pip at a CPU-only
# index instead. See "GPU acceleration" below if you have an NVIDIA card.
pipx install "korvoice @ git+https://github.com/r4ven-me/korvoice" \
  --pip-args="--extra-index-url https://download.pytorch.org/whl/cpu"

korvoice          # starts the tray daemon
korvoice --check  # environment diagnostics (mic, ffmpeg, hotkey backend, gigaam)
```

The first recording triggers a one-time GigaAM weight download (~1 GB,
cached in `~/.cache/gigaam/`) — expect a pause the first time you use the
hotkey.

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
| Tray icon colour | `auto` / `dark` / `light` | `auto` |
| Recording mode | `push_to_talk` / `toggle` | `push_to_talk` |
| Record hotkey | any `Ctrl+Alt+...`-style sequence | `Ctrl+Alt+Space` |
| Model | `v3_e2e_ctc` / `v3_e2e_rnnt` / `v3_ctc` / `v3_rnnt` | `v3_e2e_ctc` |
| Inference device | `auto` / `cpu` / `cuda` | `auto` |
| Max chunk length | 5-24 seconds | `20` |
| Microphone | any input device PortAudio reports | system default |
| Output: clipboard / autotype / history window | on/off, independently | all on |
| Autostart at login | on/off | off |

### GPU acceleration

NVIDIA (CUDA) works out of the box once a CUDA-enabled `torch` is
installed — reinstall without the CPU-only `--pip-args` flag above, or
`pipx runpip korvoice install torch` into the existing venv. Set
Settings → Model → Inference device to `cuda` (or leave `auto`).

AMD is **not supported**: the RX580 and similar Polaris-generation cards
(`gfx803`) were dropped from official ROCm support in ROCm 6.0+, and the
only path back is a third-party patched ROCm/PyTorch Docker image — out of
scope for this project for now.

### Autotype on Wayland

X11 autotype works out of the box (`pynput`). Wayland has no equivalent
portal for synthetic keyboard input, so autotype there shells out to
[`ydotool`](https://github.com/ktr0731/ydotool), which needs its daemon
(`ydotoold`) running with access to `/dev/uinput`. If that isn't set up,
autotype silently fails and the reason shows up in the tray tooltip —
clipboard and the history window are unaffected either way.

## Development

```bash
make install
make check     # lint + test
```

No `make typecheck`/mypy here — see the comment in `pyproject.toml`'s
`[project.optional-dependencies]`: strict typechecking is this author's
convention for server/backend projects, optional for a small GUI utility.

No `.github/workflows/` yet either: korvoice depends on GigaAM via a
`git+https` direct reference (the only place the `v3_e2e_ctc` model line
currently lives — see `pyproject.toml`), which PyPI rejects in uploaded
package metadata, so there's no PyPI project to publish to yet.

## Author

[Ivan Cherniy](https://r4ven.me) — [r4ven.me](https://r4ven.me).
Source: [github.com/r4ven-me/korvoice](https://github.com/r4ven-me/korvoice).

## Credits

Speech recognition by [GigaAM](https://github.com/salute-developers/GigaAM)
(Sber/SberDevices), MIT licensed — not affiliated with korvoice.

## License

GNU General Public License v3.0 or later (GPL-3.0-or-later), see
[LICENSE](LICENSE).
