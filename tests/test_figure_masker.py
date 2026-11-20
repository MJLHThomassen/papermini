"""Tests of finding the figure in a picture, with a mask, the picture's transparency
or a stand-in model."""

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini.pipeline.pipeline import Pipeline
from papermini.pipeline.segmentation.segmenter_registry import SegmenterRegistry


def _two_figures(tmp_path, alpha=False):
    """Saves a picture with a dark figure on each side, and its mask. With ``alpha``
    the background is transparent."""
    h, w = 400, 600
    im = np.full((h, w, 4), (255, 255, 255, 0 if alpha else 255), np.uint8)
    mask = np.zeros((h, w), np.uint8)
    for cx in (150, 450):
        cv2.ellipse(im, (cx, 200), (80, 150), 0, 0, 360, (40, 40, 40, 255), -1)
        cv2.ellipse(mask, (cx, 200), (80, 150), 0, 0, 360, 255, -1)
    img = tmp_path / "two.png"
    Image.fromarray(im if alpha else im[..., :3]).save(img)
    Image.fromarray(mask).save(tmp_path / "two_mask.png")
    return img, tmp_path / "two_mask.png"


@pytest.mark.parametrize("source", ["mask", "alpha", "model"])
def test_a_crop_limits_the_figure_to_its_box(fonts, tmp_path, source, mask_options):
    img, mask = _two_figures(tmp_path, alpha=source == "alpha")
    seen = []

    def segmenter(rgb):  # a stand-in model: the dark pixels are the figure
        seen.append(rgb.size)
        return np.where(np.asarray(rgb.convert("L")) < 128, 255, 0).astype(np.uint8)

    SegmenterRegistry.path("birefnet-lite").write_bytes(b"not a real model")
    pipeline = Pipeline(fonts, make_segmenter=lambda path, *a, **k: segmenter)
    fm = pipeline.masker.find(
        img,
        mask_options(
            crop=[0.5, 0, 1, 1],  # the right half
            model={"mask": "auto", "alpha": "alpha", "model": "birefnet-lite"}[source],
            mask_path=mask if source == "mask" else None,
        ),
        use_cache=False,
        log=lambda *_: None,
    )
    # only the right figure, where it is in the picture
    assert pipeline.morphology.bbox(fm.clean) == pytest.approx(
        (370, 50, 530, 350), abs=3
    )
    if source == "model":
        assert seen == [(300, 400)]  # the model saw only the crop
