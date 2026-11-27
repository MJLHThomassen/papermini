"""Tests of the command line: its commands and their options."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from papermini import cli
from papermini.cli import main
from papermini.project.figure_settings import FigureSettings

# region papermini add


def test_add_makes_a_project_file_with_the_images_and_their_settings(
    hero_figure, tmp_path, project_store, capsys
):
    img, mask = hero_figure
    proj = tmp_path / "minis.yaml"
    assert (
        main(
            [
                "add",
                str(proj),
                str(img),
                "--mask",
                str(mask),
                "--size",
                "large",
                "--label",
                "Hero",
                "--paper",
                "a3",
                "--sheet-margin-mm",
                "8",
            ]
        )
        == 0
    )
    assert "minis.yaml (1 figure)" in capsys.readouterr().out
    p = project_store.load(proj)
    (f,) = p.figures
    assert f.image == img and f.settings.size == "large" and f.settings.label == "Hero"
    assert f.settings.mask == str(mask)
    assert (p.sheet.paper, p.sheet.margin_mm) == ("a3", 8.0)
    assert not list(tmp_path.glob("*.svg"))  # nothing built


def test_add_appends_to_a_project_and_keeps_its_sheet(
    hero_figure, tmp_path, project_store
):
    img, _ = hero_figure
    proj = tmp_path / "minis.yaml"
    assert main(["add", str(proj), str(img), "--cut", "machine"]) == 0
    assert main(["add", str(proj), str(img), "--copies", "3"]) == 0
    p = project_store.load(proj)
    assert [f.settings.copies for f in p.figures] == [1, 3]
    assert p.sheet.cut == "machine"


def test_add_without_images_sets_the_sheet(tmp_path, project_store):
    proj = tmp_path / "minis.yaml"
    assert (
        main(["add", str(proj), "--paper-width-mm", "300", "--paper-height-mm", "200"])
        == 0
    )
    sheet = project_store.load(proj).sheet
    assert (sheet.paper, sheet.paper_width_mm, sheet.paper_height_mm) == (
        "custom",
        300.0,
        200.0,
    )
    assert main(["add", str(proj), "--paper", "letter"]) == 0
    sheet = project_store.load(proj).sheet
    assert (sheet.paper, sheet.paper_width_mm) == ("letter", None)


def test_add_a_folder_names_the_figures_that_share_a_name(
    monsters, tmp_path, project_store, capsys
):
    proj = tmp_path / "minis.yaml"
    assert main(["add", str(proj), str(monsters)]) == 0
    assert "Monsters: 5 images (2 other files skipped)" in capsys.readouterr().out
    names = [f.name for f in project_store.load(proj).figures]
    assert names == [None, None, None, "goblins-leader", "orcs-leader"]


def test_add_sets_the_grid_of_the_project(hero_figure, tmp_path, project_store):
    img, _ = hero_figure
    proj = tmp_path / "minis.yaml"
    assert main(["add", str(proj), str(img), "--grid-mm", "30"]) == 0
    p = project_store.load(proj)
    assert p.sizes.grid_mm == 30
    assert p.figures[0].settings.height_mm == 37.8  # 32 mm * 30 / 25.4


def test_add_refuses_a_project_file_that_is_not_yaml(hero_figure, tmp_path):
    img, _ = hero_figure
    with pytest.raises(SystemExit, match="a project file ends in .yaml"):
        main(["add", str(tmp_path / "minis.txt"), str(img)])


# endregion

# region papermini build: a project file


def test_build_writes_the_pieces_and_the_sheet(hero_figure, tmp_path):
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
    assert main(["build", str(tmp_path / "minis.yaml"), "--preview"]) == 0
    assert (tmp_path / "out" / "Hero.svg").exists()
    assert (tmp_path / "out" / "hero-double.svg").exists()
    assert (tmp_path / "out" / "sheet.pdf").exists()
    assert (tmp_path / "out" / "sheet.png").exists()


def test_build_cut_by_machine_builds_the_bleed(
    hero_figure, tmp_path, pipeline_mini, mask_options, read_svg
):
    img, mask = hero_figure
    (tmp_path / "p.yaml").write_text(
        f"output: out\nsheet:\n  output: out/s.pdf\n  cut: machine\n  bleed_mm: 1.5\n"
        f"figures:\n  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n"
        f"  - image: {img.as_posix()}\n    mask: {mask.as_posix()}\n    name: b\n",
        encoding="utf-8",
    )
    assert main(["build", str(tmp_path / "p.yaml")]) == 0
    assert (tmp_path / "out" / "s.pdf").exists() and (
        tmp_path / "out" / "s-cut.svg"
    ).exists()
    plain = pipeline_mini(img, mask=mask_options(mask_path=mask))
    bled = read_svg(tmp_path / "out" / "b.svg")
    assert bled.width_mm > plain.width_mm + 2  # built with the sheet's bleed


def test_tokens_and_minis_on_one_sheet(tmp_path, capsys, transparent_figure):
    transparent_figure(tmp_path / "goblin.png")
    (tmp_path / "p.yaml").write_text(
        "sheet: {output: sheet.pdf}\n"
        "figures:\n"
        "  - {image: goblin.png, model: alpha}\n"
        "  - {image: goblin.png, name: tok, model: alpha, kind: token, copies: 3,\n"
        "     token_text: number}\n"
    )
    assert cli.main(["build", str(tmp_path / "p.yaml")]) == 0
    assert "4 pieces" in capsys.readouterr().out
    assert (tmp_path / "minis" / "tok-3.svg").is_file()


def test_build_numbers_the_copies(goblin_figure, tmp_path, project_store):
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
    assert project_store.load(proj).figures[0].settings.copies == 4
    assert main(["build", str(proj)]) == 0
    assert sorted(p.name for p in (tmp_path / "out").glob("*.svg")) == [
        f"goblin-{i}.svg" for i in range(1, 5)
    ]


@pytest.fixture
def built(figure_builder, square_mini):
    """The ``command_line`` fixture's papermini build builds without a model: each
    image becomes a plain square figure. Returns the images it built."""
    images = []

    def fake_build(img, s, **k):
        images.append(Path(img))
        return square_mini(Path(img).stem, 20.0, 30.0, px_per_mm=4)

    figure_builder.make = fake_build
    return images


@pytest.fixture
def square_project(tmp_path, transparent_figure):
    """A project file with one figure, a goblin, whose sheet is on."""
    transparent_figure(tmp_path / "goblin.png")
    proj = tmp_path / "p.yaml"
    proj.write_text("figures:\n  - image: goblin.png\n", encoding="utf-8")
    return proj


@pytest.mark.parametrize(
    ("flags", "written"),
    [
        ([], ["minis/goblin.svg", "minis/sheet.pdf"]),
        (["--png"], ["minis/goblin.png"]),
        (["--sheet"], ["minis/sheet.pdf"]),
        (
            ["--svg", "--preview"],
            ["minis/goblin.svg", "minis/sheet.pdf", "minis/sheet.png"],
        ),
    ],
)
def test_build_writes_the_outputs_asked_for(
    built, command_line, square_project, flags, written
):
    assert command_line.run(["build", str(square_project), *flags]) == 0
    base = square_project.parent
    found = sorted(p.relative_to(base).as_posix() for p in (base / "minis").iterdir())
    assert found == written


def test_build_without_a_sheet_writes_the_pieces_only(
    built, command_line, square_project
):
    square_project.write_text(
        "sheet: {enabled: false}\nfigures:\n  - image: goblin.png\n", encoding="utf-8"
    )
    assert command_line.run(["build", str(square_project)]) == 0
    assert [p.name for p in (square_project.parent / "minis").iterdir()] == [
        "goblin.svg"
    ]


def test_build_writes_a_project_in_another_folder(
    built, command_line, square_project, tmp_path
):
    assert (
        command_line.run(
            ["build", str(square_project), "-o", str(tmp_path / "elsewhere")]
        )
        == 0
    )
    assert sorted(p.name for p in (tmp_path / "elsewhere").iterdir()) == [
        "goblin.svg",
        "sheet.pdf",
    ]


def test_build_sheet_flags_change_the_sheet_for_this_build_only(
    built, command_line, square_project, project_store, media_box_mm
):
    assert (
        command_line.run(["build", str(square_project), "--sheet", "--paper", "a3"])
        == 0
    )
    assert media_box_mm(square_project.parent / "minis" / "sheet.pdf") == (297, 420)
    assert project_store.load(square_project).sheet.paper == "a4"


def test_build_refuses_figure_flags_for_a_project(built, command_line, square_project):
    with pytest.raises(SystemExit, match="the figure flags are for images"):
        command_line.run(["build", str(square_project), "--label", "Goblin"])


def test_build_refuses_a_project_without_figures(tmp_path):
    (tmp_path / "p.yaml").write_text("output: out\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no 'figures' listed"):
        main(["build", str(tmp_path / "p.yaml")])


# endregion

# region papermini build: images


def test_build_reports_an_unknown_model(hero_figure, capsys):
    img, _ = hero_figure
    assert main(["build", str(img), "--model", "no-such-model", "--no-cache"]) == 2
    assert "unknown model" in capsys.readouterr().err


def test_build_names_the_flags_to_try_when_no_figure_is_found(tmp_path, capsys):
    Image.new("RGB", (300, 400), "white").save(tmp_path / "blank.png")
    Image.new("L", (300, 400), 0).save(tmp_path / "empty.png")
    argv = ["build", str(tmp_path / "blank.png"), "--model", "mask"]
    assert main([*argv, "--mask", str(tmp_path / "empty.png"), "--no-cache"]) == 2
    err = capsys.readouterr().err
    assert "found no figure" in err and "--strength" in err


def test_build_names_the_height_flag_for_a_figure_too_large_for_the_sheet(
    hero_figure, tmp_path, capsys
):
    img, mask = hero_figure
    argv = ["build", str(img), "--mask", str(mask), "--height-mm", "400", "--sheet"]
    assert main([*argv, "-o", str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert "does not fit on A4" in err and "--height-mm" in err


def test_build_makes_double_sided_minis_unless_told_not_to(
    hero_figure, tmp_path, read_svg
):
    """Double-sided is the default; --no-double-sided prints the front only."""
    img, mask = hero_figure
    for name, extra in (("both", []), ("front", ["--no-double-sided"])):
        out = str(tmp_path / f"{name}.svg")
        assert main(["build", str(img), "--mask", str(mask), "-o", out, *extra]) == 0
    both, front = read_svg(tmp_path / "both.svg"), read_svg(tmp_path / "front.svg")
    assert both.height_mm > 1.8 * front.height_mm  # front and back, one above the other


def test_build_width_alone_scales_by_width(
    hero_figure, tmp_path, pipeline_mini, params, mask_options, read_svg
):
    img, mask = hero_figure
    out = tmp_path / "w.svg"
    assert (
        main(
            [
                "build",
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
    by_h = pipeline_mini(img, params(double_sided=False), mask_options(mask_path=mask))
    # 25 mm wide at the image's proportions: the figure is 25 / aspect high, not
    # Medium's 32 mm (margin and tab stay the same, so compare the difference)
    assert r.height_mm - by_h.height_mm == pytest.approx(25 / by_h.aspect - 32, abs=0.5)


def test_build_images_cut_by_machine_writes_the_cut_file(hero_figure, tmp_path):
    img, mask = hero_figure
    assert (
        main(
            [
                "build",
                str(img),
                "--mask",
                str(mask),
                "--sheet",
                "--cut",
                "machine",
                "--marks",
                "silhouette",
                "--cut-folds",
                "-o",
                str(tmp_path / "out"),
            ]
        )
        == 0
    )
    assert (tmp_path / "out" / "minis.pdf").exists()
    svg = (tmp_path / "out" / "minis-cut.svg").read_text()
    assert 'id="registration"' in svg and 'id="cut"' in svg and 'id="fold"' in svg
    assert not (tmp_path / "out" / "hero.svg").exists()  # only the sheet was asked for


def test_no_command_opens_the_app(monkeypatch, command_line):
    """One program for both: without a command (double-clicked, or with files dropped on
    it) papermini opens the desktop app; with a command it runs the command line."""
    from papermini.gui.app import App

    opened = []
    monkeypatch.setattr(App, "run", lambda self, files: opened.append(list(files)) or 0)
    assert cli.main([]) == 0 and opened[-1] == []
    assert cli.main(["hero.png", "lair.yaml"]) == 0 and opened[-1] == [
        "hero.png",
        "lair.yaml",
    ]
    assert command_line.route(["build", "hero.png"]) == ["build", "hero.png"]
    assert command_line.route(["add", "p.yaml"]) == ["add", "p.yaml"]
    assert command_line.route(["--version"]) == ["--version"]
    assert command_line.route(["-psn_0_42"]) == [
        "gui"
    ]  # (older macOS adds a process id)


def test_build_tokens_on_the_command_line(tmp_path, transparent_figure):
    img = transparent_figure(tmp_path / "goblin.png")
    out = tmp_path / "out"
    assert (
        cli.main(
            [
                "build",
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
                "--svg",
                "--png",
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
                "build",
                str(img),
                "--model",
                "alpha",
                "--kind",
                "token",
                "--png",
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
        cli.main(["build", str(img), "--png-px", "100", "--png-dpi", "300"])
    with pytest.raises(SystemExit, match="--png-dpi must be above 0"):
        cli.main(["build", str(img), "--png-dpi", "0"])


def test_build_takes_the_paper_size_and_orientation(
    built, command_line, tmp_path, capsys, transparent_figure, media_box_mm
):
    img = transparent_figure(tmp_path / "goblin.png")
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
        out = tmp_path / "s"
        assert (
            command_line.run(["build", str(img), "--sheet", "-o", str(out)] + args) == 0
        )
        assert media_box_mm(out / "minis.pdf") == size
        assert f"1 page, {name})" in capsys.readouterr().out
    # a mat smaller than the paper: a note, and the sheet is still made
    assert (
        command_line.run(
            [
                "build",
                str(img),
                "--sheet",
                "-o",
                str(tmp_path / "m"),
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
            command_line.run(
                ["build", str(img), "--sheet", "-o", str(tmp_path / "x")] + args
            )


def test_build_takes_the_number_options(goblin_figure, tmp_path, read_svg):
    img, mask = goblin_figure
    assert (
        main(
            [
                "build",
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
    texts = read_svg(tmp_path / "goblin-3.svg").texts
    # (on the front tab, the back tab, which is the same as the front, and the back)
    assert [t for kind, t in texts if kind == "number"] == ["3", "3", "3"]


def test_build_a_folder_into_an_output_folder(
    monsters, tmp_path, built, command_line, capsys
):
    out = tmp_path / "out"
    assert command_line.run(["build", str(monsters), "-o", str(out)]) == 0
    assert "Monsters: 5 images (2 other files skipped)" in capsys.readouterr().out
    assert len(built) == 5
    svgs = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.svg"))
    assert svgs == [
        "goblins/goblin 10.svg",
        "goblins/goblin 2.svg",
        "goblins/leader.svg",
        "leader.svg",
        "orcs/leader.svg",
    ]  # the subfolders, inside -o DIR


def test_build_a_folder_next_to_its_images(monsters, built, command_line):
    assert command_line.run(["build", str(monsters), "--no-subfolders"]) == 0
    assert built == [monsters / "leader.png"]
    assert (monsters / "leader.svg").is_file()


def test_build_an_empty_folder(tmp_path, built, command_line):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no images to build"):
        command_line.run(["build", str(tmp_path / "empty")])


def test_build_one_file_only_for_one_image(monsters, tmp_path, built, command_line):
    with pytest.raises(SystemExit, match="only works with a single image"):
        command_line.run(["build", str(monsters), "-o", str(tmp_path / "a.svg")])


def test_build_prints_in_the_font_asked_for_or_in_arial(
    goblin_figure, tmp_path, capsys, read_svg
):
    img, mask = goblin_figure
    for name, font in (("kalam", "Kalam"), ("missing", "No Such Font")):
        out = str(tmp_path / f"{name}.svg")
        assert (
            main(["build", str(img), "--mask", str(mask), "--font", font, "-o", out])
            == 0
        )
    assert read_svg(tmp_path / "kalam.svg").font == "'Kalam', serif"
    assert read_svg(tmp_path / "missing.svg").font == "Arial, Helvetica, sans-serif"
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


@pytest.fixture
def build_disc(disc, read_svg):
    """Returns ``build_disc(out, *flags)``, which builds the disc single-sided at
    ``out`` and returns the piece's height: the figure, its margin and the tab below
    the fold."""
    img, mask = disc

    def build_disc(out, *flags) -> float:
        argv = ["build", str(img), "--mask", str(mask), "--no-double-sided"]
        assert main([*argv, "-o", str(out), *flags]) == 0
        return read_svg(out).height_mm

    return build_disc


def test_build_sizes_the_figure_by_creature_size_and_grid(
    disc, build_disc, tmp_path, capsys
):
    medium = build_disc(tmp_path / "m.svg")
    large = build_disc(tmp_path / "l.svg", "--size", "large")
    assert large - medium == pytest.approx((48 - 32) + (25 - 12.5), abs=0.3)
    capsys.readouterr()
    # a 30 mm grid: bases and heights scale with it
    grid = build_disc(tmp_path / "g.svg", "--size", "large", "--grid-mm", "30")
    assert grid - large == pytest.approx(
        (48 * 30 / 25.4 - 48) + (59.06 - 50) / 2, abs=0.3
    )
    # an explicit flag wins
    own = build_disc(tmp_path / "o.svg", "--size", "large", "--height-mm", "40")
    assert own - large == pytest.approx(40 - 48, abs=0.3)
    assert "wider" not in capsys.readouterr().err
    # a round Tiny figure is wider than half a square
    build_disc(tmp_path / "t.svg", "--size", "tiny")
    assert (
        "d.png: This figure is 16 mm wide, wider than its half a square"
        in capsys.readouterr().err
    )
    with pytest.raises(SystemExit, match="--grid-mm must be above 0"):
        main(["build", str(disc[0]), "--grid-mm", "0"])


def test_build_takes_the_color_options(red_disc, tmp_path):
    img, mask = red_disc
    out = tmp_path / "g.svg"
    assert (
        main(
            [
                "build",
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


def test_build_makes_a_mini_from_a_link_into_the_current_folder(
    fake_web, tmp_path, monkeypatch, figure_bytes
):
    url = "https://example.com/minis/hero.webp"
    fake_web[url] = figure_bytes("WEBP")
    monkeypatch.chdir(tmp_path)
    assert main(["build", url, "--model", "alpha"]) == 0
    assert (tmp_path / "hero.svg").is_file()  # here, not next to the cached download
    assert (
        main(["build", "https://example.com/nothing.png"]) == 2
    )  # a clear error, no traceback


def test_webp_file_works_like_any_other(figure_builder, tmp_path, figure_bytes):
    (tmp_path / "ogre.webp").write_bytes(figure_bytes("WEBP"))
    m = figure_builder.build(tmp_path / "ogre.webp", FigureSettings())
    assert m.name == "ogre" and abs(m.figure_height_mm - 32) < 0.5
    assert (
        main(["build", (tmp_path / "ogre.webp").as_uri()]) == 0
    )  # a file:// URI is a path
    assert (tmp_path / "ogre.svg").is_file()


def test_build_refuses_files_that_are_not_there(tmp_path):
    with pytest.raises(SystemExit, match="file not found"):
        main(["build", str(tmp_path / "nothing.png")])
    with pytest.raises(SystemExit, match="no files match"):
        main(["build", str(tmp_path / "*.png")])


# endregion
