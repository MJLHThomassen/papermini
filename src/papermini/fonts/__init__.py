"""Fonts for a miniature's text: Times (the default, built into every PDF reader), the
fonts bundled with papermini (free fonts under the SIL Open Font Licence, in this folder)
and the TrueType fonts installed on this computer.

A figure uses one font for all its text (labels, numbers, back text), in bold where the
font has a bold. Installed fonts are found by scanning the system's font folders; the
result is kept in an index in papermini's cache folder, so later scans only read new or
changed font files. A font that is not on this computer prints in Times instead.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("papermini")
HERE = Path(__file__).resolve().parent
DEFAULT = "Times"
# the bundled fonts: name -> (regular, bold or None), relative to this folder
BUNDLED: Dict[str, Tuple[str, Optional[str]]] = {
    "Fira Sans": ("firasans/FiraSans-Regular.ttf", "firasans/FiraSans-Bold.ttf"),
    "Crimson Text": ("crimsontext/CrimsonText-Regular.ttf", "crimsontext/CrimsonText-Bold.ttf"),
    "Almendra": ("almendra/Almendra-Regular.ttf", "almendra/Almendra-Bold.ttf"),
    "MedievalSharp": ("medievalsharp/MedievalSharp.ttf", None),
    "Uncial Antiqua": ("uncialantiqua/UncialAntiqua-Regular.ttf", None),
    "Kalam": ("kalam/Kalam-Regular.ttf", "kalam/Kalam-Bold.ttf"),
}
REGULAR_STYLES = ("Regular", "Book", "Normal", "Roman", "Medium")
INDEX_VERSION = 1


@dataclass(frozen=True)
class Font:
    """A font papermini can print with: its name and its regular and bold files (both
    None for Times, which PDF readers have built in; no bold file: bold uses regular)."""

    name: str
    regular: Optional[Path] = None
    bold: Optional[Path] = None
    bundled: bool = False


TIMES = Font(DEFAULT, bundled=True)


def bundled() -> List[Font]:
    """Times and the fonts that come with papermini."""
    return [TIMES] + [Font(n, HERE / r, HERE / b if b else None, True)
                      for n, (r, b) in BUNDLED.items()]


# ----------------------------------------------------------------- installed fonts
def font_dirs() -> List[Path]:
    """The folders where this system keeps its fonts."""
    home = Path.home()
    if sys.platform == "win32":
        win = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [win / "Fonts", local / "Microsoft" / "Windows" / "Fonts"]
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"]
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".fonts",
            data / "fonts"]


def _index_path() -> Path:
    from ..segment import cache_dir

    return cache_dir() / "fonts.json"


def _read_name(path: Path) -> Optional[Tuple[str, str]]:
    """(family, style) of a TrueType font file, or None when it cannot be used."""
    from PIL import ImageFont

    try:
        family, style = ImageFont.truetype(str(path), 10).getname()
    except Exception:  # noqa: BLE001 - a broken or unsupported file: leave it out
        return None
    return (family, style) if family else None


_lock = threading.Lock()
_installed: Optional[Dict[str, Font]] = None


def installed(refresh: bool = False) -> Dict[str, Font]:
    """The TrueType fonts installed on this computer that papermini can print with, by
    name (the bundled ones and Times left out). The first call scans the font folders
    (reading only files that are new or changed since the index in the cache folder);
    later calls return what it found. Safe to call from any thread."""
    global _installed
    with _lock:
        if _installed is None or refresh:
            _installed = _scan()
        return _installed


def _scan() -> Dict[str, Font]:
    try:
        old = json.loads(_index_path().read_text(encoding="utf-8"))
        if old.get("version") != INDEX_VERSION:
            old = {}
    except (OSError, ValueError):
        old = {}
    known = old.get("files", {})
    files: Dict[str, list] = {}
    for d in font_dirs():
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.suffix.lower() != ".ttf":
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            key, stamp = str(f), [st.st_size, int(st.st_mtime)]
            entry = known.get(key)
            if entry and entry[:2] == stamp:
                files[key] = entry
            else:
                files[key] = stamp + list(_read_name(f) or ("", ""))
    try:
        _index_path().parent.mkdir(parents=True, exist_ok=True)
        _index_path().write_text(json.dumps({"version": INDEX_VERSION, "files": files}),
                                 encoding="utf-8")
    except OSError as e:
        logger.debug("could not save the font index: %s", e)
    styles: Dict[str, Dict[str, Path]] = {}
    for key, (_, _, family, style) in files.items():
        if family:
            styles.setdefault(family, {}).setdefault(style, Path(key))
    skip = {DEFAULT} | set(BUNDLED)
    out = {}
    for family in sorted(styles, key=str.lower):
        s = styles[family]
        regular = next((s[k] for k in REGULAR_STYLES if k in s), None)
        if family in skip or regular is None:
            continue
        out[family] = Font(family, regular, s.get("Bold"))
    return out


# ----------------------------------------------------------------- finding a font
def find(name: str) -> Optional[Font]:
    """The font called ``name``, or None when it is not on this computer (Times and the
    bundled fonts always are; looking for an installed one may scan the font folders)."""
    for f in bundled():
        if f.name == name:
            return f
    return installed().get(name)


def resolve(name: str) -> Tuple[Font, bool]:
    """The font to print ``name`` with, and whether it was found (if not: Times)."""
    f = find(name) if name else TIMES
    return (f, True) if f is not None else (TIMES, False)


_registered: Dict[Tuple[str, bool], str] = {}


def pdf_name(name: str, bold: bool = False) -> str:
    """The font's name for the PDF writer (and for measuring text), registering its file
    the first time."""
    font, _ = resolve(name)
    if font.regular is None:
        return "Times-Bold" if bold else "Times-Roman"
    path = font.bold if bold and font.bold else font.regular
    key = (font.name, bold and font.bold is not None)
    if key not in _registered:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        ident = f"papermini-{font.name}{'-Bold' if key[1] else ''}".replace(" ", "")
        try:
            pdfmetrics.registerFont(TTFont(ident, str(path)))
        except Exception as e:  # noqa: BLE001 - e.g. an outline format reportlab cannot read
            logger.warning("could not use the font %s (%s): printing in Times", font.name, e)
            ident = "Times-Bold" if bold else "Times-Roman"
        _registered[key] = ident
    return _registered[key]


def text_width(text: str, name: str, size: float, bold: bool = False) -> float:
    """How wide ``text`` is in the font at ``size`` (in the units of ``size``)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, pdf_name(name, bold), size)


def svg_family(name: str) -> str:
    """The font-family an SVG file names (with a generic fallback)."""
    font, _ = resolve(name)
    if font.regular is None:
        return "Times New Roman, Times, serif"
    return f"'{font.name}', serif"


def from_svg_family(family: str) -> str:
    """The font name back from an SVG font-family."""
    first = family.split(",")[0].strip().strip("'\"")
    return DEFAULT if first in ("", "Times New Roman", "Times", "serif") else first


def file_for(name: str, bold: bool = False) -> Optional[Path]:
    """The font file to draw ``name`` with (None for Times)."""
    font, _ = resolve(name)
    return font.bold if bold and font.bold else font.regular
