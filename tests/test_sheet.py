"""Tests of the print sheet: the paper, the packing, the PDF and the cut files."""

import numpy as np
import pytest

from papermini.output.sheet import (
    PAPER_CHOICES,
    fits_mat,
    mat_warning,
    pack,
    paper_size,
    paper_text,
    write_cut_files,
    write_pdf,
    write_previews,
)
from papermini.output.svg import read_svg, write_svg
from papermini.project.figure_settings import FigureSettings
from papermini.project.settings import build_mini


def test_paper_sizes_turn_and_name_themselves():
    assert PAPER_CHOICES == ("a3", "a4", "a5", "letter", "legal", "tabloid", "custom")
    assert paper_size("a3") == (297, 420) and paper_size("a3", "landscape") == (
        420,
        297,
    )
    assert paper_size("tabloid") == pytest.approx((279.4, 431.8))
    assert paper_size((300, 200), "landscape") == (
        300,
        200,
    )  # a custom size is as given
    assert (
        paper_text("letter") == "Letter"
        and paper_text("a5", "landscape") == "A5 landscape"
    )
    assert paper_text((300, 450.5)) == "300 x 450.5 mm"
    for bad in (("a2", "portrait"), ("a4", "sideways")):
        with pytest.raises(ValueError):
            paper_size(*bad)


def test_mats_fit_either_way_round():
    assert fits_mat((210, 297), "12x12") and fits_mat((297, 210), "12x12")
    assert not fits_mat((297, 420), "12x12")
    assert fits_mat((420, 297), "12x24") and fits_mat((279.4, 431.8), "12x24")
    assert not fits_mat((310, 400), "12x24")
    assert (
        mat_warning("a3", "portrait", None) == ""
        and mat_warning("a3", "portrait", "12x24") == ""
    )
    assert mat_warning("tabloid", "landscape", "12x12") == (
        "Tabloid landscape (432 × 279 mm) is bigger than the 12 × 12 in mat "
        "(305 × 305 mm)."
    )


def test_pack_uses_the_page_size(square_mini):
    m = square_mini(w=100, h=150)
    assert pack([(m, 2)], "a4").pages == 2  # (two side by side are wider than A4)
    lay = pack([(m, 2)], "a4", orientation="landscape")
    assert (
        lay.paper == (297, 210) and lay.pages == 1 and lay.paper_name == "A4 landscape"
    )
    lay = pack([(m, 3)], (400, 200))  # custom: three in a row
    assert lay.paper == (400, 200) and lay.pages == 1
    with pytest.raises(ValueError, match="does not fit on A5 landscape"):
        pack([(m, 1)], "a5", orientation="landscape")
    with pytest.raises(ValueError, match="does not fit on 150 x 160 mm"):
        pack([(m, 1)], (150, 160))


def test_figures_too_big_for_the_paper_can_be_left_out(square_mini):
    big, small, wide = (
        square_mini("big", 100, 250),
        square_mini("small"),
        square_mini("wide", 200, 40),
    )
    lay = pack([(big, 3), (small, 2), (wide, 1)], "a4", leave_out=True)
    assert lay.too_big_names() == ["big", "wide"]  # one entry per figure
    assert [p.mini.name for p in lay.placements] == ["small", "small"]
    assert lay.too_big_names({id(big.art): "Big dragon"}) == ["Big dragon", "wide"]
    lay = pack([(big, 1)], "a4", leave_out=True)
    assert lay.placements == [] and lay.pages == 0 and lay.too_big_names() == ["big"]
    assert pack([(small, 1)], "a4", leave_out=True).left_out == []
    # cut by machine, a piece that only the alignment marks keep off the page
    # (the page between the margins)
    tall = square_mini("tall", 210 - 24, 297 - 24 - 24)
    with pytest.raises(ValueError, match="between the alignment marks"):
        pack([(tall, 1)], "a4", cut="machine")
    assert pack([(tall, 1)], "a4", cut="machine", leave_out=True).too_big_names() == [
        "tall"
    ]


def test_marks_and_cut_files_follow_the_page(tmp_path, square_mini, media_box_mm):
    lay = pack([(square_mini("m"), 1)], "a3", cut="machine", orientation="landscape")
    rects = lay.mark_rects()
    assert max(x + w for x, y, w, h in rects) == pytest.approx(420 - 12)
    assert max(y + h for x, y, w, h in rects) == pytest.approx(297 - 12)
    cut = write_cut_files(lay, tmp_path / "s-cut.svg")[0].read_text(encoding="utf-8")
    assert 'width="420mm"' in cut and 'height="297mm"' in cut
    assert media_box_mm(write_pdf(lay, tmp_path / "s.pdf")) == (420, 297)


def test_pack_keeps_the_pieces_inside_the_margins_without_overlap(
    hero_figure, tmp_path, pipeline_mini, params, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, params(height_mm=60), mask_options(mask_path=mask))
    lay = pack([(m, 9)], "a4")
    assert len(lay.placements) == 9
    for p in lay.placements:
        assert 12 <= p.x and p.x + m.width_mm <= 210 - 12 + 1e-9
        assert p.y + m.height_mm <= 297 - 12 + 1e-9
    same_page = [p for p in lay.placements if p.page == 0]
    for a in same_page:
        for b in same_page:
            if a is not b:
                overlap_x = a.x < b.x + m.width_mm and b.x < a.x + m.width_mm
                overlap_y = a.y < b.y + m.height_mm and b.y < a.y + m.height_mm
                assert not (overlap_x and overlap_y)
    out = write_pdf(lay, tmp_path / "s.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pack_refuses_a_figure_too_big_for_the_paper(
    hero_figure, pipeline_mini, params, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, params(height_mm=300), mask_options(mask_path=mask))
    with pytest.raises(ValueError, match="does not fit"):
        pack([(m, 1)], "a4")


def test_machine_sheet_keeps_clear_of_the_marks(square_mini):
    """The pieces keep MARK_CLEAR_MM away from the corner marks only, so a machine sheet
    holds as many pieces as one cut by hand; the header starts beside the marks."""
    from papermini.output.sheet import MARK_CLEAR_MM

    m = square_mini(folds=[(0.0, 30.0, 35.0)])
    hand = pack([(m, 40)], "a4", 12, 7)
    assert hand.mark_rects() == [] and hand.header_x == 12
    for kind in ("corners", "silhouette"):
        lay = pack([(m, 40)], "a4", 12, 7, cut="machine", marks=kind)
        rects = lay.mark_rects()
        # the marks sit 12 mm from the paper edges, inside the paper
        assert min(x for x, *_ in rects) == pytest.approx(12)
        assert max(x + w for x, _, w, _ in rects) == pytest.approx(210 - 12)
        assert max(y + h for _, y, _, h in rects) == pytest.approx(297 - 12)
        c = MARK_CLEAR_MM
        for p in lay.placements:  # no piece within MARK_CLEAR_MM of a mark
            for x, y, w, h in rects:
                apart = (
                    p.x + m.width_mm <= x - c + 1e-9
                    or p.x >= x + w + c - 1e-9
                    or p.y + m.height_mm <= y - c + 1e-9
                    or p.y >= y + h + c - 1e-9
                )
                assert apart, (kind, p.x, p.y, (x, y, w, h))
        assert lay.header_x > 12  # beside the top-left mark
        # about as many on a page as cut by hand: only the bottom corners cost room
        first = sum(p.page == 0 for p in lay.placements)
        assert first >= sum(p.page == 0 for p in hand.placements) - 2
    none = pack([(m, 40)], "a4", 12, 7, cut="machine", marks="none")
    assert none.mark_rects() == [] and none.header_x == 12 and none.machine
    assert [p.page for p in none.placements] == [p.page for p in hand.placements]
    assert "edges of this page" not in none.instructions()[1]  # (its own wording)
    assert "with this page" in none.instructions()[1]
    with pytest.raises(ValueError, match="marks must be"):
        pack([(m, 1)], "a4", cut="machine", marks="dots")
    with pytest.raises(ValueError, match="cut must be"):
        pack([(m, 1)], "a4", cut="laser")


def test_cut_files_match_the_sheet(tmp_path, square_mini):
    """Cut by machine: the PDF gets no cut lines, and a cut file per page holds the cut
    lines where the pieces are on the page plus the same marks as the PDF."""
    import re
    import xml.etree.ElementTree as ET

    from papermini.output.sheet import cut_file_paths, default_cut_file, write_cut_files

    m = square_mini(folds=[(0.0, 30.0, 35.0)])
    lay = pack([(m, 30)], "a4", 12, 7, cut="machine", marks="corners")
    assert lay.pages > 1 and lay.machine
    pdf = write_pdf(lay, tmp_path / "s.pdf")
    assert pdf.read_bytes()[:5] == b"%PDF-"
    paths = write_cut_files(lay, default_cut_file(pdf))
    assert paths == cut_file_paths(tmp_path / "s-cut.svg", lay.pages)
    assert [p.name for p in paths[:2]] == ["s-cut.svg", "s-cut-2.svg"]
    ns = {"s": "http://www.w3.org/2000/svg"}
    root = ET.parse(paths[0]).getroot()
    assert root.get("width") == "210mm" and root.get("viewBox") == "0 0 210 297"
    rects = [
        tuple(float(r.get(k)) for k in ("x", "y", "width", "height"))
        for r in root.findall("s:g[@id='registration']/s:rect", ns)
    ]
    assert np.allclose(rects, lay.mark_rects(), atol=1e-3)  # the same marks as the PDF
    cuts = root.findall("s:g[@id='cut']/s:path", ns)
    first = [p for p in lay.placements if p.page == 0]
    assert len(cuts) == len(first)
    xy = [float(v) for v in re.findall(r"[-\d.]+", cuts[0].get("d"))[:2]]
    assert xy == pytest.approx(
        [first[0].x, first[0].y], abs=1e-3
    )  # placed as on the page
    assert root.find("s:g[@id='fold']", ns) is None  # fold lines only when asked for
    folded = ET.fromstring(
        write_cut_files(lay, tmp_path / "f.svg", folds=True)[0].read_text()
    )
    assert len(folded.findall("s:g[@id='fold']/s:line", ns)) == len(first)


def test_the_sheet_numbers_the_copies(goblin_figure, tmp_path, numbered_mini):
    a = numbered_mini(goblin_figure, tab_front="number")
    b = numbered_mini(goblin_figure, back="number")
    plain = numbered_mini(goblin_figure)
    lay = pack([(a, 3), (b, 2), (plain, 2)])
    by_art = {}
    for p in lay.placements:
        by_art.setdefault(id(p.mini.art), []).append(p.mini.number)
    assert sorted(by_art[id(a.art)]) == [1, 2, 3]
    assert sorted(by_art[id(b.art)]) == [1, 2]
    assert by_art[id(plain.art)] == [None, None]
    assert a.number is None  # (the copies are new minis; the figure keeps no number)
    assert write_pdf(lay, tmp_path / "s.pdf").read_bytes()[:5] == b"%PDF-"
    assert write_previews(lay, tmp_path / "s.pdf")


def test_the_pdf_embeds_the_font_and_the_svg_names_it(goblin_figure, tmp_path):
    img, mask = goblin_figure
    s = FigureSettings(
        mask=str(mask), label="Hero", font="Almendra", back="text_number"
    )
    m = build_mini(img, s, log=lambda *_: None)
    assert m.style.font == "Almendra"
    pdf = write_pdf(pack([(m, 2)]), tmp_path / "s.pdf").read_bytes()
    assert b"Almendra-Regular" in pdf and b"Almendra-Bold" in pdf  # (numbers are bold)
    svg = write_svg(m, tmp_path / "hero.svg").read_text(encoding="utf-8")
    assert "font-family=\"'Almendra', serif\"" in svg
    assert 'class="number"' in svg and 'font-weight="bold"' in svg
    assert read_svg(tmp_path / "hero.svg").style.font == "Almendra"
    # Times: the names every program knows
    t = write_svg(
        build_mini(
            img, FigureSettings(mask=str(mask), label="Hero"), log=lambda *_: None
        ),
        tmp_path / "t.svg",
    )
    assert 'font-family="Times New Roman, Times, serif"' in t.read_text(
        encoding="utf-8"
    )
    assert read_svg(t).style.font == "Times"
