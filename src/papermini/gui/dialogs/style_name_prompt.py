from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from ..style_library import StyleLibrary


class StyleNamePrompt:
    """Asks the user for the name of a style preset of their own. A built-in preset's
    name is refused, and taking the name of one of their own presets replaces it,
    once they agree."""

    def __init__(self, styles: StyleLibrary):
        self._styles = styles

    def ask(self, parent: QWidget, title: str, current: str = "", old: str = "") -> str:
        """Return the name the user gives, starting from ``current``, or "" when they
        cancel. ``old`` is the name of the preset being renamed, which the user may
        keep."""
        name = current
        while True:
            name, ok = QInputDialog.getText(
                parent,
                title,
                "Name of the style preset:",
                QLineEdit.EchoMode.Normal,
                name,
            )
            name = name.strip()
            if not ok or not name:
                return ""
            if name == old:
                return name
            if self._styles.is_builtin(name):
                QMessageBox.information(
                    parent,
                    title,
                    f"{name} is a style preset that comes with papermini. Pick another "
                    "name.",
                )
                continue
            if not self._styles.is_users(name):
                return name
            answer = QMessageBox.question(
                parent,
                title,
                f"You already have a style preset called {name}. Replace it?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                return name
