"""Look and feel: light/dark palettes, one style sheet, line icons and the logo.

``apply(app, mode)`` sets everything up; mode is "system", "light" or "dark".
Colours are design tokens (``Theme``) so widgets that paint themselves (the
canvas, the figure cards) can use the same values.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QStyleFactory


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str           # window
    surface: str      # panels, cards
    surface2: str     # inputs, hover
    canvas: str       # behind the paper
    dots: str         # canvas dot grid
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    accent_soft: str  # selection background
    danger: str
    shadow: str


DRAGON_RED = "#fd3c1b"  # the logo's red: the accent in both themes

LIGHT = Theme("light", bg="#f4f4f6", surface="#ffffff", surface2="#f7f7f9", canvas="#e9e9ee",
              dots="#d4d4dc", border="#e2e2e8", text="#1d1d22", muted="#6e6e7a",
              accent=DRAGON_RED, accent_text="#ffffff", accent_soft="#ffe9e4",
              danger="#d64545", shadow="#00000028")
DARK = Theme("dark", bg="#161618", surface="#1e1e21", surface2="#26262a", canvas="#111113",
             dots="#26262b", border="#2f2f34", text="#ececf0", muted="#9a9aa6",
             accent=DRAGON_RED, accent_text="#ffffff", accent_soft="#45231f",
             danger="#f07070", shadow="#00000070")

current: Theme = LIGHT


# --------------------------------------------------------------------------- icons
# 24x24 line icons, drawn for papermini (stroke = currentColor)
ICONS: Dict[str, str] = {
    "open": '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.8l2 2h7.2a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "add": '<path d="M13.5 4.5H6a1.5 1.5 0 0 0-1.5 1.5v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-7.5"/>'
           '<path d="M4.5 15.5l4-4 3.5 3.5 2-2 5.5 5.5"/><path d="M18.5 2.5v6M15.5 5.5h6"/>',
    "save": '<path d="M5.5 4.5h10l4 4v10a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1z"/>'
            '<path d="M8 4.5v4.5h6.5V4.5M8 19.5v-5.5h8v5.5"/>',
    "export": '<path d="M12 4v10.5M7.5 10.5l4.5 4.5 4.5-4.5M5 19.5h14"/>',
    "pdf": '<path d="M6.5 3.5h7.5l4.5 4.5v11a1.5 1.5 0 0 1-1.5 1.5h-10.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5z"/>'
           '<path d="M14 3.5V8h4.5M8.5 13h7M8.5 16.5h5"/>',
    "fit": '<path d="M4.5 9V4.5H9M19.5 9V4.5H15M4.5 15v4.5H9M19.5 15v4.5H15"/>',
    "zoom_in": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5M10.5 11v5M13.5 11v5"/>',
    # side panel toggles: outline = hidden, filled strip = shown
    "panel_left": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>',
    "panel_left_on": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>'
                     '<path d="M9.5 4.5h-4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h4z" fill="currentColor"/>',
    "panel_right": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M14.5 4.5v15"/>',
    "panel_right_on": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M14.5 4.5v15"/>'
                      '<path d="M14.5 4.5h4a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-4z" fill="currentColor"/>',
    "sliders": '<path d="M5 7h9M18 7h1M5 12h3M12 12h7M5 17h6M15 17h4"/>'
               '<circle cx="16" cy="7" r="2"/><circle cx="10" cy="12" r="2"/>'
               '<circle cx="13" cy="17" r="2"/>',
    "menu": '<path d="M4.5 7h15M4.5 12h15M4.5 17h15"/>',
    "plus": '<path d="M12 5.5v13M5.5 12h13"/>',
    "chevron_down": '<path d="M7 10l5 5 5-5"/>',
    "chevron_right": '<path d="M10 7l5 5-5 5"/>',
    "chevron_up": '<path d="M7 14l5-5 5 5"/>',
    "check": '<path d="M5.5 12.5l4 4 9-9.5"/>',
    "image": '<rect x="4" y="4.5" width="16" height="15" rx="2"/><circle cx="9" cy="9.5" r="1.5"/>'
             '<path d="M4 16l4.5-4.5 4 4 2.5-2.5 5 5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2'
           'M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "warning": '<path d="M12 4l9 15.5H3z"/><path d="M12 10v4.5M12 17.2v.3"/>',
}


def icon_svg(name: str, color: str, stroke: float = 1.7) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round" color="{color}">{ICONS[name]}</svg>')


def pixmap(name: str, color: Optional[str] = None, size: int = 18, ratio: float = 2.0) -> QPixmap:
    color = color or current.text
    r = QSvgRenderer(QByteArray(icon_svg(name, color).encode()))
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.transparent)
    p = QPainter(px)
    r.render(p, QRectF(0, 0, px.width(), px.height()))
    p.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: Optional[str] = None, size: int = 18) -> QIcon:
    ic = QIcon(pixmap(name, color, size))
    ic.addPixmap(pixmap(name, current.muted, size), QIcon.Disabled)
    return ic


# --------------------------------------------------------------------------- logo
LOGO = Path(__file__).with_name("logo.svg")  # the full-colour dragon


def logo_pixmap(size: int, ratio: float = 2.0) -> QPixmap:
    """The logo, centred in a size x size square."""
    r = QSvgRenderer(str(LOGO))
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.transparent)
    vb = r.viewBoxF()
    k = px.width() / max(vb.width(), vb.height())
    w, h = vb.width() * k, vb.height() * k
    p = QPainter(px)
    r.render(p, QRectF((px.width() - w) / 2, (px.height() - h) / 2, w, h))
    p.end()
    px.setDevicePixelRatio(ratio)
    return px


def app_icon() -> QIcon:
    """The window and taskbar icon, rendered for each common size."""
    ic = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s, 1.0))
    return ic


# --------------------------------------------------------------------------- apply
_ASSETS = Path(tempfile.gettempdir()) / "papermini-theme"


def _asset(name: str, color: str, stroke: float = 2.0) -> str:
    """An icon as an SVG file the style sheet can reference."""
    _ASSETS.mkdir(parents=True, exist_ok=True)
    f = _ASSETS / f"{name}-{color.lstrip('#')}.svg"
    if not f.exists():
        f.write_text(icon_svg(name, color, stroke), encoding="utf-8")
    return f.as_posix()


def resolve(mode: str) -> Theme:
    if mode == "dark":
        return DARK
    if mode == "light":
        return LIGHT
    app = QApplication.instance()
    scheme = app.styleHints().colorScheme() if app else Qt.ColorScheme.Light
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def apply(app: QApplication, mode: str = "system") -> Theme:
    global current
    t = current = resolve(mode)
    app.setStyle(QStyleFactory.create("Fusion"))

    families = QFontDatabase.families()
    for fam in ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Inter", "Cantarell"):
        if fam in families:
            f = QFont(fam)
            f.setPointSizeF(9.5)
            app.setFont(f)
            break

    pal = QPalette()
    for role, c in ((QPalette.Window, t.bg), (QPalette.Base, t.surface2),
                    (QPalette.AlternateBase, t.surface), (QPalette.WindowText, t.text),
                    (QPalette.Text, t.text), (QPalette.Button, t.surface),
                    (QPalette.ButtonText, t.text), (QPalette.Highlight, t.accent),
                    (QPalette.HighlightedText, t.accent_text), (QPalette.ToolTipBase, t.surface),
                    (QPalette.ToolTipText, t.text), (QPalette.PlaceholderText, t.muted),
                    (QPalette.Mid, t.border), (QPalette.Dark, t.border), (QPalette.Light, t.surface),
                    (QPalette.Link, t.accent), (QPalette.LinkVisited, t.accent)):
        pal.setColor(role, QColor(c))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t.muted))
    app.setPalette(pal)
    app.setStyleSheet(style_sheet(t))
    return t


def style_sheet(t: Theme) -> str:
    down = _asset("chevron_down", t.muted)
    check = _asset("check", t.accent_text, 2.6)
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, #Body {{ background: {t.bg}; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
            padding: 6px 8px; border-radius: 6px; }}

/* header */
#Header {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
#AppName {{ font-size: 11pt; font-weight: 600; }}
#ProjectName {{ color: {t.muted}; }}
#Header QToolButton {{ border: none; border-radius: 7px; padding: 6px; background: transparent; }}
#Header QToolButton:hover {{ background: {t.surface2}; }}
#Header QToolButton:pressed {{ background: {t.border}; }}
#Header QToolButton:focus {{ border: 2px solid {t.accent}; padding: 4px; }}
#Header QToolButton::menu-indicator {{ image: none; width: 0; }}

/* segmented view switch */
#Segmented {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: 9px; }}
#Segmented QPushButton {{ border: none; background: transparent; border-radius: 7px;
                         padding: 5px 14px; color: {t.muted}; min-height: 0; }}
#Segmented QPushButton:hover {{ color: {t.text}; }}
#Segmented QPushButton:checked {{ background: {t.surface}; color: {t.text};
                                 border: 1px solid {t.border}; }}

/* buttons */
QPushButton {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 7px;
               padding: 6px 14px; min-height: 18px; }}
QPushButton:hover {{ background: {t.surface2}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:disabled {{ color: {t.muted}; }}
QPushButton[primary="true"] {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent};
                               font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t.accent}; border-color: {t.text}; }}
QPushButton[primary="true"]:disabled {{ background: {t.surface2}; color: {t.muted};
                                        border-color: {t.border}; }}
QToolButton {{ border: none; border-radius: 6px; padding: 4px; background: transparent; }}
QToolButton:hover {{ background: {t.surface2}; }}
QToolButton:focus {{ border: 2px solid {t.accent}; padding: 2px; }}

/* inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t.surface2}; border: 1px solid {t.border}; border-radius: 6px;
    padding: 3px 8px; min-height: 22px; selection-background-color: {t.accent};
    selection-color: {t.accent_text}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {t.muted}; }}

/* spin boxes: no arrow buttons (type, arrow keys, or the wheel once focused); zero-width
   buttons rather than NoButtons, which collapses the text field under a style sheet */
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px; border: none; }}
QSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    image: none; width: 0px; height: 0px; }}
QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {t.border}; }}
QSlider::sub-page:horizontal {{ height: 4px; border-radius: 2px; background: {t.accent}; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -6px 0; border-radius: 8px;
    background: {t.surface}; border: 2px solid {t.accent}; }}
QSlider::handle:horizontal:hover {{ background: {t.accent_soft}; }}
QSlider::sub-page:horizontal:disabled {{ background: {t.muted}; }}
QSlider::handle:horizontal:disabled {{ border-color: {t.muted}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
    border-radius: 6px; padding: 4px; selection-background-color: {t.accent_soft};
    selection-color: {t.text}; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid {t.border}; background: {t.surface2}; }}
QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url({check}); }}

/* side panels */
#Side {{ background: {t.surface}; }}
#SideLeft {{ background: {t.surface}; border-right: 1px solid {t.border}; }}
#SideRight {{ background: {t.surface}; border-left: 1px solid {t.border}; }}
#PanelTitle {{ font-weight: 600; font-size: 10pt; }}
#PanelSub, #Hint, #Muted {{ color: {t.muted}; }}
#Hint {{ font-size: 8.5pt; }}
#SectionHeader {{ border: none; background: transparent; text-align: left; padding: 10px 2px 6px 2px;
                  font-weight: 600; color: {t.text}; }}
#SectionHeader:hover {{ color: {t.accent}; }}
#Section {{ border-bottom: 1px solid {t.border}; }}
#SubHeading {{ color: {t.muted}; font-size: 8.5pt; font-weight: 600; padding-top: 6px; }}
#FormLabel {{ color: {t.muted}; }}
QListWidget#Figures {{ background: transparent; border: none; outline: none; }}

/* canvas overlays */
#ZoomBar {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 9px; }}
#ZoomBar QLabel {{ color: {t.muted}; padding: 0 4px; }}
#EmptyCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 14px; }}
#EmptyTitle {{ font-size: 12pt; font-weight: 600; }}
#PanelEmpty #Muted {{ font-size: 10pt; }}
#ErrorBanner {{ background: {t.surface}; border: 1px solid {t.danger}; border-radius: 10px; }}
#ErrorBanner QLabel {{ color: {t.text}; }}
#SheetBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
#Busy {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px;
         padding: 5px 14px; color: {t.muted}; }}
QTabWidget::pane {{ border: none; }}

/* chrome */
QSplitter::handle {{ background: {t.border}; }}
QStatusBar {{ background: {t.surface}; border-top: 1px solid {t.border}; color: {t.muted}; }}
QStatusBar QLabel {{ color: {t.muted}; padding: 0 6px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
QMenu::item:disabled {{ color: {t.muted}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QProgressDialog, QMessageBox, #DownloadDialog, #ModelsDialog {{ background: {t.surface}; }}
#DialogTitle {{ font-size: 11pt; font-weight: 600; }}
#ModelCard {{ background: {t.surface2}; border: 1px solid {t.border}; border-radius: 10px; }}
#DownloadDialog QProgressBar {{ background: {t.surface2}; border: 1px solid {t.border};
    border-radius: 4px; }}
#DownloadDialog QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
"""
