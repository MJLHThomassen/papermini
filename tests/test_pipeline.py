"""End-to-end tests with a supplied mask (no model download)."""

import numpy as np
import cv2
import pytest
from PIL import Image

from papermini import geometry as geo
from papermini.cli import main
from papermini.mini import make_mini
from papermini.sheet import pack, write_pdf
from papermini.svg import read_svg, write_svg


@pytest.fixture
def figure(tmp_path):
    """A dark figure on white, exactly 700 px high, plus its mask."""
    im = np.full((1000, 800, 3), 255, np.uint8)
    cv2.ellipse(im, (400, 300), (150, 120), 0, 0, 360, (40, 40, 40), -1)
    cv2.rectangle(im, (300, 300), (500, 899), (40, 40, 40), -1)   # rows 180..899 -> 720 px
    mask = np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(mask).save(tmp_path / "hero_mask.png")
    return tmp_path / "hero.png", tmp_path / "hero_mask.png"


def _dark_rows_mm(mini):
    a = np.asarray(mini.art.convert("RGBA"))
    dark = (a[..., 3] > 0) & (a[..., :3].max(-1) < 128)
    rows = np.flatnonzero(dark.any(1))
    return (rows.max() - rows.min() + 1) * mini.height_mm / a.shape[0]


@pytest.mark.parametrize("height", [30.0, 42.0])
def test_printed_figure_height(figure, height):
    img, mask = figure
    m = make_mini(img, geo.Params(height_mm=height), mask_path=mask, log=lambda *_: None)
    assert _dark_rows_mm(m) == pytest.approx(height, abs=0.5)


def test_svg_roundtrip(figure, tmp_path):
    img, mask = figure
    m = make_mini(img, geo.Params(), mask_path=mask, label="Hero", log=lambda *_: None)
    p = write_svg(m, tmp_path / "hero.svg")
    r = read_svg(p)
    assert r.width_mm == pytest.approx(m.width_mm, abs=1e-3)
    assert r.height_mm == pytest.approx(m.height_mm, abs=1e-3)
    assert r.label == "Hero"
    assert np.allclose(r.cut.points, m.cut.points, atol=1e-3)
    assert np.allclose(r.cut.controls, m.cut.controls, atol=1e-3)
    assert np.allclose(r.folds, m.folds, atol=1e-3)
    assert np.allclose(r.labels, m.labels, atol=1e-3)
    assert r.art.size == m.art.size


def test_polygon_roundtrip(figure, tmp_path):
    img, mask = figure
    m = make_mini(img, geo.Params(), mask_path=mask, smooth_path=False, log=lambda *_: None)
    r = read_svg(write_svg(m, tmp_path / "hero.svg"))
    assert r.cut.controls is None
    assert np.allclose(r.cut.points, m.cut.points, atol=1e-3)


def test_sheet_packing_and_pdf(figure, tmp_path):
    img, mask = figure
    m = make_mini(img, geo.Params(height_mm=60), mask_path=mask, log=lambda *_: None)
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


def test_too_big_for_paper(figure):
    img, mask = figure
    m = make_mini(img, geo.Params(height_mm=300), mask_path=mask, log=lambda *_: None)
    with pytest.raises(ValueError, match="does not fit"):
        pack([(m, 1)], "a4")


def test_alpha_png_needs_no_model(tmp_path):
    a = np.zeros((600, 400, 4), np.uint8)
    cv2.circle(a, (200, 300), 150, (90, 60, 30, 255), -1)
    Image.fromarray(a, "RGBA").save(tmp_path / "cut.png")
    m = make_mini(tmp_path / "cut.png", geo.Params(height_mm=20, tab=False), log=lambda *_: None)
    assert _dark_rows_mm(m) == pytest.approx(20, abs=0.5)


def test_batch_cli(figure, tmp_path):
    img, mask = figure
    (tmp_path / "minis.yaml").write_text(
        "output: out\n"
        "sheet: {output: out/sheet.pdf, paper: letter, copies: 2}\n"
        "defaults: {height_mm: 40}\n"
        "figures:\n"
        f"  - image: {img.name}\n"
        f"    mask: {mask.name}\n"
        "    label: Hero\n"
        f"  - image: {img.name}\n"
        f"    mask: {mask.name}\n"
        "    name: hero-double\n"
        "    double_sided: true\n"
        "    copies: 1\n",
        encoding="utf-8",
    )
    assert main(["batch", str(tmp_path / "minis.yaml"), "--preview"]) == 0
    assert (tmp_path / "out" / "Hero.svg").exists()
    assert (tmp_path / "out" / "hero-double.svg").exists()
    assert (tmp_path / "out" / "sheet.pdf").exists()
    assert (tmp_path / "out" / "sheet.png").exists()


def test_cli_reports_bad_model(figure, capsys):
    img, _ = figure
    assert main(["make", str(img), "--model", "no-such-model", "--no-cache"]) == 2
    assert "unknown model" in capsys.readouterr().err


def test_double_sided_back_text(figure, tmp_path):
    img, mask = figure
    prm = geo.Params(double_sided=True, back="text")
    m = make_mini(img, prm, mask_path=mask, label="Hero", back_text="Hero of the Crypt",
                  log=lambda *_: None)
    assert m.texts and all(rot == 180 for _, _, _, rot, _ in m.texts)
    assert " ".join(t for t, *_ in m.texts) == "Hero of the Crypt"  # stored in reading order
    ys = [cy for _, _, cy, _, _ in m.texts]
    assert ys == sorted(ys, reverse=True)  # first line nearest the fold = on top once folded
    for _, cx, cy, _, size in m.texts:
        assert 0 < cx < m.width_mm and 0 < cy < m.height_mm / 2 and size > 1
    # default text is the label; round-trips through the SVG
    m2 = make_mini(img, prm, mask_path=mask, label="Hero", log=lambda *_: None)
    assert [t for t, *_ in m2.texts] == ["Hero"]
    r = read_svg(write_svg(m, tmp_path / "hero.svg"))
    assert [(t, round(x, 2), round(y, 2), rot, round(s, 2)) for t, x, y, rot, s in r.texts] == \
           [(t, round(x, 2), round(y, 2), rot, round(s, 2)) for t, x, y, rot, s in m.texts]
    write_pdf(pack([(r, 1)]), tmp_path / "s.pdf")



def test_back_text_has_its_own_color(figure, tmp_path):
    from papermini.settings import FigureSettings, build_mini

    img, mask = figure
    s = FigureSettings(mask=str(mask), double_sided=True, back="text", back_text="Hero",
                       label_color="#111111", back_text_color="#c0a030")
    m = build_mini(img, s, log=lambda *_: None)
    svg = write_svg(m, tmp_path / "h.svg").read_text(encoding="utf-8")
    assert 'class="backtext"' in svg and 'fill="#c0a030"' in svg
    assert read_svg(tmp_path / "h.svg").style.back_text_color == "#c0a030"



def test_mask_model_choice(figure):
    from papermini.settings import FigureSettings, build_mini

    img, mask = figure
    m = build_mini(img, FigureSettings(model="mask", mask=str(mask)), log=lambda *_: None)
    assert m.figure_height_mm == pytest.approx(42, abs=0.05)
    with pytest.raises(ValueError, match="needs a mask image"):
        build_mini(img, FigureSettings(model="mask"), log=lambda *_: None)



def test_bleed(figure):
    """A bleed (for a sheet cut by machine) prints the edge colors beyond the cut line."""
    from papermini.settings import FigureSettings, build_mini

    img, mask = figure
    s = FigureSettings(mask=str(mask), margin_color="#204080", tab_color="#3b6e2a",
                       double_sided=False)  # (the points below assume one side)
    plain = build_mini(img, s, log=lambda *_: None)
    bled = build_mini(img, s, bleed_mm=1.5, log=lambda *_: None)
    # the canvas grows from half the 0.3 mm cut line + 0.3 to the bleed + 0.2, on each side
    assert bled.width_mm == pytest.approx(plain.width_mm + 2 * (1.5 + 0.2 - 0.45), abs=0.1)
    a = np.asarray(bled.art.convert("RGBA")).astype(int)
    px_mm = a.shape[1] / bled.width_mm
    # a point 1 mm outside the cut line, beside the figure: margin color, opaque
    pts = bled.cut.flatten()
    above = pts[pts[:, 1] < bled.folds[0][2] - 10]      # beside the figure, above the tab
    i = int(np.argmin(above[:, 0]))
    x, y = above[i, 0] - 1.0, above[i, 1]
    r, g, b, al = a[int(y * px_mm), int(x * px_mm)]
    assert al == 255 and abs(r - 0x20) < 8 and abs(g - 0x40) < 8 and abs(b - 0x80) < 8
    # below the tab: tab color continues
    by = pts[:, 1].max() + 1.0
    bx = pts[np.argmax(pts[:, 1]), 0]
    r, g, b, al = a[int(by * px_mm), int(bx * px_mm)]
    assert al == 255 and abs(r - 0x3b) < 8 and abs(g - 0x6e) < 8 and abs(b - 0x2a) < 8


@pytest.mark.parametrize("size", [(700, 900), (3000, 4000)])   # the big one is downscaled
@pytest.mark.parametrize("double_sided", [False, True])
def test_cut_line_in_source_pixels(tmp_path, size, double_sided):
    """The cut line drawn on the Source view: in source-image pixels, around the drawing
    by the margin, with the tab below it (and a double-sided back above the image)."""
    from papermini.settings import FigureSettings, build_mini

    W, H = size
    im = np.full((H, W, 3), 255, np.uint8)
    cx, cy, ax, ay = W // 2 + W // 10, H // 2, W // 5, H // 3
    cv2.ellipse(im, (cx, cy), (ax, ay), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(tmp_path / "m.png")
    m = build_mini(tmp_path / "a.png", FigureSettings(model="mask", mask=str(tmp_path / "m.png"),
                                                      double_sided=double_sided), log=lambda *_: None)
    p = m.source_cut.points
    margin = 1.6 * (2 * ay + 1) / m.figure_height_mm    # default margin, in source pixels
    tol = 0.25 * margin
    assert p[:, 0].min() == pytest.approx(cx - ax - margin, abs=tol)
    assert p[:, 0].max() == pytest.approx(cx + ax + margin, abs=tol)
    assert p[:, 1].max() > cy + ay + margin                # the tab hangs below the drawing
    if double_sided:
        assert p[:, 1].min() < 0                           # the mirrored back, above the image
        assert m.source_top == pytest.approx(cy - ay - margin, abs=tol)  # front starts at the fold
        assert any(y == pytest.approx(cy - ay - margin, abs=tol) for _, _, y in m.source_folds)
    else:
        assert p[:, 1].min() == pytest.approx(cy - ay - margin, abs=tol)
        assert m.source_top == 0
    fold_y = [y for _, _, y in m.source_folds if y > cy]
    assert fold_y and cy + ay < fold_y[0] < p[:, 1].max()   # the tab fold, below the drawing


def _dark_cols_mm(mini):
    a = np.asarray(mini.art.convert("RGBA"))
    dark = (a[..., 3] > 0) & (a[..., :3].max(-1) < 128)
    cols = np.flatnonzero(dark.any(0))
    return (cols.max() - cols.min() + 1) * mini.width_mm / a.shape[1]


def test_size_by_width_or_stretched(figure):
    """Height alone or width alone keep the proportions; both stretch the figure sideways."""
    img, mask = figure
    quiet = dict(mask_path=mask, log=lambda *_: None)
    by_h = make_mini(img, geo.Params(height_mm=42.0), **quiet)
    ratio = by_h.figure_width_mm / by_h.figure_height_mm
    assert by_h.aspect == pytest.approx(301 / 720, rel=0.01) == pytest.approx(ratio, rel=0.01)
    assert _dark_cols_mm(by_h) == pytest.approx(42.0 * 301 / 720, abs=0.5)

    by_w = make_mini(img, geo.Params(height_mm=None, width_mm=20.0), **quiet)
    assert _dark_cols_mm(by_w) == pytest.approx(20.0, abs=0.5)
    assert _dark_rows_mm(by_w) == pytest.approx(20.0 * 720 / 301, abs=0.5)
    assert by_w.figure_width_mm == pytest.approx(20.0)

    both = make_mini(img, geo.Params(height_mm=42.0, width_mm=30.0), **quiet)
    assert _dark_rows_mm(both) == pytest.approx(42.0, abs=0.5)
    assert _dark_cols_mm(both) == pytest.approx(30.0, abs=0.5)
    assert both.aspect == pytest.approx(by_h.aspect)  # the image's own proportions
    # the cut line still lands on the original image: stretched back, it hugs the figure
    x0, _, x1, _ = both.source_cut.extent()
    assert 250 - 40 < x0 < 250 and 550 < x1 < 550 + 40


def test_source_outline_is_the_detected_figure(figure):
    """The outline is what background removal found, without margin or tab."""
    img, mask = figure
    m = make_mini(img, geo.Params(margin_mm=5.0), mask_path=mask, log=lambda *_: None)
    pts = np.vstack(m.source_outline)
    assert pts[:, 0].min() == pytest.approx(250, abs=2) and pts[:, 0].max() == pytest.approx(551, abs=2)
    assert pts[:, 1].min() == pytest.approx(180, abs=2) and pts[:, 1].max() == pytest.approx(900, abs=2)


def test_on_stage_reports_the_outline_before_the_layout(figure):
    img, mask = figure
    seen = []
    make_mini(img, geo.Params(), mask_path=mask, log=lambda *_: None, use_cache=False,
              on_stage=lambda name, data: seen.append(name))
    assert seen == ["outline"]  # a mask file runs no model, so no "segment" stage


def test_cli_makes_double_sided_minis_unless_told_not_to(figure, tmp_path):
    """Double-sided is the default; --no-double-sided prints the front only."""
    img, mask = figure
    for name, extra in (("both", []), ("front", ["--no-double-sided"])):
        assert main(["make", str(img), "--mask", str(mask), "-o",
                     str(tmp_path / f"{name}.svg")] + extra) == 0
    both, front = read_svg(tmp_path / "both.svg"), read_svg(tmp_path / "front.svg")
    assert both.height_mm > 1.8 * front.height_mm       # front and back, one above the other


def test_cli_width_alone_scales_by_width(figure, tmp_path):
    img, mask = figure
    out = tmp_path / "w.svg"
    assert main(["make", str(img), "--mask", str(mask), "--width-mm", "25",
                 "--no-double-sided", "-o", str(out)]) == 0
    r = read_svg(out)
    by_h = make_mini(img, geo.Params(), mask_path=mask, log=lambda *_: None)
    # 25 mm wide at the image's proportions: the figure is 25 / aspect high, not the
    # default 42 mm (margin and tab stay the same, so compare the difference)
    assert r.height_mm - by_h.height_mm == pytest.approx(25 / by_h.aspect - 42, abs=0.5)


def _square_mini(name="sq", w=30.0, h=40.0):
    from papermini.geometry import CutPath
    from papermini.mini import Mini

    sq = CutPath(np.array([[0, 0], [w, 0], [w, h], [0, h]], float))
    return Mini(name, w, h, Image.new("RGBA", (int(w * 10), int(h * 10)), (200, 40, 30, 255)),
                sq, folds=[(0.0, w, h - 5)])


def test_machine_sheet_keeps_clear_of_the_marks():
    """The pieces keep MARK_CLEAR_MM away from the corner marks only, so a machine sheet
    holds as many pieces as one cut by hand; the header starts beside the marks."""
    from papermini.sheet import MARK_CLEAR_MM

    m = _square_mini()
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
                apart = (p.x + m.width_mm <= x - c + 1e-9 or p.x >= x + w + c - 1e-9
                         or p.y + m.height_mm <= y - c + 1e-9 or p.y >= y + h + c - 1e-9)
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


def test_cut_files_match_the_sheet(tmp_path):
    """Cut by machine: the PDF gets no cut lines, and a cut file per page holds the cut
    lines where the pieces are on the page plus the same marks as the PDF."""
    import re
    import xml.etree.ElementTree as ET

    from papermini.sheet import cut_file_paths, default_cut_file, write_cut_files

    m = _square_mini()
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
    rects = [tuple(float(r.get(k)) for k in ("x", "y", "width", "height"))
             for r in root.findall("s:g[@id='registration']/s:rect", ns)]
    assert np.allclose(rects, lay.mark_rects(), atol=1e-3)  # the same marks as the PDF
    cuts = root.findall("s:g[@id='cut']/s:path", ns)
    first = [p for p in lay.placements if p.page == 0]
    assert len(cuts) == len(first)
    xy = [float(v) for v in re.findall(r"[-\d.]+", cuts[0].get("d"))[:2]]
    assert xy == pytest.approx([first[0].x, first[0].y], abs=1e-3)  # placed as on the page
    assert root.find("s:g[@id='fold']", ns) is None  # fold lines only when asked for
    folded = ET.fromstring(write_cut_files(lay, tmp_path / "f.svg", folds=True)[0].read_text())
    assert len(folded.findall("s:g[@id='fold']/s:line", ns)) == len(first)


def test_sheet_cli_cut_by_machine(figure, tmp_path):
    img, mask = figure
    from papermini.cli import main

    assert main(["make", str(img), "--mask", str(mask), "--bleed-mm", "1", "-o",
                 str(tmp_path / "hero.svg")]) == 0
    assert main(["sheet", str(tmp_path / "hero.svg"), "-o", str(tmp_path / "s.pdf"),
                 "--cut", "machine", "--marks", "silhouette", "--cut-folds"]) == 0
    assert (tmp_path / "s.pdf").exists()
    svg = (tmp_path / "s-cut.svg").read_text()
    assert 'id="registration"' in svg and 'id="cut"' in svg and 'id="fold"' in svg


def test_batch_cut_by_machine_builds_the_bleed(figure, tmp_path):
    img, mask = figure
    (tmp_path / "p.yaml").write_text(
        f"output: out\nsheet:\n  output: out/s.pdf\n  cut: machine\n  bleed_mm: 1.5\n"
        f"figures:\n  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n"
        f"  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n    name: b\n",
        encoding="utf-8")
    from papermini.cli import main

    assert main(["batch", str(tmp_path / "p.yaml")]) == 0
    assert (tmp_path / "out" / "s.pdf").exists() and (tmp_path / "out" / "s-cut.svg").exists()
    from papermini.svg import read_svg

    plain = make_mini(img, geo.Params(), mask_path=mask, log=lambda *_: None)
    bled = read_svg(tmp_path / "out" / "b.svg")
    assert bled.width_mm > plain.width_mm + 2  # built with the sheet's bleed
