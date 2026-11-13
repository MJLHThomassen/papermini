"""Shared settings and project (batch YAML) round-trip."""

from pathlib import Path

import pytest

from papermini import __version__, sizes
from papermini.settings import (FigureEntry, FigureSettings, Project, SheetSettings,
                                load_project, save_project)


def test_from_dict_accepts_dashes_and_rejects_unknown():
    s = FigureSettings.from_dict({"height-mm": 30, "strength": 60})
    assert s.height_mm == 30 and s.strength == 60
    with pytest.raises(ValueError, match="unknown"):
        FigureSettings.from_dict({"heigth_mm": 30})


def test_to_dict_only_non_defaults():
    """Only options not at their default, but always the creature size and the values
    it fills in (left out with ``with_size=False``, as the log does)."""
    medium = {"size": "medium", "height_mm": 32.0, "tab_radius_mm": 12.5,
              "tab_width_mm": 25.0, "tab_height_mm": 12.5}
    assert FigureSettings().to_dict() == medium
    assert FigureSettings().to_dict(with_size=False) == {}
    assert FigureSettings(label="X", crop=[0, 0, 1, 0.5]).to_dict(with_size=False) == {
        "label": "X", "crop": [0, 0, 1, 0.5]}
    assert FigureSettings(label="X").to_dict() == {**medium, "label": "X"}


def test_sheet_settings_cut_by_machine():
    from papermini.settings import SheetSettings

    assert SheetSettings().figure_bleed == 0.0  # cut by hand: no bleed
    s = SheetSettings.from_dict({"cut": "machine", "bleed-mm": 1.5, "marks": "silhouette"})
    assert s.machine and s.figure_bleed == 1.5 and s.marks == "silhouette"
    for bad, match in (({"cut": "laser"}, "cut must be"), ({"marks": "dots"}, "marks must be"),
                       ({"bleed_mm": 9}, "bleed_mm"), ({"paper": "a3"}, "paper must be"),
                       ({"cutter": True}, "unknown sheet option")):
        with pytest.raises(ValueError, match=match):
            SheetSettings.from_dict(bad)


def test_project_roundtrip(tmp_path):
    (tmp_path / "img").mkdir()
    a, b = tmp_path / "img" / "a.png", tmp_path / "img" / "b.png"
    p = Project(
        output="out",
        sheet=SheetSettings(paper="letter", title="Crypt"),
        figures=[
            FigureEntry(a, FigureSettings(label="Red dragon", copies=2)),
            FigureEntry(b, FigureSettings(size="custom", height_mm=56,
                                          crop=[0.08, 0, 0.92, 0.62], double_sided=True),
                        name="boss"),
        ],
    )
    path = save_project(p, tmp_path / "proj.yaml")
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f"papermini: {__version__}\nformat: 1\n")
    assert "img/a.png" in text and str(tmp_path) not in text  # relative paths
    q = load_project(path)
    assert q.output == "out" and q.sheet.paper == "letter" and q.sheet.title == "Crypt"
    assert [f.image for f in q.figures] == [a.resolve(), b.resolve()]
    assert q.figures[0].settings == p.figures[0].settings
    assert q.figures[1].settings == p.figures[1].settings
    assert q.figures[1].name == "boss" and q.figures[1].svg_name() == "boss.svg"


def test_frozen_1_0_project():
    path = Path(__file__).parent / "fixtures" / "project-v1.0.yaml"
    p = load_project(path)
    assert p.output == "finished"
    assert p.sheet == SheetSettings(output="finished/print.pdf", paper="letter",
                                    copies=2, title="Dragon collection")
    assert [f.image for f in p.figures] == [
        p.base / "images/dragon.png", p.base / "images/knight.png"]
    # (no sizes: the built-in table; its own heights make each figure custom)
    assert p.sizes == sizes.BUILTIN
    assert [f.settings for f in p.figures] == [
        FigureSettings(size="custom", height_mm=45, strength=55, label="Red dragon",
                       copies=3),
        FigureSettings(size="custom", height_mm=38, strength=55, double_sided=False,
                       copies=2),
    ]
    assert p.figures[1].name == "blue-knight"


def test_project_format_defaults_to_one_and_rejects_newer(tmp_path):
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text("figures: [dragon.png]\n", encoding="utf-8")
    assert load_project(legacy).figures[0].image == tmp_path / "dragon.png"

    newer = tmp_path / "newer.yaml"
    newer.write_text("papermini: 2.1.0\nformat: 2\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_project(newer)
    assert str(e.value) == (f"newer.yaml was made by papermini 2.1.0 (project format 2), and "
                            f"papermini {__version__} opens project format 1. Update papermini "
                            "to open it.")

    hand_written = tmp_path / "hand.yaml"
    hand_written.write_text("format: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^hand.yaml uses a newer project format \(project format 2\)"):
        load_project(hand_written)

    for bad in ("x", "true", "0"):
        (tmp_path / "bad.yaml").write_text(f"format: {bad}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="project format must be a whole number from 1"):
            load_project(tmp_path / "bad.yaml")


def test_errors_in_a_project_from_a_newer_papermini_say_so(tmp_path):
    """A newer papermini of the same format may save options this one does not know: the
    error then names the papermini that saved the project."""
    (tmp_path / "p.yaml").write_text(
        "papermini: 99.1.0\nformat: 1\nfigures:\n  - {image: a.png, sparkle: true}\n",
        encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_project(tmp_path / "p.yaml")
    assert str(e.value) == (f"p.yaml: a.png: unknown option(s) sparkle. The project was made by "
                            f"papermini 99.1.0, which is newer than papermini {__version__}. "
                            "Update papermini to open it.")
    # the same mistake in a project from an older papermini is just the error
    (tmp_path / "p.yaml").write_text(
        "papermini: 0.1.0\nformat: 1\nfigures:\n  - {image: a.png, sparkle: true}\n",
        encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_project(tmp_path / "p.yaml")
    assert str(e.value) == "p.yaml: a.png: unknown option(s) sparkle"


def test_sheet_copies_are_the_default_for_figures(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "sheet: {copies: 3}\nfigures:\n  - a.png\n  - {image: b.png, copies: 1}\n",
        encoding="utf-8")
    q = load_project(tmp_path / "p.yaml")
    assert [f.settings.copies for f in q.figures] == [3, 1]


def test_minis_are_double_sided_by_default():
    assert FigureSettings().double_sided and FigureSettings().params().double_sided
    s = FigureSettings.from_dict({"double_sided": False})
    assert not s.params().double_sided
    assert s.to_dict(with_size=False) == {"double_sided": False}


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


def test_size_by_height_width_or_both(tmp_path):
    """A width alone scales by width; both stretch; the choice survives a save."""
    assert FigureSettings.from_dict({"width_mm": 30}).height_mm is None
    both = FigureSettings.from_dict({"width_mm": 30, "height_mm": 50})
    assert (both.height_mm, both.width_mm) == (50, 30)
    for bad in ({"height_mm": None}, {"height_mm": 0}, {"width_mm": -3}, {"width_mm": "wide"}):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)
    # stretched to the default height: the height is saved too, or reloading the
    # file would read "width alone"
    stretched = FigureSettings(size="custom", width_mm=30)
    assert stretched.to_dict(with_size=False) == {"size": "custom", "width_mm": 30,
                                                  "height_mm": 32.0}
    by_width = FigureSettings(size="custom", height_mm=None, width_mm=30)
    p = Project(figures=[FigureEntry(tmp_path / "a.png", stretched),
                         FigureEntry(tmp_path / "b.png", by_width)])
    loaded = load_project(save_project(p, tmp_path / "p.yaml"))
    assert [f.settings for f in loaded.figures] == [stretched, by_width]
