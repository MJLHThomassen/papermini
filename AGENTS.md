# AGENTS.md

Rules for anyone, human or coding agent, working in this repository.

## Hard rules

- **Never edit the top of `README.md`.** Everything from the first line up to
  and including `*Disclaimer: This tool is 100% vibecoded!*` belongs to the
  maintainer. Leave those lines byte for byte as they are (wording, spacing,
  line endings). Edit only what comes after them.
- **Never install Python packages globally.** Use the project venv
  (`python scripts/setup_venv.py --dev`, at `~/.venvs/papermini`) and run
  everything with its interpreter, e.g. `~/.venvs/papermini/Scripts/python -m
  pytest` (`bin/python` on macOS and Linux).
- **Do not commit, push or open pull requests unless asked.** Never commit
  venvs, caches, model weights, `debug/` output or other generated bulk.
- **Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)**
  for every commit message: `type(scope): description`, for example
  `feat(gui): add a link bar to the figure list` or `fix(sheet): keep the
  scale bar on the first page`. Types: `feat`, `fix`, `docs`, `style`,
  `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. The scope is
  optional (`gui`, `cli`, `sheet`, `segment`, ...). Mark a breaking change with
  `!` after the type or scope (`feat(cli)!: ...`) or a `BREAKING CHANGE:`
  footer. One logical change per commit; pull request titles follow the same
  format.
- **No backwards-compatibility code.** There are no released project files to
  support yet: rename or remove options and settings outright, without
  aliases, migrations or fallbacks, unless the maintainer asks for them.
- **Never hard-code a version number.** The version comes from git tags
  through setuptools-scm (`src/papermini/_version.py` is generated and
  ignored). Releases are cut only by the maintainer, by pushing a
  `vMAJOR.MINOR.PATCH` tag; never create or push tags yourself unless asked.
- **Respect the model licences.** The default segmentation model, BRIA
  RMBG-1.4, is non-commercial; BiRefNet is MIT. Never add model weights to the
  repository; they are downloaded to `~/.cache/papermini/` on first use.

## Layout

```
src/papermini/
  cli.py        command line: make | sheet | batch | gui
  settings.py   FigureSettings / Project: the one definition of every option,
                shared by the CLI, batch YAML and the GUI
  segment.py    background removal (RMBG-1.4 / BiRefNet ONNX, alpha, masks)
                and the on-disk mask cache
  geometry.py   mask clean-up, margin, tab, cut-line tracing, bleed
  mini.py       the pipeline: image -> mask -> layout -> cut path (mm units)
  cache.py      in-memory LRU caches for the pipeline stages
  remote.py     images from links (downloaded once into the cache), image types
  svg.py        SVG writer/reader;  sheet.py  PDF sheet packing and output
  gui/          PySide6 desktop app (window, panels, views, widgets, theme,
                prefs, models: download dialog and Models window)
tests/          pytest; synthetic masks, no model download; GUI tests offscreen
scripts/        setup_venv.py, screenshots.py
packaging/      PyInstaller spec, entry scripts and app icon (make_icon.py)
.github/        CI (tests on push/PR) and release (binaries on version tags)
examples/       batch YAML examples and generated sample outputs
docs/           reference.md (full option docs) and README screenshots
```

## Making changes

- **An option lives in four places; keep them in sync:** `FigureSettings` in
  `settings.py` (with validation in `from_dict`), the CLI flags in `cli.py`,
  the GUI field in `gui/panels.py` (`SECTIONS`, `TIPS`, visibility rules), and
  the options table in `docs/reference.md`. Add a test.
- **Test before you finish.** Run the whole suite with the venv's Python. Add
  a regression test for every bug you fix. Tests must not need the network or
  the segmentation model: `tests/conftest.py` gives every test an empty model
  cache and blocks `urlopen`, and the GUI tests get a fake default model.
- **Look at GUI changes.** Render the window off-screen (`WA_DontShowOnScreen`
  plus `grab()`) and check the image, in both light and dark themes. After a
  visible change, regenerate the README screenshots with
  `scripts/screenshots.py`.
- **Regenerate the samples** in `examples/sample/` with
  `papermini batch examples/sample/sample.yaml` when the output format or
  defaults change.
- **Binaries:** new runtime dependencies or data files must also work in the
  PyInstaller build (`packaging/papermini.spec`). After such a change, build
  locally and run the frozen `papermini --version` and a `papermini make`.
- **Docs:** user-facing behaviour goes in `docs/reference.md`; keep `README.md`
  short (features, usage with screenshots, CLI basics, development setup).

## GUI pitfalls (learned the hard way)

- Read and write preferences only through `gui.prefs.store()`, never
  `QSettings("papermini", "papermini")` directly. The tests redirect it to a
  temporary folder; a direct `QSettings` would write to the user's real
  settings.
- Builds run on a single worker thread and are matched to the settings they
  were started for. Keep the 250 ms debounce. Never call `QTimer.start(0)` on
  the debounce timer, because that sets its interval to 0 for good; use
  `QTimer.singleShot(0, ...)` for "run soon".
- Never put a `QGraphicsEffect` (drop shadow, blur) on scene items in the zoom
  views. It renders the whole item off-screen at the current zoom and makes
  deep zoom take seconds per frame. Paint such effects in the item's `paint()`.
- Workers must report every failure back (`ModelError`, never `SystemExit` or
  silent exceptions), so the UI never waits forever on a build.
- Style sheets are inherited by child widgets: scope them (`#ObjectName` or a
  class selector), especially on widgets that open dialogs.
- A `QSpinBox` with `NoButtons` collapses its text field under a style sheet;
  hide the buttons with zero-width button rules instead.
