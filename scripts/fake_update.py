"""Make a fake, signed papermini release on this computer, to try the app's updates.

    python scripts/fake_update.py                          # a pretend app: test from source
    python scripts/fake_update.py --app dist/papermini     # a real build (Windows, Linux)
    python scripts/fake_update.py --app dist/papermini.app # a real build (macOS)

Writes to papermini-fake-update in the temp folder (outside the project, so a cloud
sync such as OneDrive cannot lock it):

(``just try-update`` and ``just try-update-source`` do all of this in one go, see
scripts/try_update.py.)

- ``release/``: the "new version" (default 99.0.0): its archive for this computer,
  SHA256SUMS.txt signed with a throwaway key, and release.json, a release description
  in GitHub's format that points at these files;
- without --app also ``installed/papermini``: a pretend installed papermini for a run
  from source to update.

Then it prints the environment variables to set before starting papermini (from
source, or the frozen app). papermini then finds the new version in About and Check for
updates, downloads and verifies it, and installs it over the (pretend) installed copy
when it closes. A real build in --app replaces the frozen app you start.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def pretend_app(where: Path, version: str, note: str) -> Path:
    """A folder that stands in for papermini (it only has to have the right name)."""
    app = where / ("papermini.app" if sys.platform == "darwin" else "papermini")
    if app.exists():
        shutil.rmtree(app)
    app.mkdir(parents=True)
    exe = "papermini.exe" if sys.platform == "win32" else "papermini"
    (app / exe).write_text(f"pretend papermini {version}\n", encoding="utf-8")
    (app / "VERSION.txt").write_text(f"{version} ({note})\n", encoding="utf-8")
    return app


def pack(app: Path, archive: Path) -> None:
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "w:gz") as t:
            t.add(app, arcname=app.name)
    elif sys.platform == "darwin" and (app / "Contents").exists():  # a real .app: keep links
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app),
                        str(archive)], check=True)
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(app.rglob("*")):
                z.write(f, f.relative_to(app.parent).as_posix())


def make_release(app: Optional[Path] = None, version: str = "99.0.0",
                 out: Optional[Path] = None) -> Tuple[Dict[str, str], Optional[Path], Path]:
    """Make the fake release (of the build ``app``, or of a pretend app with a pretend
    installed copy). Returns (environment variables to set, the pretend installed copy
    or None, the release folder)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from papermini import update

    tgt = update.target()
    if tgt is None:
        sys.exit("papermini has no downloads for this computer")
    out = out or Path(tempfile.gettempdir()) / "papermini-fake-update"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
        if out.exists():  # (something still has a file open in it: use a new folder)
            out = out.with_name(f"{out.name}-{int(time.time())}")
    rel = out / "release"
    rel.mkdir(parents=True)

    if app is not None:
        app = app.resolve()
        want = "dist/papermini.app" if sys.platform == "darwin" else "dist/papermini"
        if app.name != Path(want).name:
            sys.exit(f"--app must be the build for this computer: {want} (not {app})")
        if not app.exists():
            sys.exit(f"{app} does not exist: build it first with "
                     "pyinstaller packaging/papermini.spec --noconfirm")
        installed = None
    else:
        app = pretend_app(out / "new", version, "the update")
        installed = pretend_app(out / "installed", "0.0.1", "installed before the update")
    archive = rel / update.asset_name(version, tgt)
    pack(app, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = f"{digest}  {archive.name}\n".encode()
    (rel / update.CHECKSUMS).write_bytes(sums)

    key = Ed25519PrivateKey.generate()  # a throwaway key: only this test trusts it
    (rel / update.SIGNATURE).write_bytes(base64.b64encode(key.sign(sums)) + b"\n")
    public = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    feed = rel / "release.json"
    feed.write_text(json.dumps({
        "tag_name": f"v{version}",
        "html_url": "https://github.com/MJLHThomassen/papermini/releases",
        "assets": [{"name": f.name, "browser_download_url": f.resolve().as_uri()}
                   for f in (archive, rel / update.CHECKSUMS, rel / update.SIGNATURE)],
    }, indent=2), encoding="utf-8")
    env = {update.FEED_ENV: str(feed.resolve()), update.KEY_ENV: public}
    if installed is not None:
        env[update.INSTALL_ENV] = str(installed.resolve())
    return env, installed, rel


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default="99.0.0", help="the fake new version (99.0.0)")
    ap.add_argument("--app", type=Path, help="a real build to offer as the new version "
                                             "(dist/papermini or dist/papermini.app)")
    ap.add_argument("--out", type=Path, help="where to write it (a folder in the temp folder)")
    args = ap.parse_args()
    env, installed, rel = make_release(args.app, args.version, args.out)
    print(f"fake release {args.version} in {rel}")
    print("\nPowerShell:")
    for k, v in env.items():
        print(f'  $env:{k} = "{v}"')
    print("\nbash / zsh:")
    for k, v in env.items():
        print(f"  export {k}='{v}'")
    if installed is not None:
        print(f"\nThen start papermini from source in that shell. On closing it, "
              f"{installed} is replaced by the update (see its VERSION.txt).")
    else:
        exe = ("papermini.app/Contents/MacOS/papermini" if sys.platform == "darwin"
               else "papermini\\papermini.exe" if sys.platform == "win32"
               else "papermini/papermini")
        print(f"\nThen copy {args.app} somewhere outside dist (that copy plays the installed "
              f"app), and start its {exe} in that shell. Update it from the About window; "
              "on closing, the copy is replaced by the update.")


if __name__ == "__main__":
    main()
