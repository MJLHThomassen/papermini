"""Tests of reading pieces back from their SVG files."""

import base64
import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image


def test_an_svg_reads_back_as_the_mini_it_was_written_from(
    output, hero_figure, tmp_path, pipeline_mini, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, mask=mask_options(mask_path=mask), label="Hero")
    p = output.svg.write(m, tmp_path / "hero.svg")
    r = output.svg_reader.read(p)
    assert r.width_mm == pytest.approx(m.width_mm, abs=1e-3)
    assert r.height_mm == pytest.approx(m.height_mm, abs=1e-3)
    assert r.label == "Hero"
    assert np.allclose(r.cut.points, m.cut.points, atol=1e-3)
    assert np.allclose(r.cut.controls, m.cut.controls, atol=1e-3)
    assert np.allclose(r.folds, m.folds, atol=1e-3)
    assert np.allclose(r.labels, m.labels, atol=1e-3)
    assert r.art.size == m.art.size


def test_an_unsmoothed_cut_line_reads_back_as_a_polygon(
    output, hero_figure, tmp_path, pipeline_mini, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, mask=mask_options(mask_path=mask), smooth_path=False)
    r = output.svg_reader.read(output.svg.write(m, tmp_path / "hero.svg"))
    assert r.cut.controls is None
    assert np.allclose(r.cut.points, m.cut.points, atol=1e-3)


def test_the_svg_keeps_the_back_text_color(output, pipeline, hero_figure, tmp_path):
    from papermini.project.figure_settings import FigureSettings
    from papermini.project.settings import build_mini

    img, mask = hero_figure
    s = FigureSettings(
        mask=str(mask),
        double_sided=True,
        back="text",
        back_text="Hero",
        label_color="#111111",
        back_text_color="#c0a030",
    )
    m = build_mini(img, s, pipeline=pipeline, log=lambda *_: None)
    svg = output.svg.write(m, tmp_path / "h.svg").read_text(encoding="utf-8")
    assert 'class="backtext"' in svg and 'fill="#c0a030"' in svg
    assert output.svg_reader.read(tmp_path / "h.svg").style.back_text_color == "#c0a030"


def _svg(
    tmp_path,
    width="10mm",
    view_box="0 0 10 10",
    href=None,
    cut='<path id="cut" d="M 0 0 L 10 0 L 10 10 Z"/>',
):
    """Writes a small SVG in papermini's form, with one part as given."""
    if href is None:
        buf = io.BytesIO()
        Image.new("RGBA", (1, 1)).save(buf, "PNG")
        href = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    path = tmp_path / "piece.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="10mm" viewBox="{view_box}">'
        f'<image id="art" xlink:href="{href}" width="10" height="10"/>{cut}</svg>',
        encoding="utf-8",
    )
    return path


def test_a_small_papermini_svg_reads(output, tmp_path):
    m = output.svg_reader.read(
        _svg(tmp_path)
    )  # (the form the cases below each break once)
    assert m.width_mm == m.height_mm == 10 and len(m.cut.points) == 3


@pytest.mark.parametrize(
    ("part", "value", "error"),
    [
        ("width", "ten", "cannot read length"),
        ("view_box", "0 0 10 20", "non-uniform viewBox"),
        ("cut", "", "is not a papermini SVG"),
        ("href", "art.png", "must be an embedded data: URI"),
        ("cut", '<path id="cut" d="m 0 0 l 10 0 z"/>', "relative path commands"),
        ("cut", '<path id="cut" d="0 0 L 10 0 Z"/>', "unexpected path data"),
    ],
)
def test_svgs_papermini_did_not_write_are_refused(output, tmp_path, part, value, error):
    with pytest.raises(ValueError, match=error):
        output.svg_reader.read(_svg(tmp_path, **{part: value}))


def test_a_token_svg_reads_back(
    output, fonts, tmp_path, build_token, transparent_figure
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, label="Goblin", token_text="label_number")
    svg = output.svg.svg(replace(m, number=2))
    assert (
        'class="tokentext"' in svg and 'stroke="none"' in svg
    )  # (no cut line printed)
    path = tmp_path / "t.svg"
    path.write_text(svg)
    back = output.svg_reader.read(path)
    assert [t.text for t in back.text_items(fonts)] == ["Goblin", "2"]
    assert not back.style.cut_line
    lay = output.packer.pack([(back, 2), (m, 1)], "a4")
    assert len(lay.placements) == 3
    output.pdf.write(lay, tmp_path / "sheet.pdf")
