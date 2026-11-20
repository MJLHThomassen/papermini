"""Tests of the cut files of a sheet cut by machine."""

import numpy as np
import pytest


def test_marks_and_cut_files_follow_the_page(
    output, tmp_path, square_mini, media_box_mm
):
    lay = output.packer.pack(
        [(square_mini("m"), 1)], "a3", cut="machine", orientation="landscape"
    )
    rects = lay.mark_rects()
    assert max(x + w for x, y, w, h in rects) == pytest.approx(420 - 12)
    assert max(y + h for x, y, w, h in rects) == pytest.approx(297 - 12)
    cut = output.cut_files.write(lay, tmp_path / "s-cut.svg")[0].read_text(
        encoding="utf-8"
    )
    assert 'width="420mm"' in cut and 'height="297mm"' in cut
    assert media_box_mm(output.pdf.write(lay, tmp_path / "s.pdf")) == (420, 297)


def test_cut_files_match_the_sheet(output, tmp_path, square_mini):
    """Cut by machine: the PDF gets no cut lines, and a cut file per page holds the cut
    lines where the pieces are on the page plus the same marks as the PDF."""
    import re
    import xml.etree.ElementTree as ET

    m = square_mini(folds=[(0.0, 30.0, 35.0)])
    lay = output.packer.pack([(m, 30)], "a4", 12, 7, cut="machine", marks="corners")
    assert lay.pages > 1 and lay.machine
    pdf = output.pdf.write(lay, tmp_path / "s.pdf")
    assert pdf.read_bytes()[:5] == b"%PDF-"
    paths = output.cut_files.write(lay, output.cut_files.default_path(pdf))
    assert paths == output.cut_files.paths(tmp_path / "s-cut.svg", lay.pages)
    assert [p.name for p in paths[:2]] == ["s-cut.svg", "s-cut-2.svg"]
    ns = {"s": "http://www.w3.org/2000/svg"}
    root = ET.parse(paths[0]).getroot()
    assert root.get("width") == "210mm" and root.get("viewBox") == "0 0 210 297"
    rects = [
        tuple(float(r.get(k)) for k in ("x", "y", "width", "height"))
        for r in root.findall("s:g[@id='registration']/s:rect", ns)
    ]
    assert np.allclose(rects, lay.mark_rects(), atol=1e-3)  # the same marks as the PDF
    cuts = root.findall("s:g[@id='cut']/s:path", ns)
    first = [p for p in lay.placements if p.page == 0]
    assert len(cuts) == len(first)
    xy = [float(v) for v in re.findall(r"[-\d.]+", cuts[0].get("d"))[:2]]
    assert xy == pytest.approx(
        [first[0].x, first[0].y], abs=1e-3
    )  # placed as on the page
    assert root.find("s:g[@id='fold']", ns) is None  # fold lines only when asked for
    folded = ET.fromstring(
        output.cut_files.write(lay, tmp_path / "f.svg", folds=True)[0].read_text()
    )
    assert len(folded.findall("s:g[@id='fold']/s:line", ns)) == len(first)
