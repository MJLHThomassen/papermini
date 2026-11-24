from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from papermini.gui.problem_reporter import ProblemReporter
from papermini.gui.theme_service import ThemeService
from papermini.gui.views.mini_renderer import MiniRenderer
from papermini.gui.views.qt_fonts import QtFonts
from papermini.gui.views.qt_images import QtImages
from papermini.gui.views.sheet_renderer import SheetRenderer
from papermini.output.output import Output
from papermini.pipeline.pipeline import Pipeline
from papermini.project.figure_builder import FigureBuilder
from papermini.project.project_store import ProjectStore
from papermini.project.size_calculator import SizeCalculator
from papermini.support.font_library import FontLibrary
from papermini.support.image_fetcher import ImageFetcher
from papermini.support.log_session import LogSession
from papermini.support.update_service import UpdateService

DRAGONS = Path(__file__).resolve().parents[2] / "examples" / "dragons"
STAT_BLOCK, FLYING, RED = range(3)  # the dragons' rows in the list of dragons.yaml
POLL_S = 0.05  # how long to sleep between rounds of events while waiting
SETTLE_ROUNDS = 10  # rounds of events after the wait, for the last repaints
SETTLE_S = 0.03  # how long to sleep between those rounds


@dataclass
class ShotContext:
    """The app, its services and the output folder that every group of pictures
    shares."""

    app: QApplication
    out: Path  # the folder the pictures go in
    project: Path  # the project the windows open
    ratio: float  # device pixels per logical pixel
    size_calculator: SizeCalculator
    fonts: FontLibrary
    images_from_web: ImageFetcher
    updates: UpdateService
    logs: LogSession
    project_store: ProjectStore
    pipeline: Pipeline
    figure_builder: FigureBuilder
    output: Output
    themes: ThemeService
    qt_fonts: QtFonts
    images: QtImages
    minis: MiniRenderer
    sheets: SheetRenderer
    problems: ProblemReporter

    @classmethod
    def create(
        cls, app: QApplication, out: Path, project: Path, ratio: float
    ) -> ShotContext:
        """Create the app's services, as the app's entry point does."""
        size_calculator = SizeCalculator()
        fonts = FontLibrary()
        images_from_web = ImageFetcher()
        updates = UpdateService()
        pipeline = Pipeline(fonts)
        logs = LogSession(updates)
        themes = ThemeService()
        qt_fonts = QtFonts(fonts)
        images = QtImages()
        minis = MiniRenderer(fonts, qt_fonts, themes, images)
        return cls(
            app=app,
            out=out,
            project=project,
            ratio=ratio,
            size_calculator=size_calculator,
            fonts=fonts,
            images_from_web=images_from_web,
            updates=updates,
            logs=logs,
            project_store=ProjectStore(size_calculator, images_from_web),
            pipeline=pipeline,
            figure_builder=FigureBuilder(pipeline),
            output=Output(fonts),
            themes=themes,
            qt_fonts=qt_fonts,
            images=images,
            minis=minis,
            sheets=SheetRenderer(minis),
            problems=ProblemReporter(logs),
        )

    def settle(
        self, cond: Callable[[], bool] = lambda: True, timeout: float = 600
    ) -> None:
        """Process events until ``cond()`` holds or ``timeout`` seconds pass, then a
        little longer."""
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            time.sleep(POLL_S)
            if cond():
                break
        for _ in range(SETTLE_ROUNDS):
            self.app.processEvents()
            time.sleep(SETTLE_S)

    def save(self, img: QImage | QPixmap, name: str) -> None:
        """Save ``img`` as ``name``.png in the output folder; ``name`` may hold a
        subfolder."""
        path = self.out / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path))
        print(f"wrote {path}")
