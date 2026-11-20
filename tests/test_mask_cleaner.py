"""Tests of cleaning up raw masks, on synthetic masks (no model needed)."""

import cv2


def test_fill_holes_closes_translucent_areas(pipeline, ghost, mask_options):
    m = ghost(ring=True)
    assert m[700, 550] == 0
    clean = pipeline.cleaner.clean(m, mask_options(threshold=40, close_px=9))
    assert clean[700, 550] == 255


def test_largest_component_drops_specks_and_keep_all_keeps_props(
    pipeline, ghost, mask_options
):
    m = ghost()
    cv2.circle(m, (100, 100), 4, 255, -1)  # speck
    cv2.circle(m, (950, 300), 40, 255, -1)  # floating prop
    only = pipeline.cleaner.clean(m, mask_options(close_px=5))
    assert only[300, 950] == 0 and only[100, 100] == 0
    both = pipeline.cleaner.clean(
        m, mask_options(close_px=5, keep_all=True, min_area=1000)
    )
    assert both[300, 950] == 255 and both[100, 100] == 0
