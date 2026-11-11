"""Build the Windows installer of papermini with Inno Setup (packaging/papermini.iss).

    python scripts/build_installer.py                      # dist/papermini -> dist/
    python scripts/build_installer.py --version 1.2.3 --dist dist/papermini --out out

Build the app first (pyinstaller packaging/papermini.spec --noconfirm). The installer
is named like the release downloads: papermini-<version>-windows-x64-setup.exe. The
version defaults to this papermini's. Needs Inno Setup 6: ISCC on PATH, or installed
in Program Files or (installed for one user) in %LocalAppData%\\Programs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def find_iscc() -> Optional[Path]:
    """Inno Setup's command-line compiler, or None when it is not installed."""
    on_path = shutil.which("iscc")
    if on_path:
        return Path(on_path)
    for base in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(base)
        if root:
            for sub in ("Inno Setup 6", "Programs/Inno Setup 6"):
                exe = Path(root) / sub / "ISCC.exe"
                if exe.is_file():
                    return exe
    return None


def build(version: str, dist: Path, out: Path) -> Path:
    """Build the installer of the app in ``dist``, as ``version``, into ``out``;
    returns the installer."""
    from papermini import update

    iscc = find_iscc()
    if iscc is None:
        sys.exit("Inno Setup 6 is not installed (https://jrsoftware.org/isdl.php, "
                 "or: winget install JRSoftware.InnoSetup)")
    if not (dist / "papermini.exe").is_file():
        sys.exit(f"{dist} has no papermini.exe: build it first with "
                 "pyinstaller packaging/papermini.spec --noconfirm")
    out.mkdir(parents=True, exist_ok=True)
    name = update.asset_name(version, "windows-x64", setup=True)
    done = subprocess.run([str(iscc), "/Qp", f"/DAppVersion={version}",
                           f"/DSourceDir={dist.resolve()}", f"/DOutputDir={out.resolve()}",
                           f"/DOutputBaseFilename={Path(name).stem}",
                           str(ROOT / "packaging" / "papermini.iss")])
    if done.returncode:
        sys.exit(f"Inno Setup could not build the installer (exit code {done.returncode})")
    return out / name


def main() -> None:
    from papermini import __version__

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=__version__,
                    help="the version to show in Apps & features (this papermini's)")
    ap.add_argument("--dist", type=Path, default=ROOT / "dist" / "papermini",
                    help="the PyInstaller build (dist/papermini)")
    ap.add_argument("--out", type=Path, default=ROOT / "dist",
                    help="where to write the installer (dist)")
    args = ap.parse_args()
    print(f"wrote {build(args.version, args.dist, args.out)}")


if __name__ == "__main__":
    main()
