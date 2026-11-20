"""Tests of framing the picture in a token's circle."""

import pytest


def test_an_area_and_its_framing_match(pipeline):
    area = (-0.1, 0.05, 0.9, 0.8)
    fx, fy, f = pipeline.framer.from_area(area, (300, 400), 10.5)
    assert pipeline.framer.to_area(fx, fy, f, (300, 400), 10.5) == pytest.approx(
        area, abs=1e-3
    )
