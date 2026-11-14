"""Fonts: Times, the bundled fonts, the installed-font index and every output's font."""

import os
import shutil

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini import fonts
from papermini import geometry as geo
from papermini.cli import main
from papermini.mini import Style, fit_label_size, make_mini
from papermini.settings import FigureSettings, build_mini
from papermini.sheet import pack, write_pdf
from papermini.svg import read_svg, write_svg


@pytest.fixture
def figure(tmp_path):
    """A dark figure on white, plus its mask."""
    im = np.full((600, 400, 3), 255, np.uint8)
    cv2.rectangle(im, (120, 100), (280, 520), (40, 40, 40), -1)
    mask = np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(mask).save(tmp_path / "hero_mask.png")
    return tmp_path / "hero.png", tmp_path / "hero_mask.png"


@pytest.fixture
def font_folder(tmp_path, monkeypatch):
    """An installed-fonts folder of our own, with names read from a table instead of the
    files (the files are copies of a bundled font, so they can be printed with)."""
    folder = tmp_path / "fonts"
    folder.mkdir()
    names, reads = {}, []

    def read_name(path):
        reads.append(path.name)
        return names.get(path.name)

    def add(file, family, style="Regular"):
        shutil.copy(fonts.HERE / "almendra" / "Almendra-Regular.ttf", folder / file)
        names[file] = (family, style)

    monkeypatch.setattr(fonts, "font_dirs", lambda: [folder])
    monkeypatch.setattr(fonts, "_read_name", read_name)
    return folder, add, reads


def test_the_bundled_fonts_come_with_their_licence():
    found = fonts.bundled()
    assert found[0] == fonts.TIMES and found[0].regular is None
    assert [f.name for f in found[1:]] == list(fonts.BUNDLED)
    for f in found[1:]:
        assert f.regular.is_file() and (f.bold is None or f.bold.is_file())
        assert (f.regular.parent / "OFL.txt").is_file()


def test_installed_fonts_are_indexed_once(font_folder):
    folder, add, reads = font_folder
    add("fake.ttf", "Fake Serif")
    add("fakebd.ttf", "Fake Serif", "Bold")
    add("onlybold.ttf", "Only Bold", "Bold")       # no regular style: left out
    add("almendra.ttf", "Almendra")                # a bundled font: listed with those
    (folder / "broken.ttf").write_bytes(b"not a font")
    (folder / "notes.txt").write_text("not a font either")
    found = fonts.installed()
    assert list(found) == ["Fake Serif"]
    assert found["Fake Serif"].regular == folder / "fake.ttf"
    assert found["Fake Serif"].bold == folder / "fakebd.ttf"
    assert sorted(reads) == ["almendra.ttf", "broken.ttf", "fake.ttf", "fakebd.ttf",
                             "onlybold.ttf"]
    # the index in the cache folder: a new scan reads only new or changed files
    reads.clear()
    add("other.ttf", "Other Sans")
    st = (folder / "fake.ttf").stat()
    os.utime(folder / "fake.ttf", (st.st_atime, st.st_mtime + 10))
    assert list(fonts.installed(refresh=True)) == ["Fake Serif", "Other Sans"]
    assert sorted(reads) == ["fake.ttf", "other.ttf"]


def test_a_missing_font_prints_in_times(figure):
    assert fonts.resolve("No Such Font") == (fonts.TIMES, False)
    assert fonts.resolve("Almendra")[1] and fonts.resolve("Times")[1]
    assert fonts.pdf_name("No Such Font") == "Times-Roman"
    assert fonts.pdf_name("Times", bold=True) == "Times-Bold"
    img, mask = figure
    notes = []
    m = make_mini(img, geo.Params(), mask_path=mask, label="Hero",
                  style=Style(font="No Such Font"), log=notes.append)
    assert m.style.font == "Times"
    assert any("No Such Font is not on this computer" in n for n in notes)


def test_an_installed_font_is_found_and_printed(figure, font_folder, tmp_path):
    _, add, _ = font_folder
    add("fake.ttf", "Fake Serif")
    assert fonts.resolve("Fake Serif")[1]
    img, mask = figure
    m = make_mini(img, geo.Params(), mask_path=mask, label="Hero",
                  style=Style(font="Fake Serif"), log=lambda *_: None)
    assert m.style.font == "Fake Serif"
    pdf = write_pdf(pack([(m, 1)]), tmp_path / "s.pdf").read_bytes()
    assert b"Almendra" in pdf  # (the file behind the made-up name)


def test_the_font_changes_the_text_size():
    """Labels are measured in their own font: a wide font shrinks to fit sooner."""
    narrow = fit_label_size("Red dragon", 14.0, 3.4, "Times")
    wide = fit_label_size("Red dragon", 14.0, 3.4, "Uncial Antiqua")
    assert wide < narrow <= 3.4


def test_the_pdf_embeds_the_font_and_the_svg_names_it(figure, tmp_path):
    img, mask = figure
    s = FigureSettings(mask=str(mask), label="Hero", font="Almendra", back="text_number")
    m = build_mini(img, s, log=lambda *_: None)
    assert m.style.font == "Almendra"
    pdf = write_pdf(pack([(m, 2)]), tmp_path / "s.pdf").read_bytes()
    assert b"Almendra-Regular" in pdf and b"Almendra-Bold" in pdf  # (numbers are bold)
    svg = write_svg(m, tmp_path / "hero.svg").read_text(encoding="utf-8")
    assert "font-family=\"'Almendra', serif\"" in svg
    assert 'class="number"' in svg and 'font-weight="bold"' in svg
    assert read_svg(tmp_path / "hero.svg").style.font == "Almendra"
    # Times: the names every program knows
    t = write_svg(build_mini(img, FigureSettings(mask=str(mask), label="Hero"),
                             log=lambda *_: None), tmp_path / "t.svg")
    assert 'font-family="Times New Roman, Times, serif"' in t.read_text(encoding="utf-8")
    assert read_svg(t).style.font == "Times"


def test_svg_font_family_round_trip():
    assert fonts.svg_family("Times") == "Times New Roman, Times, serif"
    assert fonts.svg_family("Kalam") == "'Kalam', serif"
    assert fonts.svg_family("No Such Font") == "Times New Roman, Times, serif"
    for family, name in (("'Kalam', serif", "Kalam"), ('"Fira Sans", sans-serif', "Fira Sans"),
                         ("Times New Roman, Times, serif", "Times"), ("serif", "Times"),
                         ("", "Times")):
        assert fonts.from_svg_family(family) == name


def test_the_font_option():
    s = FigureSettings.from_dict({"font": "Kalam"})
    assert s.style().font == "Kalam" and s.to_dict(with_size=False) == {"font": "Kalam"}
    assert FigureSettings().style().font == "Times"
    assert FigureSettings.from_dict({"font": "No Such Font"}).font == "No Such Font"  # (kept)
    for bad in ("", "  ", 12):
        with pytest.raises(ValueError, match="font must be"):
            FigureSettings.from_dict({"font": bad})


def test_cli_font(figure, tmp_path, capsys):
    img, mask = figure
    for name, font in (("kalam", "Kalam"), ("missing", "No Such Font")):
        assert main(["make", str(img), "--mask", str(mask), "--font", font,
                     "-o", str(tmp_path / f"{name}.svg")]) == 0
    assert read_svg(tmp_path / "kalam.svg").style.font == "Kalam"
    assert read_svg(tmp_path / "missing.svg").style.font == "Times"
    assert "No Such Font is not on this computer" in capsys.readouterr().out
