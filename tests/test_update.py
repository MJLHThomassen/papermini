"""Updates: versions, signed downloads, unpacking and the helper that installs them.

No network: the release feed and its files are local (file:// links), and the release
key is a throwaway one made per test.
"""

import base64
import hashlib
import json
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

from papermini import update


@pytest.fixture
def keys():
    """A throwaway release key pair: (private, public), base64."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


@pytest.fixture
def local_files(monkeypatch):
    """Let update's downloads open file:// links (the tests block the network)."""
    blocked = urllib.request.urlopen

    def urlopen(req, *a, **k):
        url = getattr(req, "full_url", req)
        if str(url).startswith("file:"):
            return urllib.request.build_opener().open(req, *a, **k)
        return blocked(req, *a, **k)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def sign(data: bytes, private: str) -> bytes:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from sign_release import sign as do_sign

    return do_sign(data, private)


def fake_release(tmp_path: Path, private: str, version: str = "9.9.9") -> Path:
    """A release of a pretend app for this computer; returns its release.json."""
    tgt = update.target()
    app_name = "papermini.app" if sys.platform == "darwin" else "papermini"
    src = tmp_path / "src" / app_name
    src.mkdir(parents=True)
    (src / "VERSION.txt").write_text(version)
    rel = tmp_path / "release"
    rel.mkdir()
    archive = rel / update.asset_name(version, tgt)
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "w:gz") as t:
            t.add(src, arcname=app_name)
    else:
        with zipfile.ZipFile(archive, "w") as z:
            z.write(src / "VERSION.txt", f"{app_name}/VERSION.txt")
    sums = f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n".encode()
    (rel / update.CHECKSUMS).write_bytes(sums)
    (rel / update.SIGNATURE).write_bytes(sign(sums, private))
    feed = rel / "release.json"
    feed.write_text(json.dumps({
        "tag_name": f"v{version}", "html_url": "https://example.invalid/release",
        "assets": [{"name": f.name, "browser_download_url": f.as_uri()}
                   for f in (archive, rel / update.CHECKSUMS, rel / update.SIGNATURE)]}))
    return feed


# --------------------------------------------------------------------------- versions

def test_versions():
    assert update.parse_version("v0.5.0") == (0, 5, 0)
    assert update.parse_version("1.2.3") == (1, 2, 3)
    for not_a_release in ("0.4.1.dev3+g1a2b3c4", "1.0.0-rc.1", "", "latest"):
        assert update.parse_version(not_a_release) is None
    assert update.is_newer("0.5.0", "0.4.9") and update.is_newer("1.0.0", "0.10.0")
    assert not update.is_newer("0.5.0", "0.5.0") and not update.is_newer("0.4.0", "0.5.0")
    # run from source: a development version counts as the release it leads to
    assert update.is_newer("0.5.0", "0.4.1.dev3+g1a2b3c4")
    assert not update.is_newer("0.4.1", "0.4.1.dev3+g1a2b3c4")
    assert not update.is_newer("1.0.0-rc.1", "0.5.0")  # (no pre-releases)


def test_downloads_for_each_computer(monkeypatch):
    for platform, machine, want in (("win32", "AMD64", "windows-x64"),
                                    ("darwin", "arm64", "macos-arm64"),
                                    ("darwin", "x86_64", "macos-x64"),
                                    ("linux", "x86_64", "linux-x64"),
                                    ("linux", "aarch64", None)):
        monkeypatch.setattr(update.sys, "platform", platform)
        monkeypatch.setattr(update.platform, "machine", lambda m=machine: m)
        assert update.target() == want
    assert update.asset_name("0.5.0", "windows-x64") == "papermini-0.5.0-windows-x64.zip"
    assert update.asset_name("0.5.0", "linux-x64") == "papermini-0.5.0-linux-x64.tar.gz"


def test_only_an_installed_copy_updates_itself(monkeypatch, tmp_path, keys):
    monkeypatch.delenv(update.INSTALL_ENV, raising=False)
    assert update.install_dir() is None  # (run from source)
    assert "source" in update.unsupported()
    monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "papermini"))
    (tmp_path / "papermini").mkdir()
    monkeypatch.setattr(update, "PUBLIC_KEY", "")
    monkeypatch.delenv(update.KEY_ENV, raising=False)
    assert "signature" in update.unsupported()  # no key to check updates with
    monkeypatch.setenv(update.KEY_ENV, keys[1])
    assert update.unsupported() is None


# --------------------------------------------------------------------------- verify

def test_verify_takes_only_signed_matching_downloads(tmp_path, keys):
    private, public = keys
    archive = tmp_path / "papermini-9.9.9-windows-x64.zip"
    archive.write_bytes(b"the app")
    sums = f"{hashlib.sha256(b'the app').hexdigest()}  {archive.name}\n".encode()
    sig = sign(sums, private)
    update.verify(sums, sig, archive, public)  # (no error)
    with pytest.raises(update.UpdateError, match="not signed"):
        update.verify(sums.replace(b"  ", b"  x"), sig, archive, public)  # changed list
    with pytest.raises(update.UpdateError, match="not signed"):
        update.verify(sums, sig, archive, base64.b64encode(b"\1" * 32).decode())  # other key
    archive.write_bytes(b"another app")
    with pytest.raises(update.UpdateError, match="checksum"):
        update.verify(sums, sig, archive, public)  # a tampered download


# --------------------------------------------------------------------------- download

def test_download_verifies_and_unpacks(monkeypatch, tmp_path, keys, local_files):
    private, public = keys
    monkeypatch.setenv(update.FEED_ENV, str(fake_release(tmp_path, private)))
    monkeypatch.setenv(update.KEY_ENV, public)
    rel = update.latest_release()
    assert rel.version == "9.9.9" and update.CHECKSUMS in rel.assets
    seen, steps = [], []
    app = update.download(rel, progress=lambda done, total: seen.append((done, total)),
                          step=steps.append)
    assert (app / "VERSION.txt").read_text() == "9.9.9"
    assert seen and seen[-1][0] == seen[-1][1] > 0  # progress up to the whole size
    assert steps == ["verifying", "unpacking"]
    assert update.pending() == ("9.9.9", app)  # ready to install, also after a restart
    # a release signed with another key is refused, and nothing is left ready
    monkeypatch.setenv(update.KEY_ENV, base64.b64encode(b"\1" * 32).decode())
    with pytest.raises(update.UpdateError, match="not signed"):
        update.download(rel)
    assert update.pending() is None


def test_unreachable_feed_is_one_clear_error(monkeypatch):
    monkeypatch.delenv(update.FEED_ENV, raising=False)
    with pytest.raises(update.UpdateError, match="Could not check for updates"):
        update.latest_release()  # (the tests block the network)


def test_old_downloads_are_forgotten(monkeypatch):
    root = update.updates_dir()
    for v in ("0.0.1", "99.0.0"):
        (root / v / "new" / "papermini").mkdir(parents=True)
        (root / v / update.READY).write_text(v)
    update.forget_old()  # (0.0.1 is older than this papermini)
    assert not (root / "0.0.1").exists() and (root / "99.0.0").exists()
    assert update.pending()[0] == "99.0.0"


# --------------------------------------------------------------------------- install

def test_helper_installs_once_papermini_has_quit(tmp_path):
    """The helper waits for papermini to quit, swaps in the new version (dropping files
    of the old one) and removes the download."""
    old = tmp_path / "install" / "papermini"
    old.mkdir(parents=True)
    (old / "app.txt").write_text("old")
    (old / "only-old.txt").write_text("old")
    new = tmp_path / "updates" / "9.9.9" / "new" / "papermini"
    new.mkdir(parents=True)
    (new / "app.txt").write_text("new")
    stand_in = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    _, cmd = update.install_script(new, old, stand_in.pid, restart=False)
    if sys.platform == "win32":
        helper = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        helper = subprocess.Popen(cmd)
    time.sleep(1)
    assert (old / "app.txt").read_text() == "old"  # papermini still runs: nothing yet
    stand_in.wait()
    helper.wait(timeout=60)
    assert (old / "app.txt").read_text() == "new"
    assert not (old / "only-old.txt").exists()
    assert not new.parent.exists()  # the download is gone


# --------------------------------------------------------------------------- scripts

def test_sign_release_checks_the_apps_key(monkeypatch, tmp_path, keys):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import sign_release

    private, public = keys
    data = b"sums"
    assert sign_release.check(data, sign_release.sign(data, private), public)
    other = base64.b64encode(b"\2" * 32).decode()
    assert not sign_release.check(data, sign_release.sign(data, other), public)
    # the script refuses a secret that does not belong to the app's public key
    update_py = tmp_path / "update.py"
    update_py.write_text(f'PUBLIC_KEY = "{public}"\n')
    monkeypatch.setattr(sign_release, "UPDATE_PY", update_py)
    f = tmp_path / "SHA256SUMS.txt"
    f.write_bytes(data)
    monkeypatch.setattr(sys, "argv", ["sign_release.py", str(f)])
    monkeypatch.setenv("RELEASE_SIGNING_KEY", other)
    with pytest.raises(SystemExit, match="does not belong"):
        sign_release.main()
    monkeypatch.setenv("RELEASE_SIGNING_KEY", private)
    sign_release.main()
    assert sign_release.check(data, f.with_name(f.name + ".sig").read_bytes().strip(), public)


def test_release_key_writes_the_public_key(monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import release_key

    update_py = tmp_path / "update.py"
    update_py.write_text('x = 1\nPUBLIC_KEY = ""\n')
    monkeypatch.setattr(release_key, "UPDATE_PY", update_py)
    monkeypatch.setattr(release_key, "ROOT", tmp_path)
    key_file = tmp_path / "key"
    monkeypatch.setattr(sys, "argv", ["release_key.py", str(key_file)])
    release_key.main()
    public = update_py.read_text().split('PUBLIC_KEY = "')[1].split('"')[0]
    assert len(base64.b64decode(public)) == 32 and len(base64.b64decode(key_file.read_text())) == 32
    with pytest.raises(SystemExit, match="exists"):  # never replaces a key by accident
        release_key.main()


def test_helper_restarts_papermini_itself(tmp_path):
    """After Restart now, the helper starts the one papermini program (which opens the
    desktop app without a command)."""
    script, _ = update.install_script(tmp_path / "new" / "papermini",
                                      tmp_path / "old" / "papermini", 1, restart=True)
    text = script.read_text()
    assert "papermini-gui" not in text
    if sys.platform == "win32":
        assert 'start "" "' in text and text.count("papermini.exe") == 1
    elif sys.platform == "darwin":
        assert "open " in text
    else:
        assert '/papermini" &' in text
