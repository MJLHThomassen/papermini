"""Tests of fitting a piece's text to its room."""

from papermini.pipeline.text_fitter import TextFitter


def test_the_font_changes_the_text_size(fonts):
    """Labels are measured in their own font: a wide font shrinks to fit sooner."""
    narrow = TextFitter.label_size(fonts, "Red dragon", 14.0, 3.4, "Times")
    wide = TextFitter.label_size(fonts, "Red dragon", 14.0, 3.4, "Uncial Antiqua")
    assert wide < narrow <= 3.4
