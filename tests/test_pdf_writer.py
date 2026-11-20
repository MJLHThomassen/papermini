"""Tests of writing a sheet as a PDF."""

from papermini.project.figure_settings import FigureSettings
from papermini.project.settings import build_mini


def test_the_pdf_embeds_the_font_and_the_svg_names_it(
    output, pipeline, goblin_figure, tmp_path
):
    img, mask = goblin_figure
    s = FigureSettings(
        mask=str(mask), label="Hero", font="Almendra", back="text_number"
    )
    m = build_mini(img, s, pipeline=pipeline, log=lambda *_: None)
    assert m.style.font == "Almendra"
    pdf = output.pdf.write(
        output.packer.pack([(m, 2)]), tmp_path / "s.pdf"
    ).read_bytes()
    assert b"Almendra-Regular" in pdf and b"Almendra-Bold" in pdf  # (numbers are bold)
    svg = output.svg.write(m, tmp_path / "hero.svg").read_text(encoding="utf-8")
    assert "font-family=\"'Almendra', serif\"" in svg
    assert 'class="number"' in svg and 'font-weight="bold"' in svg
    assert output.svg_reader.read(tmp_path / "hero.svg").style.font == "Almendra"
    # Times: the names every program knows
    t = output.svg.write(
        build_mini(
            img,
            FigureSettings(mask=str(mask), label="Hero"),
            pipeline=pipeline,
            log=lambda *_: None,
        ),
        tmp_path / "t.svg",
    )
    assert 'font-family="Times New Roman, Times, serif"' in t.read_text(
        encoding="utf-8"
    )
    assert output.svg_reader.read(t).style.font == "Times"
