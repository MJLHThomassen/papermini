from __future__ import annotations

from abc import ABC, abstractmethod
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
        self.row: QWidget | None = widget  # the widget in its row; None: no row
        self.switch: QCheckBox | None = None  # the switch in its section's header
        self.switch_name = ""  # the name the panel knows the switch by
        self.labels: list[QLabel] = []  # labels in its row, lined up with the form's
        widget.setToolTip(option.tooltip)

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

    @staticmethod
    def suffix(unit: str) -> str:
        """Return the text a number field shows after the number, for ``unit``."""
        if not unit:
            return ""
        return f" {unit}" if unit.isalpha() else unit
