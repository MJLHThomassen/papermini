from __future__ import annotations

from dataclasses import dataclass, field

from ..pipeline.mini import Mini
from .placement import Placement

INSTRUCTIONS = [
    "Print at 100% / actual size (no 'fit to page'). Check: the bar below must measure 50 mm.",
    (
        "Cut along the solid line and fold along the dashed lines. Square tabs slot into a stand; "
        "round tabs fold outwards into a base."
    ),
]


INSTRUCTIONS_DOUBLE = (
    "Double-sided: fold at the top dashed line and glue the halves back to back."
)


INSTRUCTIONS_MACHINE = [
    INSTRUCTIONS[0],
    "Cut by machine: line up the cut file's marks with these marks. Fold along the dashed lines.",
]


INSTRUCTIONS_MACHINE_NO_MARKS = [
    INSTRUCTIONS[0],
    "Cut by machine: line up the cut file with this page. Fold along the dashed lines.",
]


@dataclass
class SheetLayout:
    paper: tuple[float, float]
    placements: list[Placement]
    pages: int
    header_mm: float
    margin_mm: float = 12.0  # the page margin: where the header and the pieces start
    cut: str = "hand"  # "hand" (cut lines on the sheet) or "machine"
    marks: str | None = None  # alignment marks (cut by machine)
    mark_inset: float = 0.0  # distance of the marks from the paper edges
    header_x: float = 0.0  # left of the header (right of a top-left mark)
    header_right: float = 0.0  # right end of the header (left of a top-right mark)
    paper_name: str = ""  # the paper as messages name it, e.g. "A3 landscape"
    left_out: list[Mini] = field(
        default_factory=list
    )  # too big for the paper (one each)

    def too_big_names(self, names: dict | None = None) -> list[str]:
        """The names of the figures too big for the paper. ``names``: the figures' names
        by ``id(mini.art)`` (default: the minis' own)."""
        names = names or {}
        return [names.get(id(m.art), m.name) for m in self.left_out]

    @property
    def machine(self) -> bool:
        return self.cut == "machine"

    def mark_rects(self) -> list[tuple[float, float, float, float]]:
        from .sheet import registration_marks

        return (
            registration_marks(self.paper, self.marks, self.mark_inset)
            if self.marks
            else []
        )

    def instructions(self) -> list[str]:
        double = any(
            len(p.mini.labels) > 1 or len(p.mini.folds) > 1 for p in self.placements
        )
        lines = list(
            INSTRUCTIONS
            if not self.machine
            else INSTRUCTIONS_MACHINE_NO_MARKS
            if self.marks == "none"
            else INSTRUCTIONS_MACHINE
        )
        return lines + ([INSTRUCTIONS_DOUBLE] if double else [])
