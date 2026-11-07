# papermini

Turn images (PNG/JPG) into **print-ready paper miniatures** for tabletop games like D&D (Dungeons & Dragons).

*Disclaimer: This tool is 100% vibecoded!*

![The papermini desktop app](docs/screenshots/app-miniature.png)

# Features

- cuts the figure out of its background with locally running AI segmentation (or uses the
  image's own transparency),
- a smooth **vector cut line** with a margin, ready for scissors, Cricut,
  Silhouette or Inkscape,
- a **fold-over tab** so the figure stands up: square for a stand, or round to
  fold out into a base,
- **double-sided** minis with a mirrored, blank or text back,
- an **SVG per figure** in millimetres and an **A4/Letter PDF sheet** to print
  at 100%,
- works with PNG, JPG, **WebP**, BMP and TIFF files, or a **link** to an image on
  the web,
- a **desktop app** with live previews, and a command line for batches.

# Usage

Download the archive for your system from the
[latest release](https://github.com/MJLHThomassen/papermini/releases/latest),
unpack it and start papermini. No Python needed.

| System | Download | Start |
|---|---|---|
| Windows (64-bit) | `papermini-<version>-windows-x64.zip` | `papermini-gui.exe` |
| macOS (Apple silicon) | `papermini-<version>-macos-arm64.zip` | `papermini.app` |
| macOS (Intel) | `papermini-<version>-macos-x64.zip` | `papermini.app` |
| Linux (64-bit) | `papermini-<version>-linux-x64.tar.gz` | `papermini-gui` |

The builds are not code-signed, so the first start needs one extra step:

- **Windows:** if SmartScreen warns, click *More info*, then *Run anyway*.
- **macOS:** right-click `papermini.app` and choose *Open*. If macOS says the
  app is damaged, run `xattr -dr com.apple.quarantine papermini.app` once.
- **Linux:** Qt needs a few X11 libraries; on Debian and Ubuntu,
  `sudo apt install libxcb-cursor0`.

<details><summary>Run from source instead</summary>

You need Python 3.10 or newer. The setup script creates a virtual environment
in `~/.venvs/papermini` and installs papermini with the desktop app:

```bash
git clone https://github.com/MJLHThomassen/papermini.git
```

```bash
cd papermini
```

```bash
python scripts/setup_venv.py
```

Then start `~/.venvs/papermini/Scripts/papermini-gui` (Windows) or
`~/.venvs/papermini/bin/papermini-gui` (macOS, Linux).
</details>

1. **Add images.** Drop images onto the window, or use **+**. Each one becomes
   a figure in the list on the left.
2. **Adjust the settings** on the right: height, background removal, margin,
   tab shape and label, double-sided. The preview updates as you go.
3. **Check the cut.** The *Source* view draws the cut line on your original
   image and fades everything that is cut away. If the outline is wrong, try a
   lower strength or drag a crop box there.
4. **Print.** The *Print sheet* view lays all figures out on pages. Click
   **Print…** to print them straight away at real size, or **Export PDF** and
   print that at 100% ("actual size"). Each page has a 50 mm bar to check the
   scale.

Save your work as a project (Ctrl+S). Projects are plain YAML files that the
command line can rebuild too.

| Source view | Print sheet | Dark theme |
|---|---|---|
| ![Source view with the cut line](docs/screenshots/app-source.png) | ![Print sheet view](docs/screenshots/app-sheet.png) | ![Dark theme](docs/screenshots/app-dark.png) |

The first time it needs the background-removal model (about 176 MB), the app
asks before downloading it. After that, papermini works offline. **Models…**
in the ☰ menu shows which models are downloaded, and where.

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
papermini make lotje.png --height-mm 42 --label Lotje
```

Lay SVGs out on a printable PDF sheet:

```bash
papermini sheet "minis/*.svg" --copies 2 -o minis.pdf
```

Build a whole project (images, per-figure settings and the sheet) from a YAML
file, such as one saved by the app:

```bash
papermini batch examples/sample/sample.yaml
```

Run `papermini make --help` for all options. The
[reference](docs/reference.md) explains every option, the batch file format,
stands and bases, double-sided minis and tips for tricky drawings.

# Development

## Set up your environment

Install papermini in editable mode with the test dependencies:

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
[docs/screenshots](docs/screenshots):

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
