"""Tests of the main window's layout: the side panels, the header, the start
card and the theme."""

import pytest

pytest.importorskip("PySide6")


pytestmark = pytest.mark.usefixtures("fake_default_model")


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


def test_side_panels_can_be_resized_freely(app, new_window):
    """Regression: the sheet bar held the canvas at ~760 px, so the side panels
    could hardly be dragged wider."""
    from PySide6.QtCore import Qt

    w = new_window()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1900, 900)  # (room for the settings side's minimum)
    w.show()
    app.processEvents()
    canvas = w.splitter.widget(1)
    assert canvas.minimumSizeHint().width() < 400
    w.splitter.setSizes([520, 400, 520])  # much wider side panels
    app.processEvents()
    sizes = w.splitter.sizes()
    assert sizes[0] > 480 and sizes[2] > 480
    assert w.splitter.isCollapsible(0) and w.splitter.isCollapsible(2)
    assert not w.splitter.isCollapsible(1)


def test_the_side_panels_collapse_and_reopen(app, new_window):
    """The header buttons and View menu collapse and reopen both side panels,
    and follow panels that were dragged shut."""
    from PySide6.QtCore import Qt

    w = new_window()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1440, 900)
    w.show()
    app.processEvents()
    width = w.splitter.sizes()[0]
    assert w.side_visible(0) and w.side_visible(2) and w.a_left.isChecked()

    w.btn_left.click()  # header button hides it
    app.processEvents()
    assert w.splitter.sizes()[0] == 0 and not w.a_left.isChecked()
    assert w.btn_left.isVisible()  # still there to bring it back
    w.btn_left.click()
    app.processEvents()
    assert w.splitter.sizes()[0] == width and w.a_left.isChecked()

    w.a_right.trigger()  # menu item hides it
    app.processEvents()
    assert w.splitter.sizes()[2] == 0 and "Show" in w.btn_right.toolTip()
    w.a_right.trigger()
    app.processEvents()
    assert w.splitter.sizes()[2] >= w.splitter.widget(2).minimumWidth()

    w.splitter.setSizes([0] + w.splitter.sizes()[1:])  # as if dragged shut
    w.splitter.splitterMoved.emit(0, 1)
    assert not w.a_left.isChecked()
    assert "View" in [a.text() for a in w.menu.actions()]


def test_a_panel_dragged_shut_reopens_at_its_dragged_width(app, new_window):
    from PySide6.QtCore import Qt

    w = new_window()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1900, 900)  # (room for the settings side's minimum)
    w.show()
    app.processEvents()
    s = w.splitter.sizes()
    w.splitter.setSizes([420, s[1] - 160, s[2]])  # dragged wider...
    w.splitter.splitterMoved.emit(420, 1)
    s = w.splitter.sizes()
    w.splitter.setSizes([0, s[1] + s[0], s[2]])  # ...then dragged shut
    w.splitter.splitterMoved.emit(0, 1)
    w.set_side_visible(0, True)
    app.processEvents()
    assert abs(w.splitter.sizes()[0] - 420) <= 2


def test_the_panel_layout_is_remembered(app, new_window):
    """Collapsed panels and their widths come back after a restart."""
    from PySide6.QtCore import QSettings, Qt

    from papermini.gui import prefs

    assert prefs.store().format() == QSettings.IniFormat  # not the real settings

    def window():
        w = new_window()
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1900, 900)  # (room for the settings side's minimum)
        w.show()
        app.processEvents()
        return w

    w = window()
    s = w.splitter.sizes()
    w.splitter.setSizes([400, s[1] + s[0] - 400, s[2]])
    w.splitter.splitterMoved.emit(400, 1)
    w.set_side_visible(2, False)
    right = w._side_width[2]
    w.close()

    w = window()
    try:
        assert not w.side_visible(2) and not w.a_right.isChecked()
        assert abs(w.splitter.sizes()[0] - 400) <= 2
        w.set_side_visible(2, True)
        assert abs(w.splitter.sizes()[2] - right) <= 2
        assert w.btn_left.accessibleName() == "Hide the figure list"
        assert w.btn_left.focusPolicy() == Qt.TabFocus
    finally:
        w.close()


def test_the_logo_is_in_the_header_the_start_card_and_the_window_icon(app, new_window):
    from PySide6.QtCore import QSize

    from papermini.gui import theme

    def colors(pm):
        img = pm.toImage()
        return {
            img.pixelColor(x, y).name()
            for x in range(img.width())
            for y in range(img.height())
            if img.pixelColor(x, y).alpha() == 255
        }

    assert (
        theme.LOGO.is_file()
    )  # shipped as package data (pyproject.toml, papermini.spec)
    pm = theme.logo_pixmap(64)
    assert pm.width() == 128  # 2x for sharp rendering on high-DPI screens
    assert {"#fd3c1b", "#000d1d", "#ffffff"} <= colors(
        pm
    )  # full color, not a line icon
    assert pm.toImage().pixelColor(0, 0).alpha() == 0  # transparent around the sticker

    sizes = theme.app_icon().availableSizes()
    assert QSize(16, 16) in sizes and QSize(256, 256) in sizes

    w = new_window()
    assert "#fd3c1b" in colors(w.logo.pixmap())
    assert "#fd3c1b" in colors(w.empty.icon.pixmap())
    w.set_theme("dark")  # re-theming must not swap the logo for a tinted line icon
    assert "#fd3c1b" in colors(w.logo.pixmap())
    assert "#fd3c1b" in colors(w.empty.icon.pixmap())


def test_the_start_card_offers_images_and_a_project(app, monkeypatch, new_window):
    from papermini.gui.window import main_window

    asked = []
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileNames",
        lambda parent, caption, folder, filters: (
            asked.append((caption, filters)),
            ([], ""),
        )[1],
    )
    w = new_window()
    assert w.empty.button.text() == "Add images…"
    assert w.empty.open_button.text() == "Open project…"
    w.empty.button.click()
    w.empty.open_button.click()
    assert asked[0][0] == "Add images"
    assert asked[1][1].startswith(main_window.PROJECT_FILTER)  # projects listed first


def test_the_header_steps_stay_centred(app, tmp_path, new_window):
    """The step buttons sit in the middle of the window, whatever the header holds."""
    from PySide6.QtCore import Qt

    w = new_window()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1360, 820)
    w.show()
    for change in (lambda: None, w._set_modified):
        change()
        for _ in range(5):
            app.processEvents()
        centre = w.views.mapTo(w, w.views.rect().center()).x()
        assert abs(centre - w.width() / 2) <= 2


def test_a_theme_asks_for_the_fusion_style_by_name(app, monkeypatch):
    """Applying a theme sets the Fusion style by its name, not with a style object."""
    from papermini.gui import theme

    styles = []
    monkeypatch.setattr(app, "setStyle", styles.append)
    for slow in ("setStyleSheet", "setPalette"):  # (each re-styles every widget)
        monkeypatch.setattr(app, slow, lambda *_: None)
    theme.apply(app, "light")
    assert styles == ["Fusion"]
