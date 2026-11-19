"""Tests of writing pieces as SVG files and reading them back."""

import base64
import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from papermini.output.sheet import pack, write_pdf
from papermini.output.svg import read_svg, to_svg, write_svg, write_svgs
from papermini.pipeline import geometry as geo
from papermini.pipeline.mini import make_mini


def test_an_svg_reads_back_as_the_mini_it_was_written_from(hero_figure, tmp_path):
    img, mask = hero_figure
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


def test_an_unsmoothed_cut_line_reads_back_as_a_polygon(hero_figure, tmp_path):
    img, mask = hero_figure
    m = make_mini(
        img, geo.Params(), mask_path=mask, smooth_path=False, log=lambda *_: None
    )
    r = read_svg(write_svg(m, tmp_path / "hero.svg"))
    assert r.cut.controls is None
    assert np.allclose(r.cut.points, m.cut.points, atol=1e-3)


def test_the_svg_keeps_the_back_text_color(hero_figure, tmp_path):
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
    m = build_mini(img, s, log=lambda *_: None)
    svg = write_svg(m, tmp_path / "h.svg").read_text(encoding="utf-8")
    assert 'class="backtext"' in svg and 'fill="#c0a030"' in svg
    assert read_svg(tmp_path / "h.svg").style.back_text_color == "#c0a030"


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


def test_a_small_papermini_svg_reads(tmp_path):
    m = read_svg(_svg(tmp_path))  # (the form the cases below each break once)
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
def test_svgs_papermini_did_not_write_are_refused(tmp_path, part, value, error):
    with pytest.raises(ValueError, match=error):
        read_svg(_svg(tmp_path, **{part: value}))


def test_a_token_svg_reads_back(tmp_path, build_token, transparent_figure):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, label="Goblin", token_text="label_number")
    svg = to_svg(replace(m, number=2))
    assert (
        'class="tokentext"' in svg and 'stroke="none"' in svg
    )  # (no cut line printed)
    path = tmp_path / "t.svg"
    path.write_text(svg)
    back = read_svg(path)
    assert [t.text for t in back.text_items()] == ["Goblin", "2"]
    assert not back.style.cut_line
    lay = pack([(back, 2), (m, 1)], "a4")
    assert len(lay.placements) == 3
    write_pdf(lay, tmp_path / "sheet.pdf")


def test_one_svg_per_numbered_copy(goblin_figure, tmp_path, numbered_mini):
    plain = numbered_mini(goblin_figure)
    assert write_svgs(plain, tmp_path / "plain.svg", copies=3) == [
        tmp_path / "plain.svg"
    ]
    m = numbered_mini(goblin_figure, tab_front="number", back="number")
    out = write_svgs(m, tmp_path / "goblin.svg", copies=3)
    assert [p.name for p in out] == ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert [p.name for p in write_svgs(m, tmp_path / "one.svg")] == ["one-1.svg"]
    r = read_svg(tmp_path / "goblin-2.svg")
    assert [(t.kind, t.text) for t in r.extra] == [("number", "2"), ("number", "2")]
    assert (
        not r.numbered
    )  # the numbers are in the file: a sheet prints them as they are
    lay = pack([(r, 2)])
    assert [
        [t.text for t in p.mini.text_items() if t.kind == "number"]
        for p in lay.placements
    ] == [["2", "2"], ["2", "2"]]
