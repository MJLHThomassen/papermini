"""Creature sizes: the size tables, how a size fills in a figure, projects and the
command line."""

from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini import sizes
from papermini.cli import main
from papermini.settings import (FigureEntry, FigureSettings, Project, load_project,
                                save_project, settings_with_size)
from papermini.svg import read_svg


def test_the_builtin_table():
    t = sizes.BUILTIN
    assert (t.name, t.grid_mm, t.medium_mm) == ("Standard 1-inch", 25.4, 32)
    rows = {s: (r.height_mm, r.base_mm, r.tab_width_mm, r.tab_height_mm)
            for s, r in t.rows.items()}
    assert rows == {"tiny": (16, 12.5, 12.5, 6.25), "small": (24, 25, 25, 12.5),
                    "medium": (32, 25, 25, 12.5), "large": (48, 50, 50, 25),
                    "huge": (64, 75, 75, 37.5), "gargantuan": (80, 100, 100, 50)}
    assert t.calculated()
    assert t.row("large").values() == {"height_mm": 48, "tab_radius_mm": 25,
                                       "tab_width_mm": 50, "tab_height_mm": 25}
    # the figure defaults are Medium's
    d = FigureSettings()
    assert (d.size, d.height_mm, d.tab_radius_mm, d.tab_width_mm, d.tab_height_mm) == (
        "medium", 32, 12.5, 25, 12.5)


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
    for bad, match in (({"grid_mm": 0}, "grid_mm"), ({"colossal": {}}, "unknown"),
                       ({"large": {"depth_mm": 3}}, "unknown"), ({"large": 5}, "large"),
                       ({"preset": 3}, "preset"), ({"tiny": {"height_mm": "tall"}}, "height_mm"),
                       ([1], "sizes must")):
        with pytest.raises(ValueError, match=match):
            sizes.SizeTable.from_dict(bad)


def test_a_size_fills_in_and_a_hand_edit_makes_it_custom():
    s = sizes.apply(FigureSettings(), "huge")
    assert (s.size, s.height_mm, s.tab_radius_mm, s.tab_width_mm, s.tab_height_mm) == (
        "huge", 64, 37.5, 75, 37.5)
    assert sizes.matches(s)
    edited = sizes.reconcile(s, replace(s, tab_width_mm=70))
    assert edited.size == "custom" and edited.tab_width_mm == 70
    picked = sizes.reconcile(edited, replace(edited, size="small"))
    assert (picked.size, picked.height_mm, picked.tab_width_mm) == ("small", 24, 25)
    assert sizes.reconcile(picked, replace(picked, label="X")).size == "small"
    assert sizes.apply(replace(s, width_mm=80), "large").width_mm is None  # width follows
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
        "pick a bigger size.")
    assert "half a square (12.7 mm)" in sizes.width_warning("tiny", 20, t)
    assert sizes.width_warning("custom", 500, t) == "" and sizes.width_warning("large", 0, t) == ""


def test_settings_with_size():
    assert settings_with_size({}) == sizes.apply(FigureSettings(), "medium")
    s = settings_with_size({"size": "large"})
    assert (s.size, s.height_mm, s.tab_width_mm) == ("large", 48, 50)
    s = settings_with_size({"size": "large", "height-mm": 60})  # its own height: custom
    assert (s.size, s.height_mm, s.tab_width_mm) == ("custom", 60, 50)
    s = settings_with_size({"width_mm": 30})  # regression: a width alone scales by width
    assert (s.height_mm, s.width_mm, s.size) == (None, 30, "custom")
    assert s.tab_width_mm == 25
    assert settings_with_size({"size": "large"}, sizes.calculate(30, 40)).height_mm == 60
    with pytest.raises(ValueError, match="size must be one of"):
        settings_with_size({"size": "colossal"})


def test_a_project_saves_its_table_and_every_figures_size(tmp_path):
    table = replace(sizes.calculate(30), name="My 30 mm grid")
    fig = sizes.apply(FigureSettings(label="Ogre"), "large", table)
    p = Project(sizes=table, figures=[FigureEntry(tmp_path / "a.png", fig)])
    text = save_project(p, tmp_path / "p.yaml").read_text(encoding="utf-8")
    assert "sizes:\n  preset: My 30 mm grid\n  grid_mm: 30.0\n  medium_mm: 32.0\n" in text
    assert ("  large: {height_mm: 48.0, base_mm: 59.06, tab_width_mm: 59.06, "
            "tab_height_mm: 29.53}\n") in text  # a size per line
    assert "  size: large\n" in text and "  tab_width_mm: 59.06\n" in text
    q = load_project(tmp_path / "p.yaml")
    assert q.sizes == table and q.figures[0].settings == fig
    # a figure at Medium writes its size and values too
    p = Project(figures=[FigureEntry(tmp_path / "a.png", FigureSettings())])
    text = save_project(p, tmp_path / "m.yaml").read_text(encoding="utf-8")
    assert "  size: medium\n  height_mm: 32.0\n" in text and "preset: Standard 1-inch" in text


def test_a_project_without_a_table_uses_the_builtin_one(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "figures:\n  - image: a.png\n    size: huge\n  - image: b.png\n"
        "  - image: c.png\n    size: small\n    tab_width_mm: 30\n", encoding="utf-8")
    p = load_project(tmp_path / "p.yaml")
    assert p.sizes == sizes.BUILTIN
    assert [f.settings.size for f in p.figures] == ["huge", "medium", "custom"]
    assert p.figures[0].settings.height_mm == 64
    assert (p.figures[2].settings.height_mm, p.figures[2].settings.tab_width_mm) == (24, 30)


def test_a_bad_table_names_the_file(tmp_path):
    (tmp_path / "p.yaml").write_text("sizes: {grid_mm: -1}\nfigures: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"p\.yaml: sizes grid_mm must be a number above 0"):
        load_project(tmp_path / "p.yaml")


@pytest.fixture
def disc(tmp_path):
    """A round figure (as wide as it is tall), with its own mask."""
    im = np.full((600, 600, 3), 255, np.uint8)
    cv2.circle(im, (300, 300), 250, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "d.png")
    Image.fromarray(np.where(im[..., 0] < 250, 255, 0).astype(np.uint8)).save(tmp_path / "m.png")
    return tmp_path / "d.png", tmp_path / "m.png"


def _make(disc, out, *flags):
    img, mask = disc
    assert main(["make", str(img), "--mask", str(mask), "--no-double-sided", "-o", str(out),
                 *flags]) == 0
    return read_svg(out).height_mm  # the figure, its margin and the tab below the fold


def test_cli_size_and_grid(disc, tmp_path, capsys):
    medium = _make(disc, tmp_path / "m.svg")
    large = _make(disc, tmp_path / "l.svg", "--size", "large")
    assert large - medium == pytest.approx((48 - 32) + (25 - 12.5), abs=0.3)
    capsys.readouterr()
    # a 30 mm grid: bases and heights scale with it
    grid = _make(disc, tmp_path / "g.svg", "--size", "large", "--grid-mm", "30")
    assert grid - large == pytest.approx((48 * 30 / 25.4 - 48) + (59.06 - 50) / 2, abs=0.3)
    # an explicit flag wins
    own = _make(disc, tmp_path / "o.svg", "--size", "large", "--height-mm", "40")
    assert own - large == pytest.approx(40 - 48, abs=0.3)
    assert "wider" not in capsys.readouterr().err
    # a round Tiny figure is wider than half a square
    _make(disc, tmp_path / "t.svg", "--size", "tiny")
    assert "d.png: This figure is 16 mm wide, wider than its half a square" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="--grid-mm must be above 0"):
        main(["make", str(disc[0]), "--grid-mm", "0"])
