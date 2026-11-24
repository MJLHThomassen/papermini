from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..support.log_session import LogSession


class ProblemReporter:
    """Reports problems from ``logs``, the session's log: opens the log folder or a new
    bug report, and offers to report an earlier crash."""

    def __init__(self, logs: LogSession) -> None:
        self._logs = logs

    def open_log_folder(self) -> None:
        """Open the folder of the session's log, or of the logs."""
        s = self._logs.session()
        folder = s.log.parent if s else self._logs.log_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def report(
        self, parent=None, details: str = "", files: list[Path] | None = None
    ) -> None:
        """Open a new bug report on GitHub with the version, the operating system and how
        papermini runs filled in (and ``details``, a traceback, when given), open the log
        folder, and say which file to attach: ``files``, or the newest log."""
        logs = self._logs
        QDesktopServices.openUrl(
            QUrl(logs.issue_url(details), QUrl.ParsingMode.StrictMode)
        )
        s = logs.session()
        if files is None:
            files = [s.log] if s else []
        if files:
            self.open_log_folder()
            names = "\n".join(f"  {f.name}" for f in files)
            text = (
                "A new issue opened in your browser. Describe what happened and how to "
                "make it happen again, then drag this from the log folder into its Log "
                f"file field:\n\n{names}"
            )
        else:
            text = (
                "A new issue opened in your browser. Describe what happened and how to "
                "make it happen again. (papermini could not write a log this time.)"
            )
        QMessageBox.information(parent, "Report a problem", text)

    def offer_crash_report(self, parent=None) -> None:
        """Offer to report the newest crash of an earlier session, once. Every crash
        found is marked as offered, whatever the answer."""
        logs = self._logs
        found = logs.crashes()
        if not found:
            return
        crash, crash_log = found[0]
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "papermini",
            "papermini closed unexpectedly",
            parent=parent,
        )
        box.setInformativeText(
            "The last time, papermini stopped because of a problem. "
            "Reporting it helps to get it fixed."
        )
        report = box.addButton("Report a problem…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        for c, _ in found:
            logs.mark_offered(c)
        if box.clickedButton() is report:
            done = logs.reported(crash)
            files = [done if done.exists() else crash]
            if crash_log.exists():
                files.append(crash_log)
            self.report(parent, files=files)
