from __future__ import annotations

import argparse
from collections.abc import Collection
from typing import Any, get_args

from . import sizes
from .option import Option


class OptionFlags:
    """Adds command-line flags to a parser, building a setting's flag from its option.

    Every help text ends in the flag's default, which comes from the settings dataclass.
    """

    def __init__(
        self,
        parser: argparse.ArgumentParser,
        settings: Any,
        given_only: Collection[str] = (),
    ) -> None:
        """Add the flags of ``settings``, a dataclass with ``options()``, to ``parser``.

        The flags in ``given_only``, and those of the settings a creature size fills in,
        are None unless given, so that the settings decide their values.
        """
        self._parser = parser
        self._options: dict[str, Option] = settings.options()
        self._defaults = settings()
        self._given_only = set(given_only) | {
            name for name, option in self._options.items() if option.sized
        }
        self._groups: dict[str, argparse._ArgumentGroup] = {}

    def add(self, *names: str) -> None:
        """Add the flags of the settings ``names``, each in its option's group."""
        for name in names:
            self.add_one(name)

    def add_one(self, name: str, more: str = "") -> None:
        """Add the flag of the setting ``name``, with ``more`` after its option's help."""
        option = self._options[name]
        default = getattr(self._defaults, name)
        shown = self._shown(default, option.unit, option.none_means)
        if option.sized:
            shown += f", from the {sizes.DEFAULT_SIZE.title()} size"
        self.group_of(name).add_argument(
            "--" + name.replace("_", "-"),
            help=f"{option.help}{more} (default: {shown})",
            **self._parsing(option, default),
        )

    def group_of(self, name: str) -> argparse._ActionsContainer:
        """Return the group of flags that the setting ``name`` belongs to."""
        title = self._options[name].group
        if not title:
            return self._parser
        if title not in self._groups:
            self._groups[title] = self._parser.add_argument_group(title)
        return self._groups[title]

    def with_default(
        self, text: str, default: Any, unit: str = "", none_means: str = ""
    ) -> str:
        """Return the help ``text`` of a flag without an option, ending in ``default``."""
        return f"{text} (default: {self._shown(default, unit, none_means)})"

    def _parsing(self, option: Option, default: Any) -> dict[str, Any]:
        """Return how argparse reads the option's flag: its action or type, choices and
        default."""
        if option.type is bool:
            if default:
                return {"action": argparse.BooleanOptionalAction, "default": None}
            return {"action": "store_true"}
        parsing: dict[str, Any] = {
            "default": None if option.name in self._given_only else default
        }
        for number in (int, float):
            if number in (option.type, *get_args(option.type)):
                parsing["type"] = number
        if option.choices:
            parsing["choices"] = option.choices
        return parsing

    def _shown(self, value: Any, unit: str, none_means: str) -> str:
        """Return how the help names the default ``value``."""
        if value is None:
            return none_means or "none"
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, int | float):
            if not unit:
                return f"{value:g}"
            return f"{value:g} {unit}" if unit.isalpha() else f"{value:g}{unit}"
        return str(value)
