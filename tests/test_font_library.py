"""Tests of the fonts: Times, the bundled fonts and the installed-font index."""

import os
import shutil

import pytest

from papermini.output.sheet import pack, write_pdf
from papermini.pipeline.style import Style
from papermini.support.font_library import FontLibrary


@pytest.fixture
def fonts(tmp_path):
    """The fonts, with an installed-fonts folder of our own."""
    return FontLibrary(folders=[tmp_path / "fonts"])


@pytest.fixture
def font_folder(tmp_path, monkeypatch, fonts):
    """The installed-fonts folder of ``fonts``, with names read from a table instead of
    the files (the files are copies of a bundled font, so they can be printed with)."""
    folder = tmp_path / "fonts"
    folder.mkdir()
    names, reads = {}, []

    def read_name(path):
        reads.append(path.name)
        return names.get(path.name)

    def add(file, family, style="Regular"):
        shutil.copy(
            FontLibrary.FOLDER / "almendra" / "Almendra-Regular.ttf", folder / file
        )
        names[file] = (family, style)

    monkeypatch.setattr(fonts, "_read_name", read_name)
    return folder, add, reads


def test_the_bundled_fonts_come_with_their_licence(fonts):
    found = fonts.bundled()
    assert found[0] == FontLibrary.TIMES and found[0].regular is None
    assert [f.name for f in found[1:]] == list(FontLibrary.BUNDLED)
    for f in found[1:]:
        assert f.regular.is_file() and (f.bold is None or f.bold.is_file())
        assert (f.regular.parent / "OFL.txt").is_file()


def test_installed_fonts_are_indexed_once(fonts, font_folder):
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
    fonts, goblin_figure, font_folder, tmp_path, pipeline_mini, mask_options
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
    pdf = write_pdf(pack([(m, 1)]), tmp_path / "s.pdf", fonts).read_bytes()
    assert b"Almendra" in pdf  # (the file behind the made-up name)


def test_a_font_family_reads_back_from_its_svg_name(fonts):
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
        assert FontLibrary.from_svg_family(family) == name


def test_a_library_with_folders_of_its_own_looks_only_there(tmp_path):
    assert FontLibrary(folders=[tmp_path]).font_dirs() == [tmp_path]
    assert FontLibrary(folders=[]).font_dirs() == []


def test_image_fonts_draw_in_the_pieces_font_or_a_plain_one(fonts):
    kalam = fonts.image_font(40, "Kalam")
    assert kalam.getname()[0] == "Kalam"
    assert fonts.image_font(40, "Kalam", bold=True).getname()[1] == "Bold"
    assert fonts.image_font(40).getbbox("Hero")[2] > 0  # (a sans-serif of the system)


@pytest.mark.parametrize(
    "system, folder",
    [("win32", "Fonts"), ("darwin", "/Library/Fonts"), ("linux", "/usr/share/fonts")],
)
def test_installed_fonts_are_looked_for_in_the_systems_folders(
    monkeypatch, system, folder
):
    import sys
    from pathlib import Path

    monkeypatch.setattr(sys, "platform", system)
    dirs = FontLibrary().font_dirs()
    assert any(d.as_posix().endswith(folder) for d in dirs)
    assert all(isinstance(d, Path) for d in dirs)
