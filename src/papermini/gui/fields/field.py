from __future__ import annotations

import html
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from PySide6.QtWidgets import QCheckBox, QLabel, QWidget

from ...project.option import Option


class Field(ABC):
    """One field of a settings panel, built from the option of the setting it edits. It
    shows the setting's value in its widget and reads it back.

    A field goes in a row of its section's form, a switch in its section's header, or
    both.
    """

    def __init__(self, option: Option, widget: QWidget) -> None:
        self.option = option
        self.name = option.name
        self.label = option.label  # the text beside its row; empty: a row without one
        self.widget = widget  # the input widget
        self.inputs: dict[str, QWidget] = {option.name: widget}  # (of each setting)
        self.row: QWidget | None = widget  # the widget in its row; None: no row
        self.switch: QCheckBox | None = None  # the switch in its section's header
        self.switch_name = ""  # the name the panel knows the switch by
        self.labels: list[QLabel] = []  # labels in its row, lined up with the form's
        self.tooltip = self._tooltip(option)  # its widget's and its labels' tooltip
        widget.setToolTip(self.tooltip)

    @abstractmethod
    def value(self) -> Any:
        """Return the value the field shows."""

    @abstractmethod
    def set_value(self, value: Any) -> None:
        """Show ``value``."""

    def show(self, settings: Any) -> None:
        """Show the value of its setting in ``settings``."""
        self.set_value(getattr(settings, self.name))

    def read(self) -> dict[str, Any]:
        """Return the values of the settings it edits, by name."""
        return {self.name: self.value()}

    def _tooltip(self, option: Option) -> str:
        """Return the option's tooltip, with a list of its choices when it describes
        them."""
        if not option.choice_details:
            return option.tooltip
        labels = option.choice_labels or tuple(str(c) for c in option.choices)
        return self._choice_tooltip(
            option.tooltip, zip(labels, option.choice_details, strict=True)
        )

    @staticmethod
    def _choice_tooltip(intro: str, choices: Iterable[tuple[str, str]]) -> str:
        """Return a rich-text tooltip: ``intro``, then a table of the ``choices``,
        each a name and what it does."""
        rows = "".join(
            f"<tr><td style='padding-right: 8px'><b>{html.escape(name)}</b></td>"
            f"<td>{'<br>'.join(map(html.escape, detail.splitlines()))}</td></tr>"
            for name, detail in choices
        )
        return (
            f"<p>{html.escape(intro)}</p>"
            f"<table cellspacing='0' cellpadding='3'>{rows}</table>"
        )

    @staticmethod
    def suffix(unit: str) -> str:
        """Return the text a number field shows after the number, for ``unit``."""
        if not unit:
            return ""
        return f" {unit}" if unit.isalpha() else unit
