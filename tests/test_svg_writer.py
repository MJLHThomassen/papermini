"""Tests of writing pieces as SVG files."""

import base64
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest
from PIL import Image

from papermini.output.svg_format import SvgFormat

SVG = "{http://www.w3.org/2000/svg}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _attr(root: ET.Element, path: str, name: str) -> str:
    """The attribute ``name`` of the element at ``path`` under ``root``, which both
    must have."""
    element = root if path == "." else root.find(path)
    assert element is not None and element.get(name) is not None
    return element.get(name) or ""


def test_one_svg_per_numbered_copy(
    goblin_figure, tmp_path, numbered_mini, output, read_svg
):
    plain = numbered_mini(goblin_figure)
    assert output.svg.write_copies(plain, tmp_path / "plain.svg", copies=3) == [
        tmp_path / "plain.svg"
    ]
    m = numbered_mini(goblin_figure, tab_front="number", back="number")
    out = output.svg.write_copies(m, tmp_path / "goblin.svg", copies=3)
    assert [p.name for p in out] == ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert [p.name for p in output.svg.write_copies(m, tmp_path / "one.svg")] == [
        "one-1.svg"
    ]
    texts = read_svg(tmp_path / "goblin-2.svg").texts
    assert [t for kind, t in texts if kind == "number"] == ["2", "2"]


def test_the_svg_holds_the_piece(
    output, hero_figure, tmp_path, pipeline_mini, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, mask=mask_options(mask_path=mask), label="Hero")
    root = ET.parse(output.svg.write(m, tmp_path / "hero.svg")).getroot()
    f = SvgFormat.number
    assert _attr(root, ".", "width") == f"{f(m.width_mm)}mm"
    assert _attr(root, ".", "viewBox") == f"0 0 {f(m.width_mm)} {f(m.height_mm)}"
    assert root.findtext(f"{SVG}title") == "Hero"
    d = _attr(root, f"{SVG}path[@id='cut']", "d")
    assert d == " ".join(str(command) for command in SvgFormat.path_d(m.cut))
    assert re.fullmatch(r"M [\d. ]+( C [\d. ]+)+ Z ?", d)
    folds = root.findall(f"{SVG}line[@class='fold']")
    assert [
        (float(_attr(ln, ".", "x1")), float(_attr(ln, ".", "y1"))) for ln in folds
    ] == [pytest.approx((x0, y), abs=1e-3) for x0, _, y in m.folds]
    href = _attr(root, f"{SVG}image[@id='art']", XLINK_HREF)
    art = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1])))
    assert href.startswith("data:image/png;base64,") and art.size == m.art.size


def test_an_unsmoothed_cut_line_is_written_with_straight_lines(
    output, hero_figure, tmp_path, pipeline_mini, mask_options
):
    img, mask = hero_figure
    m = pipeline_mini(img, mask=mask_options(mask_path=mask), smooth_path=False)
    root = ET.parse(output.svg.write(m, tmp_path / "hero.svg")).getroot()
    d = _attr(root, f"{SVG}path[@id='cut']", "d")
    assert "C" not in d and d.count("L") == len(m.cut.points) - 1
    assert d.rstrip().endswith("Z")


def test_the_svg_keeps_the_back_text_color(
    output, figure_builder, hero_figure, tmp_path
):
    from papermini.project.figure_settings import FigureSettings

    img, mask = hero_figure
    s = FigureSettings(
        mask=str(mask),
        double_sided=True,
        back="text",
        back_text="Hero",
        label_color="#111111",
        back_text_color="#c0a030",
    )
    m = figure_builder.build(img, s, log=lambda *_: None)
    svg = output.svg.write(m, tmp_path / "h.svg").read_text(encoding="utf-8")
    assert 'class="backtext"' in svg and 'fill="#c0a030"' in svg


def test_a_token_svg_holds_its_text_and_no_cut_line(
    output, tmp_path, build_token, transparent_figure, read_svg
):
    img = transparent_figure(tmp_path / "goblin.png")
    m = build_token(img, label="Goblin", token_text="label_number")
    path = tmp_path / "t.svg"
    path.write_text(output.svg.svg(replace(m, number=2)), encoding="utf-8")
    assert read_svg(path).texts == [("tokentext", "Goblin"), ("tokentext", "2")]
    root = ET.parse(path).getroot()
    assert _attr(root, f"{SVG}path[@id='cut']", "stroke") == "none"  # (no cut line)


def test_text_with_markup_characters_stays_valid_svg(
    output, hero_figure, tmp_path, pipeline_mini, mask_options, read_svg
):
    img, mask = hero_figure
    label = 'Fire & <Ice> "1"'
    m = pipeline_mini(img, mask=mask_options(mask_path=mask), label=label)
    path = output.svg.write(m, tmp_path / "hero.svg")
    assert ET.parse(path).getroot().findtext(f"{SVG}title") == label
    assert ("label", label) in read_svg(path).texts
