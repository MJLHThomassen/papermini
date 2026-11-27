from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from .figure_settings import STYLE_KEYS, FigureSettings
from .option import Option

_DEFAULTS = FigureSettings()


@dataclass(frozen=True)
class StylePreset:
    """A named style: the settings that give figures the same look, such as the kind
    of figure, the border, the tabs and the colors, without their size or text.

    ``values`` holds only the style settings that differ from the defaults.
    """

    name: str
    values: dict[str, Any] = field(default_factory=dict, hash=False)

    @classmethod
    def of(cls, name: str, settings: FigureSettings) -> StylePreset:
        """Return the style of ``settings`` as a preset called ``name``."""
        return cls(
            name,
            {
                k: getattr(settings, k)
                for k in STYLE_KEYS
                if getattr(settings, k) != getattr(_DEFAULTS, k)
            },
        )

    @classmethod
    def from_dict(cls, name: Any, d: Any) -> StylePreset:
        """Return the preset called ``name`` with the settings ``d``, as a file stores
        them.

        Raise a ValueError when the name is not text, or a setting is not part of a
        style or has a value its option does not allow.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"a style preset needs a name, not {name!r}")
        name = name.strip()
        where = f"style preset {name}: "
        d = Option.norm_keys(d)
        other = sorted(set(d) - set(STYLE_KEYS))
        if other:
            raise ValueError(
                f"{where}{', '.join(other)} {'is' if len(other) == 1 else 'are'} not "
                "part of a style"
            )
        try:
            settings = FigureSettings.from_dict(d)
        except ValueError as e:
            raise ValueError(f"{where}{e}") from None
        return cls.of(name, settings)

    @classmethod
    def all_from_dict(cls, d: Any) -> list[StylePreset]:
        """Return the presets of a mapping of each preset's name to its settings, as a
        project or preset file stores them.

        Raise a ValueError when ``d`` is not such a mapping or a preset is not valid.
        """
        if d is None:
            return []
        if not isinstance(d, dict):
            raise ValueError("presets must give each style preset's name and settings")
        presets = [cls.from_dict(name, values or {}) for name, values in d.items()]
        names = [p.name for p in presets]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            raise ValueError(f"there are two style presets called {twice[0]}")
        return presets

    @staticmethod
    def dict_of(presets: Iterable[StylePreset]) -> dict[str, dict[str, Any]]:
        """Return a mapping of each preset's name to its settings, as a file stores
        them."""
        return {p.name: p.to_dict() for p in presets}

    def to_dict(self) -> dict[str, Any]:
        """Return the settings as a file stores them."""
        return dict(self.values)

    def applied_to(self, settings: FigureSettings) -> FigureSettings:
        """Return ``settings`` with this style. A style setting that the preset does
        not hold goes back to its default."""
        return replace(
            settings,
            **{k: self.values.get(k, getattr(_DEFAULTS, k)) for k in STYLE_KEYS},
        )

    def matches(self, settings: FigureSettings) -> bool:
        """Tell whether ``settings`` have this style."""
        return self.applied_to(settings) == settings

    def same_values(self, other: StylePreset) -> bool:
        """Tell whether ``other`` sets the same style, whatever its name."""
        return self.values == other.values
