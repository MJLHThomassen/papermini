from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Release:
    version: str  # the release's version, without the "v" of its tag
    url: str  # the release page
    assets: dict[str, str] = field(default_factory=dict)  # file name -> download link
