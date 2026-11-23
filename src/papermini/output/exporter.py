from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..pipeline.mini import Mini
from .cut_file_writer import CutFileWriter
from .pdf_writer import PdfWriter
from .png_writer import PngWriter
from .preview_writer import PreviewWriter
from .sheet_files import SheetFiles
from .sheet_layout import SheetLayout
from .svg_writer import SvgWriter

PIECE_FORMATS = ("svg", "png")  # the formats a piece can be written in


class Exporter:
    """Writes the pieces of figures and the files of a sheet."""

    def __init__(
        self,
        svg: SvgWriter,
        png: PngWriter,
        pdf: PdfWriter,
        cut_files: CutFileWriter,
        previews: PreviewWriter,
    ):
        self._svg = svg
        self._png = png
        self._pdf = pdf
        self._cut_files = cut_files
        self._previews = previews

    def pieces(
        self,
        mini: Mini,
        path: Path,
        formats: Sequence[str],
        copies: int,
        png_px_per_mm: float,
    ) -> list[Path]:
        """Write the piece of ``mini`` at ``path`` in each of ``formats``, the suffix
        set to the format, one file per numbered copy. A PNG has ``png_px_per_mm``
        pixels per mm."""
        paths: list[Path] = []
        for fmt in formats:
            if fmt == "png":
                paths += self._png.write_copies(
                    mini, path.with_suffix(".png"), png_px_per_mm, copies
                )
            else:
                paths += self._svg.write_copies(mini, path.with_suffix(".svg"), copies)
        return paths

    def sheet(
        self,
        layout: SheetLayout,
        pdf: Path,
        title: str,
        cut_folds: bool,
        *,
        write_pdf: bool = True,
        write_cut_files: bool = True,
        write_previews: bool = False,
    ) -> SheetFiles:
        """Write the sheet laid out in ``layout`` as the PDF ``pdf``. A sheet cut by
        machine also gets its cut files next to it, with the fold lines when
        ``cut_folds``, and ``write_previews`` adds a PNG preview of each page."""
        files = SheetFiles()
        if write_pdf:
            self._pdf.write(layout, pdf, title)
            files.pdf = pdf
        if layout.machine and write_cut_files:
            files.cut_files = self._cut_files.write(
                layout, self._cut_files.default_path(pdf), cut_folds, title
            )
        if write_previews:
            files.previews = self._previews.write(
                layout, pdf.with_suffix(".png"), title=title
            )
        return files
