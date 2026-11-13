"""The desktop app's log, its crash files, and the link for reporting a problem.

Each session of the desktop app writes its own ``papermini-<date>-<time>-<pid>.log`` in
the operating system's log folder (``$PAPERMINI_LOG_DIR`` instead, when set), so copies
running at the same time never share a file. Next to it, ``faulthandler`` writes native
crashes to the session's ``.crash.log``, which a clean exit deletes: a crash file with
something in it at a later start is a crash that is offered for a report once and then
renamed to ``.crash-reported.log``. (GitHub takes ``.log`` files as attachments.) An empty
crash file left by a session that was killed is deleted at the next start. Sessions older than ``KEEP_DAYS`` are deleted at
start, except one with a crash not yet offered.

The home folder is written as ``~`` in every line. Logging never stops the app: when the
folder cannot be written, the session runs without a log. The command line does not use
this module; its errors go to the terminal.
"""

from __future__ import annotations

import atexit
import faulthandler
import logging
import os
import platform
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import IO, List, Optional, Tuple

LOG_ENV = "PAPERMINI_LOG_DIR"
KEEP_DAYS = 30
ISSUE_URL = "https://github.com/MJLHThomassen/papermini/issues/new"
MAX_URL = 8000  # (GitHub refuses much longer links)
CRASH, REPORTED = ".crash.log", ".crash-reported.log"

logger = logging.getLogger("papermini")


def log_dir() -> Path:
    """The folder for the logs: ``$PAPERMINI_LOG_DIR``, or the operating system's usual
    log folder (outside the cache, so clearing the cache keeps the logs)."""
    env = os.environ.get(LOG_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "papermini" / "logs"
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "papermini"
    state = os.environ.get("XDG_STATE_HOME") or str(home / ".local" / "state")
    return Path(state) / "papermini"


def _home_pattern() -> Optional[re.Pattern]:
    home = str(Path.home()).rstrip("\\/")
    if len(home) < 2:  # (no real home folder to hide)
        return None
    # the home folder with either kind of slash, where its name ends (not C:\Users\bob-old)
    parts = [re.escape(p) for p in re.split(r"[\\/]+", home)]
    flags = re.IGNORECASE if sys.platform == "win32" else 0
    return re.compile(r"[\\/]+".join(parts) + r"(?![\w-])", flags)


def redact(text: str) -> str:
    """``text`` with the home folder written as ``~``."""
    pattern = _home_pattern()
    return pattern.sub("~", text) if pattern else text


def runs_as() -> str:
    """How this papermini runs: "installed" (by the Windows installer), "unpacked" (from
    the download) or "from source"."""
    if not getattr(sys, "frozen", False):
        return "from source"
    from . import update

    return "installed" if update.installed_with_setup() else "unpacked"


def os_name() -> str:
    """The operating system and its version, for logs and reports."""
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]} ({platform.machine()})"
    if sys.platform == "win32":
        return f"Windows {platform.release()} ({platform.version()}, {platform.machine()})"
    try:
        name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except OSError:
        name = "Linux"
    return f"{name} ({platform.release()}, {platform.machine()})"


class _Formatter(logging.Formatter):
    """Writes every line, tracebacks included, with the home folder as ``~``."""

    def format(self, record):
        return redact(super().format(record))


class _QuietFileHandler(logging.FileHandler):
    """A log file whose own failures (a full disk, a removed folder) are ignored: the
    app has no console to report them on, and logging must never break it."""

    def handleError(self, record):
        pass


@dataclass
class Session:
    """The running session's files."""

    log: Path
    crash: Path
    handler: logging.Handler
    crash_file: Optional[IO] = None


_session: Optional[Session] = None


def session() -> Optional[Session]:
    """The running session, or None when papermini runs without a log."""
    return _session


def _stem(path: Path) -> str:
    return path.name.split(".", 1)[0]


def _prune(folder: Path, now: float) -> None:
    """Delete the sessions whose newest file is older than ``KEEP_DAYS``, except a session
    with a crash not yet offered. A file another copy still has open is left."""
    sessions = {}
    for p in folder.glob("papermini-*"):
        if p.is_file():
            sessions.setdefault(_stem(p), []).append(p)
    for files in sessions.values():
        try:
            newest = max(p.stat().st_mtime for p in files)
            unoffered = any(p.name.endswith(CRASH) and p.stat().st_size for p in files)
        except OSError:
            continue
        if unoffered or now - newest < KEEP_DAYS * 86400:
            continue
        for p in files:
            try:
                p.unlink()
            except OSError:
                pass


def _running(pid: int) -> bool:
    """Whether a process with this id is running (True when that cannot be told)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # (access denied: it exists)
        try:
            code = ctypes.c_ulong()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # (it exists, but belongs to someone else)
    return True


def _tidy_crash_files(folder: Path) -> None:
    """Delete the empty crash files of sessions that ended without a clean exit and
    without a crash (killed, or the computer went off). A running copy's file is kept."""
    for p in folder.glob(f"papermini-*{CRASH}"):
        try:
            if p.stat().st_size or _running(int(_stem(p).rsplit("-", 1)[1])):
                continue
            p.unlink()
        except (OSError, ValueError, IndexError):
            continue


def crashes() -> List[Tuple[Path, Path]]:
    """The crashes of earlier sessions not yet offered for a report, newest first, as
    (crash file, that session's log)."""
    s = _session
    folder = s.log.parent if s else log_dir()
    found = []
    try:
        for p in folder.glob(f"papermini-*{CRASH}"):
            if s is not None and p == s.crash:
                continue
            try:
                if p.stat().st_size:
                    found.append((p.stat().st_mtime, p))
            except OSError:
                continue
    except OSError:
        return []
    return [(p, p.with_name(f"{_stem(p)}.log")) for _, p in sorted(found, reverse=True)]


def reported(crash: Path) -> Path:
    """The name a crash file gets once it was offered for a report."""
    return crash.with_name(f"{_stem(crash)}{REPORTED}")


def mark_offered(crash: Path) -> None:
    """Rename a crash that was offered for a report, so it is not offered again, with the
    home folder written as ``~`` (``faulthandler`` writes whole paths)."""
    try:
        text = crash.read_text(encoding="utf-8", errors="replace")
        reported(crash).write_text(redact(text), encoding="utf-8")
        crash.unlink()
    except OSError:
        try:
            crash.replace(reported(crash))
        except OSError:
            pass


def start(qt_version: str = "") -> Optional[Session]:
    """Start this session's log and crash file, after deleting old sessions. Returns the
    session, or None (and the app runs without a log) when the folder cannot be written."""
    global _session
    from . import __version__

    if _session is not None:
        return _session
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        _prune(folder, time.time())
        _tidy_crash_files(folder)
        stem =f"papermini-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        handler = _QuietFileHandler(folder / f"{stem}.log", encoding="utf-8")
    except Exception:  # noqa: BLE001 - logging must never stop the app
        return None
    handler.setFormatter(_Formatter("%(asctime)s %(process)d %(levelname)s %(name)s: %(message)s"))
    s = Session(folder / f"{stem}.log", folder / f"{stem}{CRASH}", handler)
    try:
        s.crash_file = open(s.crash, "w", encoding="utf-8")
        faulthandler.enable(s.crash_file, all_threads=True)
    except Exception:  # noqa: BLE001 - run without catching native crashes
        s.crash_file = None
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _session = s
    atexit.register(stop)
    qt = f", Qt {qt_version}" if qt_version else ""
    logger.info("papermini %s started on %s, Python %s%s, %s; detailed log off",
                __version__, os_name(), platform.python_version(), qt, runs_as())
    return s


def stop() -> None:
    """End the session cleanly: close the log, and delete the crash file (a clean exit
    is no crash)."""
    global _session
    s, _session = _session, None
    if s is None:
        return
    logger.info("papermini closed")
    logger.removeHandler(s.handler)
    s.handler.close()
    if s.crash_file is not None:
        try:
            faulthandler.disable()
            s.crash_file.close()
            s.crash.unlink()
        except OSError:
            pass


def set_detailed(on: bool) -> None:
    """Log more (DEBUG and up) or the usual (INFO and up), for this session only."""
    logger.setLevel(logging.DEBUG if on else logging.INFO)
    logger.info("detailed log %s", "on" if on else "off")


def detailed() -> bool:
    return logger.level == logging.DEBUG


def _value(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return redact(repr(v)) if isinstance(v, str) else str(v)


def settings_text(options: dict) -> str:
    """Settings (as a saved project stores them: only those not at their default) for a
    log line, such as ``height_mm=45, margin_mm=3``, or "default settings"."""
    return ", ".join(f"{k}={_value(v)}" for k, v in options.items()) or "default settings"


def settings_diff(old, new) -> str:
    """What changed between two settings dataclasses, such as ``height_mm 42 → 45``, or
    "" when nothing did."""
    from dataclasses import asdict

    a, b = asdict(old), asdict(new)
    return ", ".join(f"{k} {_value(a.get(k))} → {_value(v)}" for k, v in b.items()
                     if a.get(k) != v)


def link_text(url: str) -> str:
    """A link for the log without its query and fragment (they can hold keys)."""
    parts = urllib.parse.urlsplit(str(url).strip())
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def issue_url(details: str = "") -> str:
    """A link that opens a new bug report on GitHub with the version, the operating
    system and how papermini runs filled in, and ``details`` (an error's traceback, home
    folder as ``~``) when given, shortened from the start to keep the link short enough."""
    from . import __version__

    fields = {"template": "bug_report.yml", "version": __version__, "os": os_name(),
              "runs-as": runs_as()}
    url = f"{ISSUE_URL}?{urllib.parse.urlencode(fields, quote_via=urllib.parse.quote)}"
    details = redact(details).strip()
    while details:
        full = f"{url}&traceback={urllib.parse.quote(details)}"
        if len(full) <= MAX_URL:
            return full
        cut = details[len(details) - int(len(details) * 0.8):]  # keep the end: where it failed
        details = "…" + cut.split("\n", 1)[-1] if "\n" in cut else "…" + cut
    return url
