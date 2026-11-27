"""Tests of writing a sheet as a PDF."""

from papermini.project.figure_settings import FigureSettings


def test_the_pdf_embeds_the_font_and_the_svg_names_it(
    output, figure_builder, goblin_figure, tmp_path
):
    img, mask = goblin_figure
    s = FigureSettings(
        mask=str(mask), label="Hero", font="Almendra", back="text_number"
    )
    m = figure_builder.build(img, s, log=lambda *_: None)
    assert m.style.font == "Almendra"
    pdf = output.pdf.write(
        output.packer.pack([(m, 2)]), tmp_path / "s.pdf"
    ).read_bytes()
    assert b"Almendra-Regular" in pdf and b"Almendra-Bold" in pdf  # (numbers are bold)
    svg = output.svg.write(m, tmp_path / "hero.svg").read_text(encoding="utf-8")
    assert "font-family=\"'Almendra', serif\"" in svg
    assert 'class="number"' in svg and 'font-weight="bold"' in svg
    # Arial, the default: the names every program knows
    t = output.svg.write(
        figure_builder.build(
            img,
            FigureSettings(mask=str(mask), label="Hero"),
            log=lambda *_: None,
        ),
        tmp_path / "t.svg",
    )
    assert 'font-family="Arial, Helvetica, sans-serif"' in t.read_text(encoding="utf-8")
