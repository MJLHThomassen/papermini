"""Tests of building a figure's miniature from its settings."""

import pytest

from papermini.project.figure_settings import FigureSettings


def test_the_mask_model_needs_a_mask_image(figure_builder, hero_figure):
    img, mask = hero_figure
    m = figure_builder.build(
        img, FigureSettings(model="mask", mask=str(mask)), log=lambda *_: None
    )
    assert m.figure_height_mm == pytest.approx(32, abs=0.05)  # Medium
    with pytest.raises(ValueError, match="needs a mask image"):
        figure_builder.build(img, FigureSettings(model="mask"), log=lambda *_: None)


@pytest.mark.parametrize("kind", ["mini", "token"])
def test_a_build_asks_before_it_downloads_a_model_and_reports_progress(
    kind, hero_figure, fonts, fake_downloader
):
    """The download question and the progress callback reach the model downloads
    through every step of a build."""
    import numpy as np

    from papermini.pipeline.pipeline import Pipeline
    from papermini.pipeline.segmentation.download_hooks import DownloadHooks
    from papermini.pipeline.segmentation.model_error import ModelError
    from papermini.project.figure_builder import FigureBuilder

    def dark(*_a, **_k):  # a model that finds everything darker than mid-grey
        return lambda im: np.where(np.asarray(im.convert("L")) < 128, 255, 0).astype(
            np.uint8
        )

    builder = FigureBuilder(Pipeline(fonts, fake_downloader, dark))
    img, _ = hero_figure
    s = FigureSettings(kind=kind, model="birefnet-lite")
    asked, seen = [], []
    refuse = DownloadHooks(confirm=lambda m: asked.append(m) or False)
    with pytest.raises(ModelError, match="not downloaded"):
        builder.build(img, s, log=lambda *_: None, downloads=refuse)
    assert asked == ["birefnet-lite"] and fake_downloader.got == []

    allow = DownloadHooks(
        confirm=lambda m: asked.append(m) or True,
        progress=lambda done, total, _msg: seen.append((done, total)),
    )
    builder.build(img, s, log=lambda *_: None, downloads=allow)
    assert asked == ["birefnet-lite"] * 2
    assert fake_downloader.got == ["birefnet-lite.onnx"] and seen[-1] == (30, 30)
