# korvoice

**Push-to-talk (or toggle) Russian voice input for Linux, powered by the
local [GigaAM](https://github.com/salute-developers/GigaAM) speech model.**
Hold a hotkey, speak, release — the recognized text lands in the clipboard,
gets typed into whatever window has focus, and/or shows up in a small
history window. Everything runs on-device; nothing is sent anywhere, aside
from two one-time first-use downloads of static model files — GigaAM's own
~1 GB weights, and (only if you enable it) the optional wake-word
listener's ~45 MB Vosk model below. Neither your voice nor any recognized
text ever leaves the device.

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
  `GlobalShortcuts` portal on Wayland. Autotype pastes with `xdotool` (X11)
  or `ydotool` + `wl-clipboard` (Wayland) — see Autotype below — while the
  history window works regardless of session type or installed tools.
- **Clipboard-history friendly** — text that autotype only puts in the
  clipboard temporarily is marked so that clipboard managers skip it
  (configurable, see Clipboard managers below).
- **Autostart** — optional login autostart entry, toggled from Settings.
- **Optional wake-word activation** — say a configured Russian phrase to
  start recording without touching the hotkey, works in either recording
  mode (auto-stops after a trailing pause, since there's no hotkey release
  to key off of). Fully offline via [Vosk](https://alphacephei.com/vosk/)'s
  grammar-constrained recognizer, the only practical way to spot an
  arbitrary Russian phrase without the cloud — expect more false
  accepts/rejects than a dedicated wake-word engine (Porcupine,
  openWakeWord) would give; that's the deliberate tradeoff for staying
  fully local and not being limited to a handful of English preset words.
  See Wake word (optional) below.

## Quick start

System packages first (Debian/Ubuntu/Mint names; use your distro's
equivalents):

```bash
# required: audio capture, audio decoding for GigaAM, Qt's X11 plugin
sudo apt install libportaudio2 ffmpeg libxcb-cursor0
# autotype on X11
sudo apt install xdotool
# autotype on Wayland (plus a running ydotoold, see Autotype below)
sudo apt install wl-clipboard ydotool
```

Then korvoice itself:

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
korvoice --check      # diagnostics: tray, hotkey backend, mic, ffmpeg, gigaam, wake word
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
| Hide from clipboard history | only temporary paste text / all recognized text / nothing | only temporary paste text |
| Keep history between restarts | on/off (last 1000 entries) | off |
| Autostart at login | on/off | off |
| Wake word enabled | on/off | off |
| Wake phrase | free text (Russian phrase) | empty |

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

Autotype puts the text in the clipboard and sends a single `Ctrl+V` instead
of typing it key by key: `xdotool type` handles Cyrillic by repeatedly
changing the X11 keymap and can freeze the whole desktop, and `ydotool type`
only knows the US layout, so it can't type Cyrillic at all. Both backends are
external system tools, not pip dependencies:

- **X11**: [`xdotool`](https://github.com/jordansissel/xdotool).
- **Wayland**: [`wl-clipboard`](https://github.com/bugaevc/wl-clipboard)
  (`wl-copy`/`wl-paste`) and [`ydotool`](https://github.com/ReimuNotMoe/ydotool),
  whose daemon (`ydotoold`) needs to be running with access to
  `/dev/uinput`. Korvoice detects whether it's ydotool 0.1.x (what
  Debian/Ubuntu ship) or 1.x and uses the matching `key` syntax.

When “keep in clipboard” is off, the previous clipboard contents come back
right after the paste (on Wayland, one format of them — text preferred —
since `wl-copy` offers a single type).

Terminals usually paste with `Ctrl+Shift+V`, not `Ctrl+V`, so autotype into
a terminal may do nothing — use the clipboard output there.

If the relevant tool isn't set up, autotype fails and the reason shows up in
the tray tooltip until the next successful autotype — clipboard and the
history window are unaffected either way.

### Wake word (optional)

Lets korvoice start recording when it hears a phrase you configure, instead
of only via the hotkey. Entirely offline (see Features above for the
accuracy tradeoff versus a dedicated wake-word engine). Setup:

```bash
pipx inject korvoice vosk
```

That's the only manual step — the recognition model
(`vosk-model-small-ru`, ~45 MB, from
[alphacephei.com](https://alphacephei.com/vosk/models)) downloads and
unpacks itself into `~/.local/share/korvoice/` automatically the first
time you enable the feature, the same way GigaAM's own weights already do
on first use.

Then in Settings → General, check "Enable wake word" and type a short,
distinctive Russian phrase into "Wake phrase" (e.g. "привет корвойс") — a
longer, unusual phrase triggers fewer false positives than a short common
one. The tray tooltip shows "downloading…" then "loading…" the first time,
before switching to "listening". `korvoice --check` reports whether `vosk`
itself is installed (the one thing it can't fix automatically) and whether
the model has been downloaded yet.

### Clipboard managers

Because autotype goes through the clipboard, a clipboard manager would see
every dictated phrase, even with “keep in clipboard” off. Korvoice therefore
marks clipboard text with `x-kde-passwordManagerHint: secret` — the same hint
password managers such as KeePassXC use — which Klipper, CopyQ, cliphist and
other managers that honour it take as “don't record this”. Settings → Output
→ “Hide from clipboard history”:

- **Only temporary paste text** (default) — hide the text autotype puts in
  the clipboard just to paste it; text you chose to keep in the clipboard is
  recorded as usual.
- **All recognized text** — also hide the kept text.
- **Nothing** — mark nothing (the old behaviour).

Managers that ignore the hint still record the text; the only alternative is
turning autotype off. The hint is X11-only for now: `wl-copy` can offer just
one MIME type, so on Wayland the text can't carry it.

## Development

```bash
make install
make check     # lint + test
```

There is no mypy/typecheck step (see the comment in `pyproject.toml`).

### Publishing to PyPI

`.github/workflows/publish.yml` tests and builds the package on pull requests,
`main` pushes and manual runs. Pushing a tag matching the version in
`pyproject.toml` (for example, `v0.1.0`) additionally publishes the wheel and
source distribution to PyPI using trusted publishing — no API token is stored
in GitHub. `make release` moves an existing tag of the same version to the
new commit, which allows retrying a failed workflow; it cannot overwrite a
version already accepted by PyPI.

Configure a PyPI trusted publisher with owner `r4ven-me`, repository
`korvoice`, workflow `publish.yml`, and environment `pypi`. The required
GigaAM Git installation remains a documented second step because PyPI rejects
direct Git dependencies and its `gigaam` 0.1.0 package lacks the v3/e2e models.

## Links

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
