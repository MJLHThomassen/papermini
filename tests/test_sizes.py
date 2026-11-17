"""Tests of the creature size tables."""

from dataclasses import replace

import pytest

from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings


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


def test_calculating_a_table():
    t = sizes.calculate(30, 40)
    assert t.row("medium") == sizes.SizeRow(40, 29.53, 29.53, 14.77)
    assert t.row("large").height_mm == 60 and t.row("tiny").base_mm == 14.76
    assert t.name == "" and t.calculated()
    g = sizes.for_grid(30)  # the command line's --grid-mm: heights scale too
    assert g.medium_mm == pytest.approx(32 * 30 / 25.4)
    assert g.row("huge").base_mm == round(3 * 30 * 25 / 25.4, 2)


def test_a_table_round_trips_and_is_checked():
    t = replace(sizes.calculate(28), name="Club")
    t = replace(t, rows={**t.rows, "large": sizes.SizeRow(50, 52, 52, 26)})
    d = t.to_dict()
    assert list(d)[:3] == ["preset", "grid_mm", "medium_mm"]
    assert sizes.SizeTable.from_dict(d) == t
    assert not t.calculated() and t.same_values(replace(t, name="Other"))
    assert not t.same_values(sizes.calculate(28))
    assert sizes.SizeTable.from_dict(None) == sizes.BUILTIN
    assert "preset" not in sizes.calculate().to_dict()  # (no name: no preset key)
    # sizes left out are calculated from the grid and Medium's height
    part = sizes.SizeTable.from_dict({"grid-mm": 30, "large": {"height_mm": 50}})
    assert part.row("medium") == sizes.calculate_row("medium", 30, 32)
    assert part.row("large").height_mm == 50
    assert part.row("large").base_mm == sizes.calculate_row("large", 30, 32).base_mm
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
            sizes.SizeTable.from_dict(bad)


def test_a_size_fills_in_and_a_hand_edit_makes_it_custom():
    s = sizes.apply(FigureSettings(), "huge")
    assert (s.size, s.height_mm, s.tab_radius_mm, s.tab_width_mm, s.tab_height_mm) == (
        "huge",
        64,
        37.5,
        75,
        37.5,
    )
    assert sizes.matches(s)
    edited = sizes.reconcile(s, replace(s, tab_width_mm=70))
    assert edited.size == "custom" and edited.tab_width_mm == 70
    picked = sizes.reconcile(edited, replace(edited, size="small"))
    assert (picked.size, picked.height_mm, picked.tab_width_mm) == ("small", 24, 25)
    assert sizes.reconcile(picked, replace(picked, label="X")).size == "small"
    assert (
        sizes.apply(replace(s, width_mm=80), "large").width_mm is None
    )  # width follows
    assert not sizes.matches(replace(picked, width_mm=30))
    assert sizes.apply(edited, "custom") == edited  # custom keeps the values
    big = sizes.apply(FigureSettings(), "large", sizes.calculate(30, 40))
    assert big.height_mm == 60 and big.tab_radius_mm == 29.53


def test_footprint_and_width_warning():
    t = sizes.BUILTIN
    assert sizes.footprint_text("large", t) == "2 × 2 squares · 50 mm base"
    assert sizes.footprint_text("medium", t) == "1 × 1 square · 25 mm base"
    assert sizes.footprint_text("tiny", t) == "½ × ½ square · 12.5 mm base"
    assert sizes.footprint_text("custom", t) == ""
    assert sizes.width_warning("large", 50, t) == ""
    assert sizes.width_warning("large", 96, t) == (
        "This figure is 96 mm wide, wider than its 2 squares (50.8 mm): set a width or "
        "pick a bigger size."
    )
    assert "half a square (12.7 mm)" in sizes.width_warning("tiny", 20, t)
    assert (
        sizes.width_warning("custom", 500, t) == ""
        and sizes.width_warning("large", 0, t) == ""
    )
