from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinModel:
    """A built-in segmentation model: what it is, its licence, where it downloads
    from and how ``OnnxSegmenter`` runs it."""

    title: str
    about: str  # one sentence on what the model is good at
    licence: str
    commercial: bool  # False: users accept that before it downloads
    licence_url: str
    mb: int  # the size of the download
    page: str  # the model's home page
    url: str  # where the model file downloads from
    file: str  # the model file's name in the cache folder
    size: int  # the width and height of the model's input, in pixels
    mean: float | tuple[float, float, float]  # per channel, or for all three
    std: float | tuple[float, float, float]
    post: str  # how the output becomes 0-1, as ``OnnxSegmenter`` explains
