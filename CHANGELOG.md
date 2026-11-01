# Changelog

## [Unreleased]

- Without a working audio system (no PortAudio, no sound server) korvoice still
  starts: `--version`, `--check` and Settings work, `--check` reports the
  reason, and recording fails with a clear message instead of an import crash.

## [1.0.7] - 2026-11-01

- CI: run on `ubuntu-24.04` instead of `ubuntu-latest`. The 26.04 image ships
  a PortAudio that fails to initialize without a sound server, which broke
  the test collection. v1.0.6 was tagged but never published to PyPI.

## [1.0.6] - 2026-11-01

- Removed the wake-word feature (Vosk listener, its settings, the `wakeword`
  extra); obsolete `wake_word_*` keys are dropped from `config.yaml`.
- Autotype no longer sends the paste shortcut when the recognized text could
  not be put in the clipboard (it used to paste the previous contents).
- Quitting waits for the model-load/transcription threads instead of
  destroying running ones.
- A second `korvoice` no longer deletes a running instance's socket; the
  socket is only replaced when it is verifiably stale.
- IPC commands are newline-delimited, size-limited and time-limited.
- `Recorder.stop()` survives PortAudio errors (e.g. an unplugged microphone).
- Boolean settings given as strings (`"false"`) are parsed correctly.
- `--debug` logs the length of a transcription, not its text.
- CI smoke-tests the built wheel in a clean virtualenv.
- X11 autotype is skipped when the focused window changed while the speech
  was being recognized, so text no longer lands in the wrong window.
- Tests: end-to-end hotkey → recorder → ASR → output flow.
- The tray icon is full-color by default; `dark`/`light` select monochrome variants.
- GigaAM is installed at a pinned commit; `make release` needs a clean tree and
  never moves an existing tag; GitHub Actions are pinned to commit SHAs.

## [1.0.5] - 2026-10-02

- Configurable autotype paste shortcut: Ctrl+V or Ctrl+Shift+V (terminals).
- Optional wake-word activation via offline Vosk (removed again after 1.0.5).
- Fixed the tray icon missing one refresh after idle/suspend on Cinnamon.

## [1.0.2] - 2026-09-26

- Autotype clipboard restore keeps every previous format and is compatible
  with all supported PySide6 versions.

## [1.0.1] - 2026-09-26

- Tray icon theming fix; `--debug` logs the transcription time at info level.

## [1.0.0] - 2026-09-26

- Clipboard managers: text that autotype puts in the clipboard only
  temporarily is now marked `x-kde-passwordManagerHint: secret`, so Klipper,
  CopyQ, cliphist and other managers that honour the hint don't record it.
  New setting Output → "Hide from clipboard history" (only temporary paste
  text / all recognized text / nothing). X11 only.
- Wayland autotype now pastes through `wl-clipboard` + one `ydotool key`
  Ctrl+V instead of `ydotool type`, which couldn't produce Cyrillic. The
  `key` syntax of ydotool 0.1.x and 1.x is detected automatically. `wl-clipboard` is now required for
  Wayland autotype; the clipboard output uses it too when installed.
- Wayland hotkey: saving settings no longer leaves the previous
  GlobalShortcuts portal session alive — before, each save made one key
  press arrive several times, which broke toggle mode.
- English UI: the hotkey, autotype, chunk-length and model notes showed their
  internal ids ("X11 hotkey note" etc.) instead of text.
- The "Autotype unavailable" tray tooltip note is cleared after the next
  successful autotype (or when autotype is switched off).
- Changing the model or device in Settings starts loading it in the
  background right away; a change made while a model was still loading is
  no longer ignored.
- The config file is written atomically, and a config whose sections aren't
  mappings falls back to defaults instead of crashing at startup.
- The autostart entry respects `XDG_CONFIG_HOME`.
- `korvoice --check` also checks for `wl-copy`/`wl-paste` on Wayland.
- README: system package requirements, the terminal `Ctrl+Shift+V` caveat,
  clipboard-manager behaviour.
- CI tests on Python 3.10–3.13.

## 0.2.1

- Packaging/CI: updated artifact upload/download actions for the PyPI
  publish workflow.

## 0.2.0

- Packaging/CI: publish workflow and README install instructions.

## 0.1.0

- Initial release: push-to-talk/toggle voice input, GigaAM (v3_e2e_ctc)
  speech recognition, Nord tray/settings GUI, clipboard/autotype/window
  output.

[Unreleased]: https://github.com/r4ven-me/korvoice/compare/v1.0.7...HEAD
[1.0.7]: https://github.com/r4ven-me/korvoice/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/r4ven-me/korvoice/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/r4ven-me/korvoice/compare/v1.0.2...v1.0.5
[1.0.2]: https://github.com/r4ven-me/korvoice/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/r4ven-me/korvoice/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/r4ven-me/korvoice/compare/v0.2.1...v1.0.0
