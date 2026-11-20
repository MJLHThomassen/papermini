"""Tests of the command-line flags built from a settings dataclass's options."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

import pytest

from papermini.project.option import Option
from papermini.project.option_flags import OptionFlags


@dataclass
class _Example:
    """A settings dataclass with one option of each sort a flag is built from."""

    width_mm: float = Option(help="the width", unit="mm", group="size").field(1.5)
    count: int | None = Option(help="how many", none_means="as many as fit").field(None)
    shape: str = Option(help="the shape", choices=("square", "round")).field("square")
    angle: int = Option(help="the angle", unit="°").field(0)
    tidy: bool = Option(help="tidy up").field(False)
    framed: bool = Option(help="a frame").field(True)
    height_mm: float = Option(help="the height", unit="mm", sized=True).field(32.0)
    area: Any = Option(help="the area").field(None)  # noqa: RUF009 (a dataclass field)

    @classmethod
    def options(cls) -> dict[str, Option]:
        return Option.of(cls)


@pytest.fixture
def parser(monkeypatch) -> argparse.ArgumentParser:
    monkeypatch.setenv("COLUMNS", "500")  # each flag's help on one line
    return argparse.ArgumentParser(prog="example")


@pytest.fixture
def flags(parser) -> OptionFlags:
    return OptionFlags(parser, _Example, given_only={"shape"})


def test_a_flag_reads_its_value_with_the_type_of_its_field(parser, flags):
    flags.add("width_mm", "count", "angle")
    a = parser.parse_args(["--width-mm", "2", "--count", "3", "--angle", "-5"])
    assert (a.width_mm, a.count, a.angle) == (2.0, 3, -5)


def test_a_flag_left_out_has_its_settings_default(parser, flags):
    flags.add("width_mm", "count", "tidy", "area")
    a = parser.parse_args([])
    assert (a.width_mm, a.count, a.tidy, a.area) == (1.5, None, False, None)


def test_a_given_only_or_sized_flag_left_out_is_none(parser, flags):
    flags.add("shape", "height_mm")
    a = parser.parse_args([])
    assert (a.shape, a.height_mm) == (None, None)


def test_a_flag_allows_only_its_options_choices(parser, flags):
    flags.add("shape")
    assert parser.parse_args(["--shape", "round"]).shape == "round"
    with pytest.raises(SystemExit):
        parser.parse_args(["--shape", "oval"])


def test_a_setting_off_by_default_is_a_switch(parser, flags):
    flags.add("tidy")
    assert parser.parse_args(["--tidy"]).tidy is True


def test_a_setting_on_by_default_can_be_turned_off(parser, flags):
    flags.add("framed")
    assert parser.parse_args([]).framed is None
    assert parser.parse_args(["--no-framed"]).framed is False
    assert parser.parse_args(["--framed"]).framed is True


@pytest.mark.parametrize(
    ("name", "flag", "expected"),
    [
        ("width_mm", "--width-mm", "the width (default: 1.5 mm)"),
        ("count", "--count", "how many (default: as many as fit)"),
        ("shape", "--shape", "the shape (default: square)"),
        ("angle", "--angle", "the angle (default: 0°)"),
        ("tidy", "--tidy", "tidy up (default: off)"),
        ("framed", "--framed", "a frame (default: on)"),
        (
            "height_mm",
            "--height-mm",
            "the height (default: 32 mm, from the Medium size)",
        ),
        ("area", "--area", "the area (default: none)"),
    ],
)
def test_a_flags_help_ends_in_its_default(parser, flags, name, flag, expected):
    flags.add(name)
    assert parser.format_help().rstrip().endswith(expected)
    assert flag in parser.format_help()


def test_more_help_goes_before_the_default(parser, flags):
    flags.add_one("width_mm", ", measured inside")
    assert "the width, measured inside (default: 1.5 mm)" in parser.format_help()


def test_a_flag_goes_in_its_options_group(parser, flags):
    flags.add("count", "width_mm", "height_mm")
    shown = parser.format_help()
    groups = shown[shown.index("options:") :]  # (after the usage line)
    assert groups.index("--count") < groups.index("size:") < groups.index("--width-mm")
    assert groups.index("--height-mm") < groups.index("size:")
    assert flags.group_of("width_mm") is flags.group_of("width_mm")


def test_a_flag_without_an_option_gets_the_same_default_text(flags):
    assert flags.with_default("the gap", 7.0, "mm") == "the gap (default: 7 mm)"
    assert flags.with_default("the file", None) == "the file (default: none)"
    assert (
        flags.with_default("the file", None, none_means="next to the image")
        == "the file (default: next to the image)"
    )


def test_a_settings_default_text_is_what_its_help_ends_in(flags):
    assert flags.default_text("width_mm") == "1.5 mm"
    assert flags.default_text("count") == "as many as fit"
    assert flags.default_text("height_mm") == "32 mm, from the Medium size"


def test_a_value_is_shown_without_a_unit_unless_given_one(flags):
    assert flags.shown(1.5) == "1.5"
    assert flags.shown(1.5, "mm") == "1.5 mm"
    assert flags.shown(90, "°") == "90°"
