"""Tests of the color adjustments of the printed picture."""

import numpy as np

from papermini.pipeline.adjust import apply
from papermini.pipeline.adjustments import Adjustments

COLORS = np.array(
    [
        [
            [255, 0, 0],
            [0, 255, 0],
            [0, 0, 255],
            [255, 255, 255],
            [0, 0, 0],
            [128, 128, 128],
        ]
    ],
    np.uint8,
)


def test_no_adjustment_leaves_the_picture_alone():
    assert Adjustments().is_identity()
    assert apply(COLORS, Adjustments()) is COLORS


def test_greyscale_and_saturation():
    grey = apply(COLORS, Adjustments(greyscale=True))[0]
    assert all(r == g == b for r, g, b in grey)  # no color left
    assert grey[0][0] < grey[1][0] and grey[2][0] < grey[0][0]  # by brightness (luma)
    assert (
        apply(COLORS, Adjustments(saturation=-100))
        == apply(COLORS, Adjustments(greyscale=True))
    ).all()
    vivid = apply(np.array([[[180, 120, 100]]], np.uint8), Adjustments(saturation=60))[
        0, 0
    ]
    assert vivid[0] > 180 and vivid[2] < 100  # further apart


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
    green = apply(red, Adjustments(hue=120))[0, 0]  # red -> green, as elsewhere
    assert green[1] > green[0] and green[1] > green[2]
    assert apply(COLORS, Adjustments(hue=90))[0][3].tolist() == [
        255,
        255,
        255,
    ]  # no hue


def test_transparent_pixels_keep_their_coverage():
    """Premultiplied RGBA (how the pipeline keeps cut-outs): colors change, alpha not."""
    px = np.array([[[100, 50, 25, 128], [0, 0, 0, 0]]], np.uint8)
    out = apply(px, Adjustments(brightness=100))
    assert out[0, 0].tolist() == [128, 128, 128, 128]  # white at half coverage
    assert out[0, 1].tolist() == [0, 0, 0, 0]
    straight = apply(
        np.array([[[200, 100, 50, 128]]], np.uint8),
        Adjustments(greyscale=True),
        premultiplied=False,
    )[0, 0]
    assert straight[0] == straight[1] == straight[2] and straight[3] == 128
