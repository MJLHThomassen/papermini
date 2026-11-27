from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .style_preset import StylePreset
from .styles import BUILTIN_STYLES

# Preset files carry this format and the papermini version that saved them, as projects do.
_PRESET_FORMAT = 1


class StylePresetFile:
    """Reads and writes style preset files (YAML), and finds a preset by its name or
    file.

    A preset file holds one preset or more, the same way a project holds its own::

        papermini: VERSION   # the papermini that saved it
        format: 1
        presets:
          Dark tabs: {tab_color: '#000000', label_color: '#ffffff'}
    """

    def load(self, path: Path) -> list[StylePreset]:
        """Read the presets in the file at ``path``.

        Raise a ValueError when it is not a valid preset file, a yaml.YAMLError when it
        is not YAML, and an OSError when it cannot be read.
        """
        import yaml

        path = Path(path)
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(cfg, dict) or "presets" not in cfg:
            raise ValueError(f"{path.name} is not a papermini style preset file")
        fmt = cfg.get("format", 1)
        if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt > _PRESET_FORMAT:
            raise ValueError(
                f"{path.name} was made by a newer papermini (preset format {fmt!r}). "
                "Update papermini to read it."
            )
        try:
            presets = StylePreset.all_from_dict(cfg["presets"])
        except ValueError as e:
            raise ValueError(f"{path.name}: {e}") from None
        if not presets:
            raise ValueError(f"{path.name} holds no style presets")
        return presets

    def save(self, presets: Iterable[StylePreset], path: Path) -> Path:
        """Write ``presets`` to a preset file at ``path``."""
        import yaml

        from .. import __version__

        path = Path(path)
        cfg = {
            "papermini": __version__,
            "format": _PRESET_FORMAT,
            "presets": StylePreset.dict_of(presets),
        }
        path.write_text(
            yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return path

    def find(self, name_or_file: str, known: Iterable[StylePreset] = ()) -> StylePreset:
        """Return the preset called ``name_or_file`` among ``known`` and the built-in
        presets, ``known`` first, or else the one preset in the file it names.

        Raise a ValueError when there is no such preset, or the file holds more than
        one.
        """
        presets = [*known, *BUILTIN_STYLES]
        wanted = name_or_file.strip()
        for match in (
            lambda p: p.name == wanted,
            lambda p: p.name.casefold() == wanted.casefold(),
        ):
            found = next((p for p in presets if match(p)), None)
            if found is not None:
                return found
        path = Path(wanted)
        if not path.is_file():
            names = ", ".join(p.name for p in presets)
            raise ValueError(
                f"there is no style preset called {wanted!r} and no file of that "
                f"name. Name a preset ({names}) or a preset file."
            )
        in_file = self.load(path)
        if len(in_file) > 1:
            raise ValueError(
                f"{path.name} holds {len(in_file)} style presets. Export the one you "
                "want to a file of its own."
            )
        return in_file[0]
