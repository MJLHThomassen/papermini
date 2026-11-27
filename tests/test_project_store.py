"""Tests of saving and loading project files."""

from dataclasses import replace
from pathlib import Path

import pytest

from papermini import __version__
from papermini.project import sizes
from papermini.project.figure_entry import FigureEntry
from papermini.project.figure_settings import FigureSettings
from papermini.project.project import Project
from papermini.project.sheet_settings import SheetSettings


def test_a_project_reads_back_as_it_was_saved(tmp_path, project_store):
    (tmp_path / "img").mkdir()
    a, b = tmp_path / "img" / "a.png", tmp_path / "img" / "b.png"
    p = Project(
        output="out",
        sheet=SheetSettings(paper="letter", title="Crypt"),
        figures=[
            FigureEntry(a, FigureSettings(label="Red dragon", copies=2)),
            FigureEntry(
                b,
                FigureSettings(
                    size="custom",
                    height_mm=56,
                    crop=[0.08, 0, 0.92, 0.62],
                    double_sided=True,
                ),
                name="boss",
            ),
        ],
    )
    path = project_store.save(p, tmp_path / "proj.yaml")
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f"papermini: {__version__}\nformat: 1\n")
    assert "img/a.png" in text and str(tmp_path) not in text  # relative paths
    q = project_store.load(path)
    assert q.output == "out" and q.sheet.paper == "letter" and q.sheet.title == "Crypt"
    assert [f.image for f in q.figures] == [a.resolve(), b.resolve()]
    assert q.figures[0].settings == p.figures[0].settings
    assert q.figures[1].settings == p.figures[1].settings
    assert q.figures[1].name == "boss" and q.figures[1].svg_name() == "boss.svg"


def test_project_keeps_mask_and_model_paths_relative(tmp_path, project_store):
    for sub in ("img", "masks", "models", "proj"):
        (tmp_path / sub).mkdir()
    image = tmp_path / "img" / "hero.png"
    mask = tmp_path / "masks" / "hero-mask.png"
    model = tmp_path / "models" / "mine.onnx"
    p = Project(
        figures=[
            FigureEntry(image, FigureSettings(model="mask", mask=str(mask))),
            FigureEntry(image, FigureSettings(model=str(model))),
        ]
    )
    path = project_store.save(p, tmp_path / "proj" / "proj.yaml")
    text = path.read_text(encoding="utf-8")
    assert "../masks/hero-mask.png" in text and "../models/mine.onnx" in text
    assert str(tmp_path) not in text and tmp_path.as_posix() not in text
    q = project_store.load(path)
    assert q.figures[0].settings.mask == str(mask.resolve())
    assert q.figures[1].settings.model == str(model.resolve())


def test_a_figure_without_an_image_is_refused(tmp_path, project_store):
    path = tmp_path / "proj.yaml"
    path.write_text("figures:\n  - label: Goblin\n", encoding="utf-8")
    with pytest.raises(ValueError, match="every figure needs an 'image'"):
        project_store.load(path)


@pytest.mark.parametrize("key", ["image", "name", "mask", "model"])
def test_a_figure_value_that_is_not_text_is_refused(tmp_path, project_store, key):
    path = tmp_path / "proj.yaml"
    figure = {"image": "goblin.png", key: [42]}
    path.write_text(f"figures:\n  - {figure}\n", encoding="utf-8")
    with pytest.raises(
        ValueError, match=rf"^proj.yaml: a figure's '{key}' must be text, not \[42\]$"
    ):
        project_store.load(path)


def test_a_file_that_is_not_a_project_is_refused(tmp_path, project_store):
    path = tmp_path / "list.yaml"
    path.write_text("- a.png\n- b.png\n", encoding="utf-8")
    with pytest.raises(ValueError, match="^list.yaml is not a papermini project$"):
        project_store.load(path)


def test_settings_that_are_not_names_with_values_are_refused(tmp_path, project_store):
    path = tmp_path / "proj.yaml"
    for text in ("defaults: [42]\n", "figures:\n  - 42\n", "sheet: a4\n"):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match="settings are option names with values"):
            project_store.load(path)


def test_a_project_saved_by_1_0_still_opens(project_store):
    path = Path(__file__).parent / "fixtures" / "project-v1.0.yaml"
    p = project_store.load(path)
    assert p.output == "finished"
    assert p.sheet == SheetSettings(
        output="finished/print.pdf", paper="letter", copies=2, title="Dragon collection"
    )
    assert [f.image for f in p.figures] == [
        p.base / "images/dragon.png",
        p.base / "images/knight.png",
    ]
    # (no sizes: the built-in table; its own heights make each figure custom)
    assert p.sizes == sizes.BUILTIN
    assert [f.settings for f in p.figures] == [
        FigureSettings(
            size="custom", height_mm=45, strength=55, label="Red dragon", copies=3
        ),
        FigureSettings(
            size="custom", height_mm=38, strength=55, double_sided=False, copies=2
        ),
    ]
    assert p.figures[1].name == "blue-knight"


def test_project_format_defaults_to_one_and_rejects_newer(tmp_path, project_store):
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text("figures: [dragon.png]\n", encoding="utf-8")
    assert project_store.load(legacy).figures[0].image == tmp_path / "dragon.png"

    newer = tmp_path / "newer.yaml"
    newer.write_text("papermini: 2.1.0\nformat: 2\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        project_store.load(newer)
    assert str(e.value) == (
        f"newer.yaml was made by papermini 2.1.0 (project format 2), and "
        f"papermini {__version__} opens project format 1. Update papermini "
        "to open it."
    )

    hand_written = tmp_path / "hand.yaml"
    hand_written.write_text("format: 2\n", encoding="utf-8")
    with pytest.raises(
        ValueError, match=r"^hand.yaml uses a newer project format \(project format 2\)"
    ):
        project_store.load(hand_written)

    for bad in ("x", "true", "0"):
        (tmp_path / "bad.yaml").write_text(f"format: {bad}\n", encoding="utf-8")
        with pytest.raises(
            ValueError, match="project format must be a whole number from 1"
        ):
            project_store.load(tmp_path / "bad.yaml")


def test_errors_in_a_project_from_a_newer_papermini_say_so(tmp_path, project_store):
    """A newer papermini of the same format may save options this one does not know: the
    error then names the papermini that saved the project."""
    (tmp_path / "p.yaml").write_text(
        "papermini: 99.1.0\nformat: 1\nfigures:\n  - {image: a.png, sparkle: true}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as e:
        project_store.load(tmp_path / "p.yaml")
    assert str(e.value) == (
        f"p.yaml: a.png: unknown option(s) sparkle. The project was made by "
        f"papermini 99.1.0, which is newer than papermini {__version__}. "
        "Update papermini to open it."
    )
    # the same mistake in a project from an older papermini is just the error
    (tmp_path / "p.yaml").write_text(
        "papermini: 0.1.0\nformat: 1\nfigures:\n  - {image: a.png, sparkle: true}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as e:
        project_store.load(tmp_path / "p.yaml")
    assert str(e.value) == "p.yaml: a.png: unknown option(s) sparkle"


def test_sheet_copies_are_the_default_for_figures(tmp_path, project_store):
    (tmp_path / "p.yaml").write_text(
        "sheet: {copies: 3}\nfigures:\n  - a.png\n  - {image: b.png, copies: 1}\n",
        encoding="utf-8",
    )
    q = project_store.load(tmp_path / "p.yaml")
    assert [f.settings.copies for f in q.figures] == [3, 1]


def test_a_project_keeps_the_size_by_height_width_or_both(tmp_path, project_store):
    """A width alone scales by width; both stretch; the choice survives a save."""
    assert FigureSettings.from_dict({"width_mm": 30}).height_mm is None
    both = FigureSettings.from_dict({"width_mm": 30, "height_mm": 50})
    assert (both.height_mm, both.width_mm) == (50, 30)
    for bad in (
        {"height_mm": None},
        {"height_mm": 0},
        {"width_mm": -3},
        {"width_mm": "wide"},
    ):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)
    # stretched to the default height: the height is saved too, or reloading the
    # file would read "width alone"
    stretched = FigureSettings(size="custom", width_mm=30)
    assert stretched.to_dict(with_size=False) == {
        "size": "custom",
        "width_mm": 30,
        "height_mm": 32.0,
    }
    by_width = FigureSettings(size="custom", height_mm=None, width_mm=30)
    p = Project(
        figures=[
            FigureEntry(tmp_path / "a.png", stretched),
            FigureEntry(tmp_path / "b.png", by_width),
        ]
    )
    loaded = project_store.load(project_store.save(p, tmp_path / "p.yaml"))
    assert [f.settings for f in loaded.figures] == [stretched, by_width]


def test_the_readme_dragon_matches_its_photo(project_store):
    """Regression: the flying dragon of the README screenshots became Large (48 mm tall on
    a 50 mm base) while the photo under them shows it printed 36 mm tall on a 25 mm round
    base. The project must build the mini in the photo."""
    root = Path(__file__).resolve().parent.parent / "examples" / "dragons"
    assert (root / "dragon-flying-photo.jpg").is_file()
    fly = {f.image.name: f for f in project_store.load(root / "dragons.yaml").figures}[
        "dragon-flying.webp"
    ]
    s = fly.settings
    assert (s.height_mm, s.tab_shape, s.tab_radius_mm) == (36, "round", 12.5)
    assert (s.margin_color, s.tab_color, s.tab_overlap_mm) == ("#000000", "#000000", 4)


def test_a_project_keeps_its_tokens(
    tmp_path, transparent_figure, project_store, size_calculator
):
    img = transparent_figure(tmp_path / "goblin.png")
    tok_s = size_calculator.settings_with_size(
        {
            "kind": "token",
            "size": "large",
            "token_area": [0, 0, 1, 1],
            "token_text": "label_number",
            "token_text_style": "curved",
        }
    )
    mini_s = size_calculator.settings_with_size({"size": "large"})
    p = Project(figures=[FigureEntry(img, tok_s), FigureEntry(img, mini_s, "mini")])
    path = project_store.save(p, tmp_path / "p.yaml")
    text = path.read_text()
    assert (
        "token_area:\n  - 0" in text or "token_area:\n    - 0" in text
    )  # (a plain list)
    back = project_store.load(path)
    assert [f.settings for f in back.figures] == [tok_s, mini_s]
    saved = [f.settings.to_dict() for f in back.figures]
    assert saved[0]["token_diameter_mm"] == 50  # a token: its size's diameter
    assert "token_diameter_mm" not in saved[1]  # a mini: nothing about tokens


def test_a_project_cannot_list_a_folder(monsters, tmp_path, project_store):
    proj = tmp_path / "minis.yaml"
    proj.write_text("figures:\n  - image: Monsters\n")
    with pytest.raises(ValueError, match="Monsters is a folder"):
        project_store.load(proj)


def test_a_project_saves_its_table_and_every_figures_size(
    tmp_path, project_store, size_calculator
):
    table = replace(size_calculator.calculate(30), name="My 30 mm grid")
    fig = size_calculator.apply(FigureSettings(label="Ogre"), "large", table)
    p = Project(sizes=table, figures=[FigureEntry(tmp_path / "a.png", fig)])
    text = project_store.save(p, tmp_path / "p.yaml").read_text(encoding="utf-8")
    assert (
        "sizes:\n  preset: My 30 mm grid\n  grid_mm: 30.0\n  medium_mm: 32.0\n" in text
    )
    assert (
        "  large: {height_mm: 48.0, base_mm: 59.06, tab_width_mm: 59.06, "
        "tab_height_mm: 29.53}\n"
    ) in text  # a size per line
    assert "  size: large\n" in text and "  tab_width_mm: 59.06\n" in text
    q = project_store.load(tmp_path / "p.yaml")
    assert q.sizes == table and q.figures[0].settings == fig
    # a figure at Medium writes its size and values too
    p = Project(figures=[FigureEntry(tmp_path / "a.png", FigureSettings())])
    text = project_store.save(p, tmp_path / "m.yaml").read_text(encoding="utf-8")
    assert (
        "  size: medium\n  height_mm: 32.0\n" in text
        and "preset: Standard 1-inch" in text
    )


def test_a_project_without_a_table_uses_the_builtin_one(tmp_path, project_store):
    (tmp_path / "p.yaml").write_text(
        "figures:\n  - image: a.png\n    size: huge\n  - image: b.png\n"
        "  - image: c.png\n    size: small\n    tab_width_mm: 30\n",
        encoding="utf-8",
    )
    p = project_store.load(tmp_path / "p.yaml")
    assert p.sizes == sizes.BUILTIN
    assert [f.settings.size for f in p.figures] == ["huge", "medium", "custom"]
    assert p.figures[0].settings.height_mm == 64
    assert (p.figures[2].settings.height_mm, p.figures[2].settings.tab_width_mm) == (
        24,
        30,
    )


def test_a_bad_table_names_the_file(tmp_path, project_store):
    (tmp_path / "p.yaml").write_text(
        "sizes: {grid_mm: -1}\nfigures: []\n", encoding="utf-8"
    )
    with pytest.raises(
        ValueError, match=r"p\.yaml: sizes grid_mm must be a number above 0"
    ):
        project_store.load(tmp_path / "p.yaml")


def test_project_keeps_the_link_not_the_cached_file(
    fake_web, tmp_path, figure_bytes, project_store, images_from_web
):
    url = "https://example.com/goblin.png"
    fake_web[url] = figure_bytes()
    (tmp_path / "p.yaml").write_text(
        f"figures:\n  - image: {url}\n    strength: 50\n", encoding="utf-8"
    )
    proj = project_store.load(tmp_path / "p.yaml")
    f = proj.figures[0]
    assert (
        f.source == url
        and f.image == images_from_web.cached_image(url)
        and f.settings.strength == 50
    )
    assert f.display_name == "goblin"
    project_store.save(proj, tmp_path / "q.yaml")
    assert f"image: {url}" in (tmp_path / "q.yaml").read_text(encoding="utf-8")


def test_project_with_a_dead_link_says_which(fake_web, tmp_path, project_store):
    (tmp_path / "p.yaml").write_text(
        "figures: [https://example.com/gone.png]\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="gone.png: 404"):
        project_store.load(tmp_path / "p.yaml")


def test_a_projects_style_presets_read_back_as_they_were_saved(tmp_path, project_store):
    from papermini.project.style_preset import StylePreset

    dark = StylePreset("Dark tabs", {"tab_color": "#000000", "margin_mm": 2.0})
    p = Project(presets=[dark, StylePreset("Plain", {})])
    path = project_store.save(p, tmp_path / "proj.yaml")
    text = path.read_text(encoding="utf-8")
    assert "  Dark tabs: {tab_color: '#000000', margin_mm: 2.0}\n" in text
    assert project_store.load(path).presets == p.presets


def test_a_project_without_style_presets_writes_none(tmp_path, project_store):
    path = project_store.save(Project(), tmp_path / "proj.yaml")
    assert "presets" not in path.read_text(encoding="utf-8")
    assert project_store.load(path).presets == []


def test_a_project_with_a_style_preset_that_is_not_valid_is_refused(
    tmp_path, project_store
):
    path = tmp_path / "proj.yaml"
    path.write_text("presets:\n  Big: {height_mm: 50}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="style preset Big: height_mm is not part of"):
        project_store.load(path)
