"""Numbered copies: numbers on the tabs and the back, one number per copy on the sheet and
one SVG file per copy."""

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini import geometry as geo
from papermini.cli import main
from papermini.mini import NUMBER_PLACEHOLDER, make_mini
from papermini.settings import FigureSettings, build_mini, load_project
from papermini.sheet import pack, write_pdf, write_previews
from papermini.svg import read_svg, write_svgs


@pytest.fixture
def figure(tmp_path):
    """A dark figure on white, plus its mask."""
    im = np.full((600, 400, 3), 255, np.uint8)
    cv2.rectangle(im, (120, 100), (280, 520), (40, 40, 40), -1)
    mask = np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)
    Image.fromarray(im).save(tmp_path / "goblin.png")
    Image.fromarray(mask).save(tmp_path / "goblin_mask.png")
    return tmp_path / "goblin.png", tmp_path / "goblin_mask.png"


def _mini(figure, **settings):
    img, mask = figure
    return build_mini(img, FigureSettings(mask=str(mask), label="Goblin", **settings),
                      log=lambda *_: None)


def _kinds(m, rot):
    return [(t.kind, t.text) for t in m.text_items() if t.rot == rot]


def test_a_mini_shows_its_number_only_where_chosen(figure):
    m = _mini(figure)
    assert not m.numbered and m.number_box is None
    assert _kinds(m, 0) == [("label", "Goblin")] and _kinds(m, 180)[0] == ("label", "Goblin")
    m = _mini(figure, tab_front="number", tab_back="label_number", back="blank")
    assert m.numbered
    assert _kinds(m, 0) == [("number", NUMBER_PLACEHOLDER)]          # (no copy number yet)
    assert _kinds(m, 180) == [("number", "#"), ("label", "Goblin")]
    m.number = 4
    assert [t.text for t in m.text_items() if t.kind == "number"] == ["4", "4"]
    assert all(t.bold for t in m.text_items() if t.kind == "number")


def test_number_and_label_share_the_tab(figure):
    """With both, the number goes above the label (towards the fold), at least as big."""
    m = _mini(figure, tab_front="label_number", tab_back="label_number", back="blank")
    m.number = 12
    for rot, towards_fold in ((0, -1), (180, 1)):
        num, label = [t for t in m.text_items() if t.rot == rot]
        assert (num.kind, label.kind) == ("number", "label")
        assert (num.cy - label.cy) * towards_fold > 0
        assert num.size_mm >= label.size_mm
        assert num.cx == pytest.approx(label.cx)
    # a number alone fills the tab's height (or width)
    alone = _mini(figure, tab_front="number", back="blank")
    alone.number = 12
    n = next(t for t in alone.text_items() if t.kind == "number")
    assert alone.label_size_mm < n.size_mm <= alone.tab_room[1] + 1e-6


def test_the_number_on_the_back(figure):
    m = _mini(figure, back="number")
    assert m.numbered and not m.texts
    cx, cy, w, h = m.number_box
    assert 0 < cy < m.height_mm / 2 and w > 0 and h > 0  # the back half is the top half
    m.number = 3
    back = [t for t in m.text_items() if t.kind == "number"]
    assert [(t.text, t.rot) for t in back] == [("3", 180.0)]
    assert back[0].size_mm > 2 * m.label_size_mm
    # with text: the number above the text (upside down, so further down the sheet)
    both = _mini(figure, back="text_number", back_text="Goblin boss")
    cx, cy, w, h = both.number_box
    assert both.texts and all(t[2] < cy - h / 2 for t in both.texts)


def test_the_sheet_numbers_the_copies(figure, tmp_path):
    a = _mini(figure, tab_front="number")
    b = _mini(figure, back="number")
    plain = _mini(figure)
    lay = pack([(a, 3), (b, 2), (plain, 2)])
    by_art = {}
    for p in lay.placements:
        by_art.setdefault(id(p.mini.art), []).append(p.mini.number)
    assert sorted(by_art[id(a.art)]) == [1, 2, 3]
    assert sorted(by_art[id(b.art)]) == [1, 2]
    assert by_art[id(plain.art)] == [None, None]
    assert a.number is None  # (the copies are new minis; the figure keeps no number)
    assert write_pdf(lay, tmp_path / "s.pdf").read_bytes()[:5] == b"%PDF-"
    assert write_previews(lay, tmp_path / "s.pdf")


def test_one_svg_per_numbered_copy(figure, tmp_path):
    plain = _mini(figure)
    assert write_svgs(plain, tmp_path / "plain.svg", copies=3) == [tmp_path / "plain.svg"]
    m = _mini(figure, tab_front="number", back="number")
    out = write_svgs(m, tmp_path / "goblin.svg", copies=3)
    assert [p.name for p in out] == ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert [p.name for p in write_svgs(m, tmp_path / "one.svg")] == ["one-1.svg"]
    r = read_svg(tmp_path / "goblin-2.svg")
    assert [(t.kind, t.text) for t in r.extra] == [("number", "2"), ("number", "2")]
    assert not r.numbered  # the numbers are in the file: a sheet prints them as they are
    lay = pack([(r, 2)])
    assert [[t.text for t in p.mini.text_items() if t.kind == "number"]
            for p in lay.placements] == [["2", "2"], ["2", "2"]]


def test_tab_options_validated():
    s = FigureSettings.from_dict({"tab_front": "number", "tab_back": "label_number"})
    assert (s.tab_front, s.tab_back) == ("number", "label_number")
    assert s.to_dict(with_size=False) == {"tab_front": "number", "tab_back": "label_number"}
    assert FigureSettings.from_dict({"back": "text_number"}).params().back == "text_number"
    for bad in ({"tab_front": "digits"}, {"tab_back": ""}, {"back": "numbers"}):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)


def test_cli_numbers(figure, tmp_path):
    img, mask = figure
    assert main(["make", str(img), "--mask", str(mask), "--tab-front", "number",
                 "--back", "text_number", "--copies", "3", "-o", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.glob("goblin*.svg")) == \
        ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert [t.text for t in read_svg(tmp_path / "goblin-3.svg").extra] == ["3", "3"]


def test_batch_numbers_the_copies(figure, tmp_path):
    img, mask = figure
    proj = tmp_path / "minis.yaml"
    proj.write_text(f"""output: out
sheet: {{copies: 2}}
figures:
  - image: {img.name}
    mask: {mask.name}
    tab_back: number
    copies: 4
""", encoding="utf-8")
    assert load_project(proj).figures[0].settings.copies == 4
    assert main(["batch", str(proj)]) == 0
    assert sorted(p.name for p in (tmp_path / "out").glob("*.svg")) == \
        [f"goblin-{i}.svg" for i in range(1, 5)]
