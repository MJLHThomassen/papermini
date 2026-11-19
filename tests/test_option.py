"""Tests of an option's definition: how it is read from a settings dataclass and how it
checks a value."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from papermini.project.figure_settings import FigureSettings
from papermini.project.option import Option
from papermini.project.sizes import BUILTIN


@dataclass
class _Example:
    """A settings dataclass with one option of each sort."""

    whole: int = Option(low=-10, high=10).field(0)
    above: float | None = Option(low=0, above=True).field(1.0)
    from_zero: float = Option(low=0).field(0.0)
    choice: str = Option(choices=("a", "b")).field("a")
    maybe_choice: str | None = Option(choices=("a", "b")).field(None)
    color: str = Option(color=True).field("#ffffff")
    parsed: float | None = Option(parse=float).field(None)


OPTIONS = Option.of(_Example)


def test_a_field_keeps_its_default_and_carries_its_option():
    assert _Example() == _Example(0, 1.0, 0.0, "a", None, "#ffffff", None)
    assert OPTIONS["choice"].choices == ("a", "b")


def test_reading_the_options_fills_in_each_name_and_type():
    assert [(o.name, o.type) for o in OPTIONS.values()][:2] == [
        ("whole", int),
        ("above", float | None),
    ]


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("whole", 11, "whole must be a whole number from -10 to 10, not 11"),
        ("whole", 1.5, "whole must be a whole number from -10 to 10, not 1.5"),
        ("whole", True, "whole must be a whole number from -10 to 10, not True"),
        ("whole", None, "whole must be a whole number from -10 to 10, not None"),
        ("above", 0, "above must be a number above 0, not 0"),
        ("above", "1", "above must be a number above 0, not '1'"),
        ("from_zero", -0.1, "from_zero must be a number from 0, not -0.1"),
        ("choice", "c", "choice must be one of a, b, not 'c'"),
        ("choice", None, "choice must be one of a, b, not None"),
    ],
)
def test_a_value_it_does_not_allow_is_refused_by_name(name, value, message):
    with pytest.raises(ValueError, match=f"^my {message}"):
        OPTIONS[name].check(value, "my ")
    assert not OPTIONS[name].allows(value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("whole", -10),
        ("above", 0.1),
        ("above", None),
        ("from_zero", 0),
        ("choice", "b"),
        ("maybe_choice", None),
        ("color", "#abc"),
        ("parsed", None),
    ],
)
def test_a_value_it_allows_is_kept(name, value):
    assert OPTIONS[name].check(value) == value
    assert OPTIONS[name].allows(value)


def test_a_color_must_be_one():
    with pytest.raises(ValueError, match="not a color"):
        OPTIONS["color"].check("#12")


def test_a_value_is_converted_by_its_parser():
    assert OPTIONS["parsed"].check("2.5") == 2.5


def test_the_sized_options_are_what_a_size_fills_in():
    sized = {k for k, o in FigureSettings.options().items() if o.sized}
    assert sized == set(BUILTIN.row("medium").values())
