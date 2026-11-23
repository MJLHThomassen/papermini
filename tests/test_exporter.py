"""Tests of exporting the pieces of figures and the files of a sheet."""

import pytest
from PIL import Image


def test_pieces_are_written_in_each_format_asked_for(output, square_mini, tmp_path):
    m = square_mini("goblin", 20, 30)
    paths = output.exporter.pieces(m, tmp_path / "goblin.svg", ("svg", "png"), 1, 4.0)
    assert paths == [tmp_path / "goblin.svg", tmp_path / "goblin.png"]
    assert Image.open(tmp_path / "goblin.png").size == (80, 120)  # 4 px per mm
    assert output.exporter.pieces(m, tmp_path / "x.svg", ("png",), 1, 4.0) == [
        tmp_path / "x.png"
    ]


@pytest.mark.parametrize(
    ("cut", "cut_files"),
    [("hand", []), ("machine", ["s-cut.svg"])],
)
def test_the_sheet_gets_its_cut_files_only_when_cut_by_machine(
    output, square_mini, tmp_path, cut, cut_files
):
    lay = output.packer.pack([(square_mini(), 2)], cut=cut)
    files = output.exporter.sheet(lay, tmp_path / "s.pdf", "Goblins", False)
    assert files.pdf == tmp_path / "s.pdf" and files.pdf.is_file()
    assert [p.name for p in files.cut_files] == cut_files
    assert files.previews == []


def test_the_sheet_writes_only_the_files_asked_for(output, square_mini, tmp_path):
    lay = output.packer.pack([(square_mini(), 1)], cut="machine")
    files = output.exporter.sheet(
        lay,
        tmp_path / "s.pdf",
        "Goblins",
        True,
        write_pdf=False,
        write_previews=True,
    )
    assert files.pdf is None and not (tmp_path / "s.pdf").exists()
    assert [p.name for p in files.paths] == ["s-cut.svg", "s.png"]
    assert 'id="fold"' in files.cut_files[0].read_text(encoding="utf-8")
