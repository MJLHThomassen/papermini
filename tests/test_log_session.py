"""The desktop app's log: its folder, session files, clean-up, crash files, the home folder
written as ~, and the link for reporting a problem."""

import logging
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

from papermini.project.figure_settings import FigureSettings
from papermini.project.sheet_settings import SheetSettings
from papermini.support import log_session
from papermini.support.update import NEW_ISSUE


def _folder() -> Path:
    return Path(os.environ[log_session.LOG_ENV])


def _query(url: str) -> dict:
    return {
        k: v[0]
        for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()
    }


@pytest.mark.parametrize(
    "platform, env, expected",
    [
        ("win32", {"LOCALAPPDATA": "C:/Local"}, "C:/Local/papermini/logs"),
        ("darwin", {}, "~/Library/Logs/papermini"),
        ("linux", {"XDG_STATE_HOME": "/state"}, "/state/papermini"),
        ("linux", {}, "~/.local/state/papermini"),
    ],
)
def test_log_dir_is_the_systems_log_folder(logs, monkeypatch, platform, env, expected):
    monkeypatch.delenv(log_session.LOG_ENV)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "platform", platform)
    assert logs.log_dir() == Path(expected.replace("~", str(Path.home())))


def test_log_dir_follows_the_environment_variable(logs, tmp_path, monkeypatch):
    monkeypatch.setenv(log_session.LOG_ENV, str(tmp_path / "here"))
    assert logs.log_dir() == tmp_path / "here"


def test_start_writes_the_start_up_line_with_the_home_folder_as_tilde(logs):
    s = logs.start("6.0.0")
    assert s is not None and s.log.parent == _folder()
    assert s.log.name.startswith("papermini-") and s.log.name.endswith(
        f"-{os.getpid()}.log"
    )
    logging.getLogger("papermini.test").info(
        "opened %s", Path.home() / "minis" / "a.yaml"
    )
    logs.stop()
    text = s.log.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert "papermini" in first and "Qt 6.0.0" in first and logs.runs_as() in first
    assert "detailed log off" in first and f" {os.getpid()} INFO " in first
    assert f"opened ~{os.sep}minis{os.sep}a.yaml" in text
    assert str(Path.home()) not in text
    assert text.rstrip().endswith("papermini closed")


def test_redact_writes_the_home_folder_as_tilde_with_either_slash(logs):
    home = str(Path.home())
    assert logs.redact(f"{home}{os.sep}x") == f"~{os.sep}x"
    assert logs.redact(home.replace("\\", "/") + "/x") == "~/x"
    assert logs.redact(f"{home}-other") == f"{home}-other"  # (a different folder)


def test_each_session_gets_its_own_file(logs, monkeypatch):
    first = logs.start()
    logs.stop()
    monkeypatch.setattr(os, "getpid", lambda: 4242)
    second = logs.start()
    logs.stop()
    assert first.log != second.log and second.log.name.endswith("-4242.log")
    assert first.log.exists() and second.log.exists()


def test_a_clean_exit_deletes_the_crash_file(logs):
    s = logs.start()
    assert s.crash.exists() and s.crash.name.endswith(log_session.CRASH)
    logs.stop()
    assert not s.crash.exists()


def test_old_sessions_are_deleted_but_an_unoffered_crash_is_kept(logs):
    d = _folder()
    old = time.time() - (log_session.KEEP_DAYS + 1) * 86400

    def session(stem, *suffixes, crash=""):
        for suffix in suffixes:
            p = d / f"{stem}{suffix}"
            p.write_text(
                crash if suffix == log_session.CRASH else "log\n", encoding="utf-8"
            )
            os.utime(p, (old, old))

    session("papermini-20250101-100000-11", ".log", log_session.REPORTED)
    session(
        "papermini-20250101-100000-12",
        ".log",
        log_session.CRASH,
        crash="Fatal Python error",
    )
    session(
        "papermini-20250101-100000-13", ".log", log_session.CRASH
    )  # killed: empty crash file
    recent = d / "papermini-20261101-100000-14.log"
    recent.write_text("log\n", encoding="utf-8")
    s = logs.start()
    names = sorted(p.name for p in d.iterdir())
    logs.stop()
    assert "papermini-20250101-100000-11.log" not in names
    assert "papermini-20250101-100000-11" + log_session.REPORTED not in names
    assert "papermini-20250101-100000-12.log" in names  # (offered at this start)
    assert "papermini-20250101-100000-12" + log_session.CRASH in names
    assert "papermini-20250101-100000-13.log" not in names
    assert recent.name in names and s.log.name in names


def test_empty_crash_files_of_ended_sessions_are_tidied_away(logs):
    d = _folder()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        gone = d / f"papermini-20261112-100000-{_dead_pid()}{log_session.CRASH}"
        running = d / f"papermini-20261112-100000-{other.pid}{log_session.CRASH}"
        crashed = d / f"papermini-20261112-100000-{_dead_pid() + 1}{log_session.CRASH}"
        gone.touch()
        running.touch()
        crashed.write_text("Fatal Python error: Segmentation fault\n", encoding="utf-8")
        logs.start()
        logs.stop()
        assert not gone.exists() and running.exists() and crashed.exists()
    finally:
        other.kill()
        other.wait()


def _dead_pid() -> int:
    """The id of a process that has ended."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_a_crash_is_found_once_and_renamed_with_the_home_folder_as_tilde(logs):
    d = _folder()
    crash = d / f"papermini-20261111-100000-77{log_session.CRASH}"
    crash.write_text(
        f'Windows fatal exception\n  File "{Path.home() / "x.py"}", line 1\n',
        encoding="utf-8",
    )
    (d / "papermini-20261111-100000-77.log").write_text("log\n", encoding="utf-8")
    logs.start()
    found = logs.crashes()
    assert found == [(crash, d / "papermini-20261111-100000-77.log")]
    logs.mark_offered(crash)
    assert logs.crashes() == []
    done = logs.reported(crash)
    assert not crash.exists() and done.name.endswith(log_session.REPORTED)
    text = done.read_text(encoding="utf-8")
    assert "~" in text and str(Path.home()) not in text


def test_an_unwritable_log_folder_does_not_stop_the_app(logs, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setenv(log_session.LOG_ENV, str(blocker / "logs"))
    assert logs.start() is None and logs.session() is None
    logging.getLogger("papermini.test").error("still fine")  # (no handler, no error)
    assert logs.crashes() == []


def test_detailed_log_is_debug_for_this_session_only(logs):
    s = logs.start()
    logging.getLogger("papermini.test").debug("hidden")
    logs.set_detailed(True)
    assert logs.detailed()
    logging.getLogger("papermini.test").debug("shown")
    logs.set_detailed(False)
    logs.stop()
    text = s.log.read_text(encoding="utf-8")
    assert "hidden" not in text and "shown" in text and "detailed log on" in text
    assert not logs.detailed()
    assert "detailed log off" in logs.start().log.read_text(encoding="utf-8")


def test_issue_url_fills_in_the_bug_report_form(logs):
    from papermini import __version__

    q = _query(logs.issue_url())
    assert q == {
        "template": "bug_report.yml",
        "version": __version__,
        "os": logs.os_name(),
        "runs-as": logs.runs_as(),
    }
    assert logs.issue_url().startswith(NEW_ISSUE + "?")


def test_issue_url_adds_the_traceback_shortened_from_the_start(logs):
    tb = (
        f'File "{Path.home() / "a.py"}"\n'
        + "".join(f"  line {i}\n" for i in range(3000))
        + "RuntimeError: the end"
    )
    url = logs.issue_url(tb)
    assert len(url) <= log_session.MAX_URL
    details = _query(url)["traceback"]
    assert details.startswith("…") and details.endswith("RuntimeError: the end")
    assert (
        str(Path.home())
        not in _query(logs.issue_url("in " + str(Path.home())))["traceback"]
    )


def test_settings_for_the_log(logs):
    a, b = FigureSettings(), FigureSettings(height_mm=45, crop=[0.1, 0.25, 0.9, 1.0])
    assert (
        logs.settings_diff(a, b) == "height_mm 32 → 45, crop None → [0.1, 0.25, 0.9, 1]"
    )
    assert logs.settings_diff(a, a) == ""
    assert (
        logs.settings_text(b.to_dict(with_size=False))
        == "height_mm=45, crop=[0.1, 0.25, 0.9, 1]"
    )
    assert logs.settings_text({}) == "default settings"
    sheet = SheetSettings()
    assert "paper" in logs.settings_diff(sheet, SheetSettings(paper="letter"))


def test_link_text_drops_the_query(logs):
    assert (
        logs.link_text("https://x.org/a/b.webp?key=secret#top")
        == "https://x.org/a/b.webp"
    )


@pytest.mark.parametrize(
    "installed, expected", [(True, "installed"), (False, "unpacked")]
)
def test_runs_as_says_how_the_standalone_app_was_installed(
    monkeypatch, updates, installed, expected
):
    from papermini.support.log_session import LogSession

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates, "installed_with_setup", lambda: installed)
    assert LogSession(updates).runs_as() == expected


def test_os_name_names_each_system(logs, monkeypatch):
    import platform

    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    monkeypatch.setattr(platform, "release", lambda: "6.1")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "mac_ver", lambda: ("15.1", ("", "", ""), ""))
    assert logs.os_name() == "macOS 15.1 (arm64)"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        platform, "freedesktop_os_release", lambda: {"PRETTY_NAME": "Debian 13"}
    )
    assert logs.os_name() == "Debian 13 (6.1, arm64)"

    def no_release():
        raise OSError("no os-release")

    monkeypatch.setattr(platform, "freedesktop_os_release", no_release)
    assert logs.os_name() == "Linux (6.1, arm64)"
