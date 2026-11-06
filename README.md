# papermini

Turn an illustration (PNG/JPG, e.g. a pencil-sketch fantasy character) into a
**print-ready paper miniature** for tabletop games:

- the figure cut out from its background (AI segmentation),
- a smooth **vector cut line** with a small white margin, one closed path,
  ready for Cricut, Silhouette or Inkscape,
- a **fold-over tab** underneath so the figure stands up, with an optional label,
- an **SVG per figure** in millimetres (embedded 300 dpi artwork),
- an **A4/Letter PDF sheet** with many figures, to print at 100%,
- a **desktop app** (Qt) with live previews, or use the command line.

```
papermini make lotje.png --height-mm 42 --label Lotje
papermini sheet "minis/*.svg" --copies 2 -o minis.pdf
```

## Install

You need Python 3.9 or newer. Install papermini into a **virtual environment**
so nothing is added to your global Python. The setup script creates one at
`~/.venvs/papermini` and installs papermini with the GUI. It works on Windows,
macOS and Linux:

```bash
python scripts/setup_venv.py
```

The venv is kept outside the project on purpose. It holds thousands of files
that OneDrive, Dropbox or iCloud should not sync. Use `--dir .venv` if you want
it elsewhere, `--no-gui` for the CLI only, or `--dev` to add pytest.

Afterwards, run the programs from the venv. On Windows:

```bash
~/.venvs/papermini/Scripts/papermini-gui
```

```bash
~/.venvs/papermini/Scripts/papermini --help
```

On macOS and Linux they are in `~/.venvs/papermini/bin/`. You can also activate
the venv first: `~/.venvs/papermini/Scripts/Activate.ps1` (PowerShell) or
`source ~/.venvs/papermini/bin/activate`. After that, `papermini` and
`papermini-gui` work from any folder.

<details><summary>Manual setup</summary>

```bash
python -m venv ~/.venvs/papermini
```

```bash
~/.venvs/papermini/Scripts/python -m pip install -e ".[gui]"
```

The optional extras are `gui` (Qt desktop app), `rembg` (more segmentation
models) and `dev` (pytest).
</details>

## Running from source

The setup above is an **editable install**: the venv points at `src/` in this
folder rather than at a copy. Changes to the code take effect the next time you
start the app, with no reinstall. Re-run the setup only when the dependencies or
commands in `pyproject.toml` change.

To run straight from the code, use the venv's Python with `-m papermini` from
the project folder. Start the desktop app:

```bash
~/.venvs/papermini/Scripts/python -m papermini gui
```

Open images or a project directly:

```bash
~/.venvs/papermini/Scripts/python -m papermini gui examples/sample/ghost-edge.png
```

Use the command line:

```bash
~/.venvs/papermini/Scripts/python -m papermini make examples/sample/ghost-edge.png --height-mm 42 --debug
```

On macOS and Linux, use `~/.venvs/papermini/bin/python` instead.

When working on the app, start it this way from a terminal. `papermini-gui`
runs without a console window on Windows, so its warnings and tracebacks are
invisible. With `python -m papermini gui` they appear in the terminal.

<details><summary>Without installing papermini at all</summary>

Install only the dependencies into a venv, then put `src/` on the Python path:

```bash
~/.venvs/papermini/Scripts/python -m pip install numpy pillow opencv-python-headless onnxruntime reportlab pyyaml tqdm PySide6-Essentials
```

In PowerShell:

```powershell
$env:PYTHONPATH = "src"; ~/.venvs/papermini/Scripts/python -m papermini gui
```

In bash:

```bash
PYTHONPATH=src ~/.venvs/papermini/bin/python -m papermini gui
```

The dependency list mirrors `pyproject.toml`; if they ever differ, the
`pyproject.toml` version is the one to trust.
</details>

To run the tests from source, install the `dev` extra
(`python scripts/setup_venv.py --dev`) and run:

```bash
~/.venvs/papermini/Scripts/python -m pytest
```

The first run downloads the segmentation model (~176 MB) into
`~/.cache/papermini/`. You can change that folder with the `PAPERMINI_CACHE`
environment variable. After that, everything works offline, and each image takes
a few seconds on a CPU. AI model masks are cached on disk per image, crop and
model, so re-running with a different `--threshold` or `--height-mm` skips the
model entirely (`--no-cache` turns this off).

Within one run (and in the desktop app), every stage is also cached in memory:
the decoded image, the raw mask (from the AI model, the alpha channel or a mask
file), the cleaned mask, and the outline and cut line. A change only redoes the
stages it affects:

- **Cosmetic** (label, colours, line width, resolution): a fraction of a second.
- **Shape** (height, margin, smoothing, tab): about a second.
- **Mask clean-up** (threshold, closing, keep-all): reruns the clean-up.
- **Model or crop**: reruns the AI model.

Small figures from very large images are processed at a bounded resolution
(about 600 dpi, twice the output's 300 dpi), so they stay fast.

## Model licence

The default model is **BRIA RMBG-1.4**
(<https://huggingface.co/briaai/RMBG-1.4>). Its licence allows **non-commercial
use only**. For commercial use, get a licence from BRIA or switch to another
model with `--model`:

| `--model`              | what                                                        |
|------------------------|-------------------------------------------------------------|
| `auto` (default)       | the image's alpha channel if it has transparency, else `rmbg-1.4` |
| `rmbg-1.4`             | BRIA RMBG-1.4 ONNX, run with onnxruntime                    |
| `rembg:u2net`          | any [rembg](https://github.com/danielgatis/rembg) model; needs the `[rembg]` extra. For example `rembg:isnet-general-use` or `rembg:birefnet-general` |
| `alpha`                | use the PNG's own transparency                              |
| `path/to/model.onnx`   | your own ONNX model with RMBG-style input (RGB, `x/255-0.5`) |

You can also skip segmentation and pass a mask you painted yourself:
`--mask hero_mask.png` (white = figure).

## Desktop app

```bash
papermini-gui
```

You can also run `papermini gui [project.yaml | images...]`. The app runs on
Windows, macOS and Linux (Qt 6 / PySide6).

- **Header.** Open, add images and save on the left; a switch between the four
  views in the middle; **Export SVG** and **Export PDF** on the right. The ☰ menu
  holds everything else: new project, save as, export all SVGs, zoom, the
  **theme** (follow the system, light or dark) and about. Keyboard shortcuts
  work without opening the menu: Ctrl+O open, Ctrl+I add images, Ctrl+S save,
  Ctrl+E export SVG, Ctrl+P export PDF, Ctrl+0 fit, Ctrl+1 actual size.
- **Figures** (left). Each figure is a card with a thumbnail of the finished
  piece, its height and number of copies. Add images with **+**, or drop
  files or a project anywhere in the window. Drag to reorder; **Delete**
  removes the selected one. A new figure starts with the settings of the one
  that is selected.
- **Settings** (right). Every option from `papermini make`, in sections you can
  fold open and closed (the app remembers which). The preview updates about a
  second after each change, and fast series of changes (holding an arrow key)
  only build the final value. The model only runs once per image and crop.
  Changing *Copies* only updates the sheet. Number fields step with the arrow
  keys, or the mouse wheel once you click into them, so scrolling the panel
  never edits values. *Apply to all figures* copies everything except label,
  crop, mask and copies.
- **Miniature** view. The piece as it will print, with a 10 mm scale bar. The
  zoom controls at the bottom right zoom, fit (Ctrl+0), or show the piece at
  real size (*1:1*, Ctrl+1), depending on the DPI your screen reports.
- **Cut-away** view. Red is cut away, light blue is the white margin, black is
  the cut line. Use it to spot problems.
- **Source** view. The original image. Drag a box to set `--crop` for busy
  backgrounds. Afterwards:
  - drag its **handles** (corners and edge midpoints, or anywhere along an
    edge) to resize it;
  - drag **inside** it to move it;
  - drag **outside** it to draw a new box;
  - press **Delete** to clear it, or **Esc** to cancel a drag.

  The mouse wheel zooms and the middle mouse button pans.
- **Print sheet** view. A live preview of the PDF layout, with paper, title,
  margin and gap settings in the bar above it.
- **Exporting.** Anything that still needs building is built in the background
  first; the window stays responsive and you can cancel.

Projects are saved as **batch YAML** files, the same format as
`papermini batch`. Anything you set up in the app can also be rebuilt from the
command line:

```bash
papermini batch my-minis.yaml
```

## Commands

### `papermini make IMAGE... [options]`

Makes one SVG per image, saved next to the image or in `-o DIR` (or
`-o name.svg` for a single image).

```bash
papermini make lotje.png --height-mm 42 --label Lotje
```

```bash
papermini make boss.png --height-mm 56 --crop 0.08,0,0.92,0.62 --threshold 60 --close 7
```

```bash
papermini make *.png -o minis --debug
```

| option | default | meaning |
|---|---|---|
| `--height-mm` | 42 | height of the drawn figure, without margin and tab |
| `--margin-mm` | 1.6 | white border between the drawing and the cut line |
| `--smooth-mm` | 0.6 | how much the outline is rounded |
| `--tab-shape` | square | `square` slots into a stand; `round` is a half disc that folds out into a base |
| `--tab-width-mm` / `--tab-height-mm` | 22 / 12 | square tab size (height measured below the fold) |
| `--tab-radius-mm` | 12.5 | round tab radius (12.5 makes a 25 mm base) |
| `--tab-color` | #ffffff | tab colour (everything below the fold), behind the label; independent of the margin colour |
| `--tab-overlap-mm` | 0 | how far the tab reaches up past the fold. It only adds paper where the figure's bottom is narrower than the tab (feet, a tail), to strengthen the joint; on a wide bottom it has no effect, and the app says so |
| `--fold-mm` | 0 | fold line distance above the silhouette's lowest point |
| `--no-tab` | | no tab |
| `--double-sided` | | front plus back, joined at a top fold, with a tab at both ends |
| `--back` | mirror | double-sided back: `mirror` (the drawing seen from behind), `blank` (white paper) or `text` |
| `--back-text` | label | text for `--back text`; auto-sized and wrapped to fit the figure |
| `--back-color` | #ffffff | colour of a `blank` or `text` back |
| `--back-text-color` | #2f5597 | colour of the back text |
| `--crop x0,y0,x1,y1` | | region the model looks at, as fractions (0–1) or pixels |
| `--threshold` | 40 | mask threshold (0–255); go lower for faint pencil, higher for busy scenes |
| `--close` | auto | closing radius in px (auto ≈ 9 px at a 1400 px image) |
| `--keep-all` / `--min-area` | / 1000 | keep detached parts (≥ min-area px) and bridge them to the figure |
| `--margin-fill` | color | `color` fills the margin with `--margin-color`; `image` shows the original picture there |
| `--margin-color` | #ffffff | colour of the margin around the drawing |
| `--label` | file name | text on the tab; `--label ""` for none |
| `--dpi` | 300 | resolution of the embedded artwork |
| `--simplify-mm` | 0.15 | cut line simplification tolerance |
| `--no-smooth` | | straight segments only (by default the cut line uses Bézier curves) |
| `--cut-color` / `--cut-width-mm` | #000000 / 0.3 | cut line style |
| `--cutter` | | cutting-machine style: red 0.1 mm cut line |
| `--bleed-mm` | 1 | with `--cutter`: print the background this far beyond the cut line, so a slightly misaligned cut shows no white edge |
| `--debug` | | write intermediate masks and a red overlay preview to `debug/` |

### `papermini sheet SVG... [-o minis.pdf]`

Lays papermini SVGs out on pages. Each page has an instruction header and a
50 mm calibration bar. Pieces are packed in rows with 7 mm gaps and 12 mm page
margins, and extra pages are added as needed.

```bash
papermini sheet "minis/*.svg" --copies 2 --paper letter -o minis.pdf --preview
```

Options: `--copies`, `--paper a4|letter`, `--margin-mm`, `--gap-mm`, `--title`, and
`--preview` (also writes a PNG per page). The sheet only reads SVGs written by
papermini. An SVG that was re-saved in another editor may not load.

### `papermini batch config.yaml`

Takes a list of images with per-image options and writes the SVGs plus a sheet.
See [examples/minis.yaml](examples/minis.yaml):

```yaml
output: minis
sheet: {output: minis/sheet.pdf, paper: a4, copies: 1, preview: true}
defaults: {height_mm: 42, threshold: 40, close: 9}
figures:
  - image: ghost-girl.jpg
    label: Lotje
    copies: 2
  - image: boss-attic.jpg
    label: Acererak
    height_mm: 56
    threshold: 60
    close: 7
    crop: [0.08, 0, 0.92, 0.62]
```

[examples/sample/sample.yaml](examples/sample/sample.yaml) builds the sample
outputs in that folder: a default mini, a round coloured base, a double-sided
mini with back text, and a print-and-cut mini with bleed. Their sheet is
[examples/sample/sample-sheet.pdf](examples/sample/sample-sheet.pdf).

```bash
papermini batch examples/sample/sample.yaml
```

## How it works

1. **Segmentation.** RMBG-1.4 runs at 1024×1024 and its mask is scaled back to the
   image size. With `--crop`, the model only sees the crop, and the result is
   pasted into an empty full-size mask.
2. **Clean-up.** Threshold, then morphological closing, then **hole filling** (so
   translucent ghosts become solid), then keep the largest part (or every part,
   with `--keep-all`).
3. **Scale.** `px_per_mm = figure height in px / --height-mm`.
4. **Margin.** Grow the mask by the margin, blur, and re-threshold to get a smooth
   outline. The canvas is padded first, so a figure that touches the image edge
   still gets a rounded margin.
5. **Tab.** Centred under the middle of the figure's bottom 6 mm, with the fold
   1 mm above the lowest point. Inner corners are rounded, which only ever adds
   paper.
6. **Cut line.** The outer contour, simplified, then smoothed into cubic Béziers.
   Sharp corners such as the tab stay sharp. The artwork's transparency comes from
   the same path, so the picture and the line match exactly.
7. **Output.** The SVG has `width`/`height` in mm, a `viewBox` in mm, an `image#art`
   element, `line.fold` dashed lines, `text.label` and `path#cut`. The PDF is drawn
   with ReportLab in exact millimetres.

## Stands and bases

The tab under the figure comes in two shapes:

- **Square** (`--tab-shape square`, the default) is a straight tab to slot into
  a stand, such as a 3D-printed one, or to glue onto a base.
- **Round** (`--tab-shape round`) is a half disc that you fold outwards so the
  figure stands on it. On a double-sided mini, the front and back tabs fold out
  to opposite sides and together make a full round base. `--tab-radius-mm` sets
  its size; 12.5 (the default) gives a 25 mm, one-inch base.

Either shape has its own colour, `--tab-color`. It is white by default,
independent of the margin colour, and covers everything below the fold. The
label is printed on it; use `--label ""` for a plain tab, for example grass
green or stone grey.

```bash
papermini make lotje.png --tab-shape round --tab-radius-mm 12.5 --tab-color "#3b6e2a" --label ""
```

The margin around the drawing can be any colour (`--margin-color "#f3e6c8"`)
instead of white, or show the original image (`--margin-fill image`).

## Double-sided minis

`--double-sided` (or the checkbox in the app) prints the piece twice, joined at
a fold above the head. Fold it over and glue the halves back to back, so the
figure looks right from both sides. The cut line is always mirrored, so the
halves line up. What shows on the back is up to you:

- `--back mirror` (default) shows the drawing seen from behind.
- `--back blank` leaves the back plain, in `--back-color` (white by default),
  for example to write or draw on by hand.
- `--back text` shows a name or short note, centred on the body and sized as
  large as fits:

  ```bash
  papermini make lotje.png --double-sided --back text --back-text "Lotje the Lost Ghost"
  ```

  Without `--back-text`, it uses the label. On the sheet the back text is upside
  down; it reads the right way up once the piece is folded.

## Tips

- **Tune with `--debug`.** `debug/<name>_overlay.png` shows red for what will be
  cut away and light blue for the white margin. It also writes the masks from
  each step (`0_raw` → `5_cut`).
- **Faint pencil.** Lower `--threshold` (for example 25–40) and raise `--close` if
  the silhouette has gaps.
- **Busy background.** Use `--crop` around the figure and try `--threshold 60`. A
  flat edge from the crop at the bottom is fine, because it sits on the tab.
- **Props lost.** Floating props are dropped by default. `--keep-all` keeps them
  and adds a bridge.
- **Printing.** Print at 100% / "actual size", never "fit to page". Measure the
  50 mm bar to check.
- **Cutting machines.** Import the SVG and use `path#cut` as the cut layer.
  `--cutter` gives a red hairline that many tools treat as a cut line. It also
  adds a bleed (`--bleed-mm`, 1 mm by default): the background is printed a
  little beyond the cut line, so a cut that lands slightly off still shows no
  white paper. The bleed extends whatever colour is at the edge (margin, tab or
  back colour).

## Tests

```bash
~/.venvs/papermini/Scripts/python -m pytest
```

The tests use synthetic masks, so they need no model or download. They cover hole
filling, part filtering, mm scaling, margin width, tab placement, a single closed
cut path that never cuts into the drawing, figures touching the border,
double-sided symmetry, Bézier deviation, SVG round-trip, sheet packing, PDF output,
the batch command and project round-trip. If PySide6 is installed, an offscreen
smoke test of the GUI also runs.
