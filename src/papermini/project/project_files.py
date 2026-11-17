"""Loads, checks and saves project files, shared by the CLI, batch YAML and the GUI.

A project file *is* a batch config (saved projects also record the papermini that
saved them and the project format)::

    papermini: 1.0.0
    format: 1
    output: minis
    sheet: {output: minis/sheet.pdf, paper: a4, copies: 1}
    defaults: {height_mm: 42}
    figures:
      - image: dragon.png
        label: Red dragon
      - image: https://example.com/goblin.webp   # a link: downloaded once, then cached
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..support import remote
from . import sizes
from .figure_entry import FigureEntry
from .project import Project
from .settings import norm_keys, settings_with_size
from .sheet_settings import SheetSettings

# Saved projects carry this format and the papermini version that saved them. The format
# changes only when a project from an older papermini could no longer be read as it is.
_PROJECT_FORMAT = 1


def load_project(path: Path) -> Project:
    import yaml

    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    newer = _check_format(cfg, path.name)
    base = path.parent
    try:
        sheet = SheetSettings.from_dict(cfg.get("sheet") or {})
        table = sizes.SizeTable.from_dict(cfg.get("sizes"))
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}{newer}") from None
    defaults = norm_keys(cfg.get("defaults"))
    figures = []
    for entry in cfg.get("figures") or []:
        if isinstance(entry, str):
            entry = {"image": entry}
        o = {**defaults, **norm_keys(entry)}
        if "image" not in o:
            raise ValueError(f"{path.name}: every figure needs an 'image'")
        src = o.pop("image")
        source = str(src).strip() if remote.is_url(src) else None
        image = (
            remote.fetch_image(source)
            if source
            else (base / remote.local_path(src)).resolve()
        )
        if image.is_dir():
            raise ValueError(
                f"{path.name}: {src} is a folder: list its images one by one, "
                "or add the folder in the app"
            )
        name = o.pop("name", None)
        o.setdefault("copies", sheet.copies)
        if o.get("mask"):
            o["mask"] = str((base / o["mask"]).resolve())
        if str(o.get("model", "")).endswith(".onnx"):
            o["model"] = str((base / o["model"]).resolve())
        try:
            s = settings_with_size(o, table)
        except ValueError as e:
            raise ValueError(f"{path.name}: {image.name}: {e}{newer}") from None
        figures.append(FigureEntry(image, s, name, source))
    return Project(
        path,
        str(cfg.get("output", "minis")),
        sheet,
        figures,
        bool(cfg.get("debug", False)),
        table,
    )


def _release(version: Any) -> tuple[int, int, int] | None:
    """The leading MAJOR.MINOR.PATCH of a papermini version (a development version such
    as 1.2.1.dev3+g1a2b3c4 counts as 1.2.1), or None when it has none."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(version).strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _check_format(cfg: dict[str, Any], name: str) -> str:
    """Refuse a project in a format this papermini cannot read, naming the papermini that
    saved it. Returns the note for errors in a project saved by a newer papermini of the
    same format (which may use options this one does not know), or ""."""
    from .. import __version__

    saved = cfg.get(
        "papermini"
    )  # the papermini that saved the project (none when hand-written)
    made_by = (
        f"was made by papermini {saved}" if saved else "uses a newer project format"
    )
    fmt = cfg.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ValueError(
            f"{name}: the project format must be a whole number from 1, not {fmt!r}"
        )
    if fmt > _PROJECT_FORMAT:
        raise ValueError(
            f"{name} {made_by} (project format {fmt}), and papermini {__version__} opens project format {_PROJECT_FORMAT}. Update papermini to open it."
        )
    made, this = _release(saved or ""), _release(__version__)
    if made and this and made > this:
        return f". The project was made by papermini {saved}, which is newer than papermini {__version__}. Update papermini to open it."
    return ""


class _Flow(dict):
    """A mapping written on one line in a saved project."""


def _dumper():
    import yaml

    class Dumper(yaml.SafeDumper):
        pass

    Dumper.add_representer(
        _Flow,
        lambda d, data: d.represent_mapping(
            "tag:yaml.org,2002:map", data, flow_style=True
        ),
    )
    return Dumper


_Dumper = None


def save_project(p: Project, path: Path) -> Path:
    """Write ``p`` as a batch YAML, with the papermini version that saved it and the
    project format. Paths are stored relative to the file."""
    import os

    import yaml

    global _Dumper
    _Dumper = _Dumper or _dumper()
    path = Path(path).resolve()
    base = path.parent

    def rel(f) -> str:
        try:
            return Path(os.path.relpath(Path(f).resolve(), base)).as_posix()
        except ValueError:  # other drive on Windows
            return Path(f).resolve().as_posix()

    sheet = {
        k: v for k, v in asdict(p.sheet).items() if v != getattr(SheetSettings(), k)
    }
    figures = []
    for f in p.figures:
        d: dict[str, Any] = {"image": f.source or rel(f.image)}
        if f.name:
            d["name"] = f.name
        o = f.settings.to_dict()
        if o.get("mask"):
            o["mask"] = rel(o["mask"])
        if str(o.get("model", "")).endswith(".onnx"):
            o["model"] = rel(o["model"])
        for key in ("crop", "token_area"):
            if isinstance(o.get(key), tuple):
                o[key] = list(o[key])
        d.update(o)
        figures.append(d)
    from .. import __version__

    cfg: dict[str, Any] = {
        "papermini": __version__,
        "format": _PROJECT_FORMAT,
        "output": p.output,
    }
    if sheet:
        cfg["sheet"] = sheet
    cfg["sizes"] = {
        k: _Flow(v) if isinstance(v, dict) else v  # (a size per line)
        for k, v in p.sizes.to_dict().items()
    }
    cfg["figures"] = figures
    path.write_text(
        yaml.dump(cfg, Dumper=_Dumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    p.path = path
    return path
