from __future__ import annotations

from ..support.font_library import FontLibrary
from .cut_file_writer import CutFileWriter
from .exporter import Exporter
from .pdf_writer import PdfWriter
from .png_writer import PngWriter
from .preview_writer import PreviewWriter
from .sheet_packer import SheetPacker
from .svg_writer import SvgWriter


class Output:
    """The services that pack the sheet and write the files, created once.
    An entry point makes one and passes on the services its code uses.

    The writers draw the pieces' text in its fonts from ``fonts``.
    """

    def __init__(self, fonts: FontLibrary):
        self.packer = SheetPacker()
        self.pdf = PdfWriter(fonts)
        self.cut_files = CutFileWriter()
        self.previews = PreviewWriter(fonts)
        self.svg = SvgWriter(fonts)
        self.png = PngWriter(fonts)
        self.exporter = Exporter(
            self.svg, self.png, self.pdf, self.cut_files, self.previews
        )
