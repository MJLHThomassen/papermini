"""Try the app's automatic update on this computer, in one go.

    python scripts/try_update.py              # build papermini, then update a copy of it
    python scripts/try_update.py --no-build   # the same with the last build of this script
    python scripts/try_update.py --source     # no build: papermini run from source updates
                                              # a pretend installed copy (quick)
    python scripts/try_update.py --installer  # Windows: install the build with its installer,
                                              # then update it with a newer installer

It builds in the temp folder (papermini-update-build), not in the project's dist/, so a
cloud sync of the project (such as OneDrive) cannot lock the build. It copies the build
(papermini, or papermini.app on macOS) to a test folder in the temp folder, which plays
the installed app, and puts OLD-COPY.txt in it. It makes a
fake, signed release 99.0.0 of the build (scripts/fake_update.py) and starts the copy,
pointed at that release. Update it in papermini (the menu's Check for updates, then
Update and Restart now, or close papermini), and the script then says whether the copy
was replaced. ``just try-update`` and ``just try-update-source`` run it.

With --installer (Windows, needs Inno Setup 6) it builds the installer of the build and
installs it silently into a test folder in the temp folder (this is a real install of
papermini for your user: it shows in Apps & features). The fake release 99.0.0 then holds
an installer, and the script checks that Apps & features shows 99.0.0 after the update.
Uninstall it afterwards in Apps & features. ``just try-update-installer`` runs it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_update import make_release  # noqa: E402

MAC = sys.platform == "darwin"
APP = "papermini.app" if MAC else "papermini"
GUI = ("Contents/MacOS/papermini" if MAC   # (started without a command: the desktop app)
       else "papermini.exe" if sys.platform == "win32" else "papermini")
MARKER = "OLD-COPY.txt"
WORK = Path(tempfile.gettempdir()) / "papermini-update-build"  # build/ and dist/ of the test
HOW = ("In papermini: open the menu, choose 'Check for updates...', click Update, then\n"
       "Restart now (or just close papermini).")


def fresh(folder: Path) -> Path:
    """An empty ``folder`` (a new one next to it if the old one is still in use)."""
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():
            folder = folder.with_name(f"{folder.name}-{int(time.time())}")
    folder.mkdir(parents=True)
    return folder


def wait_for(cond, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def run(app_cmd, env: dict) -> None:
    print(f"\n{HOW}\n")
    subprocess.run(app_cmd, env={**os.environ, **env}, cwd=ROOT)


def installed_version() -> str:
    """The version of papermini in Apps & features ("" when it is not installed)."""
    import winreg

    from papermini.update import SETUP_KEY

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETUP_KEY) as k:
            return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
    except OSError:
        return ""


def try_installer(build: Path) -> None:
    """Install ``build`` with its installer, then update it with the installer of a
    fake release 99.0.0 and check that Apps & features shows the new version."""
    from build_installer import build as build_setup

    from papermini import __version__

    setups = WORK / "installers"
    print("Building the installers (this version and the fake 99.0.0)...")
    first = build_setup(__version__, build, setups)
    newer = build_setup("99.0.0", build, setups)
    target = fresh(Path(tempfile.gettempdir()) / "papermini-installer-test") / "papermini"
    print(f"Installing papermini {__version__} into {target}...")
    subprocess.run([str(first), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    f"/DIR={target}"], check=True)
    print(f"Apps & features: papermini {installed_version()}")
    env, _, _ = make_release(version="99.0.0", setup=newer)
    run([str(target / "papermini.exe")], env)
    # the helper runs the new installer once papermini has quit (and restarts it, if asked)
    ok = wait_for(lambda: installed_version() == "99.0.0", 90)
    print("Updated: Apps & features shows papermini 99.0.0." if ok else
          f"Not updated: Apps & features shows papermini {installed_version()} "
          "(was the update installed?).")
    print("Uninstall it in Apps & features (papermini) when you are done; answer No when "
          "it asks to delete the cache, unless you want to download the models again.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-build", action="store_true",
                    help="use the last build of this script as it is")
    ap.add_argument("--source", action="store_true",
                    help="no build: papermini from source updates a pretend installed copy")
    ap.add_argument("--installer", action="store_true",
                    help="Windows: update a copy installed with the installer")
    args = ap.parse_args()
    if args.installer and sys.platform != "win32":
        sys.exit("--installer is for Windows only")

    if args.source:
        env, installed, _ = make_release()
        version = installed / "VERSION.txt"
        print(f"pretend installed copy: {installed} ({version.read_text().strip()})")
        run([sys.executable, "-m", "papermini", "gui"], env)
        ok = wait_for(lambda: version.exists() and version.read_text().startswith("99."), 20)
        print("Updated: the pretend copy is now 99.0.0." if ok else
              "Not updated: the pretend copy is unchanged (was the update installed?).")
        return

    build = WORK / "dist" / APP
    if not args.no_build:
        print(f"Building papermini in {WORK} (pyinstaller packaging/papermini.spec)...")
        subprocess.run([sys.executable, "-m", "PyInstaller", "packaging/papermini.spec",
                        "--noconfirm", "--distpath", str(WORK / "dist"),
                        "--workpath", str(WORK / "build")], cwd=ROOT, check=True)
    if not build.exists():
        sys.exit(f"{build} does not exist: run without --no-build to build it")
    if args.installer:
        try_installer(build)
        return
    copy = fresh(Path(tempfile.gettempdir()) / "papermini-update-test") / APP
    print(f"Copying the build to {copy} (it plays the installed papermini)...")
    shutil.copytree(build, copy, symlinks=True)
    (copy / MARKER).write_text("this copy is from before the update\n", encoding="utf-8")
    env, _, _ = make_release(build)
    run([str(copy / GUI)], env)
    # the helper replaces the copy once papermini has quit (and restarts it, if asked)
    ok = wait_for(lambda: (copy / GUI).exists() and not (copy / MARKER).exists(), 30)
    print("Updated: the copy was replaced by the update (OLD-COPY.txt is gone)." if ok else
          f"Not updated: {copy / MARKER} is still there (was the update installed?).")


if __name__ == "__main__":
    main()
