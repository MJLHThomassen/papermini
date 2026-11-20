from __future__ import annotations

from collections.abc import Callable
from typing import get_args

from PySide6.QtWidgets import QLineEdit

from ...project.option import Option
from .field import Field


class TextField(Field):
    """A line of text. For a setting that may be None, empty text means None and the
    text is read without its surrounding spaces."""

    def __init__(
        self, option: Option, changed: Callable[..., None], placeholder: str = ""
    ) -> None:
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._optional = type(None) in get_args(option.type)
        super().__init__(option, self._edit)
        self._edit.editingFinished.connect(changed)

    def value(self) -> str | None:
        text = self._edit.text()
        return (text.strip() or None) if self._optional else text

    def set_value(self, value: str | None) -> None:
        self._edit.setText(value or "")
