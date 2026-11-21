"""Tests of packing the pieces onto the pages of a sheet."""

import pytest


def test_pack_uses_the_page_size(output, square_mini):
    m = square_mini(w=100, h=150)
    assert (
        output.packer.pack([(m, 2)], "a4").pages == 2
    )  # (two side by side are wider than A4)
    lay = output.packer.pack([(m, 2)], "a4", orientation="landscape")
    assert (
        lay.paper == (297, 210) and lay.pages == 1 and lay.paper_name == "A4 landscape"
    )
    lay = output.packer.pack([(m, 3)], (400, 200))  # custom: three in a row
    assert lay.paper == (400, 200) and lay.pages == 1
    with pytest.raises(ValueError, match="does not fit on A5 landscape"):
        output.packer.pack([(m, 1)], "a5", orientation="landscape")
    with pytest.raises(ValueError, match="does not fit on 150 x 160 mm"):
        output.packer.pack([(m, 1)], (150, 160))


def test_figures_too_big_for_the_paper_can_be_left_out(output, square_mini):
    big, small, wide = (
        square_mini("big", 100, 250),
        square_mini("small"),
        square_mini("wide", 200, 40),
    )
    lay = output.packer.pack([(big, 3), (small, 2), (wide, 1)], "a4", leave_out=True)
    assert lay.too_big_names() == ["big", "wide"]  # one entry per figure
    assert [p.mini.name for p in lay.placements] == ["small", "small"]
    assert lay.too_big_names({id(big.art): "Big dragon"}) == ["Big dragon", "wide"]
    lay = output.packer.pack([(big, 1)], "a4", leave_out=True)
    assert lay.placements == [] and lay.pages == 0 and lay.too_big_names() == ["big"]
    assert output.packer.pack([(small, 1)], "a4", leave_out=True).left_out == []
    # cut by machine, a piece that only the alignment marks keep off the page
    # (the page between the margins)
    tall = square_mini("tall", 210 - 24, 297 - 24 - 24)
    with pytest.raises(ValueError, match="between the alignment marks"):
        output.packer.pack([(tall, 1)], "a4", cut="machine")
    assert output.packer.pack(
        [(tall, 1)], "a4", cut="machine", leave_out=True
    ).too_big_names() == ["tall"]


def test_pack_keeps_the_pieces_inside_the_margins_without_overlap(
    output, hero_figure, tmp_path, pipeline_mini, params, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, params(height_mm=60), mask_options(mask_path=mask))
    lay = output.packer.pack([(m, 9)], "a4")
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
    out = output.pdf.write(lay, tmp_path / "s.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pack_refuses_a_figure_too_big_for_the_paper(
    output, hero_figure, pipeline_mini, params, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, params(height_mm=300), mask_options(mask_path=mask))
    with pytest.raises(ValueError, match="does not fit"):
        output.packer.pack([(m, 1)], "a4")


def test_machine_sheet_keeps_clear_of_the_marks(output, square_mini):
    """The pieces keep MARK_CLEAR_MM away from the corner marks only, so a machine sheet
    holds as many pieces as one cut by hand; the header starts beside the marks."""
    from papermini.output.sheet_packer import MARK_CLEAR_MM

    m = square_mini(folds=[(0.0, 30.0, 35.0)])
    hand = output.packer.pack([(m, 40)], "a4", 12, 7)
    assert hand.mark_rects() == [] and hand.header_x == 12
    for kind in ("corners", "silhouette"):
        lay = output.packer.pack([(m, 40)], "a4", 12, 7, cut="machine", marks=kind)
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
    none = output.packer.pack([(m, 40)], "a4", 12, 7, cut="machine", marks="none")
    assert none.mark_rects() == [] and none.header_x == 12 and none.machine
    assert [p.page for p in none.placements] == [p.page for p in hand.placements]
    assert "edges of this page" not in none.instructions()[1]  # (its own wording)
    assert "with this page" in none.instructions()[1]
    with pytest.raises(ValueError, match="marks must be"):
        output.packer.pack([(m, 1)], "a4", cut="machine", marks="dots")
    with pytest.raises(ValueError, match="cut must be"):
        output.packer.pack([(m, 1)], "a4", cut="laser")


def test_the_sheet_numbers_the_copies(output, goblin_figure, tmp_path, numbered_mini):
    a = numbered_mini(goblin_figure, tab_front="number")
    b = numbered_mini(goblin_figure, back="number")
    plain = numbered_mini(goblin_figure)
    lay = output.packer.pack([(a, 3), (b, 2), (plain, 2)])
    by_art = {}
    for p in lay.placements:
        by_art.setdefault(id(p.mini.art), []).append(p.mini.number)
    assert sorted(by_art[id(a.art)]) == [1, 2, 3]
    assert sorted(by_art[id(b.art)]) == [1, 2]
    assert by_art[id(plain.art)] == [None, None]
    assert a.number is None  # (the copies are new minis; the figure keeps no number)
    assert output.pdf.write(lay, tmp_path / "s.pdf").read_bytes()[:5] == b"%PDF-"
    assert output.previews.write(lay, tmp_path / "s.pdf")
