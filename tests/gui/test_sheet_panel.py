"""Tests of the sheet settings panel."""

from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.gui.step import Step

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_the_machine_settings_show_only_when_cut_by_machine(app, prefs):
    """Bleed, marks and the cut file only show (and only matter) when cut by machine."""
    from papermini.gui.panels.sheet_panel import SheetPanel
    from papermini.project.sheet_settings import SheetSettings

    p = SheetPanel(prefs)
    got = []
    p.changed.connect(got.append)
    p.set_settings(SheetSettings())
    for w in (p.bleed, p.marks, p.cut_folds):
        assert not p.is_shown(w)
    p.cut.setCurrentIndex(p.cut.findData("machine"))
    assert got[-1].cut == "machine" and got[-1].bleed_mm == 1.0
    for w in (p.bleed, p.marks, p.cut_folds):
        assert p.is_shown(w)
    p.marks.setCurrentIndex(p.marks.findData("silhouette"))
    p.cut_folds.setChecked(True)
    assert got[-1].marks == "silhouette" and got[-1].cut_folds
    p.set_settings(SheetSettings(cut="machine", bleed_mm=2.0))
    assert p.bleed.value() == 2.0 and p.is_shown(p.bleed)
    p.marks.setCurrentIndex(p.marks.findData("none"))
    assert got[-1].marks == "none"


def test_a_new_window_shows_the_sheet_settings(app, new_window):
    """Regression: a new project's sheet bar showed 0 mm margins and an empty title
    (and editing it would have saved those)."""

    w = new_window()
    assert w.sheet_panel.margin.value() == 12 and w.sheet_panel.gap.value() == 7
    assert w.sheet_panel.title.text() == "Paper miniatures"
    assert not any(sec.isVisibleTo(w.panel) for sec in w.panel.sections)  # empty state


def test_cut_by_machine_rebuilds_with_bleed_and_exports_the_cut_file(
    app, tmp_path, monkeypatch, new_window, wait
):
    """Switching the sheet to machine cutting builds every figure with the bleed, and
    Export PDF also writes the cut file."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.export_dialog import ExportDialog

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.ellipse(im, (250, 300), (150, 220), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    w = new_window()
    w.add_images([tmp_path / "hero.png"])
    fig = w.current()
    assert wait(lambda: fig.up_to_date), fig.error
    hand_w = fig.mini.width_mm
    w.sheet_panel.cut.setCurrentIndex(w.sheet_panel.cut.findData("machine"))
    assert w.project.sheet.machine and fig.bleed_mm == 1.0 and not fig.up_to_date
    assert wait(lambda: fig.up_to_date), fig.error
    assert fig.mini.width_mm > hand_w + 1  # the bleed on both sides

    out = tmp_path / "sheet.pdf"
    seen = {}

    def run(dlg):  # instead of showing the Export dialog: save both, as "sheet"
        seen["name"] = dlg.name.text()
        dlg.folder.setText(str(tmp_path))
        dlg.name.setText("sheet")
        dlg.pdf.setChecked(True)
        dlg.cut.setChecked(True)
        return True

    monkeypatch.setattr(
        ExportDialog,
        "exec",
        lambda dlg: (
            QDialog.DialogCode.Accepted if run(dlg) else QDialog.DialogCode.Rejected
        ),
    )
    w.export_pdf()
    assert seen["name"] == "Paper miniatures"  # (named after the sheet's title)
    assert wait(lambda: (tmp_path / "sheet-cut.svg").exists())
    assert (
        out.exists() and 'id="registration"' in (tmp_path / "sheet-cut.svg").read_text()
    )


def test_the_paper_has_an_orientation_or_a_custom_size(app, prefs):
    """Orientation for a named paper, a width and height for Custom (starting at the
    paper chosen before); the mat only when cut by machine, with its warning."""
    from papermini.gui.panels.sheet_panel import SheetPanel
    from papermini.project.sheet_settings import SheetSettings

    p = SheetPanel(prefs)
    got = []
    p.changed.connect(got.append)
    p.set_settings(SheetSettings())
    assert [p.paper.itemText(i) for i in range(p.paper.count())] == [
        "A3 (297 \u00d7 420 mm)",
        "A4 (210 \u00d7 297 mm)",
        "A5 (148 \u00d7 210 mm)",
        "Letter (8.5 \u00d7 11 in)",
        "Legal (8.5 \u00d7 14 in)",
        "Tabloid (11 \u00d7 17 in)",
        "Custom",
    ]
    assert p.paper.currentData() == "a4" and p.is_shown(p.orientation)
    assert not p.is_shown(p.paper_w) and not p.is_shown(p.mat)
    p.paper.setCurrentIndex(p.paper.findData("a3"))
    p.orientation.setCurrentIndex(p.orientation.findData("landscape"))
    assert (got[-1].paper, got[-1].orientation) == ("a3", "landscape")
    assert got[-1].paper_width_mm is None
    p.paper.setCurrentIndex(p.paper.findData("custom"))  # starts at A3 landscape
    assert (got[-1].paper_width_mm, got[-1].paper_height_mm) == (420, 297)
    assert (
        p.is_shown(p.paper_w)
        and p.is_shown(p.paper_h)
        and not p.is_shown(p.orientation)
    )
    p.paper_h.setValue(350)
    assert got[-1].page == (420, 350)
    p.paper.setCurrentIndex(p.paper.findData("letter"))
    assert got[-1].paper_width_mm is None and got[-1].paper_height_mm is None
    # the mat: cut by machine only, and a warning when the paper is bigger
    p.set_settings(SheetSettings(paper="tabloid", cut="machine"))
    assert p.is_shown(p.mat) and not p.is_shown(p.mat_warning)
    p.mat.setCurrentIndex(p.mat.findData("12x12"))
    assert got[-1].mat == "12x12" and p.is_shown(p.mat_warning)
    assert p.mat_warning.text().startswith("Tabloid (279 \u00d7 432 mm) is bigger than")
    p.mat.setCurrentIndex(p.mat.findData("12x24"))
    assert not p.is_shown(p.mat_warning)
    p.cut.setCurrentIndex(p.cut.findData("hand"))  # hidden, but kept
    assert not p.is_shown(p.mat) and got[-1].mat == "12x24"
    p.set_settings(
        SheetSettings(paper="custom", paper_width_mm=300, paper_height_mm=450)
    )
    assert (p.paper_w.value(), p.paper_h.value()) == (300, 450) and p.is_shown(
        p.paper_w
    )


def test_a_figure_too_big_for_the_paper_is_listed_and_left_off(
    app, tmp_path, monkeypatch, new_window, wait
):
    """The sheet stays empty with a message, a list of the figures under Paper, and
    Print asks before leaving them off."""
    from PySide6.QtWidgets import QMessageBox

    from papermini.gui.exporting.export_dialogs import ExportDialogs
    from papermini.project.sheet_settings import SheetSettings

    im = Image.new("RGBA", (300, 450), (0, 0, 0, 0))
    from PIL import ImageDraw

    ImageDraw.Draw(im).ellipse((30, 30, 270, 420), fill=(200, 40, 30, 255))
    im.save(tmp_path / "hero.png")
    im.save(tmp_path / "imp.png")
    asked, printed = [], []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.No
    )
    monkeypatch.setattr(
        ExportDialogs,
        "print_options",
        lambda self, parent, printer, pages: printed.append(pages) or False,
    )
    w = new_window()
    w.add_images([tmp_path / "hero.png", tmp_path / "imp.png"])
    hero, _imp = w.figures
    hero.entry.settings = replace(hero.entry.settings, height_mm=150, label="Hero")
    w.tabs.setCurrentIndex(Step.SHEET)  # (builds what is missing)
    assert wait(lambda: all(f.mini is not None and f.up_to_date for f in w.figures))
    w.sheet_panel.changed.emit(SheetSettings(paper="a5", orientation="landscape"))
    sp = w.sheet_panel
    assert wait(lambda: w.sheet_banner_box.isVisibleTo(w))
    assert w.sheet_view.scene().items() == []
    assert sp.is_shown(sp.fit_warning)
    text = sp.fit_warning.text()
    assert text.startswith(
        "The following figure is too large to fit on the selected paper:"
    )
    assert "<li>Hero</li>" in text and "imp" not in text
    assert "Pick bigger paper" in text
    w.print_sheet()  # asks; No: does not print
    assert len(asked) == 1 and "\u2022 Hero" in asked[0] and "left off" in asked[0]
    assert printed == []
    w.sheet_panel.changed.emit(SheetSettings(paper="a3"))  # everything fits again
    assert wait(lambda: not w.sheet_banner_box.isVisibleTo(w))
    assert not sp.is_shown(sp.fit_warning)
    assert w.sheet_view.scene().items()
