"""Regenerate the README screenshots of the desktop app from the dragons project.

    just screenshots            # writes docs/screenshots/*.png

Renders off-screen at 1.5x scale with an English locale and default preferences
(a temporary settings folder), so the result does not depend on your own setup.
It needs the rmbg-1.4, birefnet-lite and birefnet models (downloaded on first use);
background removal results are cached, so later runs are quick.

Besides the app screenshots it writes ``crop.png`` (cropping a stat block down to its
dragon), ``models.png`` (the three models on one image, with what a model left
behind circled: wherever it kept something that BiRefNet removed) and, for the
settings guide in docs/reference.md, ``settings/*.png``: the same piece side by side
with different values of a setting, and ``settings/machine.png``: a sheet cut by
machine next to its cut file.

    just screenshots --only settings   # just those
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QApplication

from screenshots.app_shots import AppShots
from screenshots.crop_shot import CropShot
from screenshots.model_shots import ModelShots
from screenshots.picture_composer import PictureComposer
from screenshots.setting_shots import SettingShots
from screenshots.sheet_shots import SheetShots
from screenshots.shot_context import DRAGONS, ShotContext
from screenshots.window_driver import WindowDriver

GROUPS = ["app", "crop", "models", "settings"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--project", type=Path, default=DRAGONS / "dragons.yaml")
    ap.add_argument("--scale", default="1.5", help="Qt scale factor (default 1.5)")
    ap.add_argument(
        "--only",
        nargs="+",
        choices=GROUPS,
        default=GROUPS,
        help="make only these groups of images (default: all)",
    )
    args = ap.parse_args()

    os.environ["QT_SCALE_FACTOR"] = args.scale
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        tempfile.mkdtemp("papermini"),
    )
    args.out.mkdir(parents=True, exist_ok=True)

    ctx = ShotContext.create(
        QApplication([]), args.out, args.project, float(args.scale)
    )
    windows = WindowDriver(ctx)
    composer = PictureComposer(ctx.ratio)
    groups = {
        "app": [AppShots(ctx, windows)],
        "crop": [CropShot(ctx, windows, composer)],
        "models": [ModelShots(ctx, windows, composer)],
        "settings": [SettingShots(ctx, composer), SheetShots(ctx, composer)],
    }
    for name in GROUPS:
        if name in args.only:
            for group in groups[name]:
                group.run()


if __name__ == "__main__":
    main()
