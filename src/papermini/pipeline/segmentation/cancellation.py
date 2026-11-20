from __future__ import annotations

import threading
from contextlib import contextmanager

from . import segment
from .cancelled import Cancelled


class _Job:
    """A build that ``cancel_runs`` can stop, also while no model runs (e.g. while
    the model is still loading, which can take longer than the run itself)."""

    cancelled = False


class Cancellation:
    """Stops builds and model runs from another thread."""

    def __init__(self):
        # RunOptions of the model runs in progress, and the cancellable builds
        self._runs: set = set()
        self._jobs: set = set()
        self._lock = threading.Lock()
        self._local = threading.local()  # the _Job of the build on this thread

    def check(self) -> None:
        """Raise ``Cancelled`` if the build on this thread was stopped."""
        job = getattr(self._local, "job", None)
        if segment.CANCEL.is_set() or (job is not None and job.cancelled):
            raise Cancelled("cancelled")

    @contextmanager
    def cancellable(self):
        """Run a build on this thread that ``cancel_runs`` stops: a model run at once,
        anything else (loading the model) at the next ``check``."""
        job = _Job()
        with self._lock:
            self._jobs.add(job)
        prev, self._local.job = getattr(self._local, "job", None), job
        try:
            yield job
        finally:
            self._local.job = prev
            with self._lock:
                self._jobs.discard(job)

    @contextmanager
    def model_run(self, run_options):
        """Let ``cancel_runs`` stop the model run of ``run_options`` while it lasts."""
        with self._lock:
            self._runs.add(run_options)
        try:
            yield
        finally:
            with self._lock:
                self._runs.discard(run_options)

    def cancel_runs(self) -> int:
        """Stop every model run and cancellable build in progress; each raises
        ``Cancelled``. Returns how many there were."""
        with self._lock:
            for job in self._jobs:
                job.cancelled = True
            for ro in self._runs:
                ro.terminate = True
            return len(self._jobs) + len(self._runs)
