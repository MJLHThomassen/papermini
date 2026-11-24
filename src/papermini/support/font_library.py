from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import ClassVar

from PIL import ImageFont

from .cache_folder import CacheFolder
from .font import Font

logger = logging.getLogger("papermini")
REGULAR_STYLES = ("Regular", "Book", "Normal", "Roman", "Medium")
INDEX_VERSION = 1
# the fonts that draw on images when a piece's font has no file of its own
SERIF_FILES = ("times.ttf", "DejaVuSerif.ttf")
SANS_FILES = ("arial.ttf", "DejaVuSans.ttf")


class FontLibrary:
    """The fonts for a miniature's text: Times (the default, built into every PDF
    reader), the fonts bundled with papermini (free fonts under the SIL Open Font
    Licence, in its fonts folder) and the TrueType fonts installed on this computer.

    A figure uses one font for all its text (labels, numbers, back text), in bold where
    the font has a bold. Installed fonts are found by scanning ``folders``, by default
    the system's font folders; the result is kept in an index in papermini's cache
    folder, so later scans only read new or changed font files. A font that is not on
    this computer prints in Times instead.
    """

    DEFAULT = "Times"
    FOLDER = Path(__file__).resolve().parent.parent / "fonts"  # the bundled fonts
    # the bundled fonts: name -> (regular, bold or None), relative to FOLDER
    BUNDLED: ClassVar[dict[str, tuple[str, str | None]]] = {
        "Fira Sans": ("firasans/FiraSans-Regular.ttf", "firasans/FiraSans-Bold.ttf"),
        "Crimson Text": (
            "crimsontext/CrimsonText-Regular.ttf",
            "crimsontext/CrimsonText-Bold.ttf",
        ),
        "Almendra": ("almendra/Almendra-Regular.ttf", "almendra/Almendra-Bold.ttf"),
        "MedievalSharp": ("medievalsharp/MedievalSharp.ttf", None),
        "Uncial Antiqua": ("uncialantiqua/UncialAntiqua-Regular.ttf", None),
        "Kalam": ("kalam/Kalam-Regular.ttf", "kalam/Kalam-Bold.ttf"),
    }
    TIMES = Font(DEFAULT, bundled=True)

    def __init__(self, folders: list[Path] | None = None):
        self._folders = folders
        self._lock = threading.Lock()
        self._installed: dict[str, Font] | None = None
        self._registered: dict[tuple[str, bool], str] = {}

    def bundled(self) -> list[Font]:
        """Times and the fonts that come with papermini."""
        return [self.TIMES] + [
            Font(n, self.FOLDER / r, self.FOLDER / b if b else None, True)
            for n, (r, b) in self.BUNDLED.items()
        ]

    # region installed fonts
    def font_dirs(self) -> list[Path]:
        """The folders where installed fonts are looked for: the ones this library was
        made with, or the system's."""
        if self._folders is not None:
            return list(self._folders)
        home = Path.home()
        if sys.platform == "win32":
            win = Path(os.environ.get("WINDIR", r"C:\Windows"))
            local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
            return [win / "Fonts", local / "Microsoft" / "Windows" / "Fonts"]
        if sys.platform == "darwin":
            return [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                home / "Library" / "Fonts",
            ]
        data = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        return [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            home / ".fonts",
            data / "fonts",
        ]

    def installed(self, refresh: bool = False) -> dict[str, Font]:
        """The TrueType fonts installed on this computer that papermini can print with,
        by name (the bundled ones and Times left out). The first call scans the font
        folders (reading only files that are new or changed since the index in the cache
        folder); later calls return what it found. Safe to call from any thread."""
        with self._lock:
            if self._installed is None or refresh:
                self._installed = self._scan()
            return self._installed

    # endregion

    # region finding a font
    def find(self, name: str) -> Font | None:
        """The font called ``name``, or None when it is not on this computer (Times and
        the bundled fonts always are; looking for an installed one may scan the font
        folders)."""
        for f in self.bundled():
            if f.name == name:
                return f
        return self.installed().get(name)

    def resolve(self, name: str) -> tuple[Font, bool]:
        """The font to print ``name`` with, and whether it was found (if not: Times)."""
        f = self.find(name) if name else self.TIMES
        return (f, True) if f is not None else (self.TIMES, False)

    def pdf_name(self, name: str, bold: bool = False) -> str:
        """The font's name for the PDF writer (and for measuring text), registering its
        file the first time."""
        font, _ = self.resolve(name)
        if font.regular is None:
            return "Times-Bold" if bold else "Times-Roman"
        path = font.bold if bold and font.bold else font.regular
        key = (font.name, bold and font.bold is not None)
        if key not in self._registered:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            ident = f"papermini-{font.name}{'-Bold' if key[1] else ''}".replace(" ", "")
            try:
                pdfmetrics.registerFont(TTFont(ident, str(path)))
            except Exception as e:  # noqa: BLE001 - e.g. an outline format reportlab cannot read
                logger.warning(
                    "could not use the font %s (%s): printing in Times", font.name, e
                )
                ident = "Times-Bold" if bold else "Times-Roman"
            self._registered[key] = ident
        return self._registered[key]

    def text_width(
        self, text: str, name: str, size: float, bold: bool = False
    ) -> float:
        """How wide ``text`` is in the font at ``size`` (in the units of ``size``)."""
        from reportlab.pdfbase.pdfmetrics import stringWidth

        return stringWidth(text, self.pdf_name(name, bold), size)

    def svg_family(self, name: str) -> str:
        """The font-family an SVG file names (with a generic fallback)."""
        font, _ = self.resolve(name)
        if font.regular is None:
            return "Times New Roman, Times, serif"
        return f"'{font.name}', serif"

    def file_for(self, name: str, bold: bool = False) -> Path | None:
        """The font file to draw ``name`` with (None for Times)."""
        font, _ = self.resolve(name)
        return font.bold if bold and font.bold else font.regular

    def image_font(self, size_px: int, name: str | None = None, bold: bool = False):
        """A font for drawing on an image, ``size_px`` high: the font called ``name``
        (a serif when it has no file of its own), or a sans-serif without a name."""
        path = self.file_for(name, bold) if name is not None else None
        files = SERIF_FILES if name is not None else SANS_FILES
        for file in ([str(path)] if path else []) + list(files):
            try:
                return ImageFont.truetype(file, size_px)
            except OSError:
                continue
        return ImageFont.load_default()

    # endregion

    # region the index of installed fonts
    @staticmethod
    def _index_path() -> Path:
        return CacheFolder.path() / "fonts.json"

    @staticmethod
    def _read_name(path: Path) -> tuple[str, str] | None:
        """(family, style) of a TrueType font file, or None when it cannot be used. The
        style is empty when the file names none."""
        try:
            family, style = ImageFont.truetype(str(path), 10).getname()
        except Exception:  # noqa: BLE001 - a broken or unsupported file: leave it out
            return None
        return (family, style or "") if family else None

    def _scan(self) -> dict[str, Font]:
        try:
            old = json.loads(self._index_path().read_text(encoding="utf-8"))
            if old.get("version") != INDEX_VERSION:
                old = {}
        except (OSError, ValueError):
            old = {}
        known = old.get("files", {})
        files: dict[str, list] = {}
        for d in self.font_dirs():
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
                    files[key] = stamp + list(self._read_name(f) or ("", ""))
        try:
            self._index_path().parent.mkdir(parents=True, exist_ok=True)
            self._index_path().write_text(
                json.dumps({"version": INDEX_VERSION, "files": files}), encoding="utf-8"
            )
        except OSError as e:
            logger.debug("could not save the font index: %s", e)
        styles: dict[str, dict[str, Path]] = {}
        for key, (_, _, family, style) in files.items():
            if family:
                styles.setdefault(family, {}).setdefault(style, Path(key))
        skip = {self.DEFAULT} | set(self.BUNDLED)
        out = {}
        for family in sorted(styles, key=str.lower):
            s = styles[family]
            regular = next((s[k] for k in REGULAR_STYLES if k in s), None)
            if family in skip or regular is None:
                continue
            out[family] = Font(family, regular, s.get("Bold"))
        return out

    # endregion
