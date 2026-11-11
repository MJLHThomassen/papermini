"""Updates of the standalone app: check GitHub for a newer release, download and verify
it in the background, and install it when the app closes.

Every release has a ``SHA256SUMS.txt`` with the checksum of each download, signed by the
release workflow with a private Ed25519 key (``SHA256SUMS.txt.sig``). The app has the
public key built in (``PUBLIC_KEY``) and installs a download only when that signature and
its checksum match. Only the standalone app updates itself; run from source, papermini
just reports a newer version. A papermini installed with the Windows installer updates
by running the new version's installer silently; the other copies replace their folder
(or papermini.app) with the new archive's.

For trying updates locally (see scripts/fake_update.py), three environment variables
stand in for the real thing: PAPERMINI_UPDATE_FEED (a release description in GitHub's
format, as a file or a link), PAPERMINI_UPDATE_KEY (the public key to trust) and
PAPERMINI_UPDATE_INSTALL (a pretend installed papermini, so a run from source updates it).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
import urllib.request

REPO = "MJLHThomassen/papermini"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECKSUMS = "SHA256SUMS.txt"
SIGNATURE = CHECKSUMS + ".sig"
# the release workflow's public signing key, base64 (scripts/release_key.py sets it)
PUBLIC_KEY = "1tcgNayNKgRQi2eWKy0RMuAC4vx9R/ovBGmproIi0AQ="
READY = "READY"  # marks a downloaded, verified and unpacked update
FEED_ENV, KEY_ENV, INSTALL_ENV = ("PAPERMINI_UPDATE_FEED", "PAPERMINI_UPDATE_KEY",
                                  "PAPERMINI_UPDATE_INSTALL")


def _feed() -> str:
    """Where to find the latest release: GitHub, or a test feed (a file or a link)."""
    feed = os.environ.get(FEED_ENV, "").strip()
    if not feed:
        return LATEST
    return feed if "://" in feed else Path(feed).resolve().as_uri()


def _public_key() -> str:
    return os.environ.get(KEY_ENV, "").strip() or PUBLIC_KEY


class UpdateError(Exception):
    """An update could not be checked, downloaded or verified (the message says why)."""


@dataclass
class Release:
    version: str                     # the release's version, without the "v" of its tag
    url: str                         # the release page
    assets: Dict[str, str] = field(default_factory=dict)  # file name -> download link


# --------------------------------------------------------------------------- versions

def parse_version(v: str) -> Optional[Tuple[int, int, int]]:
    """Parse a release version (with or without "v") into (major, minor, patch); None
    for anything else, such as a development version or a pre-release."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest: str, current: str) -> bool:
    """Whether release ``latest`` is newer than ``current``. For a development version
    (papermini run from source), only its leading major.minor.patch counts."""
    a = parse_version(latest)
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", current.strip())
    return a is not None and m is not None and a > tuple(int(x) for x in m.groups())


# --------------------------------------------------------------------------- this app

def target() -> Optional[str]:
    """The download that fits this computer: windows-x64, macos-arm64, macos-x64 or
    linux-x64 (None for anything else)."""
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    x64 = machine in ("x86_64", "amd64")
    if sys.platform == "win32" and x64:
        return "windows-x64"
    if sys.platform == "darwin" and (arm or x64):
        return "macos-arm64" if arm else "macos-x64"
    if sys.platform.startswith("linux") and x64:
        return "linux-x64"
    return None


def asset_name(version: str, tgt: str, setup: bool = False) -> str:
    """The release download for ``tgt``: its archive, or with ``setup`` its installer
    (Windows)."""
    if setup:
        return f"papermini-{version}-{tgt}-setup.exe"
    return f"papermini-{version}-{tgt}." + ("tar.gz" if tgt.startswith("linux") else "zip")


# the installer's entry in Apps & features (per user; the AppId in packaging/papermini.iss)
SETUP_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
             r"\{8ABD2E9A-F789-4350-88F8-2565C60699F0}_is1")


def setup_install_dir() -> Optional[Path]:
    """The folder the Windows installer installed papermini in, for this user, as its
    entry in Apps & features says (None when it did not install papermini)."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETUP_KEY) as k:
            return Path(winreg.QueryValueEx(k, "Inno Setup: App Path")[0]).resolve()
    except OSError:
        return None


def installed_with_setup() -> bool:
    """Whether this papermini is the copy the Windows installer installed: the installer's
    entry in Apps & features names this folder. That copy updates by running the
    installer of the new version, which installs into the folder of that entry and keeps
    the shortcuts and the entry up to date (it also puts back an uninstaller that was
    deleted). Any other copy, such as one unpacked from the archive or a copy of the
    installed folder, replaces its own folder."""
    where = install_dir()
    installed = setup_install_dir()
    return (where is not None and installed is not None
            and os.path.normcase(installed) == os.path.normcase(where))


def install_dir() -> Optional[Path]:
    """What an update replaces: the app's folder (Windows, Linux) or papermini.app
    (macOS). None when papermini runs from source (unless a test sets a pretend one)."""
    pretend = os.environ.get(INSTALL_ENV, "").strip()
    if pretend:
        return Path(pretend).resolve()
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        app = exe.parents[2]  # (the program is in papermini.app/Contents/MacOS)
        return app if app.suffix == ".app" else None
    return exe.parent


def unsupported() -> Optional[str]:
    """Why this copy of papermini cannot update itself, or None when it can."""
    if install_dir() is None:
        return "papermini runs from source; update it with git or pip."
    if target() is None:
        return "There is no download of papermini for this computer."
    if not _public_key():
        return "This version of papermini cannot check the signature of an update."
    where = install_dir()
    if not os.access(where.parent, os.W_OK) or not os.access(where, os.W_OK):
        return f"papermini may not write to {where.parent}, so it cannot replace itself."
    return None


# --------------------------------------------------------------------------- GitHub

def _open(url: str, timeout: float):
    from . import __version__

    req = urllib.request.Request(url, headers={"User-Agent": f"papermini/{__version__}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)  # (looked up now: tests replace it)


def latest_release(timeout: float = 10.0) -> Release:
    """The newest published release (pre-releases do not count)."""
    try:
        with _open(_feed(), timeout) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001 - offline, rate limited, ...: one clear message
        raise UpdateError(f"Could not check for updates: {e}") from None
    version = str(data.get("tag_name", "")).lstrip("v")
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    return Release(version, str(data.get("html_url", "")), assets)


def _fetch(url: str, dest: Path, timeout: float,
           progress: Optional[Callable[[int, int], None]] = None) -> Path:
    tmp = dest.with_name(dest.name + ".part")
    try:
        with _open(url, timeout) as r, open(tmp, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Could not download {dest.name}: {e}") from None
    tmp.replace(dest)
    return dest


# --------------------------------------------------------------------------- verify

def verify(checksums: bytes, signature: bytes, archive: Path,
           public_key: str = "") -> None:
    """Raise UpdateError unless ``checksums`` carries a valid signature by the release
    key and lists ``archive`` with its SHA-256."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = public_key or _public_key()
    if not key:
        raise UpdateError("No release key to check the update with.")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(
            base64.b64decode(signature.strip()), checksums)
    except (InvalidSignature, ValueError):
        raise UpdateError("The update is not signed by papermini's release key; "
                          "it was not installed.") from None
    sums = {}
    for line in checksums.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if sums.get(archive.name) != h.hexdigest():
        raise UpdateError(f"{archive.name} does not match its checksum; it was not "
                          "installed.")


# --------------------------------------------------------------------------- download

def updates_dir() -> Path:
    from .segment import cache_dir

    return cache_dir() / "updates"


def _unpack(archive: Path, dest: Path) -> Path:
    """Unpack a release archive into ``dest``; returns the app in it."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    name = archive.name
    if name.endswith(".tar.gz"):
        with tarfile.open(archive) as t:  # keeps permissions and links (Qt libraries)
            if hasattr(tarfile, "data_filter"):  # (refuses paths outside dest)
                t.extractall(dest, filter="data")
            else:
                t.extractall(dest)
    elif sys.platform == "darwin":  # ditto keeps the app's links, permissions and signature
        subprocess.run(["ditto", "-x", "-k", str(archive), str(dest)], check=True)
    else:
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    for app in ("papermini.app", "papermini"):
        if (dest / app).exists():
            return dest / app
    raise UpdateError(f"{name} does not hold papermini.")


def download(release: Release, progress: Optional[Callable[[int, int], None]] = None,
             timeout: float = 30.0, step: Optional[Callable[[str], None]] = None) -> Path:
    """Download this computer's archive of ``release``, verify it and unpack it, ready to
    install; returns the unpacked app. A papermini installed with the Windows installer
    downloads the new installer instead, and gets that back. ``progress(done, total)``
    hears the bytes of the download (total 0 when unknown), ``step(name)`` the steps
    after it: "verifying" and "unpacking" (not for an installer)."""
    step = step or (lambda _name: None)
    tgt = target()
    setup = installed_with_setup()
    name = asset_name(release.version, tgt or "", setup)
    for need in (name, CHECKSUMS, SIGNATURE):
        if need not in release.assets:
            raise UpdateError(f"The release of papermini {release.version} has no {need}.")
    where = updates_dir() / release.version
    if where.exists():
        shutil.rmtree(where, ignore_errors=True)
    where.mkdir(parents=True, exist_ok=True)
    archive = _fetch(release.assets[name], where / name, timeout, progress)
    sums = _fetch(release.assets[CHECKSUMS], where / CHECKSUMS, timeout).read_bytes()
    sig = _fetch(release.assets[SIGNATURE], where / SIGNATURE, timeout).read_bytes()
    step("verifying")
    verify(sums, sig, archive)
    if setup:
        (where / "new").mkdir()
        app = archive.replace(where / "new" / name)
    else:
        step("unpacking")
        app = _unpack(archive, where / "new")
        archive.unlink(missing_ok=True)
    (where / READY).write_text(release.version, encoding="utf-8")
    return app


def _new_app(new: Path) -> Optional[Path]:
    """The update in a download's ``new`` folder: the unpacked app, or the installer."""
    for app in ("papermini.app", "papermini"):
        if (new / app).exists():
            return new / app
    return next(iter(sorted(new.glob("papermini-*-setup.exe"))), None) if new.is_dir() else None


def pending() -> Optional[Tuple[str, Path]]:
    """(version, unpacked app or installer) of a downloaded update that is newer than
    this one."""
    from . import __version__

    root = updates_dir()
    if not root.is_dir():
        return None
    best = None
    for d in root.iterdir():
        if (d / READY).is_file() and is_newer(d.name, __version__):
            app = _new_app(d / "new")
            if app is not None and (
                    best is None or parse_version(d.name) > parse_version(best[0])):
                best = (d.name, app)
    return best


def forget_old() -> None:
    """Remove downloads that are not newer than this version (installed, or skipped)."""
    from . import __version__

    root = updates_dir()
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir() and not is_newer(d.name, __version__):
                shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- install

def install_script(new_app: Path, old_app: Path, pid: int, restart: bool) -> Tuple[Path, list]:
    """Write the helper that replaces ``old_app`` with ``new_app`` once the process
    ``pid`` (papermini) has quit; returns (script, command to start it). When
    ``new_app`` is the Windows installer, the helper runs it silently instead (it
    installs over the previous install)."""
    folder = Path(tempfile.mkdtemp(prefix="papermini-update-"))
    if sys.platform == "win32":
        exe = old_app / "papermini.exe"
        sys32 = "%SystemRoot%\\System32"  # Windows' own tools, whatever else is on PATH
        if new_app.suffix.lower() == ".exe":  # the installer
            install = [f'"{new_app}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
                       f'if %ERRORLEVEL% EQU 0 rmdir /s /q "{new_app.parent}"']
        else:
            install = [f'{sys32}\\Robocopy.exe "{new_app}" "{old_app}" /MIR /R:5 /W:1 '
                       "/NFL /NDL /NJH /NJS /NP >NUL",
                       f'if %ERRORLEVEL% LSS 8 rmdir /s /q "{new_app.parent}"']
        lines = [
            "@echo off",
            ":wait",  # until papermini has quit (its files are locked while it runs)
            f'{sys32}\\tasklist.exe /FI "PID eq {pid}" /NH 2>NUL | '
            f'{sys32}\\find.exe "{pid}" >NUL && '
            f"({sys32}\\PING.EXE -n 2 127.0.0.1 >NUL & goto wait)",
            *install,
        ]
        if restart:
            lines.append(f'start "" "{exe}"')
        lines.append('(goto) 2>NUL & del "%~f0"')  # the script removes itself
        script = folder / "update.cmd"
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")  # (CRLF on Windows)
        return script, ["cmd", "/c", str(script)]
    old, new = str(old_app), str(new_app)
    lines = [
        "#!/bin/sh",
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.3; done",  # until papermini has quit
        f'rm -rf "{old}.old"',
        f'if mv "{old}" "{old}.old"; then',
        f'  if mv "{new}" "{old}"; then rm -rf "{old}.old"; else mv "{old}.old" "{old}"; fi',
        "fi",
        f'rm -rf "{new_app.parent}"',
    ]
    if restart:
        lines.append(f'open "{old}"' if sys.platform == "darwin" else f'"{old}/papermini" &')
    lines.append('rm -f "$0"')
    script = folder / "update.sh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script, ["/bin/sh", str(script)]


def install_on_exit(new_app: Path, restart: bool = False) -> None:
    """Start the helper that installs ``new_app`` over this papermini when it quits
    (and starts the new version, with ``restart``)."""
    old = install_dir()
    if old is None:
        raise UpdateError("papermini runs from source; it does not install updates.")
    _, cmd = install_script(new_app, old, os.getpid(), restart)
    quiet = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True)
    if sys.platform == "win32":  # a hidden console: a batch script needs one to run
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, **quiet)
    else:
        subprocess.Popen(cmd, start_new_session=True, **quiet)
