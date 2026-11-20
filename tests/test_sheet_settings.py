"""Tests of the sheet settings and their checks."""

import pytest

from papermini.project.project import Project
from papermini.project.sheet_settings import SheetSettings


def test_the_paper_options_are_checked_and_saved(tmp_path, project_store):
    s = SheetSettings.from_dict({"paper": "a3", "orientation": "landscape"})
    assert s.page == "a3" and s.paper_text() == "A3 landscape" and s.mat_warning() == ""
    c = SheetSettings.from_dict(
        {"paper_width_mm": 300, "paper_height_mm": 450}
    )  # custom
    assert (
        c.paper == "custom"
        and c.page == (300, 450)
        and c.paper_text() == "300 x 450 mm"
    )
    m = SheetSettings.from_dict({"paper": "tabloid", "cut": "machine", "mat": "12x12"})
    assert "bigger than the 12 × 12 in mat" in m.mat_warning()
    assert (
        SheetSettings.from_dict({"paper": "tabloid", "mat": "12x12"}).mat_warning()
        == ""
    )
    for bad, match in (
        ({"paper": "a2"}, "paper must be"),
        ({"orientation": "sideways"}, "orientation must be"),
        ({"mat": "10x10"}, "mat must be"),
        ({"paper": "custom"}, "paper_width_mm must be from 50 to 1200"),
        ({"paper_width_mm": 300, "paper_height_mm": 20}, "paper_height_mm"),
        ({"paper": "a4", "paper_width_mm": 300}, "only for paper: custom"),
    ):
        with pytest.raises(ValueError, match=match):
            SheetSettings.from_dict(bad)
    # saved and opened again; the defaults are not written
    for sheet, written in (
        (c, {"paper": "custom", "paper_width_mm": 300, "paper_height_mm": 450}),
        (m, {"paper": "tabloid", "cut": "machine", "mat": "12x12"}),
        (SheetSettings(), None),
    ):
        path = project_store.save(
            Project(tmp_path / "p.yaml", "minis", sheet, []), tmp_path / "p.yaml"
        )
        assert project_store.load(path).sheet == sheet
        import yaml

        assert yaml.safe_load(path.read_text(encoding="utf-8")).get("sheet") == written


def test_the_machine_cut_options_are_checked():
    from papermini.project.sheet_settings import SheetSettings

    assert SheetSettings().figure_bleed == 0.0  # cut by hand: no bleed
    s = SheetSettings.from_dict(
        {"cut": "machine", "bleed-mm": 1.5, "marks": "silhouette"}
    )
    assert s.machine and s.figure_bleed == 1.5 and s.marks == "silhouette"
    for bad, match in (
        ({"cut": "laser"}, "cut must be"),
        ({"marks": "dots"}, "marks must be"),
        ({"bleed_mm": 9}, "bleed_mm"),
        ({"paper": "a2"}, "paper must be"),
        ({"cutter": True}, "unknown sheet option"),
    ):
        with pytest.raises(ValueError, match=match):
            SheetSettings.from_dict(bad)


def test_the_layout_packs_with_the_sheets_settings(square_mini):
    """The layout uses the sheet's paper, orientation, margin, gap and cut."""
    from papermini.output.sheet import pack

    minis = [(square_mini("a"), 3), (square_mini("b", 60, 80), 1)]
    sheet = SheetSettings(
        paper="a5", orientation="landscape", margin_mm=8, gap_mm=4, cut="machine"
    )
    lay = sheet.layout(minis)
    same = pack(minis, "a5", 8, 4, cut="machine", orientation="landscape")
    assert (lay.paper, lay.margin_mm, lay.cut, lay.marks) == (
        (210.0, 148.0),
        8,
        "machine",
        "corners",
    )
    assert [(p.x, p.y, p.page) for p in lay.placements] == [
        (p.x, p.y, p.page) for p in same.placements
    ]


def test_the_layout_leaves_off_a_piece_too_big_for_the_paper(square_mini):
    big = square_mini("big", 100, 300)
    sheet = SheetSettings(paper="a5")
    with pytest.raises(ValueError):
        sheet.layout([(big, 1)])
    lay = sheet.layout([(big, 1), (square_mini("small"), 1)], leave_out=True)
    assert [m.name for m in lay.left_out] == ["big"] and len(lay.placements) == 1
