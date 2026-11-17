"""Tests of the command line: its commands and their options."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini import cli
from papermini.cli import main
from papermini.output.svg import read_svg, write_svg
from papermini.pipeline import geometry as geo
from papermini.pipeline.mini import make_mini
from papermini.project.figure_settings import FigureSettings
from papermini.project.project_files import load_project


def test_batch_writes_the_minis_and_the_sheet(hero_figure, tmp_path):
    img, mask = hero_figure
    (tmp_path / "minis.yaml").write_text(
        "output: out\n"
        "sheet: {output: out/sheet.pdf, paper: letter, copies: 2}\n"
        "defaults: {height_mm: 40}\n"
        "figures:\n"
        f"  - image: {img.name}\n"
        f"    mask: {mask.name}\n"
        "    label: Hero\n"
        f"  - image: {img.name}\n"
        f"    mask: {mask.name}\n"
        "    name: hero-double\n"
        "    double_sided: true\n"
        "    copies: 1\n",
        encoding="utf-8",
    )
    assert main(["batch", str(tmp_path / "minis.yaml"), "--preview"]) == 0
    assert (tmp_path / "out" / "Hero.svg").exists()
    assert (tmp_path / "out" / "hero-double.svg").exists()
    assert (tmp_path / "out" / "sheet.pdf").exists()
    assert (tmp_path / "out" / "sheet.png").exists()


def test_make_reports_an_unknown_model(hero_figure, capsys):
    img, _ = hero_figure
    assert main(["make", str(img), "--model", "no-such-model", "--no-cache"]) == 2
    assert "unknown model" in capsys.readouterr().err


def test_cli_makes_double_sided_minis_unless_told_not_to(hero_figure, tmp_path):
    """Double-sided is the default; --no-double-sided prints the front only."""
    img, mask = hero_figure
    for name, extra in (("both", []), ("front", ["--no-double-sided"])):
        assert (
            main(
                [
                    "make",
                    str(img),
                    "--mask",
                    str(mask),
                    "-o",
                    str(tmp_path / f"{name}.svg"),
                ]
                + extra
            )
            == 0
        )
    both, front = read_svg(tmp_path / "both.svg"), read_svg(tmp_path / "front.svg")
    assert both.height_mm > 1.8 * front.height_mm  # front and back, one above the other


def test_cli_width_alone_scales_by_width(hero_figure, tmp_path):
    from papermini.project.figure_settings import FigureSettings

    img, mask = hero_figure
    out = tmp_path / "w.svg"
    assert (
        main(
            [
                "make",
                str(img),
                "--mask",
                str(mask),
                "--width-mm",
                "25",
                "--no-double-sided",
                "-o",
                str(out),
            ]
        )
        == 0
    )
    r = read_svg(out)
    by_h = make_mini(
        img,
        FigureSettings(double_sided=False).params(),
        mask_path=mask,
        log=lambda *_: None,
    )
    # 25 mm wide at the image's proportions: the figure is 25 / aspect high, not
    # Medium's 32 mm (margin and tab stay the same, so compare the difference)
    assert r.height_mm - by_h.height_mm == pytest.approx(25 / by_h.aspect - 32, abs=0.5)


def test_sheet_cut_by_machine_writes_the_cut_file(hero_figure, tmp_path):
    img, mask = hero_figure
    from papermini.cli import main

    assert (
        main(
            [
                "make",
                str(img),
                "--mask",
                str(mask),
                "--bleed-mm",
                "1",
                "-o",
                str(tmp_path / "hero.svg"),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "sheet",
                str(tmp_path / "hero.svg"),
                "-o",
                str(tmp_path / "s.pdf"),
                "--cut",
                "machine",
                "--marks",
                "silhouette",
                "--cut-folds",
            ]
        )
        == 0
    )
    assert (tmp_path / "s.pdf").exists()
    svg = (tmp_path / "s-cut.svg").read_text()
    assert 'id="registration"' in svg and 'id="cut"' in svg and 'id="fold"' in svg


def test_batch_cut_by_machine_builds_the_bleed(hero_figure, tmp_path):
    img, mask = hero_figure
    (tmp_path / "p.yaml").write_text(
        f"output: out\nsheet:\n  output: out/s.pdf\n  cut: machine\n  bleed_mm: 1.5\n"
        f"figures:\n  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n"
        f"  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n    name: b\n",
        encoding="utf-8",
    )
    from papermini.cli import main

    assert main(["batch", str(tmp_path / "p.yaml")]) == 0
    assert (tmp_path / "out" / "s.pdf").exists() and (
        tmp_path / "out" / "s-cut.svg"
    ).exists()
    from papermini.output.svg import read_svg

    plain = make_mini(img, geo.Params(), mask_path=mask, log=lambda *_: None)
    bled = read_svg(tmp_path / "out" / "b.svg")
    assert bled.width_mm > plain.width_mm + 2  # built with the sheet's bleed


def test_no_command_opens_the_app(monkeypatch):
    """One program for both: without a command (double-clicked, or with files dropped on
    it) papermini opens the desktop app; with a command it runs the command line."""
    import papermini.gui.app
    from papermini import cli

    opened = []
    monkeypatch.setattr(
        papermini.gui.app, "run", lambda files=None: opened.append(list(files)) or 0
    )
    assert cli.main([]) == 0 and opened[-1] == []
    assert cli.main(["hero.png", "lair.yaml"]) == 0 and opened[-1] == [
        "hero.png",
        "lair.yaml",
    ]
    assert cli.route(["make", "hero.png"]) == ["make", "hero.png"]
    assert cli.route(["--version"]) == ["--version"]
    assert cli.route(["-psn_0_42"]) == ["gui"]  # (older macOS adds a process id)


def test_make_tokens_on_the_command_line(tmp_path, capsys, transparent_figure):
    img = transparent_figure(tmp_path / "goblin.png")
    out = tmp_path / "out"
    assert (
        cli.main(
            [
                "make",
                str(img),
                "--model",
                "alpha",
                "--kind",
                "token",
                "--size",
                "large",
                "--token-text",
                "number",
                "--copies",
                "2",
                "--format",
                "both",
                "-o",
                str(out),
            ]
        )
        == 0
    )
    assert sorted(p.name for p in out.iterdir()) == [
        "goblin-1.png",
        "goblin-1.svg",
        "goblin-2.png",
        "goblin-2.svg",
    ]
    assert Image.open(out / "goblin-1.png").width == pytest.approx(
        512, abs=8
    )  # 2 squares
    assert (
        cli.main(
            [
                "make",
                str(img),
                "--model",
                "alpha",
                "--kind",
                "token",
                "--format",
                "png",
                "--png-dpi",
                "254",
                "-o",
                str(tmp_path / "d.png"),
            ]
        )
        == 0
    )
    assert Image.open(tmp_path / "d.png").width == pytest.approx(25.9 * 10, abs=3)
    with pytest.raises(SystemExit, match="not both"):
        cli.main(["make", str(img), "--png-px", "100", "--png-dpi", "300"])


def test_tokens_and_minis_on_one_sheet(tmp_path, capsys, transparent_figure):
    transparent_figure(tmp_path / "goblin.png")
    (tmp_path / "p.yaml").write_text(
        "sheet: {output: sheet.pdf}\n"
        "figures:\n"
        "  - {image: goblin.png, model: alpha}\n"
        "  - {image: goblin.png, name: tok, model: alpha, kind: token, copies: 3,\n"
        "     token_text: number}\n"
    )
    assert cli.main(["batch", str(tmp_path / "p.yaml")]) == 0
    assert "4 pieces" in capsys.readouterr().out
    assert (tmp_path / "minis" / "tok-3.svg").is_file()


def test_sheet_takes_the_paper_size_and_orientation(
    tmp_path, capsys, square_mini, media_box_mm
):
    svg = write_svg(square_mini("goblin", 60, 90), tmp_path / "goblin.svg")
    for args, size, name in (
        (["--paper", "a3", "--orientation", "landscape"], (420, 297), "A3 landscape"),
        (
            ["--paper-width-mm", "300", "--paper-height-mm", "200"],
            (300, 200),
            "300 x 200 mm",
        ),
        (["--paper", "legal"], (216, 356), "Legal"),
        ([], (210, 297), "A4"),
    ):
        out = tmp_path / "s.pdf"
        assert main(["sheet", str(svg), "-o", str(out)] + args) == 0
        assert media_box_mm(out) == size
        assert f"1 page, {name})" in capsys.readouterr().out
    # a mat smaller than the paper: a note, and the sheet is still made
    assert (
        main(
            [
                "sheet",
                str(svg),
                "-o",
                str(tmp_path / "m.pdf"),
                "--paper",
                "tabloid",
                "--cut",
                "machine",
                "--mat",
                "12x12",
            ]
        )
        == 0
    )
    assert (
        "note: Tabloid (279 × 432 mm) is bigger than the 12 × 12 in mat"
        in capsys.readouterr().out
    )
    for args, match in (
        (["--paper", "a4", "--paper-width-mm", "300"], "leave out --paper a4"),
        (
            ["--paper", "custom", "--paper-width-mm", "30", "--paper-height-mm", "300"],
            "--paper-width-mm must be from 50",
        ),
    ):
        with pytest.raises(SystemExit, match=match):
            main(["sheet", str(svg), "-o", str(tmp_path / "x.pdf")] + args)


def test_make_takes_the_number_options(goblin_figure, tmp_path):
    img, mask = goblin_figure
    assert (
        main(
            [
                "make",
                str(img),
                "--mask",
                str(mask),
                "--tab-front",
                "number",
                "--back",
                "text_number",
                "--copies",
                "3",
                "-o",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert sorted(p.name for p in tmp_path.glob("goblin*.svg")) == [
        "goblin-1.svg",
        "goblin-2.svg",
        "goblin-3.svg",
    ]
    assert [t.text for t in read_svg(tmp_path / "goblin-3.svg").extra] == ["3", "3"]


def test_batch_numbers_the_copies(goblin_figure, tmp_path):
    img, mask = goblin_figure
    proj = tmp_path / "minis.yaml"
    proj.write_text(
        f"""output: out
sheet: {{copies: 2}}
figures:
  - image: {img.name}
    mask: {mask.name}
    tab_back: number
    copies: 4
""",
        encoding="utf-8",
    )
    assert load_project(proj).figures[0].settings.copies == 4
    assert main(["batch", str(proj)]) == 0
    assert sorted(p.name for p in (tmp_path / "out").glob("*.svg")) == [
        f"goblin-{i}.svg" for i in range(1, 5)
    ]


@pytest.fixture
def made(monkeypatch, square_mini):
    """papermini make without a model: each image becomes a plain square figure."""
    built = []

    def fake_build(img, s, **k):
        built.append(Path(img))
        return square_mini(Path(img).stem, 20.0, 30.0, px_per_mm=4)

    monkeypatch.setattr(cli, "build_mini", fake_build)
    return built


def test_make_a_folder_into_an_output_folder(monsters, tmp_path, made, capsys):
    out = tmp_path / "out"
    assert cli.main(["make", str(monsters), "-o", str(out)]) == 0
    assert "Monsters: 5 images (2 other files skipped)" in capsys.readouterr().out
    assert len(made) == 5
    svgs = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.svg"))
    assert svgs == [
        "goblins/goblin 10.svg",
        "goblins/goblin 2.svg",
        "goblins/leader.svg",
        "leader.svg",
        "orcs/leader.svg",
    ]  # the subfolders, inside -o DIR


def test_make_a_folder_next_to_its_images(monsters, made):
    assert cli.main(["make", str(monsters), "--no-subfolders"]) == 0
    assert made == [monsters / "leader.png"]
    assert (monsters / "leader.svg").is_file()


def test_make_an_empty_folder(tmp_path, made):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no images to make"):
        cli.main(["make", str(tmp_path / "empty")])


def test_make_prints_in_the_font_asked_for_or_in_times(goblin_figure, tmp_path, capsys):
    img, mask = goblin_figure
    for name, font in (("kalam", "Kalam"), ("missing", "No Such Font")):
        assert (
            main(
                [
                    "make",
                    str(img),
                    "--mask",
                    str(mask),
                    "--font",
                    font,
                    "-o",
                    str(tmp_path / f"{name}.svg"),
                ]
            )
            == 0
        )
    assert read_svg(tmp_path / "kalam.svg").style.font == "Kalam"
    assert read_svg(tmp_path / "missing.svg").style.font == "Times"
    assert "No Such Font is not on this computer" in capsys.readouterr().out


@pytest.fixture
def disc(tmp_path):
    """A round figure (as wide as it is tall), with its own mask."""
    im = np.full((600, 600, 3), 255, np.uint8)
    cv2.circle(im, (300, 300), 250, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "d.png")
    Image.fromarray(np.where(im[..., 0] < 250, 255, 0).astype(np.uint8)).save(
        tmp_path / "m.png"
    )
    return tmp_path / "d.png", tmp_path / "m.png"


def _make(disc, out, *flags):
    img, mask = disc
    assert (
        main(
            [
                "make",
                str(img),
                "--mask",
                str(mask),
                "--no-double-sided",
                "-o",
                str(out),
                *flags,
            ]
        )
        == 0
    )
    return read_svg(out).height_mm  # the figure, its margin and the tab below the fold


def test_make_sizes_the_figure_by_creature_size_and_grid(disc, tmp_path, capsys):
    medium = _make(disc, tmp_path / "m.svg")
    large = _make(disc, tmp_path / "l.svg", "--size", "large")
    assert large - medium == pytest.approx((48 - 32) + (25 - 12.5), abs=0.3)
    capsys.readouterr()
    # a 30 mm grid: bases and heights scale with it
    grid = _make(disc, tmp_path / "g.svg", "--size", "large", "--grid-mm", "30")
    assert grid - large == pytest.approx(
        (48 * 30 / 25.4 - 48) + (59.06 - 50) / 2, abs=0.3
    )
    # an explicit flag wins
    own = _make(disc, tmp_path / "o.svg", "--size", "large", "--height-mm", "40")
    assert own - large == pytest.approx(40 - 48, abs=0.3)
    assert "wider" not in capsys.readouterr().err
    # a round Tiny figure is wider than half a square
    _make(disc, tmp_path / "t.svg", "--size", "tiny")
    assert (
        "d.png: This figure is 16 mm wide, wider than its half a square"
        in capsys.readouterr().err
    )
    with pytest.raises(SystemExit, match="--grid-mm must be above 0"):
        main(["make", str(disc[0]), "--grid-mm", "0"])


def test_make_takes_the_color_options(red_disc, tmp_path):
    img, mask = red_disc
    out = tmp_path / "g.svg"
    assert (
        main(
            [
                "make",
                str(img),
                "--mask",
                str(mask),
                "--greyscale",
                "--contrast",
                "20",
                "--no-double-sided",
                "-o",
                str(out),
            ]
        )
        == 0
    )
    assert out.exists()


def test_cli_makes_a_mini_from_a_link_into_the_current_folder(
    fake_web, tmp_path, monkeypatch, figure_bytes
):
    url = "https://example.com/minis/hero.webp"
    fake_web[url] = figure_bytes("WEBP")
    monkeypatch.chdir(tmp_path)
    assert main(["make", url, "--model", "alpha"]) == 0
    assert (tmp_path / "hero.svg").is_file()  # here, not next to the cached download
    assert (
        main(["make", "https://example.com/nothing.png"]) == 2
    )  # a clear error, no traceback


def test_webp_file_works_like_any_other(tmp_path, figure_bytes):
    from papermini.project.settings import build_mini

    (tmp_path / "ogre.webp").write_bytes(figure_bytes("WEBP"))
    m = build_mini(tmp_path / "ogre.webp", FigureSettings())
    assert m.name == "ogre" and abs(m.figure_height_mm - 32) < 0.5
    assert (
        main(["make", (tmp_path / "ogre.webp").as_uri()]) == 0
    )  # a file:// URI is a path
    assert (tmp_path / "ogre.svg").is_file()
