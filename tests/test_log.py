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

from papermini import log
from papermini.settings import FigureSettings, SheetSettings


def _folder() -> Path:
    return Path(os.environ[log.LOG_ENV])


def _query(url: str) -> dict:
    return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}


@pytest.mark.parametrize("platform, env, expected", [
    ("win32", {"LOCALAPPDATA": "C:/Local"}, "C:/Local/papermini/logs"),
    ("darwin", {}, "~/Library/Logs/papermini"),
    ("linux", {"XDG_STATE_HOME": "/state"}, "/state/papermini"),
    ("linux", {}, "~/.local/state/papermini"),
])
def test_log_dir_is_the_systems_log_folder(monkeypatch, platform, env, expected):
    monkeypatch.delenv(log.LOG_ENV)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "platform", platform)
    assert log.log_dir() == Path(expected.replace("~", str(Path.home())))


def test_log_dir_follows_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv(log.LOG_ENV, str(tmp_path / "here"))
    assert log.log_dir() == tmp_path / "here"


def test_start_writes_the_start_up_line_with_the_home_folder_as_tilde():
    s = log.start("6.0.0")
    assert s is not None and s.log.parent == _folder()
    assert s.log.name.startswith("papermini-") and s.log.name.endswith(f"-{os.getpid()}.log")
    logging.getLogger("papermini.test").info("opened %s", Path.home() / "minis" / "a.yaml")
    log.stop()
    text = s.log.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert "papermini" in first and "Qt 6.0.0" in first and log.runs_as() in first
    assert "detailed log off" in first and f" {os.getpid()} INFO " in first
    assert f"opened ~{os.sep}minis{os.sep}a.yaml" in text
    assert str(Path.home()) not in text
    assert text.rstrip().endswith("papermini closed")


def test_redact_writes_the_home_folder_as_tilde_with_either_slash():
    home = str(Path.home())
    assert log.redact(f"{home}{os.sep}x") == f"~{os.sep}x"
    assert log.redact(home.replace("\\", "/") + "/x") == "~/x"
    assert log.redact(f"{home}-other") == f"{home}-other"  # (a different folder)


def test_each_session_gets_its_own_file(monkeypatch):
    first = log.start()
    log.stop()
    monkeypatch.setattr(os, "getpid", lambda: 4242)
    second = log.start()
    log.stop()
    assert first.log != second.log and second.log.name.endswith("-4242.log")
    assert first.log.exists() and second.log.exists()


def test_a_clean_exit_deletes_the_crash_file():
    s = log.start()
    assert s.crash.exists() and s.crash.name.endswith(log.CRASH)
    log.stop()
    assert not s.crash.exists()


def test_old_sessions_are_deleted_but_an_unoffered_crash_is_kept():
    d = _folder()
    old = time.time() - (log.KEEP_DAYS + 1) * 86400

    def session(stem, *suffixes, crash=""):
        for suffix in suffixes:
            p = d / f"{stem}{suffix}"
            p.write_text(crash if suffix == log.CRASH else "log\n", encoding="utf-8")
            os.utime(p, (old, old))

    session("papermini-20250101-100000-11", ".log", log.REPORTED)
    session("papermini-20250101-100000-12", ".log", log.CRASH, crash="Fatal Python error")
    session("papermini-20250101-100000-13", ".log", log.CRASH)  # killed: empty crash file
    recent = d / "papermini-20261101-100000-14.log"
    recent.write_text("log\n", encoding="utf-8")
    s = log.start()
    names = sorted(p.name for p in d.iterdir())
    log.stop()
    assert "papermini-20250101-100000-11.log" not in names
    assert "papermini-20250101-100000-11" + log.REPORTED not in names
    assert "papermini-20250101-100000-12.log" in names  # (offered at this start)
    assert "papermini-20250101-100000-12" + log.CRASH in names
    assert "papermini-20250101-100000-13.log" not in names
    assert recent.name in names and s.log.name in names


def test_empty_crash_files_of_ended_sessions_are_tidied_away():
    d = _folder()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        gone = d / f"papermini-20261112-100000-{_dead_pid()}{log.CRASH}"
        running = d / f"papermini-20261112-100000-{other.pid}{log.CRASH}"
        crashed = d / f"papermini-20261112-100000-{_dead_pid() + 1}{log.CRASH}"
        gone.touch()
        running.touch()
        crashed.write_text("Fatal Python error: Segmentation fault\n", encoding="utf-8")
        log.start()
        log.stop()
        assert not gone.exists() and running.exists() and crashed.exists()
    finally:
        other.kill()
        other.wait()


def _dead_pid() -> int:
    """The id of a process that has ended."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_a_crash_is_found_once_and_renamed_with_the_home_folder_as_tilde():
    d = _folder()
    crash = d / f"papermini-20261111-100000-77{log.CRASH}"
    crash.write_text(f'Windows fatal exception\n  File "{Path.home() / "x.py"}", line 1\n',
                     encoding="utf-8")
    (d / "papermini-20261111-100000-77.log").write_text("log\n", encoding="utf-8")
    log.start()
    found = log.crashes()
    assert found == [(crash, d / "papermini-20261111-100000-77.log")]
    log.mark_offered(crash)
    assert log.crashes() == []
    done = log.reported(crash)
    assert not crash.exists() and done.name.endswith(log.REPORTED)
    text = done.read_text(encoding="utf-8")
    assert "~" in text and str(Path.home()) not in text


def test_an_unwritable_log_folder_does_not_stop_the_app(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setenv(log.LOG_ENV, str(blocker / "logs"))
    assert log.start() is None and log.session() is None
    logging.getLogger("papermini.test").error("still fine")  # (no handler, no error)
    assert log.crashes() == []


def test_detailed_log_is_debug_for_this_session_only():
    s = log.start()
    logging.getLogger("papermini.test").debug("hidden")
    log.set_detailed(True)
    assert log.detailed()
    logging.getLogger("papermini.test").debug("shown")
    log.set_detailed(False)
    log.stop()
    text = s.log.read_text(encoding="utf-8")
    assert "hidden" not in text and "shown" in text and "detailed log on" in text
    assert not log.detailed()
    assert "detailed log off" in log.start().log.read_text(encoding="utf-8")


def test_issue_url_fills_in_the_bug_report_form():
    from papermini import __version__

    q = _query(log.issue_url())
    assert q == {"template": "bug_report.yml", "version": __version__, "os": log.os_name(),
                 "runs-as": log.runs_as()}
    assert log.issue_url().startswith(log.ISSUE_URL + "?")


def test_issue_url_adds_the_traceback_shortened_from_the_start():
    tb = f'File "{Path.home() / "a.py"}"\n' + "".join(f"  line {i}\n" for i in range(3000)) \
        + "RuntimeError: the end"
    url = log.issue_url(tb)
    assert len(url) <= log.MAX_URL
    details = _query(url)["traceback"]
    assert details.startswith("…") and details.endswith("RuntimeError: the end")
    assert str(Path.home()) not in _query(log.issue_url("in " + str(Path.home())))["traceback"]


def test_settings_for_the_log():
    a, b = FigureSettings(), FigureSettings(height_mm=45, crop=[0.1, 0.25, 0.9, 1.0])
    assert log.settings_diff(a, b) == "height_mm 42 → 45, crop None → [0.1, 0.25, 0.9, 1]"
    assert log.settings_diff(a, a) == ""
    assert log.settings_text(b.to_dict()) == "height_mm=45, crop=[0.1, 0.25, 0.9, 1]"
    assert log.settings_text({}) == "default settings"
    sheet = SheetSettings()
    assert "paper" in log.settings_diff(sheet, SheetSettings(paper="letter"))


def test_link_text_drops_the_query():
    assert log.link_text("https://x.org/a/b.webp?key=secret#top") == "https://x.org/a/b.webp"
