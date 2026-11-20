from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..output.paper_sizes import Paper, PaperSizes
from ..output.registration_marks import MARKS
from ..output.sheet_layout import SheetLayout
from ..output.sheet_packer import CUT_MODES, SheetPacker
from ..pipeline.bleed_painter import MAX_BLEED_MM
from ..pipeline.mini import Mini
from .option import Option


@dataclass
class SheetSettings:
    """The print sheet's settings, each field with its option."""

    output: str | None = Option(
        help="the sheet's PDF (default: <output>/sheet.pdf)",
    ).field(None)
    paper: str = Option(
        label="Paper",
        help="paper size; custom: give --paper-width-mm and --paper-height-mm",
        tooltip="The paper size of the sheet. Custom: a width and height of your own.",
        choices=PaperSizes.PAPER_CHOICES,
        choice_labels=tuple(
            PaperSizes.PAPER_LABELS[p] for p in PaperSizes.PAPER_CHOICES
        ),
    ).field("a4")
    paper_width_mm: float | None = Option(
        label="Width",
        help=f"a custom paper's width, {PaperSizes.CUSTOM_PAPER_MM[0]:g} to "
        f"{PaperSizes.CUSTOM_PAPER_MM[1]:g} mm, with --paper-height-mm",
        tooltip="The width of a custom paper size, as it prints (50 to 1200 mm).",
        low=PaperSizes.CUSTOM_PAPER_MM[0],
        high=PaperSizes.CUSTOM_PAPER_MM[1],
        widget=PaperSizes.CUSTOM_PAPER_MM,
        unit="mm",
        decimals=1,
    ).field(None)
    paper_height_mm: float | None = Option(
        label="Height",
        help=f"a custom paper's height, {PaperSizes.CUSTOM_PAPER_MM[0]:g} to "
        f"{PaperSizes.CUSTOM_PAPER_MM[1]:g} mm, with --paper-width-mm",
        tooltip="The height of a custom paper size, as it prints (50 to 1200 mm).",
        low=PaperSizes.CUSTOM_PAPER_MM[0],
        high=PaperSizes.CUSTOM_PAPER_MM[1],
        widget=PaperSizes.CUSTOM_PAPER_MM,
        unit="mm",
        decimals=1,
    ).field(None)
    orientation: str = Option(
        label="Orientation",
        help="portrait or landscape, for a named paper size",
        tooltip="Portrait: the page upright. Landscape: the page on its side, for wide\n"
        "figures and rows.",
        choices=PaperSizes.ORIENTATIONS,
        choice_labels=("Portrait", "Landscape"),
    ).field("portrait")
    copies: int = Option(
        help="copies of each figure",
    ).field(1)
    preview: bool = Option(
        help="also write a PNG preview per page",
    ).field(False)
    title: str = Option(
        label="Title",
        help="the title printed at the top of each page",
        tooltip="Printed at the top of each page, above the instructions.",
    ).field("Paper miniatures")
    margin_mm: float = Option(
        label="Margin",
        help="page margin; --cut machine: where the alignment marks are",
        tooltip="The empty border around each page. Cut by machine, the alignment marks "
        "sit\n"
        "here, this far from the paper edges.",
        widget=(0, 50),
        unit="mm",
    ).field(12.0)
    gap_mm: float = Option(
        label="Gap",
        help="gap between pieces",
        tooltip="The space between the pieces on the sheet.",
        widget=(0, 50),
        unit="mm",
    ).field(7.0)
    enabled: bool = Option(
        help="whether the project makes a sheet",
    ).field(True)
    cut: str = Option(
        label="Cut by",
        help="hand: cut lines on the sheet; machine: a sheet without cut lines but "
        "with alignment marks, plus a cut file (NAME-cut.svg) per page",
        tooltip="By hand: the cut lines are printed on the sheet, for scissors or a "
        "knife.\n"
        "Machine: the sheet has no cut lines but alignment marks; Export PDF also\n"
        "writes a cut file (SVG) with the cut lines and the same marks, to line up in\n"
        "your cutting machine's software.",
        choices=CUT_MODES,
        choice_labels=("By hand", "Machine"),
    ).field("hand")
    bleed_mm: float = Option(
        label="Bleed",
        help="cut by machine: the edge colors printed beyond the cut line",
        tooltip="Prints the edge colors (margin, tab or back) this far beyond the cut "
        "line, so a\n"
        "machine cut that is slightly off never shows a white edge.",
        low=0,
        high=MAX_BLEED_MM,
        widget=(0, MAX_BLEED_MM),
        unit="mm",
        step=0.1,
        decimals=1,
    ).field(1.0)
    marks: str = Option(
        label="Marks",
        help="--cut machine: alignment marks: corners, Silhouette Studio's "
        "Type 1, or none",
        tooltip="Corners: an L in each corner and a small square top-left.\n"
        "Silhouette: Silhouette Studio's Type 1 marks (a square top-left, an L "
        "top-right\n"
        "and bottom-left; length 20 mm, thickness 0.5 mm, inset = the margin).\n"
        "None: no marks; line up the cut file with the page edges.",
        choices=MARKS,
        choice_labels=("Corners", "Silhouette", "None"),
    ).field("corners")
    cut_folds: bool = Option(
        label="Fold lines in cut file",
        help="--cut machine: also put the fold lines in the cut file",
        tooltip="Also put the fold lines in the cut file (in blue, in their own group), "
        "to\n"
        "score or draw them with the machine.",
    ).field(False)
    mat: str | None = Option(
        label="Mat",
        help="--cut machine: the cutting mat (12x12 or 12x24 inches); a note when "
        "the paper is bigger",
        none_means="any size, no note",
        tooltip="The cutting mat you put the sheet on. papermini warns when the paper "
        "is\n"
        "bigger than the mat (turned either way). Any size: no warning.",
        choices=tuple(PaperSizes.MATS),
        choice_labels=tuple(PaperSizes.MAT_LABELS[m] for m in PaperSizes.MATS),
    ).field(None)

    @classmethod
    def options(cls) -> dict[str, Option]:
        """Return each field's option, by field name."""
        return _OPTIONS

    @property
    def machine(self) -> bool:
        return self.cut == "machine"

    @property
    def page(self) -> Paper:
        """The paper for ``SheetPacker.pack``: its name, or a custom (width, height)
        mm."""
        if self.paper == "custom":
            return (self.paper_width_mm, self.paper_height_mm)
        return self.paper

    def paper_text(self) -> str:
        """The paper as messages name it."""
        return PaperSizes.text(self.page, self.orientation)

    def mat_warning(self) -> str:
        """Cut by machine on a mat: why the paper does not fit it ("" when it does)."""
        return (
            PaperSizes.mat_warning(self.page, self.orientation, self.mat)
            if self.machine
            else ""
        )

    def layout(
        self,
        packer: SheetPacker,
        minis: Sequence[tuple[Mini, int]],
        leave_out: bool = False,
    ) -> SheetLayout:
        """Pack ``minis``, each with its number of copies, onto the pages of this
        sheet with ``packer``. With ``leave_out``, a piece too big for the paper is
        left off the sheet instead of being an error."""
        return packer.pack(
            minis,
            self.page,
            self.margin_mm,
            self.gap_mm,
            cut=self.cut,
            marks=self.marks,
            orientation=self.orientation,
            leave_out=leave_out,
        )

    @property
    def figure_bleed(self) -> float:
        """The bleed every figure is built with: only when cut by machine."""
        return self.bleed_mm if self.machine else 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SheetSettings:
        d = Option.norm_keys(d)
        unknown = set(d) - set(_OPTIONS)
        if unknown:
            raise ValueError(f"unknown sheet option(s) {', '.join(sorted(unknown))}")
        if "paper" not in d and ("paper_width_mm" in d or "paper_height_mm" in d):
            d["paper"] = "custom"  # (a width and height of its own: a custom size)
        for key in ("paper_width_mm", "paper_height_mm"):
            v, option = d.get(key), _OPTIONS[key]
            if d.get("paper") == "custom" and (v is None or not option.allows(v)):
                raise ValueError(
                    f"sheet {key} must be from {option.low:g} to {option.high:g} (mm) "
                    f"for a custom paper, not {v!r}"
                )
            if d.get("paper") != "custom" and v is not None:
                raise ValueError(f"sheet {key} is only for paper: custom")
        d = {key: _OPTIONS[key].check(value, "sheet ") for key, value in d.items()}
        return cls(**d)


_OPTIONS = Option.of(SheetSettings)
