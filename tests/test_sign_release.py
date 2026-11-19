"""Tests of the script that signs a release."""

import base64
import sys

import pytest


def test_sign_release_checks_the_apps_key(monkeypatch, tmp_path, keys, scripts, sign):
    sign_release = scripts("sign_release")

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
    assert sign_release.check(
        data, f.with_name(f.name + ".sig").read_bytes().strip(), public
    )
