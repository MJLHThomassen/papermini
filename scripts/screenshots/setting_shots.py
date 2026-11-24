from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsScene

from papermini.pipeline.mini import Mini
from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.option import Option

from .panel import Panel
from .picture_composer import PictureComposer
from .sample import Sample
from .shot_context import DRAGONS, ShotContext

RED, FLY = "dragon.webp", "dragon-flying.webp"
GREEN = "#3b6e2a"  # a grass-green tab: shows what folds under
# no back and no label, so that the setting shows
ONE_SIDE: dict[str, Any] = {"double_sided": False, "label": ""}
COLOR_NAMES = {"#ffffff": "white"}  # the colors a caption names in words
PAPER_MM = 2.5  # the white paper shown around a piece
PX_PER_MM = 3.6  # logical pixels per mm of a piece, unless a picture zooms in


class SettingShots:
    """The pictures of the settings guide in docs/reference.md: the same piece side
    by side with different values of a setting."""

    def __init__(self, ctx: ShotContext, composer: PictureComposer):
        self._ctx = ctx
        self._composer = composer
        self._defaults = FigureSettings()
        self._options = Option.of(FigureSettings)

    def run(self) -> None:
        """Save one picture per setting."""
        self._creature_size()
        self._back()
        self._margin()
        self._margin_fill()
        self._smoothing()
        self._bleed()
        self._tab_shape()
        self._tab_number()
        self._font()
        self._tab_overlap()
        self._fold()
        self._adjustments()
        self._token_fill()
        self._token_text()

    # region the pictures
    def _creature_size(self) -> None:
        """Compare creature sizes. A size fills in the height and the base, which a
        round tab shows."""

        def sample(size: str) -> Sample:
            row = sizes.BUILTIN.row(size)
            return Sample(
                self._mini(
                    RED,
                    size=size,
                    tab_shape="round",
                    tab_color=GREEN,
                    **row.values(),
                    **ONE_SIDE,
                ),
                sizes.LABELS[size],
                f"{row.height_mm:g} mm tall, {row.base_mm:g} mm base",
            )

        self._compare(
            "creature-size", [sample(s) for s in ("small", "medium", "large")], 3.4
        )

    def _back(self) -> None:
        """Compare what the back of a double-sided piece shows."""
        d = self._defaults
        label = "Red dragon"
        self._compare(
            "back",
            [
                Sample(
                    self._mini(RED, label=label),
                    self._choice("back", d.back),
                    "the default",
                ),
                Sample(
                    self._mini(RED, label=label, back="blank"),
                    self._choice("back", "blank"),
                    "to draw or write on",
                ),
                Sample(
                    self._mini(RED, label=label, back="text", back_text="Ember"),
                    self._choice("back", "text"),
                    "a name or a note",
                ),
                Sample(
                    replace(self._mini(RED, label=label, back="number"), number=3),
                    self._choice("back", "number"),
                    "the copy's number, here 3",
                ),
            ],
            3.4,
        )

    def _margin(self) -> None:
        """Compare margins."""
        cream: dict[str, Any] = dict(ONE_SIDE, no_tab=True, margin_color="#f3e6c8")
        self._compare(
            "margin",
            [
                Sample(
                    self._mini(RED, margin_mm=0.8, **cream),
                    "Margin 0.8 mm",
                    "close to the drawing",
                ),
                Sample(
                    self._mini(RED, **cream),
                    f"Margin {self._defaults.margin_mm:g} mm",
                    "the default",
                ),
                Sample(
                    self._mini(RED, margin_mm=3.5, **cream),
                    "Margin 3.5 mm",
                    "easier to cut",
                ),
            ],
        )

    def _margin_fill(self) -> None:
        """Compare what fills the margin."""
        flat: dict[str, Any] = dict(ONE_SIDE, height_mm=36, no_tab=True)
        self._compare(
            "margin-fill",
            [
                Sample(
                    self._mini(
                        FLY, margin_fill="color", margin_color="#24477a", **flat
                    ),
                    self._choice("margin_fill", "color"),
                    "any color, here blue",
                ),
                Sample(
                    self._mini(FLY, margin_fill="image", **flat),
                    self._choice("margin_fill", "image"),
                    "the picture around the figure",
                ),
            ],
        )

    def _smoothing(self) -> None:
        """Compare outline smoothing on the flying dragon's right wing."""
        wing = QRectF(36, 0, 36, 22)
        flat: dict[str, Any] = dict(ONE_SIDE, height_mm=36, no_tab=True)
        self._compare(
            "smoothing",
            [
                Sample(
                    self._mini(FLY, **flat),
                    f"Smoothing {self._defaults.smooth_mm:g} mm",
                    "the default: follows the wing",
                    wing,
                ),
                Sample(
                    self._mini(FLY, smooth_mm=2.5, **flat),
                    "Smoothing 2.5 mm",
                    "fewer bends, but thin tips lose their margin",
                    wing,
                ),
            ],
            7,
        )

    def _bleed(self) -> None:
        """Compare bleed, for a sheet cut by machine. The red hairline shows where the
        machine cuts."""
        tip = QRectF(50, 2, 22, 14)
        dark: dict[str, Any] = dict(
            ONE_SIDE,
            height_mm=36,
            margin_color="#1d1d2b",
            no_tab=True,
            cut_color="#ff0000",
            cut_width_mm=0.1,
        )
        self._compare(
            "bleed",
            [
                Sample(
                    self._mini(FLY, **dark),
                    "No bleed",
                    "a cut a little off leaves a white edge",
                    tip,
                ),
                Sample(
                    self._mini(FLY, bleed_mm=1.0, **dark),
                    "Bleed 1 mm",
                    "the margin color goes on past the cut",
                    tip,
                ),
            ],
            11,
        )

    def _tab_shape(self) -> None:
        """Compare the tab's shapes."""
        square = self._mini(
            RED, tab_shape="square", double_sided=False, label="Red dragon"
        )
        round_ = self._mini(RED, tab_shape="round", tab_color=GREEN, **ONE_SIDE)
        self._compare(
            "tab-shape",
            [
                Sample(
                    square,
                    "Square",
                    "slots into a stand, with the label",
                    self._bottom(square),
                ),
                Sample(
                    round_,
                    "Round",
                    "folds out into a base, here green",
                    self._bottom(round_),
                ),
            ],
            6,
        )

    def _tab_number(self) -> None:
        """Compare what the tab shows, for copy 3."""
        notes = {
            self._defaults.tab_front: "the default",
            "number": "as big as the tab allows",
            "label_number": "the number above the label",
        }
        samples = []
        for value, note in notes.items():
            m = replace(
                self._mini(
                    RED, double_sided=False, label="Red dragon", tab_front=value
                ),
                number=3,
            )
            samples.append(
                Sample(m, self._choice("tab_front", value), note, self._bottom(m))
            )
        self._compare("tab-number", samples, 6)

    def _font(self) -> None:
        """Compare fonts. One font sets all of the piece's text."""
        notes = {
            self._defaults.font: "the default",
            "Almendra": "comes with papermini",
            "Kalam": "comes with papermini",
        }
        samples = []
        for font, note in notes.items():
            m = replace(
                self._mini(
                    RED,
                    double_sided=False,
                    label="Red dragon",
                    tab_front="label_number",
                    font=font,
                ),
                number=3,
            )
            samples.append(Sample(m, font, note, self._bottom(m)))
        self._compare("font", samples, 6)

    def _tab_overlap(self) -> None:
        """Compare how far the tab reaches up the figure."""
        notes = {
            0: "the tab hangs from the tail tip",
            4: "the tab holds the tail and the claws",
        }
        samples = []
        for overlap, note in notes.items():
            m = self._mini(FLY, height_mm=36, tab_overlap_mm=overlap, **ONE_SIDE)
            samples.append(
                Sample(m, f"Overlap {overlap} mm", note, self._bottom(m, 18))
            )
        self._compare("tab-overlap", samples, 6)

    def _fold(self) -> None:
        """Compare where the tab folds."""
        notes = {
            0: "the feet float a margin above the ground",
            1.6: "the feet stand on the fold",
            4: "the claws fold under",
        }
        samples = []
        for fold, note in notes.items():
            m = self._mini(RED, fold_mm=fold, tab_color=GREEN, **ONE_SIDE)
            samples.append(Sample(m, f"Fold {fold:g} mm", note, self._bottom(m)))
        self._compare("fold", samples, 6)

    def _adjustments(self) -> None:
        """Compare image adjustments."""
        plain: dict[str, Any] = dict(ONE_SIDE, no_tab=True)
        unchanged: dict[str, Any] = {
            "greyscale": False,
            "brightness": 0,
            "contrast": 0,
            "saturation": 0,
            "hue": 0,
        }
        self._compare(
            "adjustments",
            [
                Sample(
                    self._mini(RED, **unchanged, **plain),
                    "As drawn",
                    "all at 0",
                ),
                Sample(
                    self._mini(RED, greyscale=True, contrast=15, **plain),
                    "Greyscale",
                    "contrast +15",
                ),
                Sample(
                    self._mini(RED, hue=120, **plain), "Hue +120°", "a green dragon"
                ),
            ],
        )

    def _token_fill(self) -> None:
        """Compare what fills a token's circle."""
        d = self._defaults
        token: dict[str, Any] = {"kind": "token"}
        # the picture's middle, as tall as it is: it fills the circle, and the wide
        # picture's own edges stay out
        square = [1 / 6, 0.0, 5 / 6, 1.0]
        color = COLOR_NAMES.get(d.token_fill_color, d.token_fill_color)
        self._compare(
            "token-fill",
            [
                Sample(
                    self._mini(FLY, **token),
                    self._choice("token_fill", d.token_fill),
                    f"{color}, the default",
                ),
                Sample(
                    self._mini(FLY, token_fill="image", token_area=square, **token),
                    self._choice("token_fill", "image"),
                    "the picture around the figure",
                ),
                Sample(
                    self._mini(
                        FLY,
                        token_fill="image",
                        token_area=square,
                        token_outline=True,
                        **token,
                    ),
                    "Image outline",
                    "a white outline, on the picture",
                ),
            ],
            8,
        )

    def _token_text(self) -> None:
        """Compare the text on a token's ring."""
        numbered: dict[str, Any] = {
            "kind": "token",
            "label": "Red dragon",
            "token_text": "label_number",
        }
        self._compare(
            "token-text",
            [
                Sample(
                    replace(self._mini(RED, **numbered), number=3),
                    self._choice("token_text_style", self._defaults.token_text_style),
                    "the label and copy 3",
                ),
                Sample(
                    replace(
                        self._mini(
                            RED,
                            token_text_style="curved",
                            token_border_color="#7a1f1f",
                            **numbered,
                        ),
                        number=3,
                    ),
                    self._choice("token_text_style", "curved"),
                    "the ring as wide as the text needs",
                ),
            ],
            8,
        )

    # endregion

    # region helpers
    def _mini(self, image: str, bleed_mm: float = 0.0, **settings) -> Mini:
        """Build a miniature of one of the dragons, with BiRefNet unless ``settings``
        says otherwise."""
        settings.setdefault("model", "birefnet")
        return self._ctx.figure_builder.build(
            DRAGONS / image,
            FigureSettings(**settings),
            bleed_mm=bleed_mm,
            log=lambda *_: None,
        )

    def _choice(self, name: str, value: str) -> str:
        """The settings panel's name for the choice ``value`` of the option ``name``."""
        option = self._options[name]
        return option.choice_labels[option.choices.index(value)]

    @staticmethod
    def _bottom(m: Mini, above: float = 14.0) -> QRectF:
        """The tab of a single-sided miniature and ``above`` mm of figure over its
        fold."""
        fold = m.folds[0][2]
        return QRectF(0, fold - above, m.width_mm, m.height_mm - fold + above)

    def _compare(
        self, name: str, samples: Sequence[Sample], px_per_mm: float = PX_PER_MM
    ) -> None:
        """Save ``samples`` side by side as the picture ``name``, at ``px_per_mm``
        logical pixels per mm."""
        self._ctx.save(
            self._composer.panels(
                [
                    Panel(self._piece(s.mini, s.rect, px_per_mm), s.title, s.caption)
                    for s in samples
                ]
            ),
            f"settings/{name}",
        )

    def _piece(self, m: Mini, rect: QRectF | None, px_per_mm: float) -> QPixmap:
        """Draw ``m`` as in the app, on white paper: all of it, or the part in ``rect``
        (mm), at ``px_per_mm`` logical pixels per mm."""
        ratio = self._ctx.ratio
        sc = QGraphicsScene()
        self._ctx.minis.draw(sc, m)
        r = rect or QRectF(0, 0, m.width_mm, m.height_mm)
        r = r.adjusted(-PAPER_MM, -PAPER_MM, PAPER_MM, PAPER_MM)
        img = QImage(
            int(r.width() * px_per_mm * ratio),
            int(r.height() * px_per_mm * ratio),
            QImage.Format.Format_ARGB32,
        )
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        sc.render(p, QRectF(img.rect()), r)
        p.end()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(ratio)
        return pix

    # endregion
