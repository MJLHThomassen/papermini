"""Tests of the script that builds the Windows installer."""

import sys

import pytest


def test_installer_script_compiles(tmp_path, scripts):
    """Inno Setup compiles packaging/papermini.iss, its [Code] included (Windows, with
    Inno Setup 6 installed)."""
    build_installer = scripts("build_installer")

    if sys.platform != "win32" or build_installer.find_iscc() is None:
        pytest.skip("needs Windows and Inno Setup 6")
    dist = tmp_path / "papermini"
    (dist / "_internal").mkdir(parents=True)
    (dist / "papermini.exe").write_bytes(b"pretend papermini")
    (dist / "_internal" / "a.dll").write_bytes(b"pretend library")
    setup = build_installer.build("0.0.1", dist, tmp_path / "out")
    assert setup.is_file() and setup.name == "papermini-0.0.1-windows-x64-setup.exe"
