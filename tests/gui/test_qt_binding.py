"""Tests of the Qt binding the desktop app is built on."""

import sys

import pytest

pytest.importorskip("PySide6")


@pytest.mark.skipif(
    sys.version_info >= (3, 12), reason="None has no reference count from Python 3.12"
)
def test_qt_calls_keep_the_references_to_none(app):
    """Regression: PySide6 6.12.0 dropped a reference to None on every Qt call that
    returns nothing. After enough calls Python freed None, and the test run crashed
    as it ended."""
    from PySide6.QtWidgets import QLabel

    label = QLabel()
    before = sys.getrefcount(None)
    for _ in range(1000):
        label.setText("x")
    assert sys.getrefcount(None) > before - 100
