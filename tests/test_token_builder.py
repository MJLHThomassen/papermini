"""Tests of round tokens: the framing, the ring, the text and the cut line. The
pictures carry their own transparency, so no model is needed."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from papermini.output.svg import write_svgs
from papermini.pipeline.token_framer import FIT_FREE
from papermini.pipeline.token_info import TokenInfo
from papermini.pipeline.token_renderer import PLATE
from papermini.project.settings import build_mini


def test_a_fitted_figure_stays_inside_the_circle(
    tmp_path, build_token, transparent_figure
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img)
    t = m.token
    assert m.kind == "token" and t.inner_mm == pytest.approx(12.5 - 2)
    assert m.width_mm == m.height_mm and m.figure_height_mm == 25
    # every point of the figure lies inside the circle, with FIT_FREE of it free all round
    pts = np.vstack(m.source_outline)
    c = m.source_cut.points.mean(axis=0)
    r = np.hypot(
        *(m.source_cut.points[0] - c)
    )  # (the circle inside the ring, image px)
    assert np.hypot(*(pts - c).T).max() <= r * (1 - 2 * FIT_FREE) + 2
    assert np.hypot(*(pts - c).T).max() >= r * (1 - 2 * FIT_FREE) - 3  # (and fills it)
    # the cut line is the ring's edge (nothing printed on it by default)
    assert not m.style.cut_line
    assert np.hypot(*(m.cut.points - (t.cx, t.cy)).T) == pytest.approx(12.5)


def test_a_fitted_figure_stays_above_the_nameplate(
    tmp_path, build_token, transparent_figure
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, token_text="label", token_text_mm=3)
    t = m.token
    plate_top = t.cy + t.inner_mm - PLATE * 3
    assert t.figure_box[3] <= plate_top + 0.05
    assert t.plate[0] == pytest.approx(t.cx)  # the label is centred


def test_a_printed_cut_line_lies_outside_the_ring(
    pipeline,
    tmp_path,
    build_token,
    transparent_figure,
    size_calculator,
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, token_cut_line=True, cut_width_mm=0.4)
    t = m.token
    assert m.style.cut_line
    assert np.hypot(*(m.cut.points - (t.cx, t.cy)).T) == pytest.approx(12.5 + 0.2)
    # cut by machine (with bleed) the cut follows the ring
    s = size_calculator.settings_with_size(
        {"kind": "token", "model": "alpha", "token_cut_line": True}
    )
    m = build_mini(img, s, pipeline=pipeline, bleed_mm=1.0, log=lambda *a: None)
    assert np.hypot(*(m.cut.points - (m.token.cx, m.token.cy)).T) == pytest.approx(12.5)


def test_the_token_text_follows_the_ring_and_numbers_each_copy(
    fonts, tmp_path, build_token, transparent_figure
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(
        img,
        label="Goblin boss",
        token_text="label_number",
        token_text_style="curved",
        token_text_color="#2f5597",
        token_border_color="#303060",
    )
    items = m.text_items(fonts)
    assert {t.kind for t in items} == {"tokentext"}
    assert (
        "".join(t.text for t in items) == "Goblinboss#"
    )  # a letter each, # = the number
    assert {t.color for t in items} == {"#2f5597"}  # the color chosen, always
    letters = [t for t in items if t.text != "#"]
    assert (
        letters[0].rot > 20 and letters[-1].rot < -20
    )  # (along the bottom, both ways)
    # numbered copies: a file each, each with its number
    paths = write_svgs(m, tmp_path / "goblin.svg", fonts, 3)
    assert [p.name for p in paths] == ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert ">3</text>" in paths[2].read_text()
    plate = build_token(img, label="Goblin", token_text="label_number")
    t = plate.token
    assert (
        t.badge is not None
        and t.badge[1] + t.badge[2] <= t.cy + t.inner_mm - t.plate[3]
    )
    assert [i.text for i in plate.text_items(fonts)] == ["Goblin", "#"]


def _count(art, channel):
    """Counts the pixels of the art that are clearly red, green or blue (channel 0, 1
    or 2)."""
    a = np.asarray(art.convert("RGB")).astype(int)
    others = [c for c in range(3) if c != channel]
    return int(((a[..., channel] > 200) & (a[..., others] < 80).all(-1)).sum())


def test_a_token_figure_with_an_outline(tmp_path, build_token, transparent_figure):
    img = transparent_figure(tmp_path / "goblin.png")
    plain = build_token(img, margin_color="#00ff00")
    outlined = build_token(img, token_outline=True, margin_color="#00ff00")
    assert _count(plain.art, 1) == 0
    assert _count(outlined.art, 1) > 0  # the outline, in the margin color


def test_a_token_filled_with_the_picture(pipeline, tmp_path, size_calculator):
    im = Image.new("RGB", (300, 400), (0, 0, 255))  # a blue background
    ImageDraw.Draw(im).ellipse([60, 40, 240, 360], fill=(200, 40, 30))
    im.save(tmp_path / "goblin.png")
    mask = Image.new("L", (300, 400), 0)
    ImageDraw.Draw(mask).ellipse([60, 40, 240, 360], fill=255)
    mask.save(tmp_path / "goblin_mask.png")
    common = {
        "kind": "token",
        "model": "mask",
        "mask": str(tmp_path / "goblin_mask.png"),
    }

    def background(**kw):
        """Builds the token and keeps only its art inside the ring and over 1 mm from
        the figure's box."""
        s = size_calculator.settings_with_size({**common, **kw})
        m = build_mini(
            tmp_path / "goblin.png", s, pipeline=pipeline, log=lambda *a: None
        )
        t, a = m.token, np.asarray(m.art.convert("RGB")).copy()
        assert isinstance(t, TokenInfo) and t.figure_box is not None
        px = a.shape[1] / m.width_mm
        y, x = (np.mgrid[: a.shape[0], : a.shape[1]] + 0.5) / px
        x0, y0, x1, y1 = t.figure_box
        near = (x > x0 - 1) & (x < x1 + 1) & (y > y0 - 1) & (y < y1 + 1)
        a[near | (np.hypot(x - t.cx, y - t.cy) > t.inner_mm - 0.3)] = 0
        return Image.fromarray(a)

    assert _count(background(), 2) == 0  # the fill color behind the figure
    assert _count(background(token_fill="image"), 2) > 0  # the picture's background
