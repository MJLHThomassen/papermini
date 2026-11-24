from __future__ import annotations

from dataclasses import dataclass, field

from ..pipeline.mini import Mini
from .placement import Placement
from .registration_marks import RegistrationMarks

TITLE = "Paper miniatures"  # the title of a sheet that is not given one

# the baselines of the text in the sheet header, in mm below the page margin
TITLE_BASELINE_MM = 4.0
INSTRUCTIONS_BASELINE_MM = 8.5  # the first line of the instructions
INSTRUCTIONS_LINE_MM = 3.4  # from one line to the next

# the calibration bar at the bottom of the header, in mm
BAR_MM = 50  # its length
BAR_ABOVE_MM = 4  # above the bottom of the header
BAR_WIDTH_MM = 0.4
BAR_TICK_STEP_MM = 10  # a tick across the bar every this many mm
BAR_TICK_MM = 1.0  # how far a tick reaches above and below the bar...
BAR_END_TICK_MM = 1.6  # ...and a tick at either end
BAR_TICK_WIDTH_MM = 0.2
BAR_LABEL = f"{BAR_MM} mm"
BAR_LABEL_GAP_MM = 2  # the label starts this far right of the bar...
BAR_LABEL_DROP_MM = 1  # ...with its baseline this far below it

INSTRUCTIONS = [
    (
        "Print at 100% / actual size (no 'fit to page'). "
        f"Check: the bar below must measure {BAR_LABEL}."
    ),
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
    paper_name: str = ""  # the paper's name in messages, plus landscape when turned
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
        return (
            RegistrationMarks.rects(self.paper, self.marks, self.mark_inset)
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
