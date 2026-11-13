"""Color adjustments of the printed picture (greyscale, hue, saturation, brightness,
contrast): the maths, the settings, and that they never touch background removal."""

import numpy as np
import pytest
from PIL import Image

from papermini import cache
from papermini.adjust import Adjustments, apply
from papermini.cli import main
from papermini.settings import FigureSettings, build_mini

COLORS = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255],
                     [255, 255, 255], [0, 0, 0], [128, 128, 128]]], np.uint8)


def test_no_adjustment_leaves_the_picture_alone():
    assert Adjustments().is_identity()
    assert apply(COLORS, Adjustments()) is COLORS


def test_greyscale_and_saturation():
    grey = apply(COLORS, Adjustments(greyscale=True))[0]
    assert all(r == g == b for r, g, b in grey)              # no color left
    assert grey[0][0] < grey[1][0] and grey[2][0] < grey[0][0]  # by brightness (luma)
    assert (apply(COLORS, Adjustments(saturation=-100)) == apply(
        COLORS, Adjustments(greyscale=True))).all()
    vivid = apply(np.array([[[180, 120, 100]]], np.uint8), Adjustments(saturation=60))[0, 0]
    assert vivid[0] > 180 and vivid[2] < 100                 # further apart


def test_brightness_keeps_paper_white_and_lines_black():
    lighter = apply(COLORS, Adjustments(brightness=50))[0]
    assert lighter[3].tolist() == [255, 255, 255] and lighter[5][0] > 128
    darker = apply(COLORS, Adjustments(brightness=-50))[0]
    assert darker[4].tolist() == [0, 0, 0] and darker[5][0] < 128


def test_contrast_and_hue():
    assert apply(COLORS, Adjustments(contrast=-100))[0][3].tolist() == [128, 128, 128]
    hard = apply(np.array([[[100, 100, 100]]], np.uint8), Adjustments(contrast=60))
    assert hard[0, 0, 0] < 100
    red = np.array([[[255, 0, 0]]], np.uint8)
    green = apply(red, Adjustments(hue=120))[0, 0]           # red -> green, as elsewhere
    assert green[1] > green[0] and green[1] > green[2]
    assert apply(COLORS, Adjustments(hue=90))[0][3].tolist() == [255, 255, 255]  # no hue


def test_transparent_pixels_keep_their_coverage():
    """Premultiplied RGBA (how the pipeline keeps cut-outs): colors change, alpha not."""
    px = np.array([[[100, 50, 25, 128], [0, 0, 0, 0]]], np.uint8)
    out = apply(px, Adjustments(brightness=100))
    assert out[0, 0].tolist() == [128, 128, 128, 128]        # white at half coverage
    assert out[0, 1].tolist() == [0, 0, 0, 0]
    straight = apply(np.array([[[200, 100, 50, 128]]], np.uint8),
                     Adjustments(greyscale=True), premultiplied=False)[0, 0]
    assert straight[0] == straight[1] == straight[2] and straight[3] == 128


def test_settings_validate_and_round_trip():
    s = FigureSettings.from_dict({"greyscale": True, "brightness": 20, "hue": -45})
    assert s.adjustments() == Adjustments(brightness=20, hue=-45, greyscale=True)
    assert s.to_dict(with_size=False) == {"greyscale": True, "brightness": 20, "hue": -45}
    for key, bad in (("brightness", 101), ("hue", 181), ("contrast", 1.5),
                     ("saturation", True)):
        with pytest.raises(ValueError, match=key):
            FigureSettings.from_dict({key: bad})


@pytest.fixture
def figure(tmp_path):
    """A red disc on white, with its own mask (no model)."""
    import cv2

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.circle(im, (250, 300), 150, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "f.png")
    mask = np.zeros((600, 500), np.uint8)
    cv2.circle(mask, (250, 300), 150, 255, -1)
    Image.fromarray(mask).save(tmp_path / "m.png")
    return tmp_path / "f.png", tmp_path / "m.png"


def test_adjustments_change_the_print_not_the_outline(figure):
    """The picture is adjusted; the mask, outline and size are exactly as before, and
    the cached mask is reused (the model would not run again)."""
    img, mask = figure
    cache.clear_all()
    base = FigureSettings(mask=str(mask), double_sided=False, label="")
    plain = build_mini(img, base, log=lambda *_: None)
    misses = cache.raw_masks.misses
    grey = build_mini(img, FigureSettings(**{**base.__dict__, "greyscale": True,
                                             "brightness": 10}), log=lambda *_: None)
    assert cache.raw_masks.misses == misses                  # no new mask
    assert len(grey.source_outline) == len(plain.source_outline)
    assert all((a == b).all() for a, b in zip(grey.source_outline, plain.source_outline))
    assert (grey.width_mm, grey.height_mm) == (plain.width_mm, plain.height_mm)
    a = np.asarray(grey.art.convert("RGBA")).astype(int)
    p = np.asarray(plain.art.convert("RGBA")).astype(int)
    cy, cx = a.shape[0] // 2, a.shape[1] // 2                # the middle of the disc
    assert p[cy, cx, 0] > p[cy, cx, 1] + 100                 # red...
    assert abs(a[cy, cx, 0] - a[cy, cx, 1]) <= 2             # ...printed grey
    assert a[cy, cx, 3] == p[cy, cx, 3] == 255


def test_cli_color_flags(figure, tmp_path):
    img, mask = figure
    out = tmp_path / "g.svg"
    assert main(["make", str(img), "--mask", str(mask), "--greyscale", "--contrast", "20",
                 "--no-double-sided", "-o", str(out)]) == 0
    assert out.exists()
