"""Tests of saving a build's intermediate masks and its preview."""


def test_a_debug_build_saves_its_masks_and_a_preview(
    hero_figure, tmp_path, pipeline_mini, mask_options
):
    img, mask = hero_figure
    out = tmp_path / "debug"
    pipeline_mini(img, mask=mask_options(mask_path=mask), debug_dir=out)
    names = sorted(p.name for p in out.glob("*.png"))
    assert names == [
        "hero_0_raw.png",
        "hero_1_threshold.png",
        "hero_2_closed.png",
        "hero_3_filled.png",
        "hero_4_clean.png",
        "hero_5_cut.png",
        "hero_overlay.png",
    ]
