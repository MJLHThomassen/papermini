"""Tests of the creature size tables."""

from dataclasses import replace

import pytest

from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.size_row import SizeRow
from papermini.project.size_table import SizeTable


def test_the_builtin_table():
    t = sizes.BUILTIN
    assert (t.name, t.grid_mm, t.medium_mm) == ("Standard 1-inch", 25.4, 32)
    rows = {
        s: (r.height_mm, r.base_mm, r.tab_width_mm, r.tab_height_mm)
        for s, r in t.rows.items()
    }
    assert rows == {
        "tiny": (16, 12.5, 12.5, 6.25),
        "small": (24, 25, 25, 12.5),
        "medium": (32, 25, 25, 12.5),
        "large": (48, 50, 50, 25),
        "huge": (64, 75, 75, 37.5),
        "gargantuan": (80, 100, 100, 50),
    }
    assert t.calculated()
    assert t.row("large").values() == {
        "height_mm": 48,
        "tab_radius_mm": 25,
        "tab_width_mm": 50,
        "tab_height_mm": 25,
        "token_diameter_mm": 50,
    }
    # the figure defaults are Medium's
    d = FigureSettings()
    assert (d.size, d.height_mm, d.tab_radius_mm, d.tab_width_mm, d.tab_height_mm) == (
        "medium",
        32,
        12.5,
        25,
        12.5,
    )


def test_a_table_round_trips_and_is_checked(size_calculator):
    t = replace(size_calculator.calculate(28), name="Club")
    t = replace(t, rows={**t.rows, "large": SizeRow(50, 52, 52, 26)})
    d = t.to_dict()
    assert list(d)[:3] == ["preset", "grid_mm", "medium_mm"]
    assert SizeTable.from_dict(d) == t
    assert not t.calculated() and t.same_values(replace(t, name="Other"))
    assert not t.same_values(size_calculator.calculate(28))
    assert SizeTable.from_dict(None) == sizes.BUILTIN
    # (no name: no preset key)
    assert "preset" not in size_calculator.calculate().to_dict()
    # sizes left out are calculated from the grid and Medium's height
    part = SizeTable.from_dict({"grid-mm": 30, "large": {"height_mm": 50}})
    assert part.row("medium") == SizeRow.calculated("medium", 30, 32)
    assert part.row("large").height_mm == 50
    assert part.row("large").base_mm == SizeRow.calculated("large", 30, 32).base_mm
    for bad, match in (
        ({"grid_mm": 0}, "grid_mm"),
        ({"colossal": {}}, "unknown"),
        ({"large": {"depth_mm": 3}}, "unknown"),
        ({"large": 5}, "large"),
        ({"preset": 3}, "preset"),
        ({"tiny": {"height_mm": "tall"}}, "height_mm"),
        ([1], "sizes must"),
    ):
        with pytest.raises(ValueError, match=match):
            SizeTable.from_dict(bad)
