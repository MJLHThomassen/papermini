"""Tests of the fonts: Times, the bundled fonts and the installed-font index."""

import os
import shutil

import pytest

from papermini.output.sheet import pack, write_pdf
from papermini.pipeline.style import Style
from papermini.support import fonts


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
    add("onlybold.ttf", "Only Bold", "Bold")  # no regular style: left out
    add("almendra.ttf", "Almendra")  # a bundled font: listed with those
    (folder / "broken.ttf").write_bytes(b"not a font")
    (folder / "notes.txt").write_text("not a font either")
    found = fonts.installed()
    assert list(found) == ["Fake Serif"]
    assert found["Fake Serif"].regular == folder / "fake.ttf"
    assert found["Fake Serif"].bold == folder / "fakebd.ttf"
    assert sorted(reads) == [
        "almendra.ttf",
        "broken.ttf",
        "fake.ttf",
        "fakebd.ttf",
        "onlybold.ttf",
    ]
    # the index in the cache folder: a new scan reads only new or changed files
    reads.clear()
    add("other.ttf", "Other Sans")
    st = (folder / "fake.ttf").stat()
    os.utime(folder / "fake.ttf", (st.st_atime, st.st_mtime + 10))
    assert list(fonts.installed(refresh=True)) == ["Fake Serif", "Other Sans"]
    assert sorted(reads) == ["fake.ttf", "other.ttf"]


def test_an_installed_font_is_found_and_printed(
    goblin_figure, font_folder, tmp_path, pipeline_mini, mask_options
):
    _, add, _ = font_folder
    add("fake.ttf", "Fake Serif")
    assert fonts.resolve("Fake Serif")[1]
    img, mask = goblin_figure
    m = pipeline_mini(
        img,
        mask=mask_options(mask_path=mask),
        label="Hero",
        style=Style(font="Fake Serif"),
    )
    assert m.style.font == "Fake Serif"
    pdf = write_pdf(pack([(m, 1)]), tmp_path / "s.pdf").read_bytes()
    assert b"Almendra" in pdf  # (the file behind the made-up name)


def test_a_font_family_reads_back_from_its_svg_name():
    assert fonts.svg_family("Times") == "Times New Roman, Times, serif"
    assert fonts.svg_family("Kalam") == "'Kalam', serif"
    assert fonts.svg_family("No Such Font") == "Times New Roman, Times, serif"
    for family, name in (
        ("'Kalam', serif", "Kalam"),
        ('"Fira Sans", sans-serif', "Fira Sans"),
        ("Times New Roman, Times, serif", "Times"),
        ("serif", "Times"),
        ("", "Times"),
    ):
        assert fonts.from_svg_family(family) == name
