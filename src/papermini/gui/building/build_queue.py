from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ...pipeline.pipeline import Pipeline
from ...pipeline.segmentation import segment
from ...pipeline.segmentation.download_hooks import DownloadHooks
from ...project.figure_builder import FigureBuilder
from ..window.figure import Figure
from .build_job import BuildJob
from .build_result import BuildResult
from .job_signals import JobSignals
from .model_run import ModelRun

DEBOUNCE_MS = 250  # how long settings must stay put before the current figure builds
CLOSE_WAIT_MS = 15000  # how long closing waits for a build to stop


class BuildQueue(QObject):
    """Builds the figures' miniatures with ``figure_builder`` on one worker thread,
    and takes each finished build only while it matches its figure's settings (see
    ``Figure``).

    ``run`` is the model run in progress. ``cancel`` stops it and marks its figure
    cancelled for the mask it ran for, so that no build of that figure starts until its
    image, model, mask or crop changes, or the user runs it again.

    ``figure(uid)`` finds a figure, and ``current()`` returns the selected one, which
    builds first. Every build gets ``downloads``.
    """

    built = Signal(object, object)  # Figure, Mini: built for its current settings
    failed = Signal(object, str)  # Figure, message: its build for them failed
    cancelled = Signal(object)  # Figure: the user cancelled its model run
    outline = Signal(object, object)  # Figure, (contours, close_px): figure found
    run_started = Signal()  # a model run started: ``run`` is set
    run_ended = Signal()  # the model run ended: ``run`` is None
    building = Signal(object)  # Figure: the selected figure was queued
    ready = Signal(object)  # Figure: the selected figure is built for its settings
    held = Signal()  # the selected figure waits until the user runs it again
    status = Signal(str)

    def __init__(
        self,
        pipeline: Pipeline,
        figure_builder: FigureBuilder,
        downloads: DownloadHooks,
        figure: Callable[[int], Figure | None],
        current: Callable[[], Figure | None],
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._pipeline = pipeline
        self._figure_builder = figure_builder
        self.downloads = downloads
        self._figure = figure
        self._current = current
        self._closed = False
        self.run: ModelRun | None = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)  # one model run at a time
        self._sig = JobSignals(self)
        self._sig.finished.connect(self._on_finished)
        self._sig.stage.connect(self._on_stage)
        self._sig.status.connect(self.status)
        self._timer = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._timer.timeout.connect(self.build_current)
        segment.CANCEL.clear()

    # region queueing

    def build_soon(self) -> None:
        """Build the selected figure once its settings stay put for a moment."""
        self._timer.start()

    def build_current(self) -> None:
        """Build the selected figure now, unless it is built for its settings or the
        user cancelled it."""
        fig = self._current()
        if fig is None:
            return
        if fig.stopped and not fig.up_to_date:
            self.held.emit()  # cancelled by the user: wait until they run it again
        elif not fig.up_to_date:
            self.queue(fig)
            self.building.emit(fig)
        else:
            self.ready.emit(fig)  # settings went back to what is already built

    def queue(self, fig: Figure) -> None:
        """Build ``fig`` for its current settings, unless that build already waits."""
        key = fig.key()
        if fig.queued == key or fig.stopped or self._closed:
            return  # already waiting, stopped by the user (see cancel), or closed
        fig.queued = key
        # the selected figure jumps ahead of background (sheet) builds
        priority = 10 if fig is self._current() else 0
        self.pool.start(
            BuildJob(
                self._sig,
                fig,
                self._is_current,
                self._pipeline,
                self._figure_builder,
                self.downloads,
            ),
            priority,
        )

    def _is_current(self, uid, key) -> bool:
        """A build is wanted iff it is for the figure's current settings, and the user
        did not cancel its background removal."""
        f = self._figure(uid)
        return f is not None and f.key() == key and not f.stopped

    # endregion

    # region results

    def _on_finished(self, result: BuildResult) -> None:
        if result.mini is not None:
            self._on_done(result)
        elif result.error is not None:
            self._on_failed(result)
        else:
            self._on_cancelled(result)

    def _on_done(self, result: BuildResult) -> None:
        fig = self._figure(result.uid)
        if fig is None or fig.key() != result.key:
            return  # settings changed meanwhile (a newer build is queued)
        if fig.queued == result.key:
            fig.queued = None
        fig.mini, fig.built_key, fig.error = result.mini, result.key, None
        fig.cancelled = None  # (finished just before a cancel could stop it)
        self._end_run(result.uid)
        self.built.emit(fig, result.mini)

    def _on_failed(self, result: BuildResult) -> None:
        self._end_run(result.uid)
        fig = self._figure(result.uid)
        if fig is None or fig.key() != result.key:
            return
        fig.error, fig.queued = result.error, None
        self.failed.emit(fig, result.error)

    def _on_cancelled(self, result: BuildResult) -> None:
        """A build stopped: by ``cancel``, which already marked the figure, or
        because a new crop or model made it useless (that one is built next)."""
        self._end_run(result.uid)
        fig = self._figure(result.uid)
        if fig is not None and fig.queued == result.key:
            fig.queued = None

    def _on_stage(self, uid, key, mask_key, name, data) -> None:
        """Progress of a build: a model starts ("segment"), or the figure was found
        ("outline", before the miniature is laid out)."""
        if name == "segment":
            self.run = ModelRun(uid, mask_key, data, time.monotonic())
            self.run_started.emit()
            return
        if name == "outline":
            self._end_run(uid)
            fig = self._figure(uid)
            if fig is not None and fig.key() == key:
                self.outline.emit(fig, data)

    # endregion

    # region cancelling

    def cancel(self) -> None:
        """Stop the running model. Its figure is marked cancelled at once, even when
        the build only notices later (a model still loading finishes that first)."""
        run = self.run
        self._pipeline.cancellation.cancel_runs()
        if run is None:
            return
        self._end_run(run.uid)
        fig = self._figure(run.uid)
        if fig is None or fig.mask_key() != run.mask_key:
            return
        fig.cancelled, fig.queued = (
            run.mask_key,
            None,
        )  # (a build still waiting is skipped)
        self.cancelled.emit(fig)

    def settings_changed(self, fig: Figure, old_mask_key: str) -> None:
        """Take a change to the settings of ``fig``, whose ``mask_key()`` was
        ``old_mask_key``. A model running for the old mask stops, since the new one is
        built next, and a new image, crop or model clears an earlier cancel."""
        run = self.run
        if (
            run
            and run.uid == fig.uid
            and run.mask_key == old_mask_key != fig.mask_key()
        ):
            self._pipeline.cancellation.cancel_runs()
        if not fig.stopped:
            fig.cancelled = None

    def close(self) -> None:
        """Drop the waiting builds and stop the running one; nothing builds after
        this."""
        self._closed = True
        self._timer.stop()
        self.pool.clear()
        segment.CANCEL.set()  # abort a model download in progress
        self._pipeline.cancellation.cancel_runs()  # and a model run
        self.pool.waitForDone(CLOSE_WAIT_MS)  # builds stop at the next checkpoint
        segment.CANCEL.clear()

    def _end_run(self, uid: int) -> None:
        if self.run is not None and self.run.uid == uid:
            self.run = None
            self.run_ended.emit()

    # endregion
