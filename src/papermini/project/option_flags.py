from __future__ import annotations

import argparse
from typing import Any, get_args

from . import sizes
from .option import Option


class OptionFlags:
    """Adds command-line flags to a parser, building a setting's flag from its option.

    A flag is None unless given, so that the settings decide the values left out.
    Every help text ends in the flag's default, which comes from the settings dataclass.
    """

    def __init__(self, parser: argparse.ArgumentParser, settings: Any) -> None:
        """Add the flags of ``settings``, a dataclass with ``options()``, to ``parser``."""
        self._parser = parser
        self._options: dict[str, Option] = settings.options()
        self._defaults = settings()
        self._groups: dict[str, argparse._ArgumentGroup] = {}

    def add(self, *names: str) -> None:
        """Add the flags of the settings ``names``, each in its option's group."""
        for name in names:
            self.add_one(name)

    def add_one(self, name: str, more: str = "", flag: str = "") -> None:
        """Add the flag of the setting ``name``, with ``more`` after its option's help.
        ``flag`` names the flag when it is not the setting's name."""
        option = self._options[name]
        flag = flag or "--" + name.replace("_", "-")
        self.group_of(name).add_argument(
            flag,
            dest=flag.lstrip("-").replace("-", "_"),
            help=f"{option.help}{more} (default: {self.default_text(name)})",
            **self._parsing(option, getattr(self._defaults, name)),
        )

    def default_text(self, name: str) -> str:
        """Return how the help of the setting ``name``'s flag names its default."""
        option = self._options[name]
        shown = self.shown(
            getattr(self._defaults, name), option.unit, option.none_means
        )
        if option.sized:
            shown += f", from the {sizes.DEFAULT_SIZE.title()} size"
        return shown

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
        return f"{text} (default: {self.shown(default, unit, none_means)})"

    def shown(self, value: Any, unit: str = "", none_means: str = "") -> str:
        """Return how a help names the default ``value``, a number in ``unit``.

        None is ``none_means``, or none when that is empty. Empty text is none.
        """
        if value is None:
            return none_means or "none"
        if value == "":
            return "none"
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, int | float):
            if not unit:
                return f"{value:g}"
            return f"{value:g} {unit}" if unit.isalpha() else f"{value:g}{unit}"
        return str(value)

    def _parsing(self, option: Option, default: Any) -> dict[str, Any]:
        """Return how argparse reads the option's flag: its action or type, choices and
        default."""
        if option.type is bool:
            if default:
                return {"action": argparse.BooleanOptionalAction, "default": None}
            return {"action": "store_true", "default": None}
        parsing: dict[str, Any] = {"default": None}
        for number in (int, float):
            if number in (option.type, *get_args(option.type)):
                parsing["type"] = number
        if option.choices:
            parsing["choices"] = option.choices
        return parsing
