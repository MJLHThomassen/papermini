from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from ..project.option_flags import OptionFlags
from ..project.sheet_settings import SheetSettings

# the sheet settings with a flag, and the flag of those whose name a figure setting has
SHEET_FLAGS = (
    "paper",
    "paper_width_mm",
    "paper_height_mm",
    "orientation",
    "margin_mm",
    "gap_mm",
    "title",
    "cut",
    "bleed_mm",
    "marks",
    "cut_folds",
    "mat",
)
RENAMED = {"margin_mm": "--sheet-margin-mm"}


class SheetFlags:
    """Adds the flags of the sheet's settings to a command, and applies the flags
    given to a sheet."""

    def add_to(self, parser: argparse.ArgumentParser) -> None:
        """Add the sheet flags to ``parser``. Every flag is None unless given."""
        flags = OptionFlags(parser, SheetSettings)
        for name in SHEET_FLAGS:
            flags.add_one(name, flag=RENAMED.get(name, ""))

    def apply(self, args: argparse.Namespace, sheet: SheetSettings) -> SheetSettings:
        """``sheet`` with the settings whose flags ``args`` gives."""
        given = self._given(args)
        if not given:
            return sheet
        custom = {"paper_width_mm", "paper_height_mm"} & set(given)
        if custom and given.get("paper", "custom") != "custom":
            raise SystemExit(
                "--paper-width-mm and --paper-height-mm are a custom paper size: "
                f"leave out --paper {given['paper']}"
            )
        d = asdict(sheet)
        if custom:
            given["paper"] = "custom"
        elif given.get("paper", "custom") != "custom":
            d["paper_width_mm"] = d["paper_height_mm"] = None
        try:
            return SheetSettings.from_dict({**d, **given})
        except ValueError as e:
            raise SystemExit(str(e).replace("sheet ", "--").replace("_", "-")) from None

    def _given(self, args: argparse.Namespace) -> dict[str, Any]:
        """The sheet settings whose flags ``args`` gives."""
        dest = {
            name: RENAMED.get(name, name).lstrip("-").replace("-", "_")
            for name in SHEET_FLAGS
        }
        return {
            name: getattr(args, d)
            for name, d in dest.items()
            if getattr(args, d, None) is not None
        }
