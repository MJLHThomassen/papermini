from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .cut_path import CutPath
from .style import Style
from .text_fitter import TextFitter
from .text_item import NUMBER_PLACEHOLDER, TextItem
from .token_info import TokenInfo

TAB_SHOWS = ("label", "number", "label_number")  # what a tab shows


@dataclass
class Mini:
    """A finished miniature in millimetres (origin top-left, y down)."""

    name: str
    width_mm: float
    height_mm: float
    art: Image.Image  # RGBA, covers 0..width_mm x 0..height_mm
    cut: CutPath  # in mm
    folds: list[tuple[float, float, float]] = field(default_factory=list)  # x0, x1, y
    labels: list[tuple[float, float, float]] = field(
        default_factory=list
    )  # cx, cy, rot
    label: str = ""
    label_size_mm: float = 3.4
    style: Style = field(default_factory=Style)
    # extra lines of text, such as the text on the back of a double-sided mini
    texts: list[TextItem] = field(default_factory=list)
    figure_height_mm: float = 0.0  # measured height of the drawing (one side)
    figure_width_mm: float = 0.0  # measured width of the drawing
    aspect: float = 1.0  # width / height of the drawing in the image
    tab_overlap_used: bool = True  # False: the tab overlap changed nothing here
    tab_joint_mm: float = 0.0  # paper joining tab and figure (0: no tab)
    tab_width_mm: float = 0.0
    close_px: int = 0  # closing radius used (the automatic one if unset)
    # the cut line and folds in pixels of the source image (front side), to show
    # on the original artwork what is kept and what is cut away
    source_cut: CutPath | None = None
    source_folds: list[tuple[float, float, float]] = field(default_factory=list)
    source_top: float = (
        0.0  # above this row the piece is the double-sided back, not the image
    )
    # what background removal found (outer edges and holes), in source image pixels
    source_outline: list[np.ndarray] = field(default_factory=list)
    # how the figure was found: "alpha" (the image's own transparency), "mask" (a mask
    # image file) or the model that ran; for model "auto", the one it picked
    method: str = ""
    # numbers: what each tab shows (one per entry of ``labels``: "label", "number" or
    # "label_number"), the room for text on a tab (w, h mm), where the back side's number
    # goes (cx, cy, w, h mm), and this copy's number (None: the placeholder)
    tab_shows: list[str] = field(default_factory=list)
    tab_room: tuple[float, float] = (0.0, 0.0)
    number_box: tuple[float, float, float, float] | None = None
    number: int | None = None
    # text read from an SVG file, drawn as it is (numbers already written into it)
    extra: list[TextItem] = field(default_factory=list)
    # "mini" (a standing miniature) or "token" (a flat round token); a token's circle,
    # ring, text and framing
    kind: str = "mini"
    token: TokenInfo | None = None

    @property
    def numbered(self) -> bool:
        """Whether the miniature shows its copy number anywhere."""
        if self.token is not None:
            return self.token.text in ("number", "label_number")
        return self.number_box is not None or any(s != "label" for s in self.tab_shows)

    def text_items(self) -> list[TextItem]:
        """Every text on the miniature: the tab labels and numbers, the back text and the
        back side's number. On a tab showing both, the number goes above the label (on
        the fold's side), as large as fits."""
        st = self.style
        if self.token is not None:
            return self.token.text_items(self.label, self.number, st.font) + list(
                self.extra
            )
        num = NUMBER_PLACEHOLDER if self.number is None else str(self.number)
        room_w, room_h = self.tab_room
        items: list[TextItem] = []
        shows = self.tab_shows or ["label"] * len(self.labels)
        for (cx, cy, rot), what in zip(self.labels, shows):
            label = self.label if what in ("label", "label_number") else ""
            number = what in ("number", "label_number")
            if label and not number:
                items.append(
                    TextItem(
                        "label", label, cx, cy, rot, self.label_size_mm, st.label_color
                    )
                )
            elif number and not label:
                items.append(
                    TextItem(
                        "number",
                        num,
                        cx,
                        cy,
                        rot,
                        TextFitter.number_size(num, room_w, room_h, st.font),
                        st.label_color,
                        True,
                    )
                )
            elif number:
                ls, gap = self.label_size_mm, 0.15 * self.label_size_mm
                ns = max(
                    ls, TextFitter.number_size(num, room_w, room_h - ls - gap, st.font)
                )
                block = ns + gap + ls
                up = (
                    -1.0 if rot == 0 else 1.0
                )  # towards the fold (the back tab is upside down)
                items.append(
                    TextItem(
                        "number",
                        num,
                        cx,
                        cy + up * (block - ns) / 2,
                        rot,
                        ns,
                        st.label_color,
                        True,
                    )
                )
                items.append(
                    TextItem(
                        "label",
                        label,
                        cx,
                        cy - up * (block - ls) / 2,
                        rot,
                        ls,
                        st.label_color,
                    )
                )
        items += self.texts
        if self.number_box is not None:
            cx, cy, w, h = self.number_box
            items.append(
                TextItem(
                    "number",
                    num,
                    cx,
                    cy,
                    180.0,
                    TextFitter.number_size(num, w, h, st.font),
                    st.back_text_color,
                    True,
                )
            )
        return items + list(self.extra)

    def png_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.art.save(buf, "PNG", optimize=True)
        return buf.getvalue()
