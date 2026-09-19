"""Themes (system / Nord dark / Nord light) and the tray icon.

Adapted from kortalk's theme.py (~/Cloud/Projects/public/kortalk) — same
Nord palette and window chrome, minus the markdown/pygments machinery
kortalk needs for rendering chat responses, which korvoice has no use for.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPalette, QPixmap, QPolygon

# https://www.nordtheme.com/docs/colors-and-palettes
# n00 is a darker Polar Night shade used by many Nord ports for backgrounds.
NORD = {
    "n00": "#242933",
    "n0": "#2e3440", "n1": "#3b4252", "n2": "#434c5e", "n3": "#4c566a",
    "n4": "#d8dee9", "n5": "#e5e9f0", "n6": "#eceff4",
    "n8": "#88c0d0", "n9": "#81a1c1", "n10": "#5e81ac",
    "n11": "#bf616a", "n13": "#ebcb8b", "n14": "#a3be8c",
}


def _build_palette(colors: dict[QPalette.ColorRole, str]) -> QPalette:
    palette = QPalette()
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    return palette


def nord_dark_palette() -> QPalette:
    R = QPalette.ColorRole
    return _build_palette({
        R.Window: NORD["n00"], R.WindowText: NORD["n5"],
        R.Base: NORD["n0"], R.AlternateBase: NORD["n1"],
        R.Text: NORD["n5"], R.PlaceholderText: NORD["n3"],
        R.Button: NORD["n0"], R.ButtonText: NORD["n5"],
        R.Highlight: NORD["n10"], R.HighlightedText: NORD["n6"],
        R.ToolTipBase: NORD["n0"], R.ToolTipText: NORD["n5"],
        R.Link: NORD["n8"], R.BrightText: NORD["n11"],
    })


def nord_light_palette() -> QPalette:
    R = QPalette.ColorRole
    return _build_palette({
        R.Window: NORD["n6"], R.WindowText: NORD["n0"],
        R.Base: "#ffffff", R.AlternateBase: NORD["n5"],
        R.Text: NORD["n0"], R.PlaceholderText: NORD["n3"],
        R.Button: NORD["n5"], R.ButtonText: NORD["n0"],
        R.Highlight: NORD["n8"], R.HighlightedText: NORD["n0"],
        R.Link: NORD["n10"], R.BrightText: NORD["n11"],
        R.ToolTipBase: NORD["n5"], R.ToolTipText: NORD["n0"],
    })


def apply_theme(app, theme: str) -> None:
    """system — leave everything alone (Qt picks up the environment theme);
    nord-dark / nord-light — Nord palette on top of the Fusion style."""
    if theme == "nord-dark":
        app.setStyle("Fusion")
        app.setPalette(nord_dark_palette())
    elif theme == "nord-light":
        app.setStyle("Fusion")
        app.setPalette(nord_light_palette())


def is_dark(app) -> bool:
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


# -- shared "card" surface: settings dialog, history window ------------------
#
# Same derivation as kortalk's card_colors: both windows read as one visual
# system regardless of the selected theme (system / nord-dark / nord-light).

def card_colors(app) -> dict[str, str]:
    dark = is_dark(app)
    return {
        "bg": NORD["n00"] if dark else NORD["n6"],
        "field_bg": NORD["n1"] if dark else "#ffffff",
        "fg": NORD["n5"] if dark else NORD["n0"],
        "border": NORD["n3"] if dark else NORD["n4"],
        "muted": NORD["n4"] if dark else NORD["n3"],
        "code_bg": NORD["n1"] if dark else NORD["n5"],
        "highlight": NORD["n10"],
        "highlight_text": NORD["n6"],
        # Recording indicator — Nord "aurora" red, same in both themes so
        # it reads unambiguously as "active" regardless of the palette.
        "recording": NORD["n11"],
    }


def scrollbar_stylesheet(colors: dict[str, str]) -> str:
    """Slim, flat scrollbars (no arrow buttons, rounded handle) to replace
    the OS/Fusion default — thick troughs with visible step buttons read as
    dated next to the rest of the app's styling."""
    c = colors
    return f"""
        QScrollBar:vertical {{
            background: transparent; width: 11px; margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['border']}; border-radius: 4px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['highlight']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px; background: none; border: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


# Qt's stylesheet engine renders a QSpinBox's up/down glyphs as a plain
# filled rectangle when their border colours are set to fake a triangle via
# CSS's usual "transparent sides" trick — the shape has to come from a real
# image instead. A `data:` URI in `image: url(...)` is silently dropped too;
# only an actual file path renders, hence generating these once to a small
# cache directory rather than embedding them inline. (Same technique as
# kortalk/theme.py's _spin_arrow_path — verified there, reused as-is.)
_SPIN_ARROW_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "korvoice"
)


def _spin_arrow_path(up: bool, color: str) -> Path:
    path = _SPIN_ARROW_DIR / f"spin-{'up' if up else 'down'}-{color.lstrip('#')}.png"
    if not path.exists():
        pixmap = QPixmap(10, 6)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        triangle = (QPolygon([QPoint(1, 5), QPoint(9, 5), QPoint(5, 1)]) if up
                    else QPolygon([QPoint(1, 1), QPoint(9, 1), QPoint(5, 5)]))
        painter.drawPolygon(triangle)
        painter.end()
        try:
            _SPIN_ARROW_DIR.mkdir(parents=True, exist_ok=True)
            pixmap.save(str(path), "PNG")
        except OSError:
            pass
    return path


def window_stylesheet(colors: dict[str, str]) -> str:
    """Chrome shared by the settings dialog and the history window: same
    flat background and field colours, applied regardless of the selected
    Qt style so the two windows always match. Adapted from kortalk's
    window_stylesheet, trimmed to the controls korvoice actually uses."""
    c = colors
    up_arrow = _spin_arrow_path(True, c["fg"])
    down_arrow = _spin_arrow_path(False, c["fg"])
    up_arrow_muted = _spin_arrow_path(True, c["muted"])
    down_arrow_muted = _spin_arrow_path(False, c["muted"])
    return f"""
        QDialog, QMainWindow {{ background-color: {c['bg']}; }}
        QWidget {{ color: {c['fg']}; }}
        QLabel {{ color: {c['muted']}; background: transparent; }}
        QTabWidget::pane {{ border: 1px solid {c['border']}; top: -1px; }}
        QTabBar {{ qproperty-drawBase: 0; }}
        QTabBar::tab {{
            background: {c['bg']}; color: {c['muted']};
            padding: 6px 16px; margin-right: 3px;
            border: 1px solid {c['border']};
            border-top-left-radius: 6px; border-top-right-radius: 6px;
        }}
        QTabBar::tab:!selected {{
            margin-top: 3px; border-color: transparent;
        }}
        QTabBar::tab:selected {{
            color: {c['fg']}; background: {c['field_bg']};
            border-bottom-color: {c['field_bg']};
        }}
        QTabBar::tab:hover {{ color: {c['fg']}; }}

        QToolTip {{
            background-color: {c['field_bg']}; color: {c['fg']};
            border: 1px solid {c['border']}; padding: 4px 8px;
        }}

        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget, QKeySequenceEdit {{
            background-color: {c['field_bg']};
            color: {c['fg']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            selection-background-color: {c['highlight']};
            selection-color: {c['highlight_text']};
        }}
        QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover, QSpinBox:hover {{
            border-color: {c['muted']};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {c['highlight']};
        }}
        QComboBox {{ padding: 4px 8px; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QAbstractItemView {{
            background-color: {c['field_bg']}; color: {c['fg']};
            border: 1px solid {c['border']};
            selection-background-color: {c['highlight']};
            selection-color: {c['highlight_text']};
            outline: none;
        }}

        QSpinBox {{ padding-right: 2px; }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: {c['code_bg']};
            border: none;
            border-left: 1px solid {c['border']};
            width: 18px;
        }}
        QSpinBox::up-button {{ border-top-right-radius: 6px; }}
        QSpinBox::down-button {{ border-bottom-right-radius: 6px; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {c['highlight']};
        }}
        QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
            background-color: {c['muted']};
        }}
        QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {{
            background-color: {c['field_bg']};
        }}
        QSpinBox::up-arrow {{ image: url({up_arrow}); width: 10px; height: 6px; }}
        QSpinBox::down-arrow {{ image: url({down_arrow}); width: 10px; height: 6px; }}
        QSpinBox::up-arrow:disabled {{ image: url({up_arrow_muted}); }}
        QSpinBox::down-arrow:disabled {{ image: url({down_arrow_muted}); }}

        QListWidget::item {{ padding: 4px 6px; border-radius: 4px; }}
        QListWidget::item:hover {{ background-color: {c['code_bg']}; }}
        QListWidget::item:selected {{
            background-color: {c['highlight']}; color: {c['highlight_text']};
        }}

        QPushButton, QToolButton {{
            background-color: {c['field_bg']}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 14px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background-color: {c['code_bg']}; border-color: {c['highlight']};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background-color: {c['highlight']}; color: {c['highlight_text']};
            border-color: {c['highlight']};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            color: {c['muted']}; border-color: {c['border']}; background-color: {c['bg']};
        }}
        QPushButton:checkable:checked, QToolButton:checkable:checked {{
            background-color: {c['highlight']}; color: {c['highlight_text']};
            border-color: {c['highlight']};
        }}

        QPushButton#primaryButton {{
            background-color: {c['highlight']}; color: {c['highlight_text']};
            border-color: {c['highlight']}; font-weight: 600;
        }}
        QPushButton#primaryButton:hover {{ border-color: {c['fg']}; }}
        QPushButton#primaryButton:pressed {{ background-color: {c['muted']}; }}

        {scrollbar_stylesheet(c)}
    """


def apply_window_theme(window) -> None:
    """Applies the shared card stylesheet to a settings dialog or history
    window instance. Call again after the palette changes (theme change)."""
    colors = card_colors(_app_instance())
    window.setStyleSheet(window_stylesheet(colors))


def _app_instance():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance()


# -- tray icon ----------------------------------------------------------------
#
# A microphone glyph drawn directly with QPainter (capsule head + stand +
# base), rather than a sourced SVG asset — simple enough to draw exactly,
# and avoids pulling in and attributing a third-party icon for something
# this plain. Recolourable at runtime like kortalk's raven, plus a "dot"
# accent for the recording state.

def _draw_mic(painter: QPainter, rect_size: int, color: QColor, recording: bool) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    s = rect_size
    # Capsule "head" of the mic: centered, roughly the top half of the glyph.
    head_w, head_h = s * 0.34, s * 0.46
    head_rect_x = (s - head_w) / 2
    head_rect_y = s * 0.06
    path = QPainterPath()
    path.addRoundedRect(head_rect_x, head_rect_y, head_w, head_h, head_w / 2, head_w / 2)
    painter.drawPath(path)

    # Stand: an arc cradling the bottom of the head, plus a short vertical
    # post and a horizontal base — the familiar "mic on a stand" silhouette.
    pen = painter.pen()
    stroke = max(1.0, s * 0.07)
    from PySide6.QtGui import QPen
    arc_pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(arc_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    arc_rect_x = s * 0.20
    arc_rect_y = head_rect_y + head_h * 0.35
    arc_size = s * 0.60
    painter.drawArc(int(arc_rect_x), int(arc_rect_y), int(arc_size), int(arc_size),
                     -20 * 16, -140 * 16)

    post_x = s / 2
    post_top = arc_rect_y + arc_size * 0.82
    post_bottom = s * 0.88
    painter.drawLine(int(post_x), int(post_top), int(post_x), int(post_bottom))
    base_half = s * 0.16
    painter.drawLine(int(post_x - base_half), int(post_bottom),
                      int(post_x + base_half), int(post_bottom))
    painter.setPen(pen)

    if recording:
        dot_r = s * 0.16
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(NORD["n11"]))
        painter.drawEllipse(int(s - dot_r * 1.7), int(s - dot_r * 1.7),
                             int(dot_r * 1.6), int(dot_r * 1.6))


# Static icon file for the applications-menu launcher and the autostart
# entry (as opposed to make_tray_icon's runtime-recoloured pixmaps) —
# pip/pipx installs it nowhere, so korvoice writes it itself.
ICON_FILE = (Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
             / "icons" / "korvoice.png")


def install_icon_file() -> Path:
    """Writes a fixed-colour icon to ICON_FILE and returns its path. Always
    overwrites so an icon update ships to existing installs — safe to call
    on every startup, pip/pipx never places this file on its own.

    Uses QImage, not QPixmap: this runs from app.ensure_desktop_entry()
    before a QApplication exists yet (deliberately — see that function's
    docstring), and QPixmap requires one already constructed while QImage,
    being platform-independent, does not."""
    try:
        ICON_FILE.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(128, 128, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        _draw_mic(painter, 128, QColor(NORD["n10"]), recording=False)
        painter.end()
        image.save(str(ICON_FILE), "PNG")
    except OSError:
        pass
    return ICON_FILE


# Settings → General → "Tray icon" — a manual override for make_tray_icon's
# default palette-following colour. The system tray's own background isn't
# necessarily the same as the app's chosen theme, so "auto" doesn't always
# pick a legible icon.
_TRAY_ICON_COLORS = {"dark": NORD["n0"], "light": NORD["n6"]}


def tray_icon_color(setting: str) -> QColor | None:
    """None for "auto" — make_tray_icon then falls back to the app
    palette's WindowText colour, following the selected theme. An explicit
    QColor for "dark"/"light" instead, independent of the theme."""
    tone = _TRAY_ICON_COLORS.get(setting)
    return QColor(tone) if tone else None


def make_tray_icon(color: QColor | str | None = None, recording: bool = False) -> QIcon:
    """Monochrome microphone glyph. The default colour is the text colour
    of the current application palette, so the icon is light on dark
    panels and dark on light panels. `recording` adds a small red dot."""
    if color is None:
        app = _app_instance()
        color = (app.palette().color(QPalette.ColorRole.WindowText)
                 if app is not None else QColor(NORD["n5"]))
    color = QColor(color)

    icon = QIcon()
    for size in (22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        _draw_mic(painter, size, color, recording)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
