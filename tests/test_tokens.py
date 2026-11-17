"""Round tokens: settings and sizes, the token itself (framing, ring, text, cut line), its
SVG and PNG output, the command line and the print sheet, and the app. No model: the
test images carry their own transparency."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from papermini import cli
from papermini.output.png import piece_image, px_per_mm, write_pngs
from papermini.output.sheet import pack, write_pdf
from papermini.output.svg import read_svg, to_svg, write_svgs
from papermini.pipeline import token as tok
from papermini.pipeline.token_info import TokenInfo
from papermini.pipeline.token_options import min_ring_mm
from papermini.project.figure_entry import FigureEntry
from papermini.project.figure_settings import FigureSettings
from papermini.project.project import Project
from papermini.project.project_files import load_project, save_project
from papermini.project.settings import build_mini, settings_with_size


def _figure(path: Path, size=(300, 400)) -> Path:
    """A red figure (an ellipse) on a transparent background."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    w, h = size
    ImageDraw.Draw(im).ellipse(
        [w * 0.2, h * 0.1, w * 0.8, h * 0.9], fill=(200, 40, 30, 255)
    )
    im.save(path)
    return path


def _token(path, **kw):
    s = settings_with_size(dict(kind="token", model="alpha", **kw))
    return build_mini(path, s, log=lambda *a: None)


# region settings and sizes
def test_token_settings_are_checked():
    d = FigureSettings()
    assert (d.kind, d.token_diameter_mm, d.token_border_mm, d.token_text) == (
        "mini",
        25,
        2,
        "none",
    )
    assert (d.token_text_mm, d.token_text_color, d.token_cut_line) == (
        2.5,
        "#ffffff",
        False,
    )
    for bad in (
        {"kind": "standee"},
        {"token_text": "name"},
        {"token_text_style": "wavy"},
        {"token_fill": "pattern"},
        {"token_text_mm": 0},
        {"token_border_mm": -1},
        {"token_diameter_mm": 0},
        {"token_border_color": "red"},
        {"token_area": [0, 0, 0.5]},
        {"token_area": [0.5, 0, 0.4, 1]},
    ):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)
    s = FigureSettings.from_dict({"token_area": "0.1, 0.2, 0.9, 1.0"})
    assert s.token_area == [0.1, 0.2, 0.9, 1.0]
    assert (
        FigureSettings.from_dict({"token_area": [-0.2, -0.1, 1.2, 1.3]}).token_area[0]
        == -0.2
    )


def test_the_creature_size_fills_in_the_diameter():
    assert (
        settings_with_size({"kind": "token", "size": "large"}).token_diameter_mm == 50
    )
    assert settings_with_size({"kind": "token", "size": "huge"}).token_diameter_mm == 75
    edited = settings_with_size(
        {"kind": "token", "size": "large", "token_diameter_mm": 40}
    )
    assert edited.size == "custom" and edited.token_diameter_mm == 40


def test_a_project_keeps_its_tokens(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    tok_s = settings_with_size(
        {
            "kind": "token",
            "size": "large",
            "token_area": [0, 0, 1, 1],
            "token_text": "label_number",
            "token_text_style": "curved",
        }
    )
    mini_s = settings_with_size({"size": "large"})
    p = Project(figures=[FigureEntry(img, tok_s), FigureEntry(img, mini_s, "mini")])
    path = save_project(p, tmp_path / "p.yaml")
    text = path.read_text()
    assert (
        "token_area:\n  - 0" in text or "token_area:\n    - 0" in text
    )  # (a plain list)
    back = load_project(path)
    assert [f.settings for f in back.figures] == [tok_s, mini_s]
    saved = [f.settings.to_dict() for f in back.figures]
    assert saved[0]["token_diameter_mm"] == 50  # a token: its size's diameter
    assert "token_diameter_mm" not in saved[1]  # a mini: nothing about tokens


def test_curved_text_has_a_least_ring():
    assert min_ring_mm(2.5) == 3.5 and min_ring_mm(1.8) == 2.5
    o = tok.TokenOptions(border_mm=2, text="label", text_style="curved", text_mm=2.5)
    assert o.ring_mm() == 3.5
    assert replace(o, text_style="nameplate").ring_mm() == 2
    assert replace(o, text="none").ring_mm() == 2
    assert replace(o, border_mm=6).ring_mm() == 6


def test_an_area_and_its_framing_match():
    area = (-0.1, 0.05, 0.9, 0.8)
    fx, fy, f = tok.area_frame(area, (300, 400), 10.5)
    assert tok.frame_area(fx, fy, f, (300, 400), 10.5) == pytest.approx(area, abs=1e-3)


# endregion


# region the token
def test_a_fitted_figure_stays_inside_the_circle(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(img)
    t = m.token
    assert m.kind == "token" and t.inner_mm == pytest.approx(12.5 - 2)
    assert m.width_mm == m.height_mm and m.figure_height_mm == 25
    # every point of the figure lies inside the circle, with FIT_FREE of it free all round
    pts = np.vstack(m.source_outline)
    c = m.source_cut.points.mean(axis=0)
    r = np.hypot(
        *(m.source_cut.points[0] - c)
    )  # (the circle inside the ring, image px)
    assert np.hypot(*(pts - c).T).max() <= r * (1 - 2 * tok.FIT_FREE) + 2
    assert (
        np.hypot(*(pts - c).T).max() >= r * (1 - 2 * tok.FIT_FREE) - 3
    )  # (and fills it)
    # the cut line is the ring's edge (nothing printed on it by default)
    assert not m.style.cut_line
    assert np.hypot(*(m.cut.points - (t.cx, t.cy)).T) == pytest.approx(12.5)


def test_a_fitted_figure_stays_above_the_nameplate(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(img, token_text="label", token_text_mm=3)
    t = m.token
    plate_top = t.cy + t.inner_mm - tok.PLATE * 3
    assert t.figure_box[3] <= plate_top + 0.05
    assert t.plate[0] == pytest.approx(t.cx)  # the label is centred


def test_a_printed_cut_line_lies_outside_the_ring(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(img, token_cut_line=True, cut_width_mm=0.4)
    t = m.token
    assert m.style.cut_line
    assert np.hypot(*(m.cut.points - (t.cx, t.cy)).T) == pytest.approx(12.5 + 0.2)
    # cut by machine (with bleed) the cut follows the ring
    s = settings_with_size({"kind": "token", "model": "alpha", "token_cut_line": True})
    m = build_mini(img, s, bleed_mm=1.0, log=lambda *a: None)
    assert np.hypot(*(m.cut.points - (m.token.cx, m.token.cy)).T) == pytest.approx(12.5)


def test_the_token_text(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(
        img,
        label="Goblin boss",
        token_text="label_number",
        token_text_style="curved",
        token_text_color="#2f5597",
        token_border_color="#303060",
    )
    items = m.text_items()
    assert {t.kind for t in items} == {"tokentext"}
    assert (
        "".join(t.text for t in items) == "Goblinboss#"
    )  # a letter each, # = the number
    assert {t.color for t in items} == {"#2f5597"}  # the color chosen, always
    letters = [t for t in items if t.text != "#"]
    assert (
        letters[0].rot > 20 and letters[-1].rot < -20
    )  # (along the bottom, both ways)
    # numbered copies: a file each, each with its number
    paths = write_svgs(m, tmp_path / "goblin.svg", 3)
    assert [p.name for p in paths] == ["goblin-1.svg", "goblin-2.svg", "goblin-3.svg"]
    assert ">3</text>" in paths[2].read_text()
    plate = _token(img, label="Goblin", token_text="label_number")
    t = plate.token
    assert (
        t.badge is not None
        and t.badge[1] + t.badge[2] <= t.cy + t.inner_mm - t.plate[3]
    )
    assert [i.text for i in plate.text_items()] == ["Goblin", "#"]


def test_a_token_svg_reads_back(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(img, label="Goblin", token_text="label_number")
    svg = to_svg(replace(m, number=2))
    assert (
        'class="tokentext"' in svg and 'stroke="none"' in svg
    )  # (no cut line printed)
    path = tmp_path / "t.svg"
    path.write_text(svg)
    back = read_svg(path)
    assert [t.text for t in back.text_items()] == ["Goblin", "2"]
    assert not back.style.cut_line
    lay = pack([(back, 2), (m, 1)], "a4")
    assert len(lay.placements) == 3
    write_pdf(lay, tmp_path / "sheet.pdf")


def test_png_of_a_piece(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    m = _token(img, token_text="number")
    scale = px_per_mm(256, 25.4)
    im = piece_image(m, scale)
    assert im.width == pytest.approx(m.width_mm * scale, abs=1) and im.mode == "RGBA"
    assert im.getpixel((0, 0))[3] == 0  # transparent around it
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 255
    paths = write_pngs(m, tmp_path / "goblin.png", scale, 2)
    assert [p.name for p in paths] == ["goblin-1.png", "goblin-2.png"]
    mini = build_mini(img, settings_with_size({"model": "alpha"}), log=lambda *a: None)
    assert piece_image(mini, scale).height == pytest.approx(
        mini.height_mm * scale, abs=1
    )


def test_make_tokens_on_the_command_line(tmp_path, capsys):
    img = _figure(tmp_path / "goblin.png")
    out = tmp_path / "out"
    assert (
        cli.main(
            [
                "make",
                str(img),
                "--model",
                "alpha",
                "--kind",
                "token",
                "--size",
                "large",
                "--token-text",
                "number",
                "--copies",
                "2",
                "--format",
                "both",
                "-o",
                str(out),
            ]
        )
        == 0
    )
    assert sorted(p.name for p in out.iterdir()) == [
        "goblin-1.png",
        "goblin-1.svg",
        "goblin-2.png",
        "goblin-2.svg",
    ]
    assert Image.open(out / "goblin-1.png").width == pytest.approx(
        512, abs=8
    )  # 2 squares
    assert (
        cli.main(
            [
                "make",
                str(img),
                "--model",
                "alpha",
                "--kind",
                "token",
                "--format",
                "png",
                "--png-dpi",
                "254",
                "-o",
                str(tmp_path / "d.png"),
            ]
        )
        == 0
    )
    assert Image.open(tmp_path / "d.png").width == pytest.approx(25.9 * 10, abs=3)
    with pytest.raises(SystemExit, match="not both"):
        cli.main(["make", str(img), "--png-px", "100", "--png-dpi", "300"])


def test_tokens_and_minis_on_one_sheet(tmp_path, capsys):
    _figure(tmp_path / "goblin.png")
    (tmp_path / "p.yaml").write_text(
        "sheet: {output: sheet.pdf}\n"
        "figures:\n"
        "  - {image: goblin.png, model: alpha}\n"
        "  - {image: goblin.png, name: tok, model: alpha, kind: token, copies: 3,\n"
        "     token_text: number}\n"
    )
    assert cli.main(["batch", str(tmp_path / "p.yaml")]) == 0
    assert "4 pieces" in capsys.readouterr().out
    assert (tmp_path / "minis" / "tok-3.svg").is_file()


def _count(art, channel):
    """Counts the pixels of the art that are clearly red, green or blue (channel 0, 1
    or 2)."""
    a = np.asarray(art.convert("RGB")).astype(int)
    others = [c for c in range(3) if c != channel]
    return int(((a[..., channel] > 200) & (a[..., others] < 80).all(-1)).sum())


def test_a_token_figure_with_an_outline(tmp_path):
    img = _figure(tmp_path / "goblin.png")
    plain = _token(img, margin_color="#00ff00")
    outlined = _token(img, token_outline=True, margin_color="#00ff00")
    assert _count(plain.art, 1) == 0
    assert _count(outlined.art, 1) > 0  # the outline, in the margin color


def test_a_token_filled_with_the_picture(tmp_path):
    im = Image.new("RGB", (300, 400), (0, 0, 255))  # a blue background
    ImageDraw.Draw(im).ellipse([60, 40, 240, 360], fill=(200, 40, 30))
    im.save(tmp_path / "goblin.png")
    mask = Image.new("L", (300, 400), 0)
    ImageDraw.Draw(mask).ellipse([60, 40, 240, 360], fill=255)
    mask.save(tmp_path / "goblin_mask.png")
    common = {
        "kind": "token",
        "model": "mask",
        "mask": str(tmp_path / "goblin_mask.png"),
    }

    def background(**kw):
        """Builds the token and keeps only its art inside the ring and over 1 mm from
        the figure's box."""
        s = settings_with_size({**common, **kw})
        m = build_mini(tmp_path / "goblin.png", s, log=lambda *a: None)
        t, a = m.token, np.asarray(m.art.convert("RGB")).copy()
        assert isinstance(t, TokenInfo) and t.figure_box is not None
        px = a.shape[1] / m.width_mm
        y, x = (np.mgrid[: a.shape[0], : a.shape[1]] + 0.5) / px
        x0, y0, x1, y1 = t.figure_box
        near = (x > x0 - 1) & (x < x1 + 1) & (y > y0 - 1) & (y < y1 + 1)
        a[near | (np.hypot(x - t.cx, y - t.cy) > t.inner_mm - 0.3)] = 0
        return Image.fromarray(a)

    assert _count(background(), 2) == 0  # the fill color behind the figure
    assert _count(background(token_fill="image"), 2) > 0  # the picture's background


# endregion


# region the app
@pytest.fixture
def window(window, wait, tmp_path):
    """The shared main window with one token figure, built, in the Miniature step."""
    w = window
    w.resize(1300, 820)
    w.add_images(
        [_figure(tmp_path / "goblin.png")],
        settings_with_size({"kind": "token", "model": "alpha"}),
    )
    w.list.setCurrentRow(0)
    w.tabs.setCurrentIndex(w.MINI)
    assert wait(lambda: w.figures[0].mini is not None and w.figures[0].up_to_date)
    return w


def _built(wait, w):
    f = w.figures[0]
    assert wait(lambda: f.mini is not None and f.up_to_date)
    return f.mini


def test_kind_switches_the_groups(app, prefs):
    from papermini.gui.panels.figure_fields import MINIATURE
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel()
    got = []
    p.changed.connect(got.append)
    p.set_settings(FigureSettings(label="Boss"), "x", "x")
    p.set_step(MINIATURE)
    shown = lambda: [s.header.text() for s in p.sections if s.isVisibleTo(p)]
    assert "Back side" in shown() and "Token" not in shown()
    assert p.kind_row.isVisibleTo(p) and p.is_shown("dimensions")
    p._w["kind"][1].buttons["token"].click()
    assert got[-1].kind == "token" and got[-1].label == "Boss"  # (the label is kept)
    assert shown() == [
        "Size",
        "Token",
        "Token text",
        "Image outline",
        "Cut line",
        "Text",
    ]
    assert p.is_shown("token_diameter_mm") and not p.is_shown("dimensions")
    assert "token" in p.step_hint.text()
    # token text: off is "none"; on, it shows the label first
    assert not p.token_text_switch.isChecked() and got[-1].token_text == "none"
    p.token_text_switch.setChecked(True)
    assert got[-1].token_text == "label" and p.is_shown("token_text_mm")
    # curved text: the ring is at least as wide as the text needs, and says so
    style = p._w["token_text_style"][1]
    style.setCurrentIndex(style.findData("curved"))
    ring = p._w["token_border_mm"][1]
    assert ring.minimum() == min_ring_mm(2.5) and ring.value() == min_ring_mm(2.5)
    assert p.ring_hint.isVisibleTo(p) and "3.5 mm" in p.ring_hint.text()
    # a token can switch its outline and cut line off; both off by default
    for name in ("token_outline", "token_cut_line"):
        box = p._switches[name]
        assert box.switch.isVisibleTo(p) and not box.active()
    p._w["kind"][1].buttons["mini"].click()
    assert got[-1].kind == "mini" and "Back side" in shown()


def test_drag_a_token_figure(app, window, wait):
    from papermini.gui.views.mini_view import MiniView

    w = window
    m = w.figures[0].mini
    v = w.mini_view
    assert isinstance(v, MiniView) and v._box is not None
    b0 = m.token.figure_box
    cx, cy = (b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2
    pa, pb = v.mapFromScene(QPointF(cx, cy)), v.mapFromScene(QPointF(cx + 3, cy + 2))
    QTest.mousePress(v.viewport(), Qt.LeftButton, pos=pa)
    for k in range(1, 5):
        QTest.mouseMove(v.viewport(), pa + (pb - pa) * (k / 4))
    assert v._preview is not None  # the figure moves with the mouse
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, pos=pb)
    assert w.figures[0].entry.settings.token_area is not None
    m = _built(wait, w)
    b = m.token.figure_box
    assert (b[0] - b0[0], b[1] - b0[1]) == pytest.approx((3, 2), abs=0.15)
    # a corner makes it bigger around the box's centre
    pa = v.mapFromScene(QPointF(b[2], b[3]))
    pb = v.mapFromScene(QPointF(b[2] + 2, b[3] + 2))
    QTest.mousePress(v.viewport(), Qt.LeftButton, pos=pa)
    QTest.mouseMove(v.viewport(), pb)
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, pos=pb)
    b1 = _built(wait, w).token.figure_box
    assert b1[2] - b1[0] > b[2] - b[0]
    assert ((b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2) == pytest.approx(
        ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), abs=0.15
    )
    # Esc cancels a drag, a click changes nothing
    area = w.figures[0].entry.settings.token_area
    QTest.mousePress(v.viewport(), Qt.LeftButton, pos=pa)
    QTest.mouseMove(v.viewport(), pb)
    QTest.keyClick(v, Qt.Key_Escape)
    assert v._preview is None
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, pos=pb)
    QTest.mouseClick(v.viewport(), Qt.LeftButton, pos=v.mapFromScene(QPointF(cx, cy)))
    assert w.figures[0].entry.settings.token_area == area
    # Clear fits it again
    w.panel._w["token_area"][1].edit.clear()
    w.panel._emit()
    assert w.figures[0].entry.settings.token_area is None


def test_export_a_figure_as_svg_or_png(app, window, tmp_path, monkeypatch, prefs):
    w = window
    item = w.list.item(0)
    from papermini.gui.widgets.figure_delegate import SUBTITLE_ROLE

    assert item.data(SUBTITLE_ROLE) == "⌀ 25 mm"
    for name, filt in (
        ("a.png", w.PNG_FILTER),
        ("b", w.PNG_FILTER),
        ("c.svg", w.SVG_FILTER),
    ):
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, n=name, f=filt: (str(tmp_path / n), f)),
        )
        w._save_piece(w.figures[0])
    assert {"a.png", "b.png", "c.svg"} <= {p.name for p in tmp_path.iterdir()}
    assert Image.open(tmp_path / "a.png").width == pytest.approx(26 * 256 / 25.4, abs=3)
    prefs.set_png_size_mode("dpi")
    prefs.set_png_dpi(127)
    assert w._png_scale() == pytest.approx(5)
    # Export all asks which files to write
    out = tmp_path / "all"
    out.mkdir()
    monkeypatch.setattr(w, "_ask_format", lambda: "both")
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(out))
    )
    w._save_all()
    assert sorted(p.suffix for p in out.iterdir()) == [".png", ".svg"]
    monkeypatch.setattr(w, "_ask_format", lambda: None)  # (cancelled: nothing)
    w._save_all()
    assert len(list(out.iterdir())) == 2


def test_the_images_preferences(app, window, prefs):
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    assert prefs.png_size_mode() == "square" and prefs.png_px_per_mm(25.4) == 256 / 25.4
    dlg = PreferencesDialog(window, "images")
    assert dlg.png_px.isEnabled() and not dlg.png_dpi.isEnabled()
    assert dlg.png_px.suffix() == ""  # (the unit is beside the box)
    dlg.png_buttons["dpi"].setChecked(True)
    assert prefs.png_size_mode() == "dpi" and dlg.png_dpi.isEnabled()
    dlg.png_dpi.setValue(600)
    assert prefs.png_px_per_mm(25.4) == pytest.approx(600 / 25.4)
    dlg.close()


def test_the_start_card_keeps_its_width(app, prefs, tmp_path):
    """Regression: the card was as wide as its recent projects first asked, then shrank
    once their folders were shortened."""
    from papermini.gui.widgets.empty_state import EmptyState

    paths = []
    for n in ("a.yaml", "a-much-longer-project-name.yaml"):
        p = tmp_path / "D&D" / "some deep folder" / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("figures: []\n")
        paths.append(p)
    e = EmptyState()
    assert e.sizeHint().width() == e.maximumWidth()
    e.set_recent(paths)
    assert e.sizeHint().width() == e.maximumWidth()


# endregion
