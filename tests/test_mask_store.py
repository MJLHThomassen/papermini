"""Tests of keeping the models' masks on disk."""

from papermini.pipeline.segmentation import segment
from papermini.pipeline.segmentation.mask_store import MaskStore
from papermini.pipeline.segmentation.segmenter_registry import SegmenterRegistry


def test_clear_masks_keeps_the_folder_and_other_files():
    """Clearing the masks deletes them (and leftovers of interrupted writes) but keeps
    the folder, so a build saving a mask meanwhile still can, and the models."""
    masks = MaskStore()
    d = masks.folder()
    d.mkdir(parents=True)
    for name in ("a.png", "b.png", "c.123.456.tmp"):
        (d / name).write_bytes(b"x")
    model = SegmenterRegistry.path(segment.DEFAULT_MODEL)
    model.write_bytes(b"model")
    assert [p.name for p in masks.files()] == ["a.png", "b.png"]
    assert masks.clear() == 2
    assert d.is_dir() and not any(d.iterdir()) and masks.files() == []
    assert model.exists()
    assert masks.clear() == 0
