"""The desktop app's error handling (offscreen): the error dialog, start-up errors, the
crash offer, Report a problem, and what the window writes to the log."""

import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from papermini.project.figure_settings import FigureSettings
from papermini.support import log


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch, downloaded_default_model):
    """The default model is "downloaded" (so nothing asks to download it), and the
    window's warnings are not shown (they would wait for a click)."""
    from papermini.gui.window import main_window

    monkeypatch.setattr(
        main_window.QMessageBox, "warning", staticmethod(lambda *a, **k: None)
    )


@pytest.fixture
def opened(monkeypatch):
    """Links and folders papermini opens, and the messages it shows (nothing opens)."""
    from papermini.gui import errors

    got = {"urls": [], "info": []}
    monkeypatch.setattr(
        errors.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: got["urls"].append(url.toString()) or True),
    )
    monkeypatch.setattr(
        errors.QMessageBox,
        "information",
        staticmethod(lambda parent, title, text, *a: got["info"].append(text)),
    )
    return got


@pytest.fixture
def handler(app, monkeypatch):
    """An installed error handler whose dialogs are recorded instead of shown."""
    from papermini.gui import error_handler

    shown = []
    monkeypatch.setattr(
        error_handler.ErrorDialog, "exec", lambda self: shown.append(self) or 0
    )
    monkeypatch.setattr(error_handler, "_handler", None)
    h = error_handler.install()
    h.shown_dialogs = shown
    yield h
    qInstallMessageHandler(None)


def _log_text() -> str:
    s = log.session()
    for h in log.logger.handlers:
        h.flush()
    return s.log.read_text(encoding="utf-8")


def _raise_later(app, message="boom"):
    def boom():
        raise RuntimeError(message)

    QTimer.singleShot(0, boom)
    app.processEvents()
    app.processEvents()


def test_an_uncaught_error_is_logged_and_shown_once_and_the_app_keeps_running(
    app, handler, wait
):
    log.start()
    handler.started(None)
    for _ in range(2):  # the same error (type and place) twice
        _raise_later(app)
    assert len(handler.shown_dialogs) == 1
    dlg = handler.shown_dialogs[0]
    assert "RuntimeError: boom" in dlg.details.toPlainText()
    text = _log_text()
    assert text.count("ERROR papermini.error: Unexpected error") == 2
    assert "Traceback (most recent call last)" in text and "RuntimeError: boom" in text
    assert str(Path.home()) not in text
    assert wait(lambda: True)  # (still running)


def test_errors_from_threads_reach_the_dialog(app, handler, wait):
    import threading

    log.start()
    handler.started(None)
    t = threading.Thread(target=lambda: 1 / 0, name="worker")
    t.start()
    t.join()
    assert wait(lambda: handler.shown_dialogs, 10)
    assert "ZeroDivisionError" in handler.shown_dialogs[0].details.toPlainText()
    assert "Unexpected error in thread worker" in _log_text()


def test_the_error_dialog_unfolds_its_details_in_a_resizable_window(app):
    from papermini.gui.dialogs.error_dialog import ErrorDialog

    details = "Traceback (most recent call last):\n" + '  File "x.py", line 1\n' * 40
    dlg = ErrorDialog(None, "RuntimeError: boom", details)
    dlg.setAttribute(Qt.WA_DontShowOnScreen)
    dlg.show()
    app.processEvents()
    folded = dlg.size()
    assert not dlg.details.isVisible() and dlg.isSizeGripEnabled()
    dlg.toggle.click()
    app.processEvents()
    assert dlg.details.isVisible() and dlg.copy.isVisible()
    assert dlg.width() > folded.width() and dlg.height() > folded.height()
    assert dlg.toggle.text() == "Hide details"
    dlg.copy.click()
    assert QApplication.clipboard().text() == details
    dlg.grab()  # (renders)
    buttons = [b.text() for b in dlg.findChildren(type(dlg.toggle))]
    assert "Report a problem…" in buttons and "Continue" in buttons
    dlg.close()


def test_report_a_problem_from_the_error_dialog_fills_in_the_traceback(
    app, handler, opened, monkeypatch
):
    from papermini.gui import error_handler

    log.start()
    handler.started(None)
    monkeypatch.setattr(
        error_handler.ErrorDialog,
        "exec",
        lambda self: setattr(self, "reported", True) or 0,
    )
    _raise_later(app, "reported error")
    issue, folder = opened["urls"]
    assert "template=bug_report.yml" in issue and "traceback=" in issue
    assert "reported error" in issue
    assert (
        folder.startswith("file:")
        and Path(folder[len("file:///") :]).name == _folder_name()
    )
    assert log.session().log.name in opened["info"][0]


def _folder_name() -> str:
    return log.session().log.parent.name


def test_an_error_while_starting_offers_quit_and_exits(app, handler, monkeypatch):
    from papermini.gui import error_handler

    exits = []
    monkeypatch.setattr(error_handler.os, "_exit", exits.append)
    log.start()
    try:
        raise RuntimeError("cannot start")
    except RuntimeError:
        handler.report_exception(*sys.exc_info())
    dlg = handler.shown_dialogs[0]
    assert "Quit" in [b.text() for b in dlg.findChildren(type(dlg.toggle))]
    assert exits == [1]


def test_run_reports_a_failing_start_and_returns_1(app, monkeypatch):
    from papermini.gui import app as gui_app
    from papermini.gui import error_handler

    shown, exits = [], []
    monkeypatch.setattr(
        error_handler.ErrorDialog, "exec", lambda self: shown.append(self) or 0
    )
    monkeypatch.setattr(error_handler.os, "_exit", exits.append)
    monkeypatch.setattr(error_handler, "_handler", None)

    def fail(app, files):
        raise RuntimeError("no window")

    monkeypatch.setattr(gui_app, "_start", fail)
    try:
        assert gui_app.run([]) == 1
    finally:
        qInstallMessageHandler(None)
    assert len(shown) == 1 and exits == [1]
    assert "RuntimeError: no window" in Path(
        max(Path(os.environ[log.LOG_ENV]).glob("papermini-*.log"))
    ).read_text(encoding="utf-8")


def test_a_crash_is_offered_once_and_names_its_files(app, opened, monkeypatch):
    from papermini.gui import errors

    d = Path(os.environ[log.LOG_ENV])
    crash = d / f"papermini-20261111-100000-77{log.CRASH}"
    crash.write_text("Fatal Python error: Segmentation fault\n", encoding="utf-8")
    (d / "papermini-20261111-100000-77.log").write_text("log\n", encoding="utf-8")
    log.start()
    asked = []

    def answer(box):
        asked.append(box.text())
        next(b for b in box.buttons() if b.text() == "Report a problem…").click()

    monkeypatch.setattr(errors.QMessageBox, "exec", answer)
    errors.offer_crash_report(None)
    assert asked == ["papermini closed unexpectedly"]
    assert opened["urls"][0].startswith(log.ISSUE_URL)
    info = opened["info"][0]
    assert (
        log.reported(crash).name in info and "papermini-20261111-100000-77.log" in info
    )
    assert not crash.exists() and log.reported(crash).exists()
    errors.offer_crash_report(None)  # once only
    assert len(asked) == 1


def test_report_a_problem_in_the_menu_names_the_newest_log(app, opened, new_window):
    s = log.start()
    w = new_window()
    assert w.a_open_logs.isEnabled()
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    assert PreferencesDialog(w, "logging").detailed_log.isEnabled()
    w.a_report.trigger()
    issue, _folder = opened["urls"]
    assert issue.startswith(log.ISSUE_URL) and "traceback=" not in issue
    assert s.log.name in opened["info"][0]


def test_without_a_log_the_menu_still_reports(
    app, opened, tmp_path, monkeypatch, new_window
):

    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(log.LOG_ENV, str(blocker / "logs"))
    assert log.start() is None
    w = new_window()
    assert not w.a_open_logs.isEnabled()
    w.a_report.trigger()
    assert len(opened["urls"]) == 1 and "could not write a log" in opened["info"][0]


def test_about_shows_where_the_log_is(app, new_window):
    from PySide6.QtWidgets import QLabel

    from papermini.gui.dialogs.about_dialog import AboutDialog

    s = log.start()
    w = new_window()
    d = AboutDialog(w)
    texts = " ".join(lb.text() for lb in d.findChildren(QLabel))
    assert s.log.name in texts and "Log:" in texts
    d.close()


@pytest.mark.parametrize(
    "error, expected",
    [
        (
            ValueError("the figure is too small"),
            (
                "WARNING papermini.build: Building hero.png failed: "
                "the figure is too small (height_mm=45)"
            ),
        ),
        (
            RuntimeError("bug"),
            (
                "ERROR papermini.build: Building hero.png failed unexpectedly "
                "(height_mm=45)"
            ),
        ),
    ],
)
def test_build_errors_are_logged_with_the_figures_settings(
    app, tmp_path, monkeypatch, error, expected, new_window, wait, figure_image
):
    from papermini.gui.window import build_job

    def fail(*a, **k):
        raise error

    monkeypatch.setattr(build_job, "build_mini", fail)
    log.start()
    w = new_window()
    w.add_images(
        [figure_image(tmp_path / "hero.png", (200, 300), mask=False)[0]],
        FigureSettings(height_mm=45),
    )
    assert wait(lambda: w.figures and w.figures[0].error)
    text = _log_text()
    assert expected in text
    assert ("Traceback" in text) == isinstance(error, RuntimeError)
    assert "Added 1 image(s): hero.png" in text


def test_settings_changes_go_to_the_detailed_log_once_they_settle(
    app, tmp_path, monkeypatch, wait, new_window, figure_image
):
    from papermini.gui.window import build_job

    monkeypatch.setattr(
        build_job,
        "build_mini",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("not built in this test")),
    )
    log.start()
    w = new_window()
    try:
        w.add_images([figure_image(tmp_path / "hero.png", (200, 300), mask=False)[0]])
        fig = w.figures[0]
        w.panel.changed.emit(
            replace(fig.entry.settings, height_mm=50)
        )  # not detailed yet
        from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

        prefs_dlg = PreferencesDialog(
            w, "logging"
        )  # (Preferences → Logging → Detailed log)
        assert not prefs_dlg.detailed_log.isChecked()
        prefs_dlg.detailed_log.setChecked(True)
        assert log.detailed()
        for h in (51, 52, 53):  # like dragging a spin box
            w.panel.changed.emit(replace(fig.entry.settings, height_mm=h))
        w.sheet_panel.changed.emit(replace(w.project.sheet, paper="letter"))
        assert wait(lambda: "height_mm 50 → 53" in _log_text(), 10)
        text = _log_text()
        assert "hero.png: height_mm 50 → 53" in text and "32 → 50" not in text
        assert "sheet: paper 'a4' → 'letter'" in text
        assert text.count("height_mm 5") == 1  # one line for the three changes
        w.project.path = tmp_path / "project.yaml"
        assert w.save()  # (nothing asks to save before opening the next project)
        broken = tmp_path / "broken.yaml"
        broken.write_text("figures: [", encoding="utf-8")
        w.load(broken)
        text = _log_text()  # (the home folder is written as ~)
        assert "WARNING papermini.ui: Could not open " in text
        assert "broken.yaml:; " in text  # one line
    finally:
        log.set_detailed(False)
    assert logging.getLogger("papermini").level == logging.INFO
