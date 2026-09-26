# Changelog

## Unreleased

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
