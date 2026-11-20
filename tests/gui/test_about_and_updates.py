"""Tests of the About window and of updating from the app."""

import time

import pytest

pytest.importorskip("PySide6")


pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_the_about_window_shows_each_update_state(app, new_window):
    from papermini.gui.dialogs.about_dialog import AboutDialog
    from papermini.support.release import Release

    w = new_window()
    d = AboutDialog(w)
    rel = Release("99.0.0", "")
    for state, data, text, button in (
        ("checking", None, "Checking", None),
        ("latest", rel, "latest version", None),
        ("available", (rel, None), "99.0.0", "Update"),
        (
            "available",
            (rel, "runs from source"),
            "runs from source",
            "Release page",
        ),
        ("downloading", rel, "Downloading", None),
        ("ready", (rel, None), "ready", "Restart now"),
        ("error", "Could not check for updates: offline", "offline", "Try again"),
    ):
        d.update_state(state, data)
        assert text in d.status.text(), state
        assert d.action.isVisibleTo(d) == (button is not None), state
        if button:
            assert d.action.text() == button
    d.update_state("downloading", rel)
    d.update_state("progress", (58_000_000, 129_000_000))
    assert d.progress.isVisibleTo(d) and "58 of 129 MB" in d.progress.format()
    d.update_state("ready", (rel, None))
    assert not d.progress.isVisibleTo(d)


@pytest.fixture
def fake_updates(monkeypatch, tmp_path):
    """A newer release that this copy can install, without network or helper: records
    the checks, and what would be downloaded and installed."""
    from papermini.support import update

    calls = {"check": [], "download": [], "install": []}
    rel = update.Release("99.0.0", "https://example.invalid/release")

    def latest_release(*a, **k):
        calls["check"].append(rel.version)
        return rel

    monkeypatch.setattr(update, "latest_release", latest_release)
    monkeypatch.setattr(update, "unsupported", lambda: None)

    def download(r, progress=None, step=None, **k):
        calls["download"].append(r.version)
        if progress:
            progress(50, 100)
            progress(100, 100)
        for name in ("verifying", "unpacking"):
            if step:
                step(name)
        app = tmp_path / "new" / "papermini"
        app.mkdir(parents=True, exist_ok=True)
        return app

    monkeypatch.setattr(update, "download", download)
    monkeypatch.setattr(
        update,
        "install_on_exit",
        lambda app, restart=False: calls["install"].append((app, restart)),
    )
    return calls


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """Makes papermini run as an installed copy, which updates itself."""
    from papermini.support import update

    monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "installed"))


@pytest.fixture
def waiting_update(monkeypatch, tmp_path):
    """Puts a downloaded update of papermini 99.0.0 in place, ready to install."""
    from papermini.support import update

    app = tmp_path / "updates" / "99.0.0" / "new" / "papermini"
    monkeypatch.setattr(update, "pending", lambda: ("99.0.0", app))
    monkeypatch.setattr(update, "forget_old", lambda: None)
    return app


def start_up(w, wait):
    """Run the window's start-up update step, as turning on Update automatically in
    the Preferences does."""
    from PySide6.QtCore import QTimer

    dlg = w.preferences_dialog("updates")
    dlg.auto_updates.setChecked(False)
    dlg.auto_updates.setChecked(True)
    dlg.deleteLater()
    done = []
    QTimer.singleShot(0, lambda: done.append(True))
    assert wait(lambda: done, 20)


def daily_check(w):
    """Start the daily update check whatever the preferences say."""
    w.check_updates(source="auto")


def update_bar(w):
    from PySide6.QtWidgets import QFrame

    return w.findChild(QFrame, "UpdateBar")


def bar_state(w):
    """Return the update bar's text and the texts of its buttons, or None while it is
    hidden."""
    from PySide6.QtWidgets import QLabel, QPushButton

    bar = update_bar(w)
    if not bar.isVisibleTo(w):
        return None
    text = bar.findChild(QLabel, "UpdateText").text()
    return text, [b.text() for b in bar.findChildren(QPushButton)]


def click_in_bar(w, text):
    from PySide6.QtWidgets import QPushButton

    bar = update_bar(w)
    next(b for b in bar.findChildren(QPushButton) if b.text() == text).click()


def status(w):
    return w.statusBar().currentMessage()


READY = "papermini 99.0.0 is ready: it is installed when you close papermini."


def test_an_update_from_the_about_window_installs_on_quit(
    app, fake_updates, monkeypatch, new_window, wait
):
    """About checks, Update downloads with progress, the bar shows it is ready, and
    closing papermini installs it (and starts it again after Restart now)."""
    from papermini.gui.dialogs.about_dialog import AboutDialog

    def use(about):  # (instead of the modal exec)
        assert wait(lambda: about.action.isVisibleTo(about), 20)
        assert about.action.text() == "Update" and "99.0.0" in about.status.text()
        assert fake_updates["download"] == []  # the About window asks first
        about.action.click()
        assert wait(lambda: about.action.text() == "Restart now", 20)
        assert fake_updates["download"] == ["99.0.0"]
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    w = new_window()
    w.show_about()
    assert bar_state(w) == (READY, ["What's new", "Restart now"])
    assert status(w) == "papermini 99.0.0 is ready to install"
    click_in_bar(w, "Restart now")  # closes the window: the helper installs, restarts
    assert len(fake_updates["install"]) == 1 and fake_updates["install"][0][1] is True


def test_an_installed_copy_checks_for_updates_once_a_day(
    app, fake_updates, monkeypatch, tmp_path, new_window, wait, prefs
):
    """Only an installed copy checks, at most once a day; with Update automatically on
    it downloads the new version and shows in the bar that it is ready."""
    from papermini.support import update

    w = new_window()
    monkeypatch.delenv(update.INSTALL_ENV, raising=False)
    start_up(w, wait)
    assert fake_updates["check"] == []  # run from source: no daily check
    monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "installed"))
    prefs.set_last_update_check(time.time())
    start_up(w, wait)
    assert fake_updates["check"] == []  # checked today already
    prefs.set_last_update_check(0.0)
    start_up(w, wait)
    assert wait(lambda: bar_state(w) is not None, 20)
    assert fake_updates["check"] == ["99.0.0"]
    assert fake_updates["download"] == ["99.0.0"]
    assert bar_state(w) == (READY, ["What's new", "Restart now"])
    assert status(w) == "papermini 99.0.0 is ready to install"
    assert time.time() - prefs.last_update_check() < 60


def test_with_update_automatically_off_nothing_is_checked_at_start_up(
    app, fake_updates, installed, new_window, wait, prefs
):
    from PySide6.QtCore import QTimer

    w = new_window()
    dlg = w.preferences_dialog("updates")
    dlg.auto_updates.setChecked(False)
    dlg.deleteLater()
    done = []
    QTimer.singleShot(0, lambda: done.append(True))
    assert wait(lambda: done, 20)
    assert prefs.auto_updates() is False
    assert fake_updates["check"] == []
    assert bar_state(w) is None


def test_the_update_bar_announces_an_update_and_opens_the_about_window_for_it(
    app, fake_updates, installed, monkeypatch, new_window, wait, prefs
):
    """With Update automatically off, the daily check announces the new version in the
    bar and downloads nothing; the bar's Update hides the bar and opens About, which
    checks again and offers Update."""
    from papermini.gui.dialogs.about_dialog import AboutDialog

    prefs.set_auto_updates(False)
    w = new_window()
    daily_check(w)
    assert wait(lambda: bar_state(w) is not None, 20)
    assert bar_state(w) == (
        "papermini 99.0.0 is available.",
        ["What's new", "Update…"],
    )
    assert fake_updates["download"] == []
    assert prefs.auto_updates() is False

    shown = []

    def use(about):  # (instead of the modal exec)
        assert wait(lambda: about.action.isVisibleTo(about), 20)
        shown.append((about.status.text(), about.action.text()))
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    click_in_bar(w, "Update…")
    assert shown == [("<b>papermini 99.0.0</b> is available.", "Update")]
    assert fake_updates["check"] == ["99.0.0", "99.0.0"]
    assert fake_updates["download"] == []
    assert bar_state(w) is None


def test_an_update_waiting_at_start_up_shows_in_the_bar_and_the_about_window(
    app, fake_updates, installed, waiting_update, monkeypatch, new_window, wait
):
    """A downloaded update shows in the bar at once, without a check; What's new opens
    its release page, and About offers Restart now, which installs it and restarts."""
    from PySide6.QtGui import QDesktopServices

    from papermini.gui.dialogs.about_dialog import AboutDialog

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    w = new_window()
    start_up(w, wait)
    assert bar_state(w) == (READY, ["What's new", "Restart now"])
    assert status(w) == "papermini 99.0.0 is ready to install"
    click_in_bar(w, "What's new")
    assert [u.toString() for u in opened] == [
        "https://github.com/MJLHThomassen/papermini/releases/tag/v99.0.0"
    ]

    shown = []

    def use(about):  # (instead of the modal exec)
        shown.append((about.status.text(), about.action.text()))
        about.action.click()
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    w.show_about()
    assert shown == [
        (
            (
                "<b>papermini 99.0.0</b> is ready: it is installed when you close "
                "papermini."
            ),
            "Restart now",
        )
    ]
    assert fake_updates["check"] == []
    assert fake_updates["install"] == [(waiting_update, True)]


def test_closing_papermini_installs_a_waiting_update_without_restarting(
    app, fake_updates, installed, waiting_update, new_window, wait
):
    w = new_window()
    start_up(w, wait)
    w.close()
    assert fake_updates["install"] == [(waiting_update, False)]


def test_closing_papermini_without_an_update_installs_nothing(
    app, fake_updates, new_window
):
    w = new_window()
    w.close()
    assert fake_updates["install"] == []


def test_the_about_window_says_when_this_is_the_latest_version(
    app, fake_updates, monkeypatch, new_window, wait, prefs
):
    from papermini.gui.dialogs.about_dialog import AboutDialog
    from papermini.support import update

    monkeypatch.setattr(
        update, "latest_release", lambda *a, **k: update.Release("0.0.1", "")
    )
    shown = []

    def use(about):  # (instead of the modal exec)
        assert wait(lambda: "Checking" not in about.status.text(), 20)
        shown.append((about.status.text(), about.action.isVisibleTo(about)))
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    w = new_window()
    w.show_about()
    assert shown == [("This is the latest version.", False)]
    assert status(w) == "papermini is up to date"
    assert bar_state(w) is None
    assert time.time() - prefs.last_update_check() < 60


def test_an_error_from_the_check_shows_in_the_about_window_which_can_try_again(
    app, fake_updates, monkeypatch, new_window, wait, prefs
):
    """A failed check shows its error in About and in the status bar, and is not
    remembered as a check; Try again checks again."""
    from papermini.gui.dialogs.about_dialog import AboutDialog
    from papermini.support import update

    working = update.latest_release

    def offline(*a, **k):
        raise OSError("Could not check for updates: offline")

    monkeypatch.setattr(update, "latest_release", offline)
    shown = []

    def use(about):  # (instead of the modal exec)
        assert wait(lambda: about.action.isVisibleTo(about), 20)
        shown.append((about.status.text(), about.action.text(), status(w)))
        monkeypatch.setattr(update, "latest_release", working)
        about.action.click()
        shown.append(about.status.text())
        assert wait(lambda: about.action.text() == "Update", 20)
        shown.append((about.status.text(), about.action.text()))
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    w = new_window()
    w.show_about()
    assert shown == [
        (
            "Could not check for updates: offline",
            "Try again",
            "Could not check for updates: offline",
        ),
        "Checking for updates…",
        ("<b>papermini 99.0.0</b> is available.", "Update"),
    ]
    assert fake_updates["check"] == ["99.0.0"]
    assert bar_state(w) is None


def test_an_error_from_the_daily_check_shows_in_the_status_bar(
    app, fake_updates, installed, monkeypatch, new_window, wait, prefs
):
    from papermini.support import update

    def offline(*a, **k):
        raise OSError("Could not check for updates: offline")

    monkeypatch.setattr(update, "latest_release", offline)
    w = new_window()
    start_up(w, wait)
    assert wait(lambda: status(w) == "Could not check for updates: offline", 20)
    assert bar_state(w) is None
    assert fake_updates["download"] == []
    assert prefs.last_update_check() == 0.0


def test_an_error_from_the_download_shows_in_the_about_window(
    app, fake_updates, monkeypatch, new_window, wait
):
    """A failed download shows its error in About and in the status bar, and leaves
    nothing to install."""
    from papermini.gui.dialogs.about_dialog import AboutDialog
    from papermini.support import update

    def broken(*a, **k):
        raise OSError("The download is damaged")

    monkeypatch.setattr(update, "download", broken)
    shown = []

    def use(about):  # (instead of the modal exec)
        assert wait(lambda: about.action.text() == "Update", 20)
        about.action.click()
        assert wait(lambda: about.action.text() == "Try again", 20)
        shown.append((about.status.text(), about.progress.isVisibleTo(about)))
        return 0

    monkeypatch.setattr(AboutDialog, "exec", use)
    w = new_window()
    w.show_about()
    assert shown == [("The download is damaged", False)]
    assert status(w) == "The download is damaged"
    assert bar_state(w) is None
    w.close()
    assert fake_updates["install"] == []


def test_check_for_updates_is_in_the_menu_and_update_automatically_in_the_preferences(
    app, new_window, prefs
):
    """Check for updates is in the menu; Update automatically is in Preferences, on by
    default, and its tick box sets the preference."""
    w = new_window()
    texts = [a.text() for a in w.menu.actions()]
    assert "Check for updates…" in texts
    assert prefs.auto_updates()  # on by default
    dlg = w.preferences_dialog("updates")
    assert dlg.auto_updates.isChecked()
    dlg.auto_updates.setChecked(False)
    assert prefs.auto_updates() is False
    dlg.close()


def test_about_names_the_font_licence(app, monkeypatch, new_window):
    """About lists the bundled fonts and their licence, with a link to their folder."""
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QLabel

    from papermini.gui.dialogs.about_dialog import AboutDialog
    from papermini.support import fonts

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    w = new_window()
    d = AboutDialog(w)
    label = next(
        lb for lb in d.findChildren(QLabel) if "Open Font License" in lb.text()
    )
    assert all(name in label.text() for name in fonts.BUNDLED)
    label.linkActivated.emit("fonts")
    assert [u.toLocalFile() for u in opened] == [fonts.HERE.as_posix()]
    assert (fonts.HERE / "kalam" / "OFL.txt").is_file()
