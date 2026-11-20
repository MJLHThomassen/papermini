from __future__ import annotations

import re
from dataclasses import dataclass, field

# a release version: MAJOR.MINOR.PATCH, with or without the "v" of its tag
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


@dataclass
class Release:
    """A published release of papermini. Its static methods read release versions."""

    version: str  # the release's version, without the "v" of its tag
    url: str  # the release page
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download link

    @staticmethod
    def parse_version(text: str) -> tuple[int, int, int] | None:
        """Parse a release version (with or without "v") into (major, minor, patch); None
        for anything else, such as a development version or a pre-release."""
        m = _VERSION.fullmatch(text.strip())
        return (int(m[1]), int(m[2]), int(m[3])) if m else None

    @staticmethod
    def leading_version(text: str) -> tuple[int, int, int] | None:
        """The leading (major, minor, patch) of a papermini version: a development
        version counts as the release it leads up to. None when it has none."""
        m = _VERSION.match(text.strip())
        return (int(m[1]), int(m[2]), int(m[3])) if m else None

    @staticmethod
    def is_newer(latest: str, current: str) -> bool:
        """Whether release ``latest`` is newer than ``current``. For a development version
        (papermini run from source), only its leading major.minor.patch counts."""
        a, b = Release.parse_version(latest), Release.leading_version(current)
        return a is not None and b is not None and a > b
