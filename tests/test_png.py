"""Tests of writing pieces as PNG files."""

import pytest

from papermini.output.png import piece_image, px_per_mm, write_pngs
from papermini.project.settings import build_mini


def test_a_piece_becomes_a_png_of_its_size(
    fonts, pipeline, tmp_path, build_token, transparent_figure, size_calculator
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, token_text="number")
    scale = px_per_mm(256, 25.4)
    im = piece_image(m, scale, fonts)
    assert im.width == pytest.approx(m.width_mm * scale, abs=1) and im.mode == "RGBA"
    assert im.getpixel((0, 0))[3] == 0  # transparent around it
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 255
    paths = write_pngs(m, tmp_path / "goblin.png", scale, fonts, 2)
    assert [p.name for p in paths] == ["goblin-1.png", "goblin-2.png"]
    mini = build_mini(
        img,
        size_calculator.settings_with_size({"model": "alpha"}),
        pipeline=pipeline,
        log=lambda *a: None,
    )
    assert piece_image(mini, scale, fonts).height == pytest.approx(
        mini.height_mm * scale, abs=1
    )
