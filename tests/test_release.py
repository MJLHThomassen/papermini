"""Release versions: parsing them and telling which is newer."""

from papermini.support.release import Release


def test_versions():
    assert Release.parse_version("v0.5.0") == (0, 5, 0)
    assert Release.parse_version("1.2.3") == (1, 2, 3)
    for not_a_release in ("0.4.1.dev3+g1a2b3c4", "1.0.0-rc.1", "", "latest"):
        assert Release.parse_version(not_a_release) is None
    assert Release.is_newer("0.5.0", "0.4.9") and Release.is_newer("1.0.0", "0.10.0")
    assert not Release.is_newer("0.5.0", "0.5.0") and not Release.is_newer(
        "0.4.0", "0.5.0"
    )
    # run from source: a development version counts as the release it leads to
    assert Release.is_newer("0.5.0", "0.4.1.dev3+g1a2b3c4")
    assert not Release.is_newer("0.4.1", "0.4.1.dev3+g1a2b3c4")
    assert not Release.is_newer("1.0.0-rc.1", "0.5.0")  # (no pre-releases)


def test_the_leading_version_of_a_development_version():
    assert Release.leading_version("0.4.1.dev3+g1a2b3c4") == (0, 4, 1)
    assert Release.leading_version("v1.2.3") == (1, 2, 3)
    assert Release.leading_version("latest") is None
