"""The creature size table presets, stored in the preferences."""

from __future__ import annotations

import json

from ..project import sizes
from . import prefs

PRESETS_KEY = "sizes/presets"
DEFAULT_KEY = "sizes/default_preset"


def user_presets() -> list[sizes.SizeTable]:
    """The user's own size table presets (entries that cannot be read are left out)."""
    text = prefs.store().value(PRESETS_KEY, "", type=str)
    try:
        data = json.loads(text) if text else []
    except ValueError:
        return []
    out, seen = [], {sizes.BUILTIN_NAME}
    for d in data if isinstance(data, list) else []:
        try:
            t = sizes.SizeTable.from_dict(d)
        except (ValueError, TypeError, AttributeError):
            continue
        if t.name and t.name not in seen:
            seen.add(t.name)
            out.append(t)
    return out


def save_user_presets(tables: list[sizes.SizeTable]) -> None:
    prefs.store().setValue(PRESETS_KEY, json.dumps([t.to_dict() for t in tables]))


def presets() -> list[sizes.SizeTable]:
    """Every preset: the built-in one first, then the user's own."""
    return [sizes.BUILTIN] + user_presets()


def default_name() -> str:
    return prefs.store().value(DEFAULT_KEY, sizes.BUILTIN_NAME, type=str)


def set_default_name(name: str) -> None:
    prefs.store().setValue(DEFAULT_KEY, name)


def default_table() -> sizes.SizeTable:
    """The preset new projects start with (the built-in one when the default is gone)."""
    return find(presets(), default_name()) or sizes.BUILTIN


def find(tables: list[sizes.SizeTable], name: str) -> sizes.SizeTable | None:
    return next((t for t in tables if t.name == name), None)


def preset_of(
    table: sizes.SizeTable, tables: list[sizes.SizeTable] | None = None
) -> str:
    """The name of the preset ``table`` is (same name and values), or ""."""
    p = find(tables if tables is not None else presets(), table.name)
    return p.name if p is not None and p.same_values(table) else ""


def table_label(table: sizes.SizeTable) -> str:
    """How the size hint names a project's table: its preset, or this project's own."""
    return preset_of(table) or "this project's table"
