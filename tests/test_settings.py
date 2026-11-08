"""Shared settings and project (batch YAML) round-trip."""

import pytest

from papermini.settings import (FigureEntry, FigureSettings, Project, SheetSettings,
                                load_project, save_project)


def test_from_dict_accepts_dashes_and_rejects_unknown():
    s = FigureSettings.from_dict({"height-mm": 30, "strength": 60})
    assert s.height_mm == 30 and s.strength == 60
    with pytest.raises(ValueError, match="unknown"):
        FigureSettings.from_dict({"heigth_mm": 30})


def test_to_dict_only_non_defaults():
    assert FigureSettings().to_dict() == {}
    assert FigureSettings(label="X", crop=[0, 0, 1, 0.5]).to_dict() == {
        "label": "X", "crop": [0, 0, 1, 0.5]}


def test_cutter_style():
    st = FigureSettings(cutter=True).style()
    assert st.cut_color == "#ff0000" and st.cut_width_mm == 0.1


def test_project_roundtrip(tmp_path):
    (tmp_path / "img").mkdir()
    a, b = tmp_path / "img" / "a.png", tmp_path / "img" / "b.png"
    p = Project(
        output="out",
        sheet=SheetSettings(paper="letter", title="Crypt"),
        figures=[
            FigureEntry(a, FigureSettings(label="Lotje", copies=2)),
            FigureEntry(b, FigureSettings(height_mm=56, crop=[0.08, 0, 0.92, 0.62],
                                          double_sided=True), name="boss"),
        ],
    )
    path = save_project(p, tmp_path / "proj.yaml")
    text = path.read_text(encoding="utf-8")
    assert "img/a.png" in text and str(tmp_path) not in text  # relative paths
    q = load_project(path)
    assert q.output == "out" and q.sheet.paper == "letter" and q.sheet.title == "Crypt"
    assert [f.image for f in q.figures] == [a.resolve(), b.resolve()]
    assert q.figures[0].settings == p.figures[0].settings
    assert q.figures[1].settings == p.figures[1].settings
    assert q.figures[1].name == "boss" and q.figures[1].svg_name() == "boss.svg"


def test_sheet_copies_are_the_default_for_figures(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "sheet: {copies: 3}\nfigures:\n  - a.png\n  - {image: b.png, copies: 1}\n",
        encoding="utf-8")
    q = load_project(tmp_path / "p.yaml")
    assert [f.settings.copies for f in q.figures] == [3, 1]


def test_back_option_validated():
    assert FigureSettings.from_dict({"double_sided": True, "back": "blank"}).params().back == "blank"
    with pytest.raises(ValueError, match="back must be"):
        FigureSettings.from_dict({"back": "photo"})



def test_tab_and_margin_options():
    p = FigureSettings.from_dict({"tab_shape": "round", "tab_color": "#123456",
                                  "margin_fill": "image"}).params()
    assert (p.tab_shape, p.tab_color, p.margin_fill) == ("round", "#123456", "image")
    for bad in ({"tab_shape": "oval"}, {"margin_fill": "white"}, {"tab_fill": "color"},
                {"tab_color": "green-ish"}):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)
