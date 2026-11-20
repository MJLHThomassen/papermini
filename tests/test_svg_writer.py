"""Tests of writing pieces as SVG files."""


def test_one_svg_per_numbered_copy(
    output, fonts, goblin_figure, tmp_path, numbered_mini
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
    r = output.svg_reader.read(tmp_path / "goblin-2.svg")
    assert [(t.kind, t.text) for t in r.extra] == [("number", "2"), ("number", "2")]
    assert (
        not r.numbered
    )  # the numbers are in the file: a sheet prints them as they are
    lay = output.packer.pack([(r, 2)])
    assert [
        [t.text for t in p.mini.text_items(fonts) if t.kind == "number"]
        for p in lay.placements
    ] == [["2", "2"], ["2", "2"]]
