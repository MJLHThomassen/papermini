from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MergeKey:
    """What a change edits, when it edits the settings of one figure or of the
    sheet and nothing else: the figure's uid, or None for the sheet, and the names
    of the settings."""

    figure: int | None
    names: frozenset[str]

    def overlaps(self, other: MergeKey) -> bool:
        """Tell whether ``other`` edits the same figure, or the sheet, and at least
        one of the same settings."""
        return other.figure == self.figure and bool(other.names & self.names)

    def joined(self, other: MergeKey) -> MergeKey:
        """Return the key of this change and ``other`` made as one."""
        return MergeKey(self.figure, self.names | other.names)
