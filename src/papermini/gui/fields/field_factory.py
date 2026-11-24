from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial

from ...project.option import Option
from ..theme_service import ThemeService
from .check_field import CheckField
from .choice_field import ChoiceField
from .color_field import ColorField
from .field import Field
from .int_slider_field import IntSliderField
from .number_field import NumberField
from .text_field import TextField

FieldMaker = Callable[[Option, Callable[..., None]], Field]


class FieldFactory:
    """Builds the fields of a settings panel from their options. ``special`` gives the
    fields that are not built from their option alone the class that builds them, by the
    name the panel knows them by. ``themes`` gives the sliders their colors."""

    def __init__(self, special: Mapping[str, FieldMaker], themes: ThemeService) -> None:
        self._special = special
        self._themes = themes

    def build(self, name: str, option: Option, changed: Callable[..., None]) -> Field:
        """Return the field ``name``, built from ``option``, which calls ``changed`` on
        every edit."""
        maker = self._special.get(name) or self._maker(option)
        return maker(option, changed)

    def _maker(self, option: Option) -> FieldMaker:
        if option.type is bool:
            return CheckField
        if option.color:
            return ColorField
        if option.choices:
            return ChoiceField
        if option.slider is not None:
            return partial(IntSliderField, themes=self._themes)
        if option.widget:
            return NumberField
        return TextField
