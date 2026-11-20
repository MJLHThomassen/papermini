from __future__ import annotations

from dataclasses import dataclass

from ...pipeline.mini import Mini


@dataclass(frozen=True)
class BuildResult:
    """How a build job ended, for the figure ``uid`` and the settings ``key`` it
    started with: its miniature, or the message of its failure. A cancelled build has
    neither."""

    uid: int
    key: str
    mini: Mini | None = None
    error: str | None = None
