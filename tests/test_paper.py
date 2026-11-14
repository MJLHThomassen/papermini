"""Paper sizes: named sizes and their orientation, a custom size, cutting mats, and
figures too big for the paper."""

import re

import numpy as np
import pytest
from PIL import Image

from papermini.cli import main
from papermini.geometry import CutPath
from papermini.mini import Mini
from papermini.settings import Project, SheetSettings, load_project, save_project
from papermini.sheet import (PAPER, PAPER_CHOICES, fits_mat, mat_warning, pack, paper_size,
                             paper_text, write_cut_files, write_pdf)
from papermini.svg import write_svg


def _mini(name="m", w=30.0, h=40.0) -> Mini:
    sq = CutPath(np.array([[0, 0], [w, 0], [w, h], [0, h]], float))
    return Mini(name, w, h, Image.new("RGBA", (int(w * 4), int(h * 4)), (200, 40, 30, 255)), sq)


def _media_box_mm(pdf) -> tuple:
    w, h = re.search(rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf.read_bytes()).groups()
    return round(float(w) / 72 * 25.4), round(float(h) / 72 * 25.4)


def test_paper_sizes_and_orientation():
    assert PAPER_CHOICES == ("a3", "a4", "a5", "letter", "legal", "tabloid", "custom")
    assert paper_size("a3") == (297, 420) and paper_size("a3", "landscape") == (420, 297)
    assert paper_size("tabloid") == pytest.approx((279.4, 431.8))
    assert paper_size((300, 200), "landscape") == (300, 200)  # a custom size is as given
    assert paper_text("letter") == "Letter" and paper_text("a5", "landscape") == "A5 landscape"
    assert paper_text((300, 450.5)) == "300 x 450.5 mm"
    for bad in (("a2", "portrait"), ("a4", "sideways")):
        with pytest.raises(ValueError):
            paper_size(*bad)


def test_mats_fit_either_way_round():
    assert fits_mat((210, 297), "12x12") and fits_mat((297, 210), "12x12")
    assert not fits_mat((297, 420), "12x12")
    assert fits_mat((420, 297), "12x24") and fits_mat((279.4, 431.8), "12x24")
    assert not fits_mat((310, 400), "12x24")
    assert mat_warning("a3", "portrait", None) == "" and mat_warning("a3", "portrait", "12x24") == ""
    assert mat_warning("tabloid", "landscape", "12x12") == (
        "Tabloid landscape (432 × 279 mm) is bigger than the 12 × 12 in mat "
        "(305 × 305 mm).")


def test_pack_uses_the_page_size():
    m = _mini(w=100, h=150)
    assert pack([(m, 2)], "a4").pages == 2       # (two side by side are wider than A4)
    lay = pack([(m, 2)], "a4", orientation="landscape")
    assert lay.paper == (297, 210) and lay.pages == 1 and lay.paper_name == "A4 landscape"
    lay = pack([(m, 3)], (400, 200))                               # custom: three in a row
    assert lay.paper == (400, 200) and lay.pages == 1
    with pytest.raises(ValueError, match="does not fit on A5 landscape"):
        pack([(m, 1)], "a5", orientation="landscape")
    with pytest.raises(ValueError, match="does not fit on 150 x 160 mm"):
        pack([(m, 1)], (150, 160))


def test_figures_too_big_for_the_paper_can_be_left_out():
    big, small, wide = _mini("big", 100, 250), _mini("small"), _mini("wide", 200, 40)
    lay = pack([(big, 3), (small, 2), (wide, 1)], "a4", leave_out=True)
    assert lay.too_big_names() == ["big", "wide"]                  # one entry per figure
    assert [p.mini.name for p in lay.placements] == ["small", "small"]
    assert lay.too_big_names({id(big.art): "Big dragon"}) == ["Big dragon", "wide"]
    lay = pack([(big, 1)], "a4", leave_out=True)
    assert lay.placements == [] and lay.pages == 0 and lay.too_big_names() == ["big"]
    assert pack([(small, 1)], "a4", leave_out=True).left_out == []
    # cut by machine, a piece that only the alignment marks keep off the page
    tall = _mini("tall", 210 - 24, 297 - 24 - 24)  # (the page between the margins)
    with pytest.raises(ValueError, match="between the alignment marks"):
        pack([(tall, 1)], "a4", cut="machine")
    assert pack([(tall, 1)], "a4", cut="machine", leave_out=True).too_big_names() == ["tall"]


def test_sheet_settings_paper_options(tmp_path):
    s = SheetSettings.from_dict({"paper": "a3", "orientation": "landscape"})
    assert s.page == "a3" and s.paper_text() == "A3 landscape" and s.mat_warning() == ""
    c = SheetSettings.from_dict({"paper_width_mm": 300, "paper_height_mm": 450})  # custom
    assert c.paper == "custom" and c.page == (300, 450) and c.paper_text() == "300 x 450 mm"
    m = SheetSettings.from_dict({"paper": "tabloid", "cut": "machine", "mat": "12x12"})
    assert "bigger than the 12 × 12 in mat" in m.mat_warning()
    assert SheetSettings.from_dict({"paper": "tabloid", "mat": "12x12"}).mat_warning() == ""
    for bad, match in (({"paper": "a2"}, "paper must be"),
                       ({"orientation": "sideways"}, "orientation must be"),
                       ({"mat": "10x10"}, "mat must be"),
                       ({"paper": "custom"}, "paper_width_mm must be from 50 to 1200"),
                       ({"paper_width_mm": 300, "paper_height_mm": 20}, "paper_height_mm"),
                       ({"paper": "a4", "paper_width_mm": 300}, "only for paper: custom")):
        with pytest.raises(ValueError, match=match):
            SheetSettings.from_dict(bad)
    # saved and opened again; the defaults are not written
    for sheet, written in ((c, {"paper": "custom", "paper_width_mm": 300,
                                "paper_height_mm": 450}),
                           (m, {"paper": "tabloid", "cut": "machine", "mat": "12x12"}),
                           (SheetSettings(), None)):
        path = save_project(Project(tmp_path / "p.yaml", "minis", sheet, []), tmp_path / "p.yaml")
        assert load_project(path).sheet == sheet
        import yaml

        assert yaml.safe_load(path.read_text(encoding="utf-8")).get("sheet") == written


def test_cli_paper(tmp_path, capsys):
    svg = write_svg(_mini("goblin", 60, 90), tmp_path / "goblin.svg")
    for args, size, name in ((["--paper", "a3", "--orientation", "landscape"], (420, 297),
                              "A3 landscape"),
                             (["--paper-width-mm", "300", "--paper-height-mm", "200"],
                              (300, 200), "300 x 200 mm"),
                             (["--paper", "legal"], (216, 356), "Legal"),
                             ([], (210, 297), "A4")):
        out = tmp_path / "s.pdf"
        assert main(["sheet", str(svg), "-o", str(out)] + args) == 0
        assert _media_box_mm(out) == size
        assert f"1 page, {name})" in capsys.readouterr().out
    # a mat smaller than the paper: a note, and the sheet is still made
    assert main(["sheet", str(svg), "-o", str(tmp_path / "m.pdf"), "--paper", "tabloid",
                 "--cut", "machine", "--mat", "12x12"]) == 0
    assert "note: Tabloid (279 × 432 mm) is bigger than the 12 × 12 in mat" in \
        capsys.readouterr().out
    for args, match in ((["--paper", "a4", "--paper-width-mm", "300"], "leave out --paper a4"),
                        (["--paper", "custom", "--paper-width-mm", "30",
                          "--paper-height-mm", "300"], "--paper-width-mm must be from 50")):
        with pytest.raises(SystemExit, match=match):
            main(["sheet", str(svg), "-o", str(tmp_path / "x.pdf")] + args)


def test_marks_and_cut_files_follow_the_page(tmp_path):
    lay = pack([(_mini(), 1)], "a3", cut="machine", orientation="landscape")
    rects = lay.mark_rects()
    assert max(x + w for x, y, w, h in rects) == pytest.approx(420 - 12)
    assert max(y + h for x, y, w, h in rects) == pytest.approx(297 - 12)
    cut = write_cut_files(lay, tmp_path / "s-cut.svg")[0].read_text(encoding="utf-8")
    assert 'width="420mm"' in cut and 'height="297mm"' in cut
    assert _media_box_mm(write_pdf(lay, tmp_path / "s.pdf")) == (420, 297)
