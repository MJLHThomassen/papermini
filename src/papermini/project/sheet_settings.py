from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from ..output.sheet import (
    CUSTOM_PAPER_MM,
    CUT_MODES,
    MARKS,
    MATS,
    ORIENTATIONS,
    PAPER_CHOICES,
    Paper,
    mat_warning,
    paper_text,
)


@dataclass
class SheetSettings:
    output: str | None = None  # default: <output>/sheet.pdf
    paper: str = "a4"  # a name in sheet.PAPER, or "custom"
    paper_width_mm: float | None = None  # paper "custom": its width and height
    paper_height_mm: float | None = None
    orientation: str = "portrait"  # "portrait" or "landscape" (named paper only)
    copies: int = 1  # default copies for figures that set none
    preview: bool = False
    title: str = "Paper miniatures"
    margin_mm: float = 12.0
    gap_mm: float = 7.0
    enabled: bool = True
    cut: str = "hand"  # "hand": cut lines on the sheet; "machine": see below
    bleed_mm: float = 1.0  # cut by machine: edge colors printed beyond the cut line
    marks: str = "corners"  # cut by machine: "corners" or "silhouette" alignment marks
    cut_folds: bool = False  # cut by machine: fold lines in the cut file too
    mat: str | None = None  # cut by machine: the cutting mat ("12x12" or "12x24"),
    # only to warn when the paper is bigger; None: any size

    @property
    def machine(self) -> bool:
        return self.cut == "machine"

    @property
    def page(self) -> Paper:
        """The paper for ``sheet.pack``: its name, or a custom (width, height) mm."""
        if self.paper == "custom":
            return (self.paper_width_mm, self.paper_height_mm)
        return self.paper

    def paper_text(self) -> str:
        """The paper as messages name it, e.g. "A3 landscape"."""
        return paper_text(self.page, self.orientation)

    def mat_warning(self) -> str:
        """Cut by machine on a mat: why the paper does not fit it ("" when it does)."""
        return (
            mat_warning(self.page, self.orientation, self.mat) if self.machine else ""
        )

    @property
    def figure_bleed(self) -> float:
        """The bleed every figure is built with: only when cut by machine."""
        return self.bleed_mm if self.machine else 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SheetSettings:
        from .settings import norm_keys

        d = norm_keys(d)
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown sheet option(s) {', '.join(sorted(unknown))}")
        if "paper" not in d and ("paper_width_mm" in d or "paper_height_mm" in d):
            d["paper"] = "custom"  # (a width and height of its own: a custom size)
        for key, allowed in (
            ("cut", CUT_MODES),
            ("marks", MARKS),
            ("paper", PAPER_CHOICES),
            ("orientation", ORIENTATIONS),
            ("mat", tuple(MATS) + (None,)),
        ):
            if key in d and d[key] not in allowed:
                shown = ", ".join(str(a) for a in allowed if a is not None)
                raise ValueError(f"sheet {key} must be one of {shown}, not {d[key]!r}")
        lo, hi = CUSTOM_PAPER_MM
        for key in ("paper_width_mm", "paper_height_mm"):
            v = d.get(key)
            if d.get("paper") == "custom" and not (
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and lo <= v <= hi
            ):
                raise ValueError(
                    f"sheet {key} must be from {lo:g} to {hi:g} (mm) for a "
                    f"custom paper, not {v!r}"
                )
            if d.get("paper") != "custom" and v is not None:
                raise ValueError(f"sheet {key} is only for paper: custom")
        if "bleed_mm" in d and not (
            isinstance(d["bleed_mm"], (int, float)) and 0 <= d["bleed_mm"] <= 5
        ):
            raise ValueError(
                f"sheet bleed_mm must be from 0 to 5, not {d['bleed_mm']!r}"
            )
        return cls(**d)
