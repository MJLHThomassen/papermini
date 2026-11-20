"""Characterisation tests of the options: every command-line flag with its default,
the setting each flag fills in, and where docs/reference.md describes each setting.
They record today's behaviour, gaps included, so that a refactor of the options can't
drop or rename one unnoticed. The reference is also checked against the options: the
label, default and choices it gives each setting."""

import argparse
import itertools
import re
from dataclasses import fields
from pathlib import Path

import pytest

from papermini import cli
from papermini.output.svg import write_svg
from papermini.project.figure_settings import FIGURE_OPTIONS, FigureSettings
from papermini.project.option_flags import OptionFlags
from papermini.project.sheet_settings import SheetSettings

REFERENCE = Path(__file__).parents[1] / "docs" / "reference.md"
SHEET_FIELDS = {f.name for f in fields(SheetSettings)}

# region flags

# Every flag of every command: (command, flag, option it sets, its default, a value to
# give it or None for a flag that takes none, the option that value gives).
FLAGS = [
    ("make", "--no-subfolders", "no_subfolders", False, None, True),
    ("make", "-o", "output", None, "out", "out"),
    ("make", "--output", "output", None, "out", "out"),
    ("make", "--format", "format", "svg", "png", "png"),
    ("make", "--png-px", "png_px", None, "128", 128.0),
    ("make", "--png-dpi", "png_dpi", None, "150", 150.0),
    ("make", "--bleed-mm", "bleed_mm", 0.0, "1", 1.0),
    ("make", "--copies", "copies", 1, "3", 3),
    ("make", "--kind", "kind", "mini", "token", "token"),
    ("make", "--size", "size", None, "large", "large"),
    ("make", "--grid-mm", "grid_mm", None, "30", 30.0),
    ("make", "--height-mm", "height_mm", None, "40", 40.0),
    ("make", "--width-mm", "width_mm", None, "20", 20.0),
    ("make", "--margin-mm", "margin_mm", 1.6, "2.5", 2.5),
    ("make", "--smooth-mm", "smooth_mm", 0.6, "1.2", 1.2),
    ("make", "--margin-fill", "margin_fill", "color", "image", "image"),
    ("make", "--margin-color", "margin_color", "#ffffff", "#123456", "#123456"),
    ("make", "--tab-shape", "tab_shape", "square", "round", "round"),
    ("make", "--tab-color", "tab_color", "#ffffff", "#3b6e2a", "#3b6e2a"),
    ("make", "--tab-width-mm", "tab_width_mm", None, "30", 30.0),
    ("make", "--tab-radius-mm", "tab_radius_mm", None, "20", 20.0),
    ("make", "--tab-height-mm", "tab_height_mm", None, "15", 15.0),
    ("make", "--tab-overlap-mm", "tab_overlap_mm", 0.0, "3", 3.0),
    ("make", "--fold-mm", "fold_mm", 0.0, "2", 2.0),
    ("make", "--no-tab", "no_tab", False, None, True),
    ("make", "--double-sided", "double_sided", None, None, True),
    ("make", "--no-double-sided", "double_sided", None, None, False),
    ("make", "--back", "back", "mirror", "text", "text"),
    ("make", "--back-text", "back_text", None, "Stats", "Stats"),
    ("make", "--back-color", "back_color", "#ffffff", "#eeeeee", "#eeeeee"),
    ("make", "--back-text-color", "back_text_color", "#2f5597", "#111111", "#111111"),
    ("make", "--token-diameter-mm", "token_diameter_mm", None, "40", 40.0),
    ("make", "--token-area", "token_area", None, "0.1,0.2,0.9,1", "0.1,0.2,0.9,1"),
    ("make", "--token-fill", "token_fill", "color", "image", "image"),
    ("make", "--token-fill-color", "token_fill_color", "#ffffff", "#222222", "#222222"),
    ("make", "--token-border-mm", "token_border_mm", 2.0, "3", 3.0),
    (
        "make",
        "--token-border-color",
        "token_border_color",
        "#000000",
        "#333333",
        "#333333",
    ),
    ("make", "--token-cut-line", "token_cut_line", False, None, True),
    ("make", "--token-outline", "token_outline", False, None, True),
    ("make", "--token-text", "token_text", "none", "label", "label"),
    ("make", "--token-text-style", "token_text_style", "nameplate", "curved", "curved"),
    ("make", "--token-text-color", "token_text_color", "#ffffff", "#444444", "#444444"),
    ("make", "--token-text-mm", "token_text_mm", 2.5, "4", 4.0),
    ("make", "--greyscale", "greyscale", False, None, True),
    ("make", "--brightness", "brightness", 0, "10", 10),
    ("make", "--contrast", "contrast", 0, "20", 20),
    ("make", "--saturation", "saturation", 0, "-30", -30),
    ("make", "--hue", "hue", 0, "90", 90),
    ("make", "--model", "model", "auto", "birefnet", "birefnet"),
    ("make", "--mask", "mask", None, "m.png", "m.png"),
    ("make", "--crop", "crop", None, "0.1,0,0.9,1", "0.1,0,0.9,1"),
    ("make", "--strength", "strength", 40, "60", 60),
    ("make", "--fill-gaps", "fill_gaps", None, "7", 7),
    ("make", "--keep-all", "keep_all", False, None, True),
    ("make", "--min-area", "min_area", 1000, "500", 500),
    ("make", "--no-cache", "no_cache", False, None, True),
    ("make", "--label", "label", None, "Hero", "Hero"),
    ("make", "--tab-front", "tab_front", "label", "number", "number"),
    ("make", "--tab-back", "tab_back", "label", "label_number", "label_number"),
    ("make", "--dpi", "dpi", 300, "150", 150),
    ("make", "--simplify-mm", "simplify_mm", 0.15, "0.3", 0.3),
    ("make", "--no-smooth", "no_smooth", False, None, True),
    ("make", "--cut-color", "cut_color", "#000000", "#ff0000", "#ff0000"),
    ("make", "--cut-width-mm", "cut_width_mm", 0.3, "0.5", 0.5),
    ("make", "--label-color", "label_color", "#2f5597", "#555555", "#555555"),
    ("make", "--label-size-mm", "label_size_mm", 3.4, "4", 4.0),
    ("make", "--font", "font", "Times", "Kalam", "Kalam"),
    ("make", "--debug", "debug", False, None, True),
    ("sheet", "-o", "output", "minis.pdf", "out.pdf", "out.pdf"),
    ("sheet", "--output", "output", "minis.pdf", "out.pdf", "out.pdf"),
    ("sheet", "--copies", "copies", 1, "2", 2),
    ("sheet", "--paper", "paper", None, "a3", "a3"),
    ("sheet", "--paper-width-mm", "paper_width_mm", None, "200", 200.0),
    ("sheet", "--paper-height-mm", "paper_height_mm", None, "300", 300.0),
    ("sheet", "--orientation", "orientation", "portrait", "landscape", "landscape"),
    ("sheet", "--margin-mm", "margin_mm", 12.0, "8", 8.0),
    ("sheet", "--gap-mm", "gap_mm", 7.0, "5", 5.0),
    ("sheet", "--title", "title", "Paper miniatures", "Goblins", "Goblins"),
    ("sheet", "--preview", "preview", False, None, True),
    ("sheet", "--cut", "cut", "hand", "machine", "machine"),
    ("sheet", "--marks", "marks", "corners", "silhouette", "silhouette"),
    ("sheet", "--cut-folds", "cut_folds", False, None, True),
    ("sheet", "--mat", "mat", None, "12x12", "12x12"),
    ("batch", "--debug", "debug", False, None, True),
    ("batch", "--preview", "preview", False, None, True),
    ("batch", "--no-cache", "no_cache", False, None, True),
]

# what each command needs besides its options
POSITIONALS = {"make": ["a.png"], "sheet": ["a.svg"], "batch": ["a.yaml"], "gui": []}

# the flags of papermini itself, before a command
TOP_LEVEL_FLAGS = ["--version"]


def _flag_id(row) -> str:
    return f"{row[0]} {row[1]}"


@pytest.fixture
def help_flags(capsys):
    """List the flags that ``papermini [command] --help`` shows, without -h itself."""

    def help_flags(*command: str) -> list[str]:
        with pytest.raises(SystemExit):
            cli.main([*command, "--help"])
        found = set()
        for line in capsys.readouterr().out.splitlines():
            if re.match(r"  -", line):  # an option, not its wrapped help text
                invocation = re.split(r"\s{2,}", line.strip())[0]
                found |= {part.split()[0] for part in invocation.split(", ")}
        return sorted(found - {"-h", "--help"})

    return help_flags


@pytest.mark.parametrize("command", sorted(POSITIONALS))
def test_each_command_has_exactly_its_flags(help_flags, command):
    assert help_flags(command) == sorted(f for c, f, *_ in FLAGS if c == command)


def test_papermini_has_exactly_its_own_flags(help_flags):
    assert help_flags() == TOP_LEVEL_FLAGS


@pytest.mark.parametrize("row", FLAGS, ids=_flag_id)
def test_each_flag_keeps_its_default(row, project_store, size_calculator, pipeline):
    command, _, dest, default, _, _ = row
    parser = cli.build_parser(size_calculator, project_store, pipeline)
    got = getattr(parser.parse_args([command, *POSITIONALS[command]]), dest)
    assert (type(got), got) == (type(default), default)


@pytest.mark.parametrize("row", FLAGS, ids=_flag_id)
def test_each_flag_sets_its_option(row, project_store, size_calculator, pipeline):
    command, flag, dest, _, given, parsed = row
    argv = [command, flag, *([] if given is None else [given]), *POSITIONALS[command]]
    parser = cli.build_parser(size_calculator, project_store, pipeline)
    got = getattr(parser.parse_args(argv), dest)
    assert (type(got), got) == (type(parsed), parsed)


# endregion

# region figure settings


# The settings a flag's value gives where it differs from the parsed option.
FIGURE_SETTING_VALUES = {"token_area": [0.1, 0.2, 0.9, 1.0]}
# (--crop keeps the text as given; --token-area becomes a list of fractions)

# FigureSettings fields that papermini make has no flag for.
FIGURE_FIELDS_WITHOUT_FLAG: set[str] = set()


class _Built(Exception):
    """Raised by the fake build with what it was given, to stop papermini make there."""

    def __init__(self, settings: FigureSettings, options: dict):
        super().__init__()
        self.settings, self.options = settings, options


@pytest.fixture
def make(monkeypatch, tmp_path):
    """Run papermini make with the flags given on an image, and return the settings and
    the build options it would build the figure with."""

    def fake_build(img, s, **options):
        raise _Built(s, options)

    monkeypatch.setattr(cli, "build_mini", fake_build)
    image = tmp_path / "a.png"
    image.write_bytes(b"")

    def make(*flags: str) -> _Built:
        with pytest.raises(_Built) as built:
            cli.main(["make", str(image), *flags])
        return built.value

    return make


def _non_default_flag(command: str, dest: str, default):
    """Return the row of FLAGS that gives ``dest`` a value other than ``default``."""
    return next(
        r for r in FLAGS if r[0] == command and r[2] == dest and r[5] != default
    )


def test_every_figure_setting_has_a_make_flag():
    make_options = {dest for c, _, dest, *_ in FLAGS if c == "make"}
    assert FIGURE_OPTIONS - make_options == FIGURE_FIELDS_WITHOUT_FLAG


@pytest.mark.parametrize("name", sorted(FIGURE_OPTIONS - FIGURE_FIELDS_WITHOUT_FLAG))
def test_each_make_flag_reaches_the_figure_settings(make, name):
    default = getattr(FigureSettings(), name)
    _, flag, _, _, given, parsed = _non_default_flag("make", name, default)
    expected = FIGURE_SETTING_VALUES.get(name, parsed)
    assert expected != default
    built = make(flag, *([] if given is None else [given]))
    assert getattr(built.settings, name) == expected


@pytest.mark.parametrize(
    ("flags", "option", "expected"),
    [
        (["--bleed-mm", "1"], "bleed_mm", 1.0),
        (["--no-cache"], "use_cache", False),
    ],
)
def test_make_flags_outside_the_settings_reach_the_build(make, flags, option, expected):
    assert make(*flags).options[option] == expected


def test_make_debug_writes_next_to_the_image(make, tmp_path):
    assert make("--debug").options["debug_dir"] == tmp_path / "debug"


def test_make_grid_scales_the_creature_size_to_a_tenth_of_a_mm(make):
    assert make("--grid-mm", "30").settings.height_mm == 37.8  # 32 mm * 30 / 25.4


# endregion

# region sheet settings

# SheetSettings fields that papermini sheet has no flag for (a project file sets them).
SHEET_FIELDS_WITHOUT_FLAG = {"bleed_mm", "enabled"}

# papermini sheet flags named after a SheetSettings field whose value goes to the
# sheet directly and leaves that field at its default.
SHEET_FLAGS_OUTSIDE_THE_SETTINGS = {"output", "copies", "preview"}

# what a flag needs alongside it to be accepted
SHEET_FLAG_PARTNERS = {
    "paper_width_mm": ["--paper-height-mm", "300"],
    "paper_height_mm": ["--paper-width-mm", "200"],
}


@pytest.fixture
def sheet(monkeypatch, tmp_path, square_mini):
    """Run papermini sheet with the flags given on one SVG, and return what it would
    write: the figures with their copies, the PDF, the settings and the preview."""
    written = []
    monkeypatch.setattr(cli, "write_sheet", lambda *a: written.append(a) or 0)
    svg = write_svg(square_mini("goblin", 30, 40), tmp_path / "goblin.svg")

    def sheet(*flags: str):
        assert cli.main(["sheet", str(svg), *flags]) == 0
        return written[-1]

    return sheet


def test_every_sheet_setting_has_a_sheet_flag_or_is_listed():
    sheet_options = {dest for c, _, dest, *_ in FLAGS if c == "sheet"}
    assert SHEET_FIELDS - sheet_options == SHEET_FIELDS_WITHOUT_FLAG


@pytest.mark.parametrize(
    "name",
    sorted(SHEET_FIELDS - SHEET_FIELDS_WITHOUT_FLAG - SHEET_FLAGS_OUTSIDE_THE_SETTINGS),
)
def test_each_sheet_flag_reaches_the_sheet_settings(sheet, name):
    default = getattr(SheetSettings(), name)
    _, flag, _, _, given, parsed = _non_default_flag("sheet", name, default)
    assert parsed != default
    flags = [flag, *([] if given is None else [given])]
    _, _, settings, _ = sheet(*flags, *SHEET_FLAG_PARTNERS.get(name, []))
    assert getattr(settings, name) == parsed


def test_sheet_output_copies_and_preview_flags_skip_the_settings(sheet, tmp_path):
    minis, output, settings, preview = sheet(
        "-o", str(tmp_path / "out.pdf"), "--copies", "2", "--preview"
    )
    assert (output, minis[0][1], preview) == (tmp_path / "out.pdf", 2, True)
    assert (settings.output, settings.copies, settings.preview) == (None, 1, False)


# endregion

# region docs


# FigureSettings fields whose flag the settings guide doesn't name.
FIGURE_FLAGS_NOT_IN_THE_GUIDE: set[str] = set()

# FigureSettings fields whose flag the table of papermini make options leaves out.
FIGURE_FLAGS_NOT_IN_THE_MAKE_TABLE: set[str] = set()

# SheetSettings fields that docs/reference.md names neither as a flag nor as a
# project key.
SHEET_FIELDS_NOT_IN_THE_REFERENCE = {"enabled", "output"}


@pytest.fixture(scope="module")
def reference() -> str:
    return REFERENCE.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def _names(text: str, word: str) -> bool:
    """Whether ``text`` has ``word`` as a word of its own: not part of a longer flag."""
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


@pytest.mark.parametrize("name", sorted(FIGURE_OPTIONS))
def test_each_figure_flag_is_in_the_settings_guide(reference, name):
    guide = _section(reference, "## Settings guide", "\n## Commands")
    assert _names(guide, _flag(name)) == (name not in FIGURE_FLAGS_NOT_IN_THE_GUIDE)


@pytest.mark.parametrize("name", sorted(FIGURE_OPTIONS))
def test_each_figure_flag_is_in_the_make_options_table(reference, name):
    commands = _section(reference, "### `papermini make", "### `papermini sheet")
    table = "\n".join(
        line.split("|")[1] for line in commands.splitlines() if line.startswith("| `-")
    )
    assert _names(table, _flag(name)) == (
        name not in FIGURE_FLAGS_NOT_IN_THE_MAKE_TABLE
    )


@pytest.mark.parametrize("name", sorted(SHEET_FIELDS))
def test_each_sheet_setting_is_in_the_reference(reference, name):
    described = _names(reference, _flag(name)) or f"`{name}`" in reference
    assert described == (name not in SHEET_FIELDS_NOT_IN_THE_REFERENCE)


# endregion

# region reference against the options

# Settings guide entries, by heading and first flag, about a control of the app that
# is not an option of its own.
GUIDE_ENTRIES_WITHOUT_AN_OPTION = {'Print a label: --label ""'}

# Settings guide entries, by heading and first flag, whose heading is not the label of
# their option. The headings are what the app shows: the token's field for the label,
# and the figure card's control for the copies, whose option has no label.
GUIDE_HEADINGS_NOT_THE_LABEL = {"Label: --label", "Amount: papermini sheet --copies"}

# The sections of docs/reference.md that hold each command's table of options, and the
# settings the command builds its flags from.
COMMAND_TABLES = {
    "make": ("### `papermini make", "### `papermini sheet", FigureSettings),
    "sheet": ("### `papermini sheet", "### `papermini batch", SheetSettings),
    "batch": ("### `papermini batch", "## Model licence", SheetSettings),
}

# Flags named after a setting that the command builds without the setting's option.
COMMAND_FLAGS_WITHOUT_THEIR_OPTION = {("sheet", "output")}

# the type of a settings dataclass
Settings = type[FigureSettings] | type[SheetSettings]

# How the help of each settings' flags names a default.
SHOWN: dict[Settings, OptionFlags] = {
    settings: OptionFlags(argparse.ArgumentParser(), settings)
    for settings in (FigureSettings, SheetSettings)
}

_CODE = re.compile(r"`([^`]*)`")


def _setting(settings: Settings, code: str) -> str:
    """Return the setting that ``code``, a flag or project key and what follows it,
    names. A flag --no-x turns off the setting x when there is no setting no_x."""
    word = re.sub(r"^papermini \w+ ", "", code).split()[0]
    name = word.lstrip("-").replace("-", "_")
    options = settings.options()
    if name not in options and name.startswith("no_") and name[3:] in options:
        return name[3:]
    return name


def _settings_of(settings: Settings, codes: list[str]) -> list[str]:
    """Return the settings that ``codes`` name, each once, in order."""
    return list(dict.fromkeys(_setting(settings, code) for code in codes))


def _gives(text: str, default: str) -> bool:
    """Whether ``text`` gives ``default``, perhaps with a note in brackets after it."""
    return text == default or (text.startswith(f"{default} (") and text.endswith(")"))


def _guide_entries() -> list[tuple[Settings, str, str]]:
    """Return the settings, heading and flag line of each settings guide entry."""
    reference = REFERENCE.read_text(encoding="utf-8")
    lines = _section(reference, "## Settings guide", "\n## Commands").splitlines()
    settings: Settings = FigureSettings
    entries = []
    for line, after in itertools.pairwise(lines):
        if line.startswith("### Step 3"):
            settings = SheetSettings
        if line.startswith("##### "):
            entries.append((settings, line.removeprefix("##### "), after))
    return entries


def _guide_id(entry: tuple[Settings, str, str]) -> str:
    _, heading, line = entry
    codes = _CODE.findall(line)
    return f"{heading}: {codes[0] if codes else ''}"


def _guide_settings(entry: tuple[Settings, str, str]) -> list[str]:
    settings, _, line = entry
    return _settings_of(settings, _CODE.findall(line.split(" [")[0]))


GUIDE_ENTRIES = [
    e for e in _guide_entries() if _guide_id(e) not in GUIDE_ENTRIES_WITHOUT_AN_OPTION
]


@pytest.mark.parametrize("entry", GUIDE_ENTRIES, ids=_guide_id)
def test_each_guide_heading_is_the_label_of_its_options(entry):
    settings, heading, _ = entry
    options = settings.options()
    labels = [
        options[name].label if name in options else f"(no setting {name})"
        for name in _guide_settings(entry)
    ]
    assert (" and ".join(labels) == heading) == (
        _guide_id(entry) not in GUIDE_HEADINGS_NOT_THE_LABEL
    ), f"{heading!r}; the option's label is {' and '.join(labels)!r}"


@pytest.mark.parametrize(
    "entry", [e for e in GUIDE_ENTRIES if len(_guide_settings(e)) == 1], ids=_guide_id
)
def test_each_guide_entry_gives_the_default_of_its_option(entry):
    settings, _, line = entry
    [name] = _guide_settings(entry)
    expected = SHOWN[settings].default_text(name)
    given = re.search(r" \[(.*)\]\\?$", line)
    assert given is not None, f"no default; the help gives [{expected}]"
    assert _gives(given[1], expected), f"[{given[1]}]; the help gives [{expected}]"


def _choice_lists() -> list[tuple[Settings, str, str]]:
    """Return the settings, flag and choices of each choice list, such as a|b, that
    docs/reference.md gives the flag of a setting."""
    found = []
    for code in _CODE.findall(REFERENCE.read_text(encoding="utf-8")):
        listed = re.fullmatch(r"(?:papermini (\w+) )?(--[\w-]+) (\S+\|\S+)", code)
        if listed is None:
            continue
        command, flag, choices = listed.groups()
        candidates = [SheetSettings] if command == "sheet" else SHOWN
        for settings in candidates:
            if _setting(settings, flag) in settings.options():
                found.append((settings, flag, choices))
                break
    return found


@pytest.mark.parametrize(
    ("settings", "flag", "listed"),
    _choice_lists(),
    ids=lambda value: getattr(value, "__name__", value),
)
def test_each_choice_list_is_the_choices_of_its_option(settings, flag, listed):
    option = settings.options()[_setting(settings, flag)]
    assert listed.split("|") == [str(choice) for choice in option.choices]


def _table_rows() -> list[tuple[str, str, str, str]]:
    """Return the command, flags, defaults and meaning of each row of each command's
    table of options."""
    reference = REFERENCE.read_text(encoding="utf-8")
    rows = []
    for command, (start, end, _) in COMMAND_TABLES.items():
        for line in _section(reference, start, end).splitlines():
            if line.startswith("| `-"):
                flags, defaults, meaning = line.strip().strip("|").split("|", 2)
                rows.append((command, flags.strip(), defaults.strip(), meaning.strip()))
    return rows


TABLE_ROWS = _table_rows()


def _row_id(row: tuple[str, str, str, str]) -> str:
    return f"{row[0]} {row[1].replace('`', '')}"


def _row_settings(command: str, flags: str) -> tuple[Settings, list[str]]:
    """Return the settings ``command`` builds its flags from, and those of them that
    ``flags`` name, each once."""
    settings = COMMAND_TABLES[command][2]
    return settings, _settings_of(settings, _CODE.findall(flags))


def _built_from_its_option(command: str, settings: Settings, name: str) -> bool:
    return (
        name in settings.options()
        and (command, name) not in COMMAND_FLAGS_WITHOUT_THEIR_OPTION
    )


@pytest.mark.parametrize(
    ("command", "flag"),
    [
        (command, flag)
        for command, flag, name, *_ in FLAGS
        if command in ("sheet", "batch")
        and _built_from_its_option(command, COMMAND_TABLES[command][2], name)
    ],
)
def test_each_sheet_and_batch_flag_of_an_option_is_in_its_options_table(command, flag):
    rows = [r for r in TABLE_ROWS if r[0] == command]
    assert any(_names(flags, flag) for _, flags, _, _ in rows)


@pytest.mark.parametrize("row", TABLE_ROWS, ids=_row_id)
def test_each_options_table_row_gives_the_defaults_of_its_options(row):
    command, flags, defaults, _ = row
    settings, names = _row_settings(command, flags)
    given = [d.strip() for d in defaults.split("/")]
    assert len(given) == len(names), f"{defaults!r} is not one default per setting"
    expected = []
    for name, text in zip(names, given, strict=True):
        if not _built_from_its_option(command, settings, name):
            expected.append(text)
            continue
        option = settings.options()[name]
        shown = SHOWN[settings].shown(
            getattr(settings(), name), none_means=option.none_means
        )
        expected.append(text if _gives(text, shown) else shown)
    assert given == expected


@pytest.mark.parametrize("row", TABLE_ROWS, ids=_row_id)
def test_each_options_table_row_names_the_choices_of_its_options(row):
    command, flags, _, meaning = row
    settings, names = _row_settings(command, flags)
    choices = {
        str(choice)
        for name in names
        if _built_from_its_option(command, settings, name)
        for choice in settings.options()[name].choices
    }
    if choices:
        assert {w for w in _CODE.findall(meaning) if re.fullmatch(r"\w+", w)} == choices


# endregion
