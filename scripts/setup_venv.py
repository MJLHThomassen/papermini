"""Create a virtual environment for papermini and install it (with the GUI).

    python scripts/setup_venv.py               # -> ~/.venvs/papermini
    python scripts/setup_venv.py --dir .venv   # or anywhere else
    python scripts/setup_venv.py --no-gui      # CLI only

The default location is outside the project folder on purpose: a venv holds
thousands of files and should not be synced by OneDrive/Dropbox/iCloud.
Works on Windows, macOS and Linux.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(Path.home() / ".venvs" / "papermini"),
                    help="where to create the venv (default: ~/.venvs/papermini)")
    ap.add_argument("--no-gui", action="store_true", help="skip the Qt GUI dependencies")
    ap.add_argument("--dev", action="store_true", help="also install pytest")
    ap.add_argument("--build", action="store_true",
                    help="also install PyInstaller, to build the standalone binaries")
    a = ap.parse_args()

    if sys.version_info < (3, 10):
        sys.exit("papermini needs Python 3.10 or newer")
    target = Path(a.dir).expanduser().resolve()
    if not (target / "pyvenv.cfg").exists():
        print(f"Creating venv in {target}")
        venv.EnvBuilder(with_pip=True).create(target)
    py = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    extras = [x for x, on in (("gui", not a.no_gui), ("dev", a.dev), ("build", a.build)) if on]
    spec = f"{ROOT}[{','.join(extras)}]" if extras else str(ROOT)
    subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(py), "-m", "pip", "install", "-e", spec])

    bindir = py.parent
    print("\nDone. Run papermini with:")
    print(f"  {bindir / 'papermini'} --help")
    if not a.no_gui:
        print(f"  {bindir / 'papermini-gui'}")
    if os.name == "nt":
        print(f"\nOr activate the venv first:  {bindir / 'Activate.ps1'}   (PowerShell)")
    else:
        print(f"\nOr activate the venv first:  source {bindir / 'activate'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
