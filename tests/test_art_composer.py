"""Tests of painting the artwork onto the margin color."""

import cv2
import numpy as np


def _ring_drawing():
    """A grey pencil ring on white paper, its mask, and the same as a soft cut-out."""
    img = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(img, (200, 200), 120, (150, 150, 150), 6, cv2.LINE_AA)
    fig = np.zeros((400, 400), np.uint8)
    cv2.circle(fig, (200, 200), 126, 255, -1)
    return img, fig


def test_no_white_halo_on_a_dark_margin(pipeline):
    """Regression: the white paper around the drawing showed as a halo on dark margins."""
    img, fig = _ring_drawing()
    pxmm = 20.0
    art = pipeline.composer.compose(img, fig, (0, 0, 0), pxmm, False)
    outside = (
        pipeline.morphology.dilate(fig, 0.6 * pxmm) & ~fig
    )  # just beyond the outline
    assert art[outside > 0].max() < 40  # no light halo there
    assert art[200, 200].min() == 255  # the drawing's inside stays white
    # with a white margin the result is the plain picture, as before
    plain = pipeline.composer.compose(img, fig, (255, 255, 255), pxmm, False)
    assert np.abs(plain[fig > 0].astype(int) - img[fig > 0]).max() <= 1


def test_alpha_cutout_blends_into_the_margin(pipeline):
    """A cut-out's soft edge blends into the margin color (no white fringe), while
    see-through parts inside the figure look as they do on white paper."""
    img, fig = _ring_drawing()
    alpha = cv2.GaussianBlur(fig, (0, 0), 3)  # soft edge
    alpha[150:250, 150:250] = 120  # a translucent patch inside
    rgba = np.dstack([img, alpha]).astype(np.float32)
    rgba[..., :3] *= rgba[..., 3:4] / 255.0  # premultiplied, as loaded
    rgba = np.clip(rgba + 0.5, 0, 255).astype(np.uint8)
    art = pipeline.composer.compose(rgba, fig, (0, 0, 0), 20.0, False)
    edge = (alpha > 5) & (alpha < 250) & (fig == 0)
    assert art[edge].max() < 40  # soft edge: dark, not white
    assert art[200, 200].min() > 240  # translucent inside: light


def test_the_image_fill_is_the_whole_picture(pipeline):
    """Regression: the original image filled only the margin, so the paper between the
    margin and the cut line stayed white."""
    img, fig = _ring_drawing()
    img[:, :, 2] = 90  # a tinted picture, so white paper would show
    art = pipeline.composer.compose(img, fig, (255, 255, 255), 20.0, True)
    assert np.array_equal(art, img)
