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
from typing import Any

import pytest

from papermini import cli
from papermini.commands import build_command
from papermini.commands.sheet_flags import RENAMED
from papermini.project.figure_settings import FIGURE_OPTIONS, FigureSettings
from papermini.project.option_flags import OptionFlags
from papermini.project.sheet_settings import SheetSettings

REFERENCE = Path(__file__).parents[1] / "docs" / "reference.md"
SHEET_FIELDS = {f.name for f in fields(SheetSettings)}

# region flags

# The flags of a figure's settings, which papermini add and papermini build share:
# (flag, option it sets, a value to give it or None for a flag that takes none, the
# option that value gives). Each is None unless given.
FIGURE_FLAGS = [
    ("--copies", "copies", "3", 3),
    ("--kind", "kind", "token", "token"),
    ("--size", "size", "large", "large"),
    ("--height-mm", "height_mm", "40", 40.0),
    ("--width-mm", "width_mm", "20", 20.0),
    ("--margin-mm", "margin_mm", "2.5", 2.5),
    ("--smooth-mm", "smooth_mm", "1.2", 1.2),
    ("--margin-fill", "margin_fill", "image", "image"),
    ("--margin-color", "margin_color", "#123456", "#123456"),
    ("--tab-shape", "tab_shape", "round", "round"),
    ("--tab-color", "tab_color", "#3b6e2a", "#3b6e2a"),
    ("--tab-width-mm", "tab_width_mm", "30", 30.0),
    ("--tab-radius-mm", "tab_radius_mm", "20", 20.0),
    ("--tab-height-mm", "tab_height_mm", "15", 15.0),
    ("--tab-overlap-mm", "tab_overlap_mm", "3", 3.0),
    ("--fold-mm", "fold_mm", "2", 2.0),
    ("--no-tab", "no_tab", None, True),
    ("--double-sided", "double_sided", None, True),
    ("--no-double-sided", "double_sided", None, False),
    ("--back", "back", "text", "text"),
    ("--back-text", "back_text", "Stats", "Stats"),
    ("--back-color", "back_color", "#eeeeee", "#eeeeee"),
    ("--back-text-color", "back_text_color", "#111111", "#111111"),
    ("--token-diameter-mm", "token_diameter_mm", "40", 40.0),
    ("--token-area", "token_area", "0.1,0.2,0.9,1", "0.1,0.2,0.9,1"),
    ("--token-fill", "token_fill", "image", "image"),
    ("--token-fill-color", "token_fill_color", "#222222", "#222222"),
    ("--token-border-mm", "token_border_mm", "3", 3.0),
    ("--token-border-color", "token_border_color", "#333333", "#333333"),
    ("--token-cut-line", "token_cut_line", None, True),
    ("--token-outline", "token_outline", None, True),
    ("--token-text", "token_text", "label", "label"),
    ("--token-text-style", "token_text_style", "curved", "curved"),
    ("--token-text-color", "token_text_color", "#444444", "#444444"),
    ("--token-text-mm", "token_text_mm", "4", 4.0),
    ("--greyscale", "greyscale", None, True),
    ("--brightness", "brightness", "10", 10),
    ("--contrast", "contrast", "20", 20),
    ("--saturation", "saturation", "-30", -30),
    ("--hue", "hue", "90", 90),
    ("--model", "model", "birefnet", "birefnet"),
    ("--mask", "mask", "m.png", "m.png"),
    ("--crop", "crop", "0.1,0,0.9,1", "0.1,0,0.9,1"),
    ("--strength", "strength", "60", 60),
    ("--fill-gaps", "fill_gaps", "7", 7),
    ("--keep-all", "keep_all", None, True),
    ("--min-area", "min_area", "500", 500),
    ("--label", "label", "Hero", "Hero"),
    ("--tab-front", "tab_front", "number", "number"),
    ("--tab-back", "tab_back", "label_number", "label_number"),
    ("--dpi", "dpi", "150", 150),
    ("--simplify-mm", "simplify_mm", "0.3", 0.3),
    ("--no-smooth", "no_smooth", None, True),
    ("--cut-color", "cut_color", "#ff0000", "#ff0000"),
    ("--cut-width-mm", "cut_width_mm", "0.5", 0.5),
    ("--label-color", "label_color", "#555555", "#555555"),
    ("--label-size-mm", "label_size_mm", "4", 4.0),
    ("--font", "font", "Kalam", "Kalam"),
]

# The flags of the sheet's settings, which papermini add and papermini build share.
SHEET_FLAGS = [
    ("--paper", "paper", "a3", "a3"),
    ("--paper-width-mm", "paper_width_mm", "200", 200.0),
    ("--paper-height-mm", "paper_height_mm", "300", 300.0),
    ("--orientation", "orientation", "landscape", "landscape"),
    ("--sheet-margin-mm", "sheet_margin_mm", "8", 8.0),
    ("--gap-mm", "gap_mm", "5", 5.0),
    ("--title", "title", "Goblins", "Goblins"),
    ("--cut", "cut", "machine", "machine"),
    ("--bleed-mm", "bleed_mm", "2", 2.0),
    ("--marks", "marks", "silhouette", "silhouette"),
    ("--cut-folds", "cut_folds", None, True),
    ("--mat", "mat", "12x12", "12x12"),
]

# Every flag of every command: (command, flag, option it sets, its default, a value to
# give it or None for a flag that takes none, the option that value gives).
FLAGS = [
    *(
        (command, flag, dest, None, given, parsed)
        for command in ("add", "build")
        for flag, dest, given, parsed in [
            *FIGURE_FLAGS,
            ("--grid-mm", "grid_mm", "30", 30.0),
            *SHEET_FLAGS,
        ]
    ),
    ("add", "--no-subfolders", "no_subfolders", False, None, True),
    ("build", "--no-subfolders", "no_subfolders", False, None, True),
    ("build", "-o", "output", None, "out", "out"),
    ("build", "--output", "output", None, "out", "out"),
    ("build", "--svg", "svg", False, None, True),
    ("build", "--png", "png", False, None, True),
    ("build", "--sheet", "sheet", False, None, True),
    ("build", "--preview", "preview", False, None, True),
    ("build", "--png-px", "png_px", None, "128", 128.0),
    ("build", "--png-dpi", "png_dpi", None, "150", 150.0),
    ("build", "--debug", "debug", False, None, True),
    ("build", "--no-cache", "no_cache", False, None, True),
]

# what each command needs besides its options
POSITIONALS = {"add": ["a.yaml"], "build": ["a.png"], "gui": []}

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
def test_each_flag_keeps_its_default(
    row, project_store, size_calculator, pipeline, output, images_from_web
):
    command, _, dest, default, _, _ = row
    parser = cli.build_parser(
        size_calculator, project_store, pipeline, output, images_from_web
    )
    got = getattr(parser.parse_args([command, *POSITIONALS[command]]), dest)
    assert (type(got), got) == (type(default), default)


@pytest.mark.parametrize("row", FLAGS, ids=_flag_id)
def test_each_flag_sets_its_option(
    row, project_store, size_calculator, pipeline, output, images_from_web
):
    command, flag, dest, _, given, parsed = row
    argv = [command, flag, *([] if given is None else [given]), *POSITIONALS[command]]
    parser = cli.build_parser(
        size_calculator, project_store, pipeline, output, images_from_web
    )
    got = getattr(parser.parse_args(argv), dest)
    assert (type(got), got) == (type(parsed), parsed)


# endregion

# region figure settings


# The settings a flag's value gives where it differs from the parsed option.
FIGURE_SETTING_VALUES = {"token_area": [0.1, 0.2, 0.9, 1.0]}
# (--crop keeps the text as given; --token-area becomes a list of fractions)

# FigureSettings fields that have no flag.
FIGURE_FIELDS_WITHOUT_FLAG: set[str] = set()


class _Built(Exception):
    """Raised by the fake build with what it was given, to stop papermini build there."""

    def __init__(self, settings: FigureSettings, options: dict):
        super().__init__()
        self.settings, self.options = settings, options


@pytest.fixture
def build(monkeypatch, tmp_path):
    """Run papermini build with the flags given on an image, and return the settings
    and the build options it would build the figure with."""

    def fake_build(img, s, **options):
        raise _Built(s, options)

    monkeypatch.setattr(build_command, "build_mini", fake_build)
    image = tmp_path / "a.png"
    image.write_bytes(b"")

    def build(*flags: str) -> _Built:
        with pytest.raises(_Built) as built:
            cli.main(["build", str(image), *flags])
        return built.value

    return build


@pytest.fixture
def add(tmp_path, project_store):
    """Run papermini add with the flags given on an image, and return the project it
    saved."""
    image = tmp_path / "a.png"
    image.write_bytes(b"")
    path = tmp_path / "p.yaml"

    def add(*flags: str):
        path.unlink(missing_ok=True)
        assert cli.main(["add", str(path), str(image), *flags]) == 0
        return project_store.load(path)

    return add


def test_every_figure_setting_has_a_flag():
    assert FIGURE_OPTIONS - {dest for _, dest, *_ in FIGURE_FLAGS} == (
        FIGURE_FIELDS_WITHOUT_FLAG
    )


def _figure_flag(name: str) -> tuple[list[str], Any]:
    """Return the flag, with its value, that gives the figure setting ``name`` a value
    other than its default, and the setting that gives."""
    default = getattr(FigureSettings(), name)
    flag, _, given, parsed = next(
        r for r in FIGURE_FLAGS if r[1] == name and r[3] != default
    )
    expected = FIGURE_SETTING_VALUES.get(name, parsed)
    assert expected != default
    return [flag, *([] if given is None else [given])], expected


@pytest.mark.parametrize("name", sorted(FIGURE_OPTIONS - FIGURE_FIELDS_WITHOUT_FLAG))
def test_each_figure_flag_reaches_the_built_figure(build, name):
    flags, expected = _figure_flag(name)
    assert getattr(build(*flags).settings, name) == expected


@pytest.mark.parametrize(
    "name", sorted(FIGURE_OPTIONS - FIGURE_FIELDS_WITHOUT_FLAG - {"mask", "model"})
)
def test_each_figure_flag_reaches_the_added_figure(add, name):
    # (a project keeps a mask or model file relative to itself)
    flags, expected = _figure_flag(name)
    assert getattr(add(*flags).figures[0].settings, name) == expected


@pytest.mark.parametrize(
    ("flags", "option", "expected"),
    [
        (["--cut", "machine", "--bleed-mm", "1.5"], "bleed_mm", 1.5),
        (["--bleed-mm", "1.5"], "bleed_mm", 0.0),  # only cut by machine
        (["--no-cache"], "use_cache", False),
    ],
)
def test_build_flags_outside_the_figure_settings_reach_the_build(
    build, flags, option, expected
):
    assert build(*flags).options[option] == expected


def test_build_debug_writes_next_to_the_image(build, tmp_path):
    assert build("--debug").options["debug_dir"] == tmp_path / "debug"


def test_build_grid_scales_the_creature_size_to_a_tenth_of_a_mm(build):
    assert build("--grid-mm", "30").settings.height_mm == 37.8  # 32 mm * 30 / 25.4


# endregion

# region sheet settings

# SheetSettings fields without a flag: a project file sets them, and papermini build
# has flags of its own for the outputs.
SHEET_FIELDS_WITHOUT_FLAG = {"copies", "enabled", "output", "preview"}

# what a flag needs alongside it to be accepted
SHEET_FLAG_PARTNERS = {
    "paper_width_mm": ["--paper-height-mm", "300"],
    "paper_height_mm": ["--paper-width-mm", "200"],
}


def _sheet_option(flag: str) -> str:
    """Return the sheet setting that ``flag`` sets."""
    renamed = {f: name for name, f in RENAMED.items()}
    return renamed.get(flag, flag).lstrip("-").replace("-", "_")


def test_every_sheet_setting_has_a_flag_or_is_listed():
    flagged = {_sheet_option(flag) for flag, *_ in SHEET_FLAGS}
    assert SHEET_FIELDS - flagged == SHEET_FIELDS_WITHOUT_FLAG


@pytest.mark.parametrize("row", SHEET_FLAGS, ids=lambda row: row[0])
def test_each_sheet_flag_reaches_the_added_sheet(add, row):
    flag, _, given, parsed = row
    name = _sheet_option(flag)
    assert parsed != getattr(SheetSettings(), name)
    flags = [flag, *([] if given is None else [given])]
    sheet = add(*flags, *SHEET_FLAG_PARTNERS.get(name, [])).sheet
    assert getattr(sheet, name) == parsed


# endregion


# region docs


# FigureSettings fields whose flag the settings guide doesn't name.
FIGURE_FLAGS_NOT_IN_THE_GUIDE: set[str] = set()

# FigureSettings fields whose flag the table of figure options leaves out.
FIGURE_FLAGS_NOT_IN_THE_FIGURE_TABLE: set[str] = set()

# SheetSettings fields that docs/reference.md names neither as a flag nor as a
# project key.
SHEET_FIELDS_NOT_IN_THE_REFERENCE = {"enabled"}


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
def test_each_figure_flag_is_in_the_figure_options_table(reference, name):
    commands = _section(reference, "#### Figure options", "#### Sheet options")
    table = "\n".join(
        line.split("|")[1] for line in commands.splitlines() if line.startswith("| `-")
    )
    assert _names(table, _flag(name)) == (
        name not in FIGURE_FLAGS_NOT_IN_THE_FIGURE_TABLE
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
GUIDE_HEADINGS_NOT_THE_LABEL = {"Label: --label", "Amount: --copies"}

# The sections of docs/reference.md that hold each table of options, and the settings
# its flags are built from.
COMMAND_TABLES = {
    "figure": ("#### Figure options", "#### Sheet options", FigureSettings),
    "sheet": ("#### Sheet options", "### `papermini build", SheetSettings),
    "build": ("### `papermini build", "### Project files", SheetSettings),
}

# Flags named after a setting that the command builds without the setting's option.
COMMAND_FLAGS_WITHOUT_THEIR_OPTION = {("build", "output")}

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
    renamed = {flag: name for name, flag in RENAMED.items()}
    if settings is SheetSettings and word in renamed:
        return renamed[word]
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


@pytest.mark.parametrize("flag", [flag for flag, *_ in SHEET_FLAGS])
def test_each_sheet_flag_is_in_the_sheet_options_table(flag):
    rows = [r for r in TABLE_ROWS if r[0] == "sheet"]
    assert any(_names(flags, flag) for _, flags, _, _ in rows)


# papermini build flags that its table of options leaves out.
BUILD_FLAGS_NOT_IN_THE_BUILD_TABLE = {"-o"}  # (named in the --output row)


@pytest.mark.parametrize(
    "flag",
    [
        flag
        for command, flag, *_ in FLAGS
        if command == "build"
        and flag not in {f for f, *_ in [*FIGURE_FLAGS, *SHEET_FLAGS]} | {"--grid-mm"}
    ],
)
def test_each_build_flag_is_in_the_build_options_table(flag):
    rows = [r for r in TABLE_ROWS if r[0] == "build"]
    assert any(_names(flags, flag) for _, flags, _, _ in rows) == (
        flag not in BUILD_FLAGS_NOT_IN_THE_BUILD_TABLE
    )


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
