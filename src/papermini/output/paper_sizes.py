from __future__ import annotations

from typing import ClassVar

Paper = str | tuple[float, float]  # a paper name, or a custom (width, height) in mm


class PaperSizes:
    """The paper sizes and cutting mats a sheet can use, and how messages name them."""

    # paper sizes, portrait (width, height mm), and their names in the app
    PAPER: ClassVar[dict[str, tuple[float, float]]] = {
        "a3": (297.0, 420.0),
        "a4": (210.0, 297.0),
        "a5": (148.0, 210.0),
        "letter": (215.9, 279.4),
        "legal": (215.9, 355.6),
        "tabloid": (279.4, 431.8),
    }

    PAPER_LABELS: ClassVar[dict[str, str]] = {
        "a3": "A3 (297 \u00d7 420 mm)",
        "a4": "A4 (210 \u00d7 297 mm)",
        "a5": "A5 (148 \u00d7 210 mm)",
        "letter": "Letter (8.5 \u00d7 11 in)",
        "legal": "Legal (8.5 \u00d7 14 in)",
        "tabloid": "Tabloid (11 \u00d7 17 in)",
        "custom": "Custom",
    }

    # custom: a width and height of its own
    PAPER_CHOICES = tuple(PAPER) + ("custom",)
    CUSTOM_PAPER_MM = (50.0, 1200.0)  # the smallest and largest side of a custom paper
    ORIENTATIONS = ("portrait", "landscape")

    # cutting mats (width, height mm): a page fits one either way round
    MATS: ClassVar[dict[str, tuple[float, float]]] = {
        "12x12": (304.8, 304.8),
        "12x24": (304.8, 609.6),
    }

    MAT_LABELS: ClassVar[dict[str, str]] = {
        "12x12": "12 \u00d7 12 in (305 \u00d7 305 mm)",
        "12x24": "12 \u00d7 24 in (305 \u00d7 610 mm)",
    }

    @staticmethod
    def size(paper: Paper, orientation: str = "portrait") -> tuple[float, float]:
        """The page's (width, height) in mm. A named paper turns for landscape; a custom
        (width, height) is used as it is."""
        if not isinstance(paper, str):
            return float(paper[0]), float(paper[1])
        if paper.lower() not in PaperSizes.PAPER:
            raise ValueError(
                f"paper must be one of {', '.join(PaperSizes.PAPER)} or a custom size, "
                f"not {paper!r}"
            )
        if orientation not in PaperSizes.ORIENTATIONS:
            raise ValueError(
                f"orientation must be one of {', '.join(PaperSizes.ORIENTATIONS)}, "
                f"not {orientation!r}"
            )
        w, h = PaperSizes.PAPER[paper.lower()]
        return (h, w) if orientation == "landscape" else (w, h)

    @staticmethod
    def text(paper: Paper, orientation: str = "portrait") -> str:
        """The paper as messages name it: its name, with "landscape" after it when it
        is turned, or a custom paper's width and height in mm."""
        if not isinstance(paper, str):
            return f"{paper[0]:g} x {paper[1]:g} mm"
        name = PaperSizes.PAPER_LABELS.get(paper.lower(), paper).split(" (")[0]
        return name + (" landscape" if orientation == "landscape" else "")

    @staticmethod
    def fits_mat(size: tuple[float, float], mat: str) -> bool:
        """Whether a page of ``size`` (mm) fits the cutting mat, either way round."""
        mw, mh = PaperSizes.MATS[mat]
        w, h = sorted(size)
        return w <= min(mw, mh) + 0.5 and h <= max(mw, mh) + 0.5

    @staticmethod
    def mat_warning(paper: Paper, orientation: str, mat: str | None) -> str:
        """Why the paper does not fit the cutting mat ("" when it fits, or without a
        mat)."""
        if not mat:
            return ""
        w, h = PaperSizes.size(paper, orientation)
        if PaperSizes.fits_mat((w, h), mat):
            return ""
        return (
            f"{PaperSizes.text(paper, orientation)} ({w:.0f} \u00d7 {h:.0f} mm) is "
            f"bigger than the {PaperSizes.MAT_LABELS[mat].replace(' (', ' mat (')}."
        )
