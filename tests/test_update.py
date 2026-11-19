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
import urllib.request
import zipfile
from pathlib import Path

import pytest

from papermini.support import update


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


def fake_release(tmp_path: Path, private: str, sign, version: str = "9.9.9") -> Path:
    """A release of a pretend app for this computer, signed with ``sign``; returns its
    release.json."""
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
    sums = (
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n".encode()
    )
    (rel / update.CHECKSUMS).write_bytes(sums)
    (rel / update.SIGNATURE).write_bytes(sign(sums, private))
    feed = rel / "release.json"
    feed.write_text(
        json.dumps(
            {
                "tag_name": f"v{version}",
                "html_url": "https://example.invalid/release",
                "assets": [
                    {"name": f.name, "browser_download_url": f.as_uri()}
                    for f in (archive, rel / update.CHECKSUMS, rel / update.SIGNATURE)
                ],
            }
        )
    )
    return feed


# region versions


def test_versions():
    assert update.parse_version("v0.5.0") == (0, 5, 0)
    assert update.parse_version("1.2.3") == (1, 2, 3)
    for not_a_release in ("0.4.1.dev3+g1a2b3c4", "1.0.0-rc.1", "", "latest"):
        assert update.parse_version(not_a_release) is None
    assert update.is_newer("0.5.0", "0.4.9") and update.is_newer("1.0.0", "0.10.0")
    assert not update.is_newer("0.5.0", "0.5.0") and not update.is_newer(
        "0.4.0", "0.5.0"
    )
    # run from source: a development version counts as the release it leads to
    assert update.is_newer("0.5.0", "0.4.1.dev3+g1a2b3c4")
    assert not update.is_newer("0.4.1", "0.4.1.dev3+g1a2b3c4")
    assert not update.is_newer("1.0.0-rc.1", "0.5.0")  # (no pre-releases)


def test_downloads_for_each_computer(monkeypatch):
    for platform, machine, want in (
        ("win32", "AMD64", "windows-x64"),
        ("darwin", "arm64", "macos-arm64"),
        ("darwin", "x86_64", "macos-x64"),
        ("linux", "x86_64", "linux-x64"),
        ("linux", "aarch64", None),
    ):
        monkeypatch.setattr(update.sys, "platform", platform)
        monkeypatch.setattr(update.platform, "machine", lambda m=machine: m)
        assert update.target() == want
    assert (
        update.asset_name("0.5.0", "windows-x64") == "papermini-0.5.0-windows-x64.zip"
    )
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


def test_a_copy_that_cannot_update_says_why(monkeypatch, tmp_path, keys):
    monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "papermini"))
    (tmp_path / "papermini").mkdir()
    monkeypatch.setenv(update.KEY_ENV, keys[1])
    monkeypatch.setattr(update, "target", lambda: None)
    reason = update.unsupported()
    assert reason and "no download of papermini for this computer" in reason
    monkeypatch.setattr(update, "target", lambda: "windows-x64")
    monkeypatch.setattr(update.os, "access", lambda path, mode: False)
    reason = update.unsupported()
    assert reason and "may not write to" in reason


def test_the_folder_a_frozen_app_replaces(monkeypatch, tmp_path):
    monkeypatch.delenv(update.INSTALL_ENV, raising=False)
    monkeypatch.setattr(update.sys, "frozen", True, raising=False)
    exe = tmp_path / "papermini" / "papermini.exe"
    monkeypatch.setattr(update.sys, "executable", str(exe))
    monkeypatch.setattr(update.sys, "platform", "win32")
    assert update.install_dir() == exe.parent.resolve()
    monkeypatch.setattr(update.sys, "platform", "darwin")
    app = tmp_path / "papermini.app"
    monkeypatch.setattr(
        update.sys, "executable", str(app / "Contents" / "MacOS" / "papermini")
    )
    assert update.install_dir() == app.resolve()
    monkeypatch.setattr(update.sys, "executable", str(exe))  # not in an app bundle
    assert update.install_dir() is None


# endregion


# region verify


def test_verify_takes_only_signed_matching_downloads(tmp_path, keys, sign):
    private, public = keys
    archive = tmp_path / "papermini-9.9.9-windows-x64.zip"
    archive.write_bytes(b"the app")
    sums = f"{hashlib.sha256(b'the app').hexdigest()}  {archive.name}\n".encode()
    sig = sign(sums, private)
    update.verify(sums, sig, archive, public)  # (no error)
    with pytest.raises(update.UpdateError, match="not signed"):
        update.verify(sums.replace(b"  ", b"  x"), sig, archive, public)  # changed list
    with pytest.raises(update.UpdateError, match="not signed"):
        update.verify(
            sums, sig, archive, base64.b64encode(b"\1" * 32).decode()
        )  # other key
    archive.write_bytes(b"another app")
    with pytest.raises(update.UpdateError, match="checksum"):
        update.verify(sums, sig, archive, public)  # a tampered download


def test_verify_refuses_without_a_release_key(monkeypatch, tmp_path, keys, sign):
    private, _ = keys
    archive = tmp_path / "papermini-9.9.9-windows-x64.zip"
    archive.write_bytes(b"the app")
    sums = f"{hashlib.sha256(b'the app').hexdigest()}  {archive.name}\n".encode()
    monkeypatch.setattr(update, "PUBLIC_KEY", "")
    monkeypatch.delenv(update.KEY_ENV, raising=False)
    with pytest.raises(update.UpdateError, match="No release key"):
        update.verify(sums, sign(sums, private), archive)


# endregion


# region download


def test_download_verifies_and_unpacks(monkeypatch, tmp_path, keys, local_files, sign):
    private, public = keys
    monkeypatch.setenv(update.FEED_ENV, str(fake_release(tmp_path, private, sign)))
    monkeypatch.setenv(update.KEY_ENV, public)
    rel = update.latest_release()
    assert rel.version == "9.9.9" and update.CHECKSUMS in rel.assets
    seen, steps = [], []
    app = update.download(
        rel, progress=lambda done, total: seen.append((done, total)), step=steps.append
    )
    assert (app / "VERSION.txt").read_text() == "9.9.9"
    assert seen and seen[-1][0] == seen[-1][1] > 0  # progress up to the whole size
    assert steps == ["verifying", "unpacking"]
    assert update.pending() == ("9.9.9", app)  # ready to install, also after a restart
    # a release signed with another key is refused, and nothing is left ready
    monkeypatch.setenv(update.KEY_ENV, base64.b64encode(b"\1" * 32).decode())
    with pytest.raises(update.UpdateError, match="not signed"):
        update.download(rel)
    assert update.pending() is None


@pytest.mark.parametrize("missing", ["archive", update.CHECKSUMS, update.SIGNATURE])
def test_a_release_missing_a_file_is_refused(
    monkeypatch, tmp_path, keys, local_files, missing, sign
):
    private, public = keys
    monkeypatch.setenv(update.FEED_ENV, str(fake_release(tmp_path, private, sign)))
    monkeypatch.setenv(update.KEY_ENV, public)
    rel = update.latest_release()
    tgt = update.target()
    assert tgt  # (fake_release makes the archive for this computer)
    name = update.asset_name(rel.version, tgt) if missing == "archive" else missing
    del rel.assets[name]
    with pytest.raises(update.UpdateError, match=f"has no {name}"):
        update.download(rel)
    assert not (update.updates_dir() / rel.version).exists()  # nothing downloaded
    assert update.pending() is None


@pytest.mark.parametrize("suffix", [".zip", ".tar.gz"])
def test_an_archive_without_papermini_is_refused(tmp_path, suffix):
    other = tmp_path / "src" / "something-else"
    other.mkdir(parents=True)
    (other / "README.txt").write_text("not papermini")
    archive = tmp_path / f"papermini-9.9.9-test{suffix}"
    if suffix == ".tar.gz":
        with tarfile.open(archive, "w:gz") as t:
            t.add(other, arcname=other.name)
    else:
        with zipfile.ZipFile(archive, "w") as z:
            z.write(other / "README.txt", f"{other.name}/README.txt")
    with pytest.raises(update.UpdateError, match="does not hold papermini"):
        update._unpack(archive, tmp_path / "new")


def test_a_failed_download_leaves_no_part_file(tmp_path, local_files):
    source = tmp_path / "source.zip"
    source.write_bytes(b"x" * 100_000)
    dest = tmp_path / "downloads" / "papermini.zip"
    dest.parent.mkdir()

    def fail(done, total):
        raise OSError("the connection dropped")

    with pytest.raises(update.UpdateError, match="Could not download papermini.zip"):
        update._fetch(source.as_uri(), dest, 10.0, progress=fail)
    assert list(dest.parent.iterdir()) == []  # neither the file nor its .part


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


# endregion


# region install


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
    stand_in = subprocess.Popen(  # (runs until its input closes)
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    _, cmd = update.install_script(new, old, stand_in.pid, restart=False)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    helper = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, text=True, creationflags=flags
    )
    reports = helper.stdout
    assert reports is not None
    for _ in range(2):  # it finds papermini running, waits, and checks again
        assert reports.readline().strip() == "waiting"
    assert (old / "app.txt").read_text() == "old"  # papermini still runs: nothing yet
    stand_in.communicate()  # papermini quits
    helper.communicate(timeout=60)
    assert (old / "app.txt").read_text() == "new"
    assert not (old / "only-old.txt").exists()
    assert not new.parent.exists()  # the download is gone


# endregion


# region restart


def test_helper_restarts_papermini_itself(tmp_path):
    """After Restart now, the helper starts the one papermini program (which opens the
    desktop app without a command)."""
    script, _ = update.install_script(
        tmp_path / "new" / "papermini", tmp_path / "old" / "papermini", 1, restart=True
    )
    text = script.read_text()
    assert "papermini-gui" not in text
    if sys.platform == "win32":
        assert 'start "" "' in text and text.count("papermini.exe") == 1
    elif sys.platform == "darwin":
        assert "open " in text
    else:
        assert '/papermini" &' in text


# endregion


# region installer


def test_only_the_installed_folder_updates_with_the_installer(monkeypatch, tmp_path):
    """The copy that the installer's Apps & features entry names updates with the
    installer; a copy elsewhere (unpacked, or a copy of the installed folder) does not."""
    installed, other = (
        tmp_path / "Programs" / "papermini",
        tmp_path / "copy" / "papermini",
    )
    installed.mkdir(parents=True)
    other.mkdir(parents=True)
    monkeypatch.setattr(update, "setup_install_dir", lambda: installed.resolve())
    monkeypatch.setenv(update.INSTALL_ENV, str(installed))
    assert update.installed_with_setup()  # (also without its uninstaller)
    monkeypatch.setenv(update.INSTALL_ENV, str(other))
    assert not update.installed_with_setup()
    monkeypatch.setattr(update, "setup_install_dir", lambda: None)  # not installed
    monkeypatch.setenv(update.INSTALL_ENV, str(installed))
    assert not update.installed_with_setup()
    monkeypatch.delenv(update.INSTALL_ENV)
    assert not update.installed_with_setup()  # (run from source)


def test_installer_entry_is_only_on_windows(monkeypatch):
    monkeypatch.setattr(update.sys, "platform", "darwin")
    assert update.setup_install_dir() is None


def test_installer_has_the_apps_id():
    """papermini finds the installer's entry by the AppId in papermini.iss."""
    iss = (
        Path(__file__).resolve().parent.parent / "packaging" / "papermini.iss"
    ).read_text()
    app_id = iss.split("AppId={", 1)[1].split("}", 1)[0].lstrip("{")
    assert update.SETUP_KEY.endswith("\\{" + app_id + "}_is1")
    assert (
        update.asset_name("0.6.0", "windows-x64", setup=True)
        == "papermini-0.6.0-windows-x64-setup.exe"
    )


def test_installed_copy_downloads_the_installer(
    monkeypatch, tmp_path, keys, local_files, sign
):
    private, public = keys
    monkeypatch.setattr(update, "target", lambda: "windows-x64")
    monkeypatch.setattr(update, "installed_with_setup", lambda: True)
    rel = tmp_path / "release"
    rel.mkdir()
    setup = rel / update.asset_name("9.9.9", "windows-x64", setup=True)
    setup.write_bytes(b"the installer")
    sums = f"{hashlib.sha256(b'the installer').hexdigest()}  {setup.name}\n".encode()
    (rel / update.CHECKSUMS).write_bytes(sums)
    (rel / update.SIGNATURE).write_bytes(sign(sums, private))
    release = update.Release("9.9.9", "", {f.name: f.as_uri() for f in rel.iterdir()})
    monkeypatch.setenv(update.KEY_ENV, public)
    steps = []
    got = update.download(release, step=steps.append)
    assert got.name == setup.name and got.read_bytes() == b"the installer"
    assert steps == ["verifying"]  # (nothing to unpack)
    assert update.pending() == ("9.9.9", got)
    # a changed installer is refused, like any download
    setup.write_bytes(b"another installer")
    with pytest.raises(update.UpdateError, match="checksum"):
        update.download(release)
    assert update.pending() is None


@pytest.mark.skipif(sys.platform != "win32", reason="the installer is for Windows")
def test_helper_runs_the_installer_silently(tmp_path):
    setup = tmp_path / "new" / "papermini-9.9.9-windows-x64-setup.exe"
    script, _ = update.install_script(setup, tmp_path / "papermini", 1, restart=True)
    text = script.read_text()
    assert f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART' in text
    assert "Robocopy" not in text  # (the installer replaces the files)
    assert 'start "" "' in text  # Restart now: start papermini after it


# endregion
