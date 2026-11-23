"""Tests of building a mini from a picture. The pictures come with a mask or
their own transparency, so no model is needed."""

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini.pipeline.style import Style
from papermini.pipeline.text_item import NUMBER_PLACEHOLDER
from papermini.project.figure_settings import FigureSettings
from papermini.support.font_library import FontLibrary


def _dark_rows_mm(mini):
    a = np.asarray(mini.art.convert("RGBA"))
    dark = (a[..., 3] > 0) & (a[..., :3].max(-1) < 128)
    rows = np.flatnonzero(dark.any(1))
    return (rows.max() - rows.min() + 1) * mini.height_mm / a.shape[0]


@pytest.mark.parametrize("height", [30.0, 42.0])
def test_the_figure_prints_at_the_height_asked_for(
    hero_figure, height, pipeline_mini, params, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, params(height_mm=height), mask_options(mask_path=mask))
    assert _dark_rows_mm(m) == pytest.approx(height, abs=0.5)


def test_alpha_png_needs_no_model(tmp_path, pipeline_mini, params):
    a = np.zeros((600, 400, 4), np.uint8)
    cv2.circle(a, (200, 300), 150, (90, 60, 30, 255), -1)
    Image.fromarray(a, "RGBA").save(tmp_path / "cut.png")
    m = pipeline_mini(tmp_path / "cut.png", params(height_mm=20, tab=False))
    assert _dark_rows_mm(m) == pytest.approx(20, abs=0.5)


def test_the_back_text_is_upside_down_and_defaults_to_the_label(
    output, hero_figure, tmp_path, pipeline_mini, params, mask_options, read_svg
):
    img, mask = hero_figure
    prm = params(double_sided=True, back="text")
    m = pipeline_mini(
        img,
        prm,
        mask_options(mask_path=mask),
        label="Hero",
        back_text="Hero of the Crypt",
    )
    assert m.texts and all(t.rot == 180 for t in m.texts)
    assert (
        " ".join(t.text for t in m.texts) == "Hero of the Crypt"
    )  # stored in reading order
    ys = [t.cy for t in m.texts]
    assert ys == sorted(
        ys, reverse=True
    )  # first line nearest the fold = on top once folded
    for t in m.texts:
        assert 0 < t.cx < m.width_mm and 0 < t.cy < m.height_mm / 2 and t.size_mm > 1
    # default text is the label; the SVG holds the lines in the same order
    m2 = pipeline_mini(img, prm, mask_options(mask_path=mask), label="Hero")
    assert [t.text for t in m2.texts] == ["Hero"]
    svg = read_svg(output.svg.write(m, tmp_path / "hero.svg"))
    assert [t for kind, t in svg.texts if kind == "backtext"] == [
        t.text for t in m.texts
    ]


def test_a_bleed_prints_the_edge_colors_beyond_the_cut_line(
    figure_builder, hero_figure
):
    """A bleed (for a sheet cut by machine) prints the edge colors beyond the cut line."""
    from papermini.project.figure_settings import FigureSettings

    img, mask = hero_figure
    s = FigureSettings(
        mask=str(mask), margin_color="#204080", tab_color="#3b6e2a", double_sided=False
    )  # (the points below assume one side)
    plain = figure_builder.build(img, s, log=lambda *_: None)
    bled = figure_builder.build(img, s, bleed_mm=1.5, log=lambda *_: None)
    # the canvas grows from half the 0.3 mm cut line + 0.3 to the bleed + 0.2, on each side
    assert bled.width_mm == pytest.approx(
        plain.width_mm + 2 * (1.5 + 0.2 - 0.45), abs=0.1
    )
    a = np.asarray(bled.art.convert("RGBA")).astype(int)
    px_mm = a.shape[1] / bled.width_mm
    # a point 1 mm outside the cut line, beside the figure: margin color, opaque
    pts = bled.cut.flatten()
    above = pts[pts[:, 1] < bled.folds[0][2] - 10]  # beside the figure, above the tab
    i = int(np.argmin(above[:, 0]))
    x, y = above[i, 0] - 1.0, above[i, 1]
    r, g, b, al = a[int(y * px_mm), int(x * px_mm)]
    assert al == 255 and abs(r - 0x20) < 8 and abs(g - 0x40) < 8 and abs(b - 0x80) < 8
    # below the tab: tab color continues
    by = pts[:, 1].max() + 1.0
    bx = pts[np.argmax(pts[:, 1]), 0]
    r, g, b, al = a[int(by * px_mm), int(bx * px_mm)]
    assert al == 255 and abs(r - 0x3B) < 8 and abs(g - 0x6E) < 8 and abs(b - 0x2A) < 8


@pytest.mark.parametrize(
    "size", [(700, 900), (3000, 4000)]
)  # the big one is downscaled
@pytest.mark.parametrize("double_sided", [False, True])
def test_the_source_cut_line_is_in_source_pixels(
    figure_builder, tmp_path, size, double_sided
):
    """The cut line drawn on the Source view: in source-image pixels, around the drawing
    by the margin, with the tab below it (and a double-sided back above the image)."""
    from papermini.project.figure_settings import FigureSettings

    W, H = size
    im = np.full((H, W, 3), 255, np.uint8)
    cx, cy, ax, ay = W // 2 + W // 10, H // 2, W // 5, H // 3
    cv2.ellipse(im, (cx, cy), (ax, ay), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(
        tmp_path / "m.png"
    )
    m = figure_builder.build(
        tmp_path / "a.png",
        FigureSettings(
            model="mask",
            mask=str(tmp_path / "m.png"),
            double_sided=double_sided,
            tab_width_mm=10,
        ),  # (narrower than the drawing)
        log=lambda *_: None,
    )
    p = m.source_cut.points
    margin = 1.6 * (2 * ay + 1) / m.figure_height_mm  # default margin, in source pixels
    tol = 0.25 * margin
    assert p[:, 0].min() == pytest.approx(cx - ax - margin, abs=tol)
    assert p[:, 0].max() == pytest.approx(cx + ax + margin, abs=tol)
    assert p[:, 1].max() > cy + ay + margin  # the tab hangs below the drawing
    if double_sided:
        assert p[:, 1].min() < 0  # the mirrored back, above the image
        assert m.source_top == pytest.approx(
            cy - ay - margin, abs=tol
        )  # front starts at the fold
        assert any(
            y == pytest.approx(cy - ay - margin, abs=tol) for _, _, y in m.source_folds
        )
    else:
        assert p[:, 1].min() == pytest.approx(cy - ay - margin, abs=tol)
        assert m.source_top == 0
    fold_y = [y for _, _, y in m.source_folds if y > cy]
    assert (
        fold_y and cy + ay < fold_y[0] < p[:, 1].max()
    )  # the tab fold, below the drawing


def _dark_cols_mm(mini):
    a = np.asarray(mini.art.convert("RGBA"))
    dark = (a[..., 3] > 0) & (a[..., :3].max(-1) < 128)
    cols = np.flatnonzero(dark.any(0))
    return (cols.max() - cols.min() + 1) * mini.width_mm / a.shape[1]


def test_width_alone_keeps_the_proportions_and_both_stretch(
    hero_figure, pipeline_mini, params, mask_options
):
    """Height alone or width alone keep the proportions; both stretch the figure sideways."""
    img, mask = hero_figure
    by_mask = mask_options(mask_path=mask)
    by_h = pipeline_mini(img, params(height_mm=42.0), by_mask)
    ratio = by_h.figure_width_mm / by_h.figure_height_mm
    assert (
        by_h.aspect
        == pytest.approx(301 / 720, rel=0.01)
        == pytest.approx(ratio, rel=0.01)
    )
    assert _dark_cols_mm(by_h) == pytest.approx(42.0 * 301 / 720, abs=0.5)

    by_w = pipeline_mini(img, params(height_mm=None, width_mm=20.0), by_mask)
    assert _dark_cols_mm(by_w) == pytest.approx(20.0, abs=0.5)
    assert _dark_rows_mm(by_w) == pytest.approx(20.0 * 720 / 301, abs=0.5)
    assert by_w.figure_width_mm == pytest.approx(20.0)

    both = pipeline_mini(img, params(height_mm=42.0, width_mm=30.0), by_mask)
    assert _dark_rows_mm(both) == pytest.approx(42.0, abs=0.5)
    assert _dark_cols_mm(both) == pytest.approx(30.0, abs=0.5)
    assert both.aspect == pytest.approx(by_h.aspect)  # the image's own proportions
    # the cut line still lands on the original image: stretched back, it hugs the figure
    x0, _, x1, _ = both.source_cut.extent()
    assert 250 - 40 < x0 < 250 and 550 < x1 < 550 + 40


def test_source_outline_is_the_detected_figure(
    hero_figure, pipeline_mini, params, mask_options
):
    """The outline is what background removal found, without margin or tab."""
    img, mask = hero_figure
    m = pipeline_mini(img, params(margin_mm=5.0), mask_options(mask_path=mask))
    pts = np.vstack(m.source_outline)
    assert pts[:, 0].min() == pytest.approx(250, abs=2) and pts[
        :, 0
    ].max() == pytest.approx(551, abs=2)
    assert pts[:, 1].min() == pytest.approx(180, abs=2) and pts[
        :, 1
    ].max() == pytest.approx(900, abs=2)


def test_on_stage_reports_the_outline_before_the_layout(
    hero_figure, pipeline_mini, mask_options
):
    img, mask = hero_figure
    seen = []
    pipeline_mini(
        img,
        mask=mask_options(mask_path=mask),
        use_cache=False,
        on_stage=lambda name, data: seen.append(name),
    )
    assert seen == ["outline"]  # a mask file runs no model, so no "segment" stage


def _kinds(fonts, m, rot):
    return [(t.kind, t.text) for t in m.text_items(fonts) if t.rot == rot]


def test_a_mini_shows_its_number_only_where_chosen(fonts, goblin_figure, numbered_mini):
    m = numbered_mini(goblin_figure)
    assert not m.numbered and m.number_box is None
    assert _kinds(fonts, m, 0) == [("label", "Goblin")] and _kinds(fonts, m, 180)[
        0
    ] == (
        "label",
        "Goblin",
    )
    m = numbered_mini(
        goblin_figure, tab_front="number", tab_back="label_number", back="blank"
    )
    assert m.numbered
    assert _kinds(fonts, m, 0) == [
        ("number", NUMBER_PLACEHOLDER)
    ]  # (no copy number yet)
    assert _kinds(fonts, m, 180) == [("number", "#"), ("label", "Goblin")]
    m.number = 4
    assert [t.text for t in m.text_items(fonts) if t.kind == "number"] == ["4", "4"]
    assert all(t.bold for t in m.text_items(fonts) if t.kind == "number")


def test_number_and_label_share_the_tab(fonts, goblin_figure, numbered_mini):
    """With both, the number goes above the label (towards the fold), at least as big."""
    m = numbered_mini(
        goblin_figure, tab_front="label_number", tab_back="label_number", back="blank"
    )
    m.number = 12
    for rot, towards_fold in ((0, -1), (180, 1)):
        num, label = [t for t in m.text_items(fonts) if t.rot == rot]
        assert (num.kind, label.kind) == ("number", "label")
        assert (num.cy - label.cy) * towards_fold > 0
        assert num.size_mm >= label.size_mm
        assert num.cx == pytest.approx(label.cx)
    # a number alone fills the tab's height (or width)
    alone = numbered_mini(goblin_figure, tab_front="number", back="blank")
    alone.number = 12
    n = next(t for t in alone.text_items(fonts) if t.kind == "number")
    assert alone.label_size_mm < n.size_mm <= alone.tab_room[1] + 1e-6


def test_the_number_is_printed_on_the_back(fonts, goblin_figure, numbered_mini):
    m = numbered_mini(goblin_figure, back="number")
    assert m.numbered and not m.texts
    _cx, cy, w, h = m.number_box
    assert 0 < cy < m.height_mm / 2 and w > 0 and h > 0  # the back half is the top half
    m.number = 3
    back = [t for t in m.text_items(fonts) if t.kind == "number"]
    assert [(t.text, t.rot) for t in back] == [("3", 180.0)]
    assert back[0].size_mm > 2 * m.label_size_mm
    # with text: the number above the text (upside down, so further down the sheet)
    both = numbered_mini(goblin_figure, back="text_number", back_text="Goblin boss")
    _cx, cy, w, h = both.number_box
    assert both.texts and all(t.cy < cy - h / 2 for t in both.texts)


def test_a_missing_font_prints_in_times(
    fonts, goblin_figure, pipeline_mini, mask_options
):
    assert fonts.resolve("No Such Font") == (FontLibrary.TIMES, False)
    assert fonts.resolve("Almendra")[1] and fonts.resolve("Times")[1]
    assert fonts.pdf_name("No Such Font") == "Times-Roman"
    assert fonts.pdf_name("Times", bold=True) == "Times-Bold"
    img, mask = goblin_figure
    notes = []
    m = pipeline_mini(
        img,
        mask=mask_options(mask_path=mask),
        label="Hero",
        style=Style(font="No Such Font"),
        log=notes.append,
    )
    assert m.style.font == "Times"
    assert any("No Such Font is not on this computer" in n for n in notes)


def test_adjustments_change_the_print_not_the_outline(
    pipeline, figure_builder, red_disc
):
    """The picture is adjusted; the mask, outline and size are exactly as before, and
    the cached mask is reused (the model would not run again)."""
    img, mask = red_disc
    base = FigureSettings(mask=str(mask), double_sided=False, label="")
    plain = figure_builder.build(img, base, log=lambda *_: None)
    misses = pipeline.caches.raw_masks.misses
    grey = figure_builder.build(
        img,
        FigureSettings(**{**base.__dict__, "greyscale": True, "brightness": 10}),
        log=lambda *_: None,
    )
    assert pipeline.caches.raw_masks.misses == misses  # no new mask
    assert len(grey.source_outline) == len(plain.source_outline)
    assert all(
        (a == b).all() for a, b in zip(grey.source_outline, plain.source_outline)
    )
    assert (grey.width_mm, grey.height_mm) == (plain.width_mm, plain.height_mm)
    a = np.asarray(grey.art.convert("RGBA")).astype(int)
    p = np.asarray(plain.art.convert("RGBA")).astype(int)
    cy, cx = a.shape[0] // 2, a.shape[1] // 2  # the middle of the disc
    assert p[cy, cx, 0] > p[cy, cx, 1] + 100  # red...
    assert abs(a[cy, cx, 0] - a[cy, cx, 1]) <= 2  # ...printed grey
    assert a[cy, cx, 3] == p[cy, cx, 3] == 255
