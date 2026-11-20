"""Tests of the token options."""

from dataclasses import replace

from papermini.pipeline.token_options import TokenOptions


def test_curved_text_has_a_least_ring():
    assert TokenOptions.min_ring_mm(2.5) == 3.5 and TokenOptions.min_ring_mm(1.8) == 2.5
    o = TokenOptions(border_mm=2, text="label", text_style="curved", text_mm=2.5)
    assert o.ring_mm() == 3.5
    assert replace(o, text_style="nameplate").ring_mm() == 2
    assert replace(o, text="none").ring_mm() == 2
    assert replace(o, border_mm=6).ring_mm() == 6
