from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from ... import __version__
from ...support.log_session import LogSession
from ...support.release import Release
from ...support.update import RELEASES
from ...support.update_service import UpdateService
from ..dialogs.about_dialog import AboutDialog
from ..preferences import Preferences
from .available_update import AvailableUpdate
from .download_progress import DownloadProgress
from .ready_update import ReadyUpdate
from .update_bar import UpdateBar
from .update_state import UpdateState

update_log = logging.getLogger("papermini.update")
ui_log = logging.getLogger("papermini.ui")  # what the user does

DAY_S = 24 * 3600  # how long the daily check waits after the last one
PROGRESS_EVERY_S = 0.1  # the shortest time between two reports of download progress


class UpdateController(QObject):
    """Checks for, downloads and installs updates of papermini with ``updates``, and
    shows them in the update bar and the About window, which shows the log of
    ``logs``."""

    status = Signal(str)  # a message for the status bar
    stateChanged = Signal(object, object)  # an UpdateState and its payload
    # an UpdateState, its payload and who asked, from a worker thread
    _reported = Signal(object, object, str)

    def __init__(
        self,
        window: QWidget,
        prefs: Preferences,
        updates: UpdateService,
        logs: LogSession,
    ):
        super().__init__(window)
        self._window = window
        self._prefs = prefs
        self._updates = updates
        self._logs = logs
        self.bar = UpdateBar()
        self.bar.releasePageRequested.connect(self.open_release_page)
        self.bar.actionRequested.connect(self._bar_action)
        self._reported.connect(self._on_report)
        self._ready: ReadyUpdate | None = None  # to install on quit
        self._restart = False
        self._busy = False
        self._release_page = ""

    # region checking and downloading
    def start_up(self) -> None:
        """Offer an update downloaded earlier, or look for one once a day."""
        # run from source: no updates of its own
        if self._updates.install_dir() is None:
            return
        self._updates.forget_old()
        pending = self._updates.pending()
        if pending is not None:
            self._show_ready(ReadyUpdate(pending[0], pending[1], ""))
            return
        last = self._prefs.last_update_check()
        if self._prefs.auto_updates() and time.time() - last > DAY_S:
            self.check(source="auto")

    def check(self, source: str) -> None:
        """Look for a newer papermini in the background. ``source`` says who asked:
        "auto" is the daily check, which runs only with automatic updating on and
        downloads the new version when this copy can install it. "about" is the About
        window, which reports the result itself and leaves downloading to the user."""
        if self._busy:
            return
        self._busy = True
        update_log.info("Checking for updates (%s)", source)
        download = source == "auto" and self._prefs.auto_updates()
        threading.Thread(
            target=self._check_job, args=(source, download), daemon=True
        ).start()

    def download(self, rel: Release, source: str = "about") -> None:
        """Download and verify ``rel`` in the background, ready to install on quit."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(
            target=self._download_job, args=(rel, source), daemon=True
        ).start()

    def _check_job(self, source: str, download: bool) -> None:  # on a worker thread
        try:
            rel = self._updates.latest_release()
        except Exception as e:  # noqa: BLE001 - always report back
            self._reported.emit(UpdateState.ERROR, str(e), source)
            return
        if not Release.is_newer(rel.version, __version__):
            self._reported.emit(UpdateState.LATEST, rel, source)
            return
        why = self._updates.unsupported()
        if why is not None or not download:
            self._reported.emit(
                UpdateState.AVAILABLE, AvailableUpdate(rel, why), source
            )
            return
        self._download_job(rel, source)

    def _download_job(self, rel: Release, source: str) -> None:  # on a worker thread
        last = [0.0]

        def progress(done: int, total: int) -> None:  # (not too often, and at the end)
            now = time.monotonic()
            if now - last[0] >= PROGRESS_EVERY_S or done == total:
                last[0] = now
                self._reported.emit(
                    UpdateState.PROGRESS, DownloadProgress(done, total), source
                )

        try:
            self._reported.emit(UpdateState.DOWNLOADING, rel, source)
            app = self._updates.download(
                rel,
                progress=progress,
                step=lambda name: self._reported.emit(UpdateState(name), rel, source),
            )
            ready = ReadyUpdate(rel.version, app, rel.url)
            self._reported.emit(UpdateState.READY, ready, source)
        except Exception as e:  # noqa: BLE001 - always report back
            self._reported.emit(UpdateState.ERROR, str(e), source)

    def _on_report(self, state: UpdateState, data, source: str) -> None:
        if not state.busy:
            self._busy = False
        self._log(state, data)
        if state in (
            UpdateState.LATEST,
            UpdateState.AVAILABLE,
            UpdateState.READY,
            UpdateState.DOWNLOADING,
        ):
            self._prefs.set_last_update_check(time.time())
        if state is UpdateState.LATEST:
            self.status.emit("papermini is up to date")
        elif state is UpdateState.AVAILABLE:
            self._release_page = data.release.url
            # the About window shows it itself; the daily check announces it only when
            # this copy can install it
            if source == "auto" and data.why is None:
                self.bar.show_available(data.release.version)
        elif state is UpdateState.DOWNLOADING:
            self.status.emit(f"Downloading papermini {data.version}…")
        elif state is UpdateState.PROGRESS:
            if data.total:
                self.status.emit(
                    f"Downloading the update… {100 * data.done // data.total}%"
                )
        elif state is UpdateState.READY:
            self._show_ready(data)
        elif state is UpdateState.ERROR:
            self.status.emit(data)
        self.stateChanged.emit(state, data)

    @staticmethod
    def _log(state: UpdateState, data) -> None:
        """Write a step of an update check, download or install to the log."""
        if state is UpdateState.LATEST:
            update_log.info("papermini is up to date (latest: %s)", data.version)
        elif state is UpdateState.AVAILABLE:
            why = data.why
            update_log.info(
                "papermini %s is available%s",
                data.release.version,
                f" ({why})" if why else "",
            )
        elif state is UpdateState.DOWNLOADING:
            update_log.info("Downloading papermini %s", data.version)
        elif state in (UpdateState.VERIFYING, UpdateState.UNPACKING):
            update_log.info("%s papermini %s", state.value.capitalize(), data.version)
        elif state is UpdateState.READY:
            update_log.info(
                "papermini %s is downloaded and verified: %s", data.version, data.app
            )
        elif state is UpdateState.ERROR:
            update_log.warning("Update failed: %s", data)

    def set_auto_updates(self, on: bool) -> None:
        """Turn updating automatically on or off; turning it on runs the start-up
        step soon after."""
        self._prefs.set_auto_updates(on)
        ui_log.info("Automatic updates %s", "on" if on else "off")
        if on:
            QTimer.singleShot(0, self.start_up)

    # endregion

    # region showing
    def _show_ready(self, ready: ReadyUpdate) -> None:
        self._ready = ready
        self._release_page = ready.page or f"{RELEASES}/tag/v{ready.version}"
        self.bar.show_ready(ready.version)
        self.status.emit(f"papermini {ready.version} is ready to install")

    def _bar_action(self) -> None:
        if self._ready is not None:
            self.restart()
        else:
            self.bar.hide()
            self.show_about()  # (it checks again and offers Update, with its progress)

    def open_release_page(self) -> None:
        """Open the page of the newest release this controller heard of."""
        QDesktopServices.openUrl(QUrl(self._release_page or f"{RELEASES}/latest"))

    def show_about(self) -> None:
        """Open the About window and start an update check for it, unless an update is
        already downloaded or a check is running."""
        about = AboutDialog(self._logs, self._window)
        about.updateRequested.connect(self.download)
        about.releasePageRequested.connect(self.open_release_page)
        about.restartRequested.connect(self.restart)
        about.checkRequested.connect(lambda: self.check(source="about"))
        self.stateChanged.connect(about.update_state)
        try:
            if self._ready is not None:
                about.update_state(UpdateState.READY, self._ready)
            else:
                about.update_state(UpdateState.CHECKING, None)
                self.check(source="about")  # (unless a check is running)
            about.exec()
        finally:
            self.stateChanged.disconnect(about.update_state)

    # endregion

    # region installing
    def restart(self) -> None:
        """Close the window, then install the downloaded update and start it."""
        self._restart = True
        if not self._window.close():  # (the user kept it open, e.g. to save first)
            self._restart = False

    def install_on_quit(self) -> None:
        """Start the helper that installs a downloaded update once papermini has quit."""
        if self._ready is None:
            return
        update_log.info(
            "Installing papermini %s when papermini has closed%s",
            self._ready.version,
            ", then restarting" if self._restart else "",
        )
        try:
            self._updates.install_on_exit(self._ready.app, restart=self._restart)
        except Exception:  # noqa: BLE001 - never block quitting
            update_log.exception("Could not install the update")

    # endregion
