from __future__ import annotations

from ..project.style_preset import StylePreset
from ..project.styles import BUILTIN_STYLES
from .preferences import Preferences


class StyleLibrary:
    """The style presets the app offers: the built-in ones, the user's own and those
    of the open project. In a project, its own version of a preset wins over the
    others with that name."""

    def __init__(self, prefs: Preferences):
        self._prefs = prefs

    def offered(self, project: list[StylePreset]) -> list[StylePreset]:
        """Return the presets to offer in a project with the presets ``project``: the
        built-in ones, then the user's, then those only the project has."""
        theirs = {p.name: p for p in project}
        shared = [
            theirs.pop(p.name, p) for p in (*BUILTIN_STYLES, *self._prefs.user_styles())
        ]
        return shared + list(theirs.values())

    def find(self, name: str, project: list[StylePreset]) -> StylePreset | None:
        """Return the preset called ``name`` among those offered, or None."""
        return next((p for p in self.offered(project) if p.name == name), None)

    def note(self, preset: StylePreset, project: list[StylePreset]) -> str:
        """Say where ``preset`` comes from, and whether the project's version differs
        from the one with its name outside the project."""
        outside = self._outside(preset.name)
        if preset not in project:
            return "Comes with papermini" if self.is_builtin(preset.name) else "Yours"
        if outside is None:
            return "Only in this project"
        if self.differs(preset):
            whose = "the built-in one" if self.is_builtin(preset.name) else "yours"
            return f"This project's version, which differs from {whose}"
        return "Yours, also in this project"

    def differs(self, preset: StylePreset) -> bool:
        """Tell whether the built-in or user's preset with the name of ``preset`` has
        other settings."""
        outside = self._outside(preset.name)
        return outside is not None and not outside.same_values(preset)

    def is_builtin(self, name: str) -> bool:
        return any(p.name == name for p in BUILTIN_STYLES)

    def is_users(self, name: str) -> bool:
        return any(p.name == name for p in self._prefs.user_styles())

    def default_style(self) -> StylePreset:
        """Return the preset that new figures get when no figure is selected, or the
        first built-in one when that preset is gone."""
        return self._outside(self._prefs.default_style_name()) or BUILTIN_STYLES[0]

    def save_users(self, preset: StylePreset) -> None:
        """Keep ``preset`` among the user's own presets, in place of one with its
        name."""
        mine = self._prefs.user_styles()
        at = next((i for i, p in enumerate(mine) if p.name == preset.name), len(mine))
        self._prefs.save_user_styles([*mine[:at], preset, *mine[at + 1 :]])

    def _outside(self, name: str) -> StylePreset | None:
        """Return the built-in or user's preset called ``name``, or None."""
        return next(
            (
                p
                for p in (*BUILTIN_STYLES, *self._prefs.user_styles())
                if p.name == name
            ),
            None,
        )
