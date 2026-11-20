"""Tests of the image files papermini reads: file types, file links and folders."""

from pathlib import Path

from papermini.support.image_files import ImageFiles


def test_file_uris_and_image_types(tmp_path):
    f = tmp_path / "my art" / "x.webp"
    assert ImageFiles.local_path(f.as_uri()) == f
    assert ImageFiles.local_path("plain.png") == Path("plain.png")
    assert ImageFiles.is_image_file("A.WEBP") and not ImageFiles.is_image_file("a.gif")


def test_names_sort_in_natural_order():
    names = ["goblin 10", "Goblin 2", "goblin 1b", "ape"]
    assert sorted(names, key=ImageFiles.natural_key) == [
        "ape",
        "goblin 1b",
        "Goblin 2",
        "goblin 10",
    ]


def test_folder_images_own_first_then_subfolders(monsters):
    images, skipped = ImageFiles.folder_images(monsters)
    assert [p.relative_to(monsters).as_posix() for p in images] == [
        "leader.png",
        "goblins/goblin 2.png",
        "goblins/goblin 10.png",
        "goblins/leader.png",
        "orcs/leader.webp",
    ]
    assert (
        skipped == 2
    )  # notes.txt and orcs/readme.md; the hidden folder is not looked at
    only, skipped = ImageFiles.folder_images(monsters, subfolders=False)
    assert only == [monsters / "leader.png"] and skipped == 1


def test_same_names_get_their_subfolder(monsters):
    images, _ = ImageFiles.folder_images(monsters)
    assert ImageFiles.figure_names(images, monsters) == [
        None,
        None,
        None,
        "goblins-leader",
        "orcs-leader",
    ]  # leader.png keeps its name
    deep = [
        monsters / "a" / "b" / "x.png",
        monsters / "c" / "x.png",
        monsters / "y.png",
    ]
    assert ImageFiles.figure_names(deep, monsters) == ["a-b-x", "c-x", None]
