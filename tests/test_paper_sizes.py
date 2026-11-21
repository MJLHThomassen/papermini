"""Tests of the paper sizes and the cutting mats."""

import pytest

from papermini.output.paper_sizes import PaperSizes


def test_paper_sizes_turn_and_name_themselves():
    assert PaperSizes.PAPER_CHOICES == (
        "a3",
        "a4",
        "a5",
        "letter",
        "legal",
        "tabloid",
        "custom",
    )
    assert PaperSizes.size("a3") == (297, 420) and PaperSizes.size(
        "a3", "landscape"
    ) == (
        420,
        297,
    )
    assert PaperSizes.size("tabloid") == pytest.approx((279.4, 431.8))
    assert PaperSizes.size((300, 200), "landscape") == (
        300,
        200,
    )  # a custom size is as given
    assert (
        PaperSizes.text("letter") == "Letter"
        and PaperSizes.text("a5", "landscape") == "A5 landscape"
    )
    assert PaperSizes.text((300, 450.5)) == "300 x 450.5 mm"
    for bad in (("a2", "portrait"), ("a4", "sideways")):
        with pytest.raises(ValueError):
            PaperSizes.size(*bad)


def test_mats_fit_either_way_round():
    assert PaperSizes.fits_mat((210, 297), "12x12") and PaperSizes.fits_mat(
        (297, 210), "12x12"
    )
    assert not PaperSizes.fits_mat((297, 420), "12x12")
    assert PaperSizes.fits_mat((420, 297), "12x24") and PaperSizes.fits_mat(
        (279.4, 431.8), "12x24"
    )
    assert not PaperSizes.fits_mat((310, 400), "12x24")
    assert (
        PaperSizes.mat_warning("a3", "portrait", None) == ""
        and PaperSizes.mat_warning("a3", "portrait", "12x24") == ""
    )
    assert PaperSizes.mat_warning("tabloid", "landscape", "12x12") == (
        "Tabloid landscape (432 × 279 mm) is bigger than the 12 × 12 in mat "
        "(305 × 305 mm)."
    )
