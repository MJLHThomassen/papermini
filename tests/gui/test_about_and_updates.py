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
    what would be downloaded and installed."""
    from papermini.support import update

    calls = {"download": [], "install": []}
    rel = update.Release("99.0.0", "https://example.invalid/release")
    monkeypatch.setattr(update, "latest_release", lambda *a, **k: rel)
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


def test_an_update_from_the_about_window_installs_on_quit(
    app, fake_updates, new_window, wait
):
    """About checks, Update downloads with progress, the bar shows it is ready, and
    closing papermini installs it (and starts it again after Restart now)."""
    from papermini.gui.dialogs.about_dialog import AboutDialog

    w = new_window()
    about = AboutDialog(w)
    w._about = about  # (as show_about does, without the modal exec)
    w.check_updates(source="about")
    assert wait(lambda: about.action.isVisibleTo(about), 20)
    assert about.action.text() == "Update" and "99.0.0" in about.status.text()
    assert fake_updates["download"] == []  # the About window asks first
    about.action.click()
    assert wait(lambda: w._update_ready is not None, 20)
    assert fake_updates["download"] == ["99.0.0"]
    assert about.action.text() == "Restart now"
    assert w.update_bar.isVisibleTo(w) and "99.0.0" in w.update_text.text()
    w._about = None
    w._restart_for_update()  # closes the window: the helper installs and restarts
    assert len(fake_updates["install"]) == 1 and fake_updates["install"][0][1] is True


def test_an_installed_copy_checks_for_updates_once_a_day(
    app, fake_updates, monkeypatch, tmp_path, new_window, wait
):
    """Only an installed copy checks, at most once a day; with Update automatically off
    it announces the new version instead of downloading it."""
    from papermini.gui import prefs
    from papermini.support import update

    w = new_window()
    asked = []
    real_check = w.check_updates
    monkeypatch.setattr(w, "check_updates", lambda *a, **k: asked.append(k or a))
    monkeypatch.delenv(update.INSTALL_ENV, raising=False)
    w._startup_updates()
    assert asked == []  # run from source: no daily check
    monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "installed"))
    prefs.store().setValue("updates/last_check", time.time())
    w._startup_updates()
    assert asked == []  # checked today already
    prefs.store().setValue("updates/last_check", 0.0)
    w._startup_updates()
    assert len(asked) == 1
    # automatic updating off: the daily check announces, and downloads nothing
    w.set_auto_updates(False)
    real_check(source="auto")
    assert wait(lambda: w.update_bar.isVisibleTo(w), 20)
    assert "available" in w.update_text.text() and w.update_restart.text() == "Update…"
    assert fake_updates["download"] == []
    assert prefs.store().value("updates/auto", type=bool) is False


def test_check_for_updates_is_in_the_menu_and_update_automatically_in_the_preferences(
    app, new_window
):
    """Check for updates is in the menu; Update automatically is in Preferences, on by
    default, and its tick box sets the preference."""
    from papermini.gui import prefs
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    w = new_window()
    texts = [a.text() for a in w.menu.actions()]
    assert "Check for updates…" in texts
    assert w.auto_updates()  # on by default
    dlg = PreferencesDialog(w, "updates")
    assert dlg.auto_updates.isChecked()
    dlg.auto_updates.setChecked(False)
    assert (
        not w.auto_updates() and prefs.store().value("updates/auto", type=bool) is False
    )
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
