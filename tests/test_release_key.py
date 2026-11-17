"""Tests of the script that makes the release key."""

import base64
import sys

import pytest


def test_release_key_writes_the_public_key(monkeypatch, tmp_path, scripts):
    release_key = scripts("release_key")

    update_py = tmp_path / "update.py"
    update_py.write_text('x = 1\nPUBLIC_KEY = ""\n')
    monkeypatch.setattr(release_key, "UPDATE_PY", update_py)
    monkeypatch.setattr(release_key, "ROOT", tmp_path)
    key_file = tmp_path / "key"
    monkeypatch.setattr(sys, "argv", ["release_key.py", str(key_file)])
    release_key.main()
    public = update_py.read_text().split('PUBLIC_KEY = "')[1].split('"')[0]
    assert (
        len(base64.b64decode(public)) == 32
        and len(base64.b64decode(key_file.read_text())) == 32
    )
    with pytest.raises(SystemExit, match="exists"):  # never replaces a key by accident
        release_key.main()
