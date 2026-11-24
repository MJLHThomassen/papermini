from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsScene

from papermini.output.sheet_layout import SheetLayout
from papermini.pipeline.mini import Mini
from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.project import Project
from papermini.project.sheet_settings import SheetSettings

from .panel import Panel
from .picture_composer import PictureComposer
from .shot_context import ShotContext

PAGE_MM_PX = 2.2  # logical pixels per mm of a page
EDGE = "#c8c8cc"  # the paper's edge
COPIES = (1, 1, 2)  # the copies of each dragon on the orientation pictures


class SheetShots:
    """The pictures of the sheet settings in the settings guide: a sheet cut by
    machine next to its cut file, and the same pieces on an upright and a sideways
    page."""

    def __init__(self, ctx: ShotContext, composer: PictureComposer):
        self._ctx = ctx
        self._composer = composer

    def run(self) -> None:
        """Save the pictures of the sheet settings."""
        project = self._ctx.project_store.load(self._ctx.project)
        sheet = replace(project.sheet, cut="machine")
        self._machine(project, sheet)
        self._orientation(project, sheet)

    def _machine(self, project: Project, sheet: SheetSettings) -> None:
        """Show a sheet cut by machine: the PDF, without cut lines and with alignment
        marks, next to its cut file."""
        lay = sheet.layout(
            self._ctx.output.packer,
            [
                (self._build(project, f.image, f.settings, sheet.figure_bleed), 1)
                for f in project.figures
            ],
        )
        assert lay.pages == 1, "the machine sheet picture should fit on one page"
        svg = QSvgRenderer(
            bytearray(
                self._ctx.output.cut_files.svg(lay, 0, folds=True, title=sheet.title),
                "utf-8",
            )
        )
        self._ctx.save(
            self._composer.panels(
                [
                    Panel(
                        self._sheet_page(lay, sheet.title),
                        "The PDF",
                        "to print: no cut lines, with alignment marks",
                    ),
                    Panel(
                        self._page(lay.paper, svg.render),
                        "The cut file (SVG)",
                        "cut lines (red), fold lines (blue) and the same marks",
                    ),
                ]
            ),
            "settings/machine",
        )

    def _orientation(self, project: Project, sheet: SheetSettings) -> None:
        """Show the same pieces on A4, upright and on its side, with the first page
        of each. With two red dragons, landscape fits them on fewer pages."""
        pieces = [
            (self._build(project, f.image, f.settings), n)
            for f, n in zip(project.figures, COPIES)
        ]
        portrait, landscape = (
            replace(sheet, paper="a4", cut="hand", orientation=o).layout(
                self._ctx.output.packer, pieces
            )
            for o in ("portrait", "landscape")
        )
        assert landscape.pages < portrait.pages, (portrait.pages, landscape.pages)
        self._ctx.save(
            self._composer.panels(
                [
                    Panel(
                        self._sheet_page(portrait, sheet.title),
                        "Portrait",
                        f"{self._pages(portrait.pages)}: the first shown",
                    ),
                    Panel(
                        self._sheet_page(landscape, sheet.title),
                        "Landscape",
                        f"the same pieces on {self._pages(landscape.pages)}",
                    ),
                ]
            ),
            "settings/orientation",
        )

    def _build(
        self,
        project: Project,
        image: Path,
        settings: FigureSettings,
        bleed_mm: float = 0.0,
    ) -> Mini:
        """Build a figure one creature size smaller, so that all three dragons fit on
        one page."""
        if settings.size in sizes.SIZES:
            down = sizes.SIZES[max(sizes.SIZES.index(settings.size) - 1, 0)]
            settings = self._ctx.size_calculator.apply(settings, down, project.sizes)
        return self._ctx.figure_builder.build(
            image, settings, bleed_mm=bleed_mm, log=lambda *_: None
        )

    def _sheet_page(self, lay: SheetLayout, title: str) -> QPixmap:
        """Draw the first page of ``lay`` as in the app."""
        sc = QGraphicsScene()
        self._ctx.sheets.draw(sc, lay, title)
        width, height = lay.paper
        return self._page(
            lay.paper, lambda p, r: sc.render(p, r, QRectF(0, 0, width, height))
        )

    def _page(
        self,
        paper: tuple[float, float],
        render: Callable[[QPainter, QRectF], None],
    ) -> QPixmap:
        """Draw a white page of ``paper`` (mm) with its edge, and ``render(painter,
        rect)`` on it."""
        ratio = self._ctx.ratio
        k = PAGE_MM_PX * ratio  # device pixels per mm
        width, height = paper
        img = QImage(int(width * k), int(height * k), QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        render(p, QRectF(img.rect()))
        p.setPen(QPen(QColor(EDGE), 1))
        p.drawRect(img.rect().adjusted(0, 0, -1, -1))
        p.end()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(ratio)
        return pix

    @staticmethod
    def _pages(n: int) -> str:
        return f"{n} page{'s' * (n != 1)}"
