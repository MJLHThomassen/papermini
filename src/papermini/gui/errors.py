"""Reports problems: opens the log folder or a new bug report, and offers to report an earlier crash."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from ..support import log


# ------------------------------------------------------------ reporting
def open_log_folder() -> None:
    s = log.session()
    folder = s.log.parent if s else log.log_dir()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def report_problem(
    parent=None, details: str = "", files: list[Path] | None = None
) -> None:
    """Open a new bug report on GitHub with the version, the operating system and how
    papermini runs filled in (and ``details``, a traceback, when given), open the log
    folder, and say which file to attach: ``files``, or the newest log."""
    QDesktopServices.openUrl(QUrl(log.issue_url(details), QUrl.StrictMode))
    s = log.session()
    if files is None:
        files = [s.log] if s else []
    if files:
        open_log_folder()
        names = "\n".join(f"  {f.name}" for f in files)
        text = (
            "A new issue opened in your browser. Describe what happened and how to make "
            "it happen again, then drag this from the log folder into its Log file "
            f"field:\n\n{names}"
        )
    else:
        text = (
            "A new issue opened in your browser. Describe what happened and how to make "
            "it happen again. (papermini could not write a log this time.)"
        )
    QMessageBox.information(parent, "Report a problem", text)


def offer_crash_report(parent=None) -> None:
    """At start: offer to report the newest crash of an earlier session, once. Every
    crash found is marked as offered, whatever the answer."""
    found = log.crashes()
    if not found:
        return
    crash, crash_log = found[0]
    box = QMessageBox(
        QMessageBox.Warning, "papermini", "papermini closed unexpectedly", parent=parent
    )
    box.setInformativeText(
        "The last time, papermini stopped because of a problem. "
        "Reporting it helps to get it fixed."
    )
    report = box.addButton("Report a problem…", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    box.exec()
    for c, _ in found:
        log.mark_offered(c)
    if box.clickedButton() is report:
        done = log.reported(crash)
        files = [done if done.exists() else crash]
        if crash_log.exists():
            files.append(crash_log)
        report_problem(parent, files=files)
