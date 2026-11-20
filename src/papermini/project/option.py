from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, TypeVar, get_args, get_type_hints

from ..pipeline import geometry as geo

T = TypeVar("T")

_KEY = "option"  # the key of a field's metadata that holds its option


@dataclass(frozen=True)
class Option:
    """The definition of one setting: how it is checked, shown and named.

    A settings dataclass gives each field an option with ``Option(...).field(default)``.
    ``Option.of`` reads them back, with each one's name and type filled in.
    """

    label: str = ""  # the name of its field in the settings panel
    help: str = ""  # one line for the command line's help, without the default
    none_means: str = ""  # what a value of None does, for the help; empty: none
    tooltip: str = ""  # the settings panel's tooltip
    group: str = ""  # the group of command-line flags it belongs to
    choices: tuple[Any, ...] = ()  # the values it allows; empty: any value
    low: float | None = None  # the least value it allows
    high: float | None = None  # the greatest value it allows
    above: bool = False  # the value must be above ``low``, not equal to it
    widget: tuple[float, ...] = ()  # the settings panel field's lowest and highest
    unit: str = ""  # the unit its value is in, such as mm or px
    auto: bool = False  # None means the value is worked out automatically
    sized: bool = False  # a creature size fills it in
    kinds: tuple[str, ...] = ()  # the kinds of figure it applies to; empty: all
    color: bool = False  # a #rrggbb color
    parse: Callable[[Any], Any] | None = None  # converts a value, raising ValueError
    name: str = ""  # the field's name, filled in by ``of``
    type: Any = None  # the field's type, filled in by ``of``

    def field(self, default: T) -> T:
        """Return a dataclass field with ``default`` and this option in its metadata."""
        return dataclasses.field(default=default, metadata={_KEY: self})

    @classmethod
    def of(cls, settings: type) -> dict[str, Option]:
        """Return the options of the fields of the dataclass ``settings``, by name."""
        hints = get_type_hints(settings)
        return {
            f.name: replace(f.metadata[_KEY], name=f.name, type=hints[f.name])
            for f in dataclasses.fields(settings)
        }

    def check(self, value: Any, where: str = "") -> Any:
        """Return ``value`` if this option allows it, converted by ``parse``.

        Raise a ValueError that names the option, after ``where``, otherwise.
        """
        if value is None and (self.type is Any or type(None) in get_args(self.type)):
            return value
        if self.choices and value not in self.choices:
            shown = ", ".join(str(c) for c in self.choices)
            raise ValueError(
                f"{where}{self.name} must be one of {shown}, not {value!r}"
            )
        if self.color:
            geo.hex_rgb(str(value))
        if self.low is not None or self.high is not None:
            self._check_number(value, where)
        return self.parse(value) if self.parse else value

    def allows(self, value: Any) -> bool:
        """Return whether this option allows ``value``."""
        try:
            self.check(value)
        except ValueError:
            return False
        return True

    def _check_number(self, value: Any, where: str) -> None:
        whole = self.type is int
        allowed = (int,) if whole else (int, float)
        if (
            isinstance(value, bool)
            or not isinstance(value, allowed)
            or not self._in_range(value)
        ):
            raise ValueError(
                f"{where}{self.name} must be {self._range_text(whole)}, not {value!r}"
            )

    def _in_range(self, value: float) -> bool:
        if self.low is not None and (
            value <= self.low if self.above else value < self.low
        ):
            return False
        return self.high is None or value <= self.high

    def _range_text(self, whole: bool) -> str:
        """Say which numbers the option allows, such as a number above 0."""
        text = "a whole number" if whole else "a number"
        if self.low is not None:
            text += f" {'above' if self.above else 'from'} {self.low:g}"
        if self.high is not None:
            text += f" to {self.high:g}"
        return text
