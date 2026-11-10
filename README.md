# papermini

Turn images (PNG/JPG) into **print-ready paper miniatures** for tabletop games like D&D (Dungeons & Dragons).

*Disclaimer: This tool is 100% vibecoded!*

![The papermini desktop app](docs/screenshots/app-miniature.png)

<p align="center"><b>⬇️ Printed, cut out and folded, this is the mini made above ⬇️</b></p>

<p align="center">
  <img src="examples/dragons/dragon-flying-photo.jpg" width="600"
       alt="The flying dragon as a real paper mini, standing on its round base">
</p>

**Contents**

- [Features](#features)
- [Quick start](#quick-start)
- [Usage via GUI](#usage-via-gui)
- [Usage via CLI](#usage-via-cli)
- [Development](#development)
  - [Run from source](#run-from-source)
  - [Set up your environment](#set-up-your-environment)
  - [Versions and releases](#versions-and-releases)
  - [Building the binaries locally](#building-the-binaries-locally)
- [Settings guide](docs/reference.md#settings-guide): every setting, with
  pictures (in the reference)

# Features

- **[Background removal](docs/reference.md#background-removal)**: AI models that run on
  your own computer, or the image's own transparency.
- **[Cropping](docs/reference.md#crop)**: drag a box to keep only the figure.
- **Cut line**: a smooth vector outline with a margin, for scissors or a
  cutting machine.
- **[Stand tab](docs/reference.md#stands-and-bases)**: square to slot into a
  stand, or round to fold out into a base.
- **[Double-sided](docs/reference.md#double-sided-minis)**: a mirrored, blank
  or text back, folded over the head.
- **[Color adjustments](docs/reference.md#color-adjustments)**: greyscale,
  brightness, contrast, saturation and hue.
- **Print sheets**: A4 or Letter PDF pages at real size, or an SVG per figure.
- **Any image**: PNG, JPG, WebP, BMP, TIFF, or a link to an image on the web.
- **[App](#usage-via-gui) and [command line](#usage-via-cli)**: live previews
  in the app, batches from the command line.

### [All features / settings →](docs/reference.md#settings-guide)


# Quick start

1. Download papermini from the
   [latest release](https://github.com/MJLHThomassen/papermini/releases/latest),
   unpack it and start it.
2. Make your first mini:
   1. Drop an image onto the window, for example
      [dragon.webp](examples/dragons/dragon.webp).
   2. In **1 Source**, drag a box around the figure. Its outline is drawn on
      the image.
   3. In **2 Miniature**, type the label for the tab, such as `Red dragon`.
   4. In **3 Print sheet**, set the figure height, such as 42 mm, and the
      number of copies.
   5. Click **Print…** and print at 100%. Cut along the solid line, fold
      along the dashed lines and glue the two halves back to back.

# Usage via GUI

1. **Add images.** Drop images onto the window, or use the add-image button
   above the figure list. You can also drag a picture from your browser, paste
   one with Ctrl+V, or paste its link into the link bar. Each image becomes a
   figure in the list on the left.
2. **Step 1, Source.** Drag a box around the figure to crop it, and pick the
   background removal model. The outline that was found is drawn on your
   image, and everything outside it is faded. If the outline is wrong, try a
   lower strength, a tighter crop or another model. A slow model can be
   cancelled. [All Source settings](docs/reference.md#step-1-source).
3. **Step 2, Miniature.** Set the back side, margin, cut line, tab and label.
   The back side, tab and label each have a checkbox in their header to turn
   them on or off; all three are on by default, so a mini has a front and a
   back, folded over the head. The preview updates as you go.
   [All Miniature settings](docs/reference.md#step-2-miniature), including
   the tab's [overlap](docs/reference.md#overlap-into-figure) and
   [fold](docs/reference.md#fold-above-lowest-point).
4. **Step 3, Print sheet.** Set each figure's size (height, width, or both)
   and copies, and see all figures laid out on pages. Click **Print…** to
   print them straight away at real size, or **Export PDF** and print that at
   100% ("actual size"). Each page has a 50 mm bar to check the scale.
   [All Print sheet settings](docs/reference.md#step-3-print-sheet).

| Step 1, Source | Step 2, Miniature (dark theme) | Step 3, Print sheet |
|---|---|---|
| ![Step 1, Source: the outline that was found, drawn on the image](docs/screenshots/app-source.png) | ![Step 2, Miniature: the paper piece with its back side and tab, in the dark theme](docs/screenshots/app-dark.png) | ![Step 3, Print sheet: all figures laid out on a page](docs/screenshots/app-sheet.png) |

The settings panel on the right shows the settings of the step you are on.
You can switch steps at any time. The
[settings guide](docs/reference.md#settings-guide) explains every setting,
with pictures of different values.

Save your work as a project (Ctrl+S). Projects are plain YAML files that the
command line can rebuild too.

> [!IMPORTANT]
> The default background-removal model,
> [BRIA RMBG-1.4](https://huggingface.co/briaai/RMBG-1.4), is licensed for
> **non-commercial use only**. For commercial use, pick a
> [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) model
> ([MIT licence](https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE)) or
> use images with transparency. See
> [background removal models](docs/reference.md#model-licence).

# Usage via CLI

The `papermini` command comes with the app: next to `papermini-gui` in the
Windows and Linux downloads, and at `papermini.app/Contents/MacOS/papermini` on
macOS. When running from source, it is in the venv (`Scripts/` on Windows,
`bin/` on macOS and Linux).

Make one SVG per image:

```bash
papermini make dragon.png --height-mm 42 --label "Red dragon"
```

Lay SVGs out on a printable PDF sheet:

```bash
papermini sheet "minis/*.svg" --copies 2 -o minis.pdf
```

Build a whole project (images, per-figure settings and the sheet) from a YAML
file, such as one saved by the app:

```bash
papermini batch examples/dragons/dragons.yaml
```

Run `papermini make --help` for all options. The
[reference](docs/reference.md) explains every option, the batch file format,
stands and bases, double-sided minis and tips for tricky drawings.

# Development

## Run from source

You need Python 3.10 or newer. Clone the repository:

```bash
git clone https://github.com/MJLHThomassen/papermini.git
```

```bash
cd papermini
```

The setup script creates a virtual environment in `~/.venvs/papermini` and
installs papermini with the desktop app:

```bash
python scripts/setup_venv.py
```

Then start `~/.venvs/papermini/Scripts/papermini-gui` (Windows) or
`~/.venvs/papermini/bin/papermini-gui` (macOS, Linux).

## Set up your environment

To work on papermini, install it in editable mode with the test dependencies:

```bash
python scripts/setup_venv.py --dev
```

The venv points at `src/` in your clone, so code changes take effect the next
time you start papermini. Re-run the setup only when `pyproject.toml` changes.

Run the app from a terminal, so its warnings and tracebacks show up there (on
Windows, `papermini-gui` has no console):

```bash
~/.venvs/papermini/Scripts/python -m papermini gui
```

Run the tests. They need no model download; the GUI tests run off-screen:

```bash
~/.venvs/papermini/Scripts/python -m pytest
```

On macOS and Linux, use `~/.venvs/papermini/bin/python`.

After changing the look of the app, regenerate the screenshots in
[docs/screenshots](docs/screenshots). They show the dragons in
[examples/dragons](examples/dragons) and need the rmbg-1.4, birefnet-lite and
birefnet models:

```bash
~/.venvs/papermini/Scripts/python scripts/screenshots.py
```

Contributors and coding agents: read [AGENTS.md](AGENTS.md) first.

## Versions and releases

papermini uses [semantic versioning](https://semver.org). The version comes
from git tags, so there is no version number to edit: tag `v1.2.3` builds
version 1.2.3, and commits after it report a development version such as
`1.2.4.dev3+g1a2b3c4` (`papermini --version`).

To release, tag a commit on `main` and push the tag:

```bash
git tag v1.2.0
```

```bash
git push origin v1.2.0
```

The [release workflow](.github/workflows/release.yml) then runs the tests,
builds the Windows, macOS and Linux downloads and publishes them as a GitHub
release with generated notes and SHA-256 checksums. A tag with a suffix, such
as `v1.2.0-rc.1`, makes a pre-release. To try the builds without releasing, run
the workflow by hand from the *Actions* tab; the downloads appear as workflow
artifacts.

## Building the binaries locally

```bash
python scripts/setup_venv.py --dev --build
```

```bash
~/.venvs/papermini/Scripts/pyinstaller packaging/papermini.spec --noconfirm
```

The result is in `dist/`. PyInstaller builds for the system it runs on only.
