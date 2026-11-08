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



def test_back_text_has_its_own_colour(figure, tmp_path):
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



def test_cutter_bleed(figure):
    """Cutting-machine style prints the edge colours beyond the cut line."""
    from papermini.settings import FigureSettings, build_mini

    img, mask = figure
    base = dict(mask=str(mask), margin_color="#204080", tab_color="#3b6e2a")
    plain = build_mini(img, FigureSettings(cutter=True, bleed_mm=0, **base), log=lambda *_: None)
    bled = build_mini(img, FigureSettings(cutter=True, bleed_mm=1.5, **base), log=lambda *_: None)
    nocut = build_mini(img, FigureSettings(bleed_mm=1.5, **base), log=lambda *_: None)
    assert bled.width_mm == pytest.approx(plain.width_mm + 2 * (1.5 + 0.2 - 0.35), abs=0.1)
    hand = build_mini(img, FigureSettings(bleed_mm=0, **base), log=lambda *_: None)
    assert nocut.width_mm == pytest.approx(hand.width_mm, abs=0.01)  # bleed needs the cutter
    a = np.asarray(bled.art.convert("RGBA")).astype(int)
    px_mm = a.shape[1] / bled.width_mm
    # a point 1 mm outside the cut line, beside the figure: margin colour, opaque
    pts = bled.cut.flatten()
    above = pts[pts[:, 1] < bled.folds[0][2] - 10]      # beside the figure, above the tab
    i = int(np.argmin(above[:, 0]))
    x, y = above[i, 0] - 1.0, above[i, 1]
    r, g, b, al = a[int(y * px_mm), int(x * px_mm)]
    assert al == 255 and abs(r - 0x20) < 8 and abs(g - 0x40) < 8 and abs(b - 0x80) < 8
    # below the tab: tab colour continues
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
