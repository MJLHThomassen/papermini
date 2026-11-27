"""Tests of style presets in the app: the Style row of the settings panel, the
presets the app offers, and the Style presets page of the preferences. Off-screen,
no model."""

from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from papermini.gui.dialogs.style_name_prompt import StyleNamePrompt
from papermini.gui.style_library import StyleLibrary
from papermini.project.style_preset import StylePreset

pytestmark = pytest.mark.usefixtures("fake_default_model")

DARK = StylePreset("Dark tabs", {"tab_color": "#000000"})
ANSWER = QMessageBox.StandardButton


@pytest.fixture
def figures(window, tmp_path, figure_image):
    """Adds two figures, a and b, to the window, with b selected."""
    paths = [figure_image(tmp_path / f"{n}.png")[0] for n in "ab"]
    window.add_images(paths)
    return window


@pytest.fixture
def named(monkeypatch):
    """Makes every name prompt answer the name given to ``named(name)``."""

    def named(name: str) -> None:
        monkeypatch.setattr(StyleNamePrompt, "ask", lambda self, *a, **k: name)

    return named


@pytest.fixture
def answer(monkeypatch):
    """Makes every question answer the button given to ``answer(button)``, and
    returns the questions asked."""
    asked = []

    def answer(button) -> list:
        def question(*args, **kwargs):
            asked.append(args[2])
            return button

        monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
        return asked

    return answer


def _select(page, name: str) -> None:
    (item,) = page.list.findItems(name, Qt.MatchFlag.MatchExactly)
    page.list.setCurrentItem(item)


def _edit(page, **changes) -> None:
    """Change the settings the page's editor shows, as typing in its fields does."""
    editor = page.editor
    editor.set_settings(replace(editor.settings(), **changes))
    editor.changed.emit(editor.settings())


# region the presets offered


def test_the_project_version_of_a_preset_wins_and_comes_in_place_of_the_other(prefs):
    prefs.save_user_styles([DARK])
    styles = StyleLibrary(prefs)
    theirs = StylePreset("Dark tabs", {"tab_color": "#222222"})
    only_here = StylePreset("Crypt", {"margin_mm": 3.0})
    offered = styles.offered([only_here, theirs])
    assert [p.name for p in offered] == [
        "Standing mini",
        "Standing mini - dark mode",
        "Token",
        "Dark tabs",
        "Crypt",
    ]
    assert offered[3] is theirs


def test_each_preset_says_where_it_comes_from(prefs):
    prefs.save_user_styles([DARK])
    styles = StyleLibrary(prefs)
    token = styles.find("Token", [])
    assert token is not None
    assert styles.note(token, []) == "Comes with papermini"
    assert styles.note(DARK, []) == "Yours"
    assert styles.note(DARK, [DARK]) == "Yours, also in this project"
    other = StylePreset("Dark tabs", {"tab_color": "#222222"})
    assert styles.note(other, [other]) == (
        "This project's version, which differs from yours"
    )
    crypt = StylePreset("Crypt", {})
    assert styles.note(crypt, [crypt]) == "Only in this project"


# endregion

# region the Style row


def test_the_style_row_shows_the_preset_the_figure_has_or_custom(figures):
    w = figures
    assert w.panel.style_name() == "Standing mini"
    w.panel.field("margin_mm").setValue(3.0)
    assert w.current().entry.settings.margin_mm == 3.0
    assert w.panel.style_name() == ""
    assert w.panel.style_box.currentText() == "Custom"


def test_picking_a_preset_gives_the_figure_its_style_as_one_step(figures):
    w = figures
    fig = w.current()
    fig.entry.settings = replace(fig.entry.settings, label="Ogre", tab_shape="round")
    w.apply_style("Token")
    assert fig.entry.settings.kind == "token"
    assert fig.entry.settings.tab_shape == "square"  # back to the default
    assert fig.entry.settings.label == "Ogre"  # not part of a style
    assert w.panel.style_name() == "Token"
    assert w.a_undo.text() == "Undo applying the style Token"
    w.a_undo.trigger()
    assert fig.entry.settings.kind == "mini"


def test_a_preset_of_the_users_is_kept_in_the_project_and_a_built_in_one_is_not(
    figures, prefs
):
    w = figures
    prefs.save_user_styles([DARK])
    w.apply_style("Standing mini - dark mode")
    assert w.project.presets == []
    w.apply_style("Dark tabs")
    assert w.project.presets == [DARK]
    w.a_undo.trigger()
    assert w.project.presets == []


def test_a_style_can_be_given_to_every_figure_as_one_step(figures):
    w = figures
    w.apply_style("Token")
    w.apply_style_to_all()
    assert [f.entry.settings.kind for f in w.figures] == ["token", "token"]
    assert w.a_undo.text() == "Undo applying the style Token to all figures"
    w.a_undo.trigger()
    assert [f.entry.settings.kind for f in w.figures] == ["mini", "token"]


def test_a_figures_style_can_be_saved_as_a_preset(figures, prefs, named):
    w = figures
    w.panel.field("margin_mm").setValue(3.0)
    named("Wide margin")
    w.save_style()
    wide = StylePreset("Wide margin", {"margin_mm": 3.0})
    assert prefs.user_styles() == [wide]
    assert w.project.presets == [wide] and w.panel.style_name() == "Wide margin"


def test_a_new_figure_gets_the_default_style_or_the_selected_figures(
    window, prefs, tmp_path, figure_image
):
    prefs.set_default_style_name("Token")
    window.add_images([figure_image(tmp_path / "a.png")[0]])
    assert window.current().entry.settings.kind == "token"
    window.apply_style("Standing mini")
    window.add_images([figure_image(tmp_path / "b.png")[0]])
    assert [f.entry.settings.kind for f in window.figures] == ["mini", "mini"]


# endregion

# region the Style presets page


def test_a_built_in_preset_cannot_be_changed(window):
    page = window.preferences_dialog("styles").styles
    _select(page, "Token")
    assert not page.editor.isEnabled()
    assert page.b_save_changes.isHidden() and page.b_cancel_changes.isHidden()


def test_the_page_shows_only_the_settings_that_matter(window, prefs):
    prefs.save_user_styles([DARK])
    page = window.preferences_dialog("styles").styles
    _select(page, "Dark tabs")

    def shown(text: str) -> bool:
        (label,) = [x for x in page.editor.findChildren(QLabel) if x.text() == text]
        return label.isVisibleTo(page.editor)

    assert shown("Tab") and shown("Front") and not shown("Token")
    _edit(page, kind="token")
    assert shown("Token") and not shown("Tab")
    _edit(page, kind="mini", no_tab=True)
    assert shown("Tab") and not shown("Front")  # (the switch of Tab is in its header)


def test_changes_to_a_preset_are_kept_only_once_saved(window, prefs):
    prefs.save_user_styles([DARK])
    page = window.preferences_dialog("styles").styles
    _select(page, "Dark tabs")
    assert not page.b_save_changes.isEnabled()
    _edit(page, tab_shape="round")
    assert page.b_save_changes.isEnabled() and prefs.user_styles() == [DARK]
    page.cancel_changes()
    assert page.editor.settings().tab_shape == "square"
    assert not page.b_save_changes.isEnabled()
    _edit(page, tab_shape="round")
    page.save_changes()
    assert prefs.user_styles() == [
        StylePreset("Dark tabs", {"tab_shape": "round", "tab_color": "#000000"})
    ]


def test_leaving_a_preset_with_unsaved_changes_asks_to_save_them(window, prefs, answer):
    prefs.save_user_styles([DARK])
    page = window.preferences_dialog("styles").styles
    _select(page, "Dark tabs")
    _edit(page, margin_mm=3.0)
    asked = answer(ANSWER.Cancel)
    _select(page, "Token")
    assert asked == ["Save the changes to the style preset Dark tabs?"]
    assert page.list.currentItem().text() == "Dark tabs"
    answer(ANSWER.Discard)
    _select(page, "Token")
    assert page.list.currentItem().text() == "Token" and prefs.user_styles() == [DARK]
    _select(page, "Dark tabs")
    _edit(page, margin_mm=3.0)
    answer(ANSWER.Save)
    _select(page, "Token")
    assert prefs.user_styles()[0].values["margin_mm"] == 3.0


def test_closing_with_unsaved_changes_asks_to_save_them(window, prefs, answer):
    prefs.save_user_styles([DARK])
    dlg = window.preferences_dialog("styles")
    dlg.show()
    _select(dlg.styles, "Dark tabs")
    _edit(dlg.styles, margin_mm=3.0)
    answer(ANSWER.Cancel)
    dlg.reject()
    assert dlg.isVisible()
    answer(ANSWER.Discard)
    dlg.reject()
    assert not dlg.isVisible() and prefs.user_styles() == [DARK]


def test_a_project_preset_changed_in_the_preferences_is_one_step(figures, monkeypatch):
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    w = figures
    w.project.presets = [DARK]

    def change(dlg):
        _select(dlg.styles, "Dark tabs")
        _edit(dlg.styles, fold_mm=2.0)
        dlg.styles.save_changes()
        return 0

    monkeypatch.setattr(PreferencesDialog, "exec", change)
    w.show_preferences("styles")
    assert w.project.presets[0].values == {"tab_color": "#000000", "fold_mm": 2.0}
    assert w.a_undo.text() == "Undo changing the style presets"
    w.a_undo.trigger()
    assert w.project.presets == [DARK]


def test_a_copy_of_a_preset_is_the_users_own_and_can_be_renamed(window, prefs, named):
    prefs.set_default_style_name("Dark tabs")
    prefs.save_user_styles([DARK])
    page = window.preferences_dialog("styles").styles
    _select(page, "Token")
    named("My token")
    page.copy_preset()
    assert page.list.currentItem().text() == "My token" and page.editor.isEnabled()
    _select(page, "Dark tabs")
    named("Black tabs")
    page.rename_preset()
    assert [p.name for p in prefs.user_styles()] == ["Black tabs", "My token"]
    assert prefs.default_style_name() == "Black tabs"


def test_a_preset_exported_to_a_file_can_be_imported(
    window, prefs, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    prefs.save_user_styles([DARK])
    page = window.preferences_dialog("styles").styles
    _select(page, "Dark tabs")
    path = tmp_path / "dark.yaml"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), ""))
    )
    page.export_preset()
    prefs.save_user_styles([])
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(path), ""))
    )
    page.import_presets()
    assert prefs.user_styles() == [DARK]
    assert page.list.currentItem().text() == "Dark tabs"


def test_the_preferences_window_can_be_made_small(window):
    dlg = window.preferences_dialog("styles")
    assert dlg.minimumSizeHint().width() < 400
    assert dlg.minimumSizeHint().height() < 300


# endregion
