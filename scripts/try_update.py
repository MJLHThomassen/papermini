"""Try the app's automatic update on this computer, in one go.

    python scripts/try_update.py              # build papermini, then update a copy of it
    python scripts/try_update.py --no-build   # the same with the last build of this script
    python scripts/try_update.py --source     # no build: papermini run from source updates
                                              # a pretend installed copy (quick)

It builds in the temp folder (papermini-update-build), not in the project's dist/, so a
cloud sync of the project (such as OneDrive) cannot lock the build. It copies the build
(papermini, or papermini.app on macOS) to a test folder in the temp folder, which plays
the installed app, and puts OLD-COPY.txt in it. It makes a
fake, signed release 99.0.0 of the build (scripts/fake_update.py) and starts the copy,
pointed at that release. Update it in papermini (the menu's Check for updates, then
Update and Restart now, or close papermini), and the script then says whether the copy
was replaced. ``just try-update`` and ``just try-update-source`` run it.
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
GUI = ("Contents/MacOS/papermini-gui" if MAC
       else "papermini-gui.exe" if sys.platform == "win32" else "papermini-gui")
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-build", action="store_true",
                    help="use the last build of this script as it is")
    ap.add_argument("--source", action="store_true",
                    help="no build: papermini from source updates a pretend installed copy")
    args = ap.parse_args()

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
