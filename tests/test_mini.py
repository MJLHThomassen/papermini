"""Tests of a finished miniature's own rules."""

import numpy as np
import pytest
from PIL import Image

from papermini.pipeline.cut_path import CutPath
from papermini.pipeline.mini import Mini


def _mini(tab_width_mm: float, tab_joint_mm: float) -> Mini:
    return Mini(
        name="hero",
        width_mm=30.0,
        height_mm=80.0,
        art=Image.new("RGBA", (1, 1)),
        cut=CutPath(np.zeros((3, 2))),
        tab_width_mm=tab_width_mm,
        tab_joint_mm=tab_joint_mm,
    )


@pytest.mark.parametrize(
    ("tab_width_mm", "tab_joint_mm", "narrow"),
    [
        (25.0, 12.0, False),  # wider than 10 mm and than 60% of the tab
        (25.0, 9.9, True),  # under 10 mm, and under 60% of the tab (15 mm)
        (12.0, 7.0, True),  # under 60% of the tab (7.2 mm)
        (12.0, 7.5, False),  # under 10 mm, but not under 60% of the tab
        (0.0, 0.0, False),  # no tab, so no joint
    ],
)
def test_a_joint_is_narrow_under_10_mm_and_under_60_percent_of_the_tab(
    tab_width_mm, tab_joint_mm, narrow
):
    assert _mini(tab_width_mm, tab_joint_mm).joint_is_narrow is narrow
