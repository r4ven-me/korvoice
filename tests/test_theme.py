from PySide6.QtGui import QColor

from korvoice import theme


def test_nord_dark_palette_is_dark():
    palette = theme.nord_dark_palette()
    from PySide6.QtGui import QPalette
    assert palette.color(QPalette.ColorRole.Window).lightness() < 128


def test_nord_light_palette_is_light():
    palette = theme.nord_light_palette()
    from PySide6.QtGui import QPalette
    assert palette.color(QPalette.ColorRole.Window).lightness() >= 128


def test_card_colors_dark_vs_light(qapp):
    theme.apply_theme(qapp, "nord-dark")
    dark_colors = theme.card_colors(qapp)
    theme.apply_theme(qapp, "nord-light")
    light_colors = theme.card_colors(qapp)
    assert dark_colors["bg"] != light_colors["bg"]
    assert dark_colors.keys() == light_colors.keys()


def test_tray_icon_color_auto_is_none():
    assert theme.tray_icon_color("auto") is None


def test_tray_icon_color_explicit():
    assert theme.tray_icon_color("dark") == QColor(theme.NORD["n00"])
    assert theme.tray_icon_color("light") == QColor(theme.NORD["n6"])


def test_make_tray_icon_not_null(qapp):
    icon = theme.make_tray_icon(QColor("#ffffff"))
    assert not icon.isNull()


def test_idle_tray_icon_is_freshly_rasterized(qapp):
    first = theme.make_tray_icon(QColor("#ffffff"), state="idle")
    second = theme.make_tray_icon(QColor("#ffffff"), state="idle")

    assert first.cacheKey() != second.cacheKey()
    assert not first.pixmap(24, 24).isNull()


def test_make_tray_icon_state_variants_not_null(qapp):
    for state in ("idle", "recording", "transcribing"):
        icon = theme.make_tray_icon(QColor("#ffffff"), state=state)
        assert not icon.isNull()


def test_make_tray_icon_states_render_differently(qapp):
    # The whole point of the per-state dot (recording vs transcribing used
    # to render identically, see theme.py's _STATE_DOT_COLORS) is that
    # they're visually distinguishable — assert that directly, not just
    # that each icon exists.
    images = {
        state: theme.make_tray_icon(QColor("#ffffff"), state=state).pixmap(64, 64).toImage()
        for state in ("idle", "recording", "transcribing")
    }
    assert images["idle"] != images["recording"]
    assert images["idle"] != images["transcribing"]
    assert images["recording"] != images["transcribing"]


def test_install_icon_file_writes_black_desktop_svg(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(theme, "ICON_FILE", tmp_path / "icons" / "korvoice.svg")
    path = theme.install_icon_file()
    assert path.exists()
    assert path.read_bytes() == theme.DESKTOP_ICON.read_bytes()
    assert "#000000" in path.read_text(encoding="utf-8")
