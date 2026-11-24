from __future__ import annotations

from enum import IntEnum
from typing import Self


class Step(IntEnum):
    """A step of the workflow, by its place in the order of the steps.

    Each step has a view in the window and its own settings in the settings panel.
    ``title`` names its view, ``subtitle`` says what the view shows, and ``hint``
    says what its settings are for. ``token_hint`` is the hint for a token.
    """

    title: str
    subtitle: str
    hint: str
    token_hint: str

    SOURCE = (
        0,
        "Source",
        "the picture, and the figure found in it",
        "Crop the picture first: background removal only looks inside the box.",
    )
    MINIATURE = (
        1,
        "Miniature",
        "the piece as it will print",
        (
            "How big the figure prints, and the paper piece around it: back side, "
            "margin, cut line and stand tab."
        ),
        "How big the token prints, how the figure sits in it, and its ring and text.",
    )
    SHEET = (
        2,
        "Print sheet",
        "the pages to print",
        "The paper, the layout and how the pieces are cut.",
    )

    def __new__(
        cls,
        index: int,
        title: str,
        subtitle: str,
        hint: str,
        token_hint: str | None = None,
    ) -> Self:
        step = int.__new__(cls, index)
        step._value_ = index
        step.title = title
        step.subtitle = subtitle
        step.hint = hint
        step.token_hint = hint if token_hint is None else token_hint
        return step
