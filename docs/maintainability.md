# Maintainability guide

This guide is the single source of truth for how papermini is kept
maintainable. It covers how the code is structured, how it is tested, how it is
documented and how it is built and released. Everyone who works on the code
follows it, whether they are a person or a coding agent.

It is written for two readers: a newcomer who has to understand the code from
the code and docs alone, and the maintainer, who reads code that was mostly
written by coding agents.

The guide is used in three ways:

- **When you write or change code.** Follow the rules below.
- **When you review a branch.** Before opening a pull request, check the
  branch's changes against these rules.
- **In a periodic audit.** Check the whole repository against these rules, rank
  what you find, and fix it in small batches.

Coding agents run the last two with the `/maintainability pr` and
`/maintainability audit` commands, from `.claude/skills/maintainability`.

[AGENTS.md](../AGENTS.md) adds only what coding agents need on top of this
guide, such as when they may commit. It doesn't repeat or override the rules
here. A rule about the code that turns up somewhere else belongs in this guide.

## What a maintainer needs

Every rule below serves one of these needs:

1. **Understand one part without reading everything.** A piece of code can be
   read on its own, and its name says what it does.
2. **Change one thing in one place.** Every piece of knowledge, such as an
   option or a default, is defined once.
3. **Know when something broke.** The tests fail when behaviour changes, and
   they keep passing when only the structure changes.
4. **Trust the docs.** What the docs and comments say matches what the code
   does.

## How to apply the rules

Each rule has an id, such as S1 or T2. It says what good looks like and why.
Many rules also give an example from this repository.

**Soft triggers** are numbers such as "a function over about 60 lines". A
trigger is a reason to look closer, not a finding by itself. A 90-line function
that reads top to bottom as one clear sequence is fine. A 40-line function that
mixes several jobs is not. The few hard limits are enforced by the tools.

**Leave mechanical checks to the tools.** Ruff checks formatting, import order,
unused names and simple bug patterns. Ty checks types. Don't report what they
catch. Report what needs judgement.

**A finding must cite a rule.** If you can't tie a problem to a rule in this
guide, either it isn't a maintainability problem, or this guide is missing a
rule. In the second case, propose the rule.

## Project Structure

```
src/papermini/   the package
  (top level)    the core: options and projects, creature sizes, background
                 removal, the pipeline from image to cut path, sheet and file
                 output, caches, updates and logging; plain Python, no Qt (S9)
  gui/           the PySide6 desktop app, built on the core
  fonts/         the bundled fonts and their licences
tests/           the pytest suite: synthetic masks, no network or model, GUI
                 tests off-screen (T4)
scripts/         developer tools: screenshots, release notes, release signing,
                 trying updates locally, building the Windows installer
packaging/       the PyInstaller build and the Windows installer
examples/        a batch example, and the images, project and sample outputs
                 of the README and the sample checks (D3)
docs/            the user reference, this guide and the README screenshots
.github/         the CI and release workflows, the Linux CI image and the
                 issue forms
.claude/         the maintainability command and its reviewer agent, for
                 coding agents
justfile         the common tasks (R1)
pyproject.toml   package metadata, dependencies and tool settings
uv.lock          the locked versions of every dependency (R3)
README.md        what papermini does and how to use it
AGENTS.md        extra rules for coding agents
```

## Code structure and readability

### S1. A module or class has one reason to change - SOLID (S)

This is the single responsibility principle. Group code by what it is
responsible for, so that a change to one feature touches one module or class. A
module that holds unrelated jobs makes every reader skip past the jobs they
don't care about.

*Soft triggers:* a file over about 800 lines, or a class over about 400 lines
or about 40 methods.

*Example:* `MainWindow` in `gui/window.py` builds the layout, queues builds and
handles their results, exports and prints, manages recent files and folders,
handles drag and drop, and checks for updates. Someone who wants to change how
exporting works has to find their way through a class of about 2,000 lines.
Better: separate collaborators, such as an export controller and an update
controller, that the window creates and wires together.

### S2. A function does one thing at one level of detail

A function either coordinates steps or does one step, not both. Its body should
read as a short sequence of named steps.

*Soft triggers:* a function over about 60 lines, nesting deeper than about
three levels, or more than about six parameters.

*Example:* `make_mini` in `mini.py` takes twenty keyword arguments and runs the
whole pipeline in one body. Related parameters, such as the segmentation
options, could travel together in a small dataclass, the way `geo.Params` and
`Style` already do.

### S3. Names say what things are

A name should tell a newcomer what a value is without reading where it was
made. Short names are fine in a tight scope, such as a loop over pixels, and for
well-known maths. They are not fine for values that travel across a long
function or between functions.

Keep abbreviations consistent across modules. Put the unit in the name when a
number could be in more than one unit, as in `width_mm` and `close_px`. The code
already does this well.

*Example:* `prm` and `lay` stand for parameters and layout, and they are used
across long functions.

### S4. Put structure in types, not in strings and tuples

When data has fields, give it a dataclass. When a value is one of a fixed set,
give it an `Enum`. Names can then be completed by editors and checked by ty.
Avoid lists of positional tuples and one-letter codes that only a comment
explains.

*Example:* the field specs in `gui/panels.py` are tuples of
`(field, label, kind, extra)`, where `kind` is a code such as `"f"` or `"col"`,
explained in a long comment above `STEPS`. Build callbacks pass
`(uid, gen, key)` positionally through several methods.

### S5. Add a variant by adding an entry - SOLID (O)

This is the open/closed principle. Adding a new kind of something, such as a
segmentation model or a tab shape, should mean adding one entry to one table,
not editing `if` chains in several modules. Code that needs to know about all
variants reads them from that table.

*Example:* the segmentation models are described in `segment.py`, but
`gui/panels.py` lists them again in `MODELS` and in a tooltip, and the help text
in `cli.py` lists them a third time. Adding a model means editing all of them.

### S6. A subclass keeps the promises of its base class - SOLID (L)

This is the Liskov substitution principle. Code that works with a base class
must keep working when it gets a subclass. An override accepts what the base
method accepts and returns what it returns. If a subclass has to refuse or
ignore part of the base class's behaviour, it probably shouldn't be a subclass.

This matters most for Qt widgets. A subclass of `QSpinBox` or `QListWidget` is
passed to Qt code that expects the base class's behaviour.

### S7. Depend only on what you use - SOLID (I)

This is the interface segregation principle. Give a function or class the
values it needs, not a large object that contains them. A widget gets the data
and signals it works with, not the whole main window. A helper that needs two
settings gets those two settings, or a small object with just those fields.

Narrow inputs make it clear what a piece of code depends on, and make it easy
to test.

### S8. Pass collaborators in - SOLID (D)

This is the dependency inversion principle. Code that decides what happens
doesn't create the things that do slow or outside work, such as downloading,
running a model, reading preferences or logging. It receives them as arguments
or callbacks. Tests then pass in fakes, and there is no need to patch module
globals.

*Example:* `make_mini` takes `log` and `on_stage` callbacks instead of printing
or signalling the GUI itself. Do the same for new outside work.

### S9. Dependencies point one way

The core modules, which are everything outside `gui/`, never import `gui` or
Qt. The GUI depends on the core, never the other way round. This keeps the
pipeline usable from the command line and testable without a display.

Inside `gui/`, widgets and panels don't reach into the main window. They emit
signals, and the window connects them.

### S10. One source of truth

A piece of knowledge, such as a default or a list of choices, lives in one
place. Copies drift apart over time.

*Options* are the main exception today, and they should stop being one. The
goal is one definition per option: its name, type, default, limits, label and
help text. The CLI flags, the GUI fields, the validation and the options table
in `docs/reference.md` should all be built from that definition, or checked
against it by a test.

Until then, an option lives in five places, and a change must keep them in
sync:

- `FigureSettings` in `settings.py`, with its validation in `from_dict`;
- the CLI flags in `cli.py`;
- the GUI field in `gui/panels.py` (`SECTIONS`, `TIPS` and the visibility
  rules);
- the options table in `docs/reference.md`;
- its entry in the settings guide there, with a comparison picture from
  `scripts/screenshots.py` when its values look different.

Add a test for every new option.

### S11. Failures are explicit

Don't catch bare exceptions, and don't swallow errors silently. Catch the
exceptions you expect, and let the rest reach the error dialog or the command
line's error output.

An error message says what went wrong in the user's terms and what they can do
about it.

### S12. No dead code

Remove unused functions, options, parameters, branches and commented-out code.
Git keeps the history. Before 1.0, don't keep compatibility code for old
project files or old flags. From 1.0, keep the migrations that R8 requires, and
nothing else.

### S13. Comments explain behaviour and reasons

Docstrings say what a function or class does, as an action or a purpose ("Build
the cut path for…"). Comments explain why the code does something that would
otherwise surprise a reader. They don't repeat what the code already says.

- Don't describe what a result is used for elsewhere. A docstring doesn't
  explain that its output has a certain shape because a function several calls
  away expects it. Describe what the function does. If a caller depends on a
  detail, the caller's code or a test says so.
- Don't quote user-interface text or use example version numbers. Describe
  formats in words instead.
- Don't write comments about history ("now", "new", "used to"). Describe the
  code as it is.
- Don't leave comments that record a review. When a change answers a review
  comment, change the code and nothing else. Don't add a comment about what used
  to be there or what shouldn't be. Add a comment only when the code itself
  needs one, such as a workaround for a known bug in a dependency.
- Give every module a docstring that says what it holds.
- Give public functions in the core modules a docstring. A private helper needs
  one only when its name and signature aren't enough.

### S14. Name the numbers

A number that means something, such as a margin or a timeout, gets a named
constant with its unit. The exception is a number used once whose meaning is
obvious from its line.

## Qt and the GUI

### G1. Keep GUI construction apart from GUI behaviour

Code that builds widgets and layouts is long and flat. Code that reacts to
events holds the logic. Keep them in separate methods, so that the logic can be
read and tested without wading through layout code. Split a long `__init__` that
builds a whole panel into one builder method per section.

*Soft trigger:* an `__init__` over about 60 lines.

### G2. Preferences go through `gui.prefs.store()`

Read and write preferences only through `gui.prefs.store()`, never with
`QSettings("papermini", "papermini")` directly. The tests redirect the store to
a temporary folder. A direct `QSettings` would write to the user's real
settings.

### G3. Builds are debounced and matched to their settings

Builds run on a single worker thread, and each result is matched to the
settings it was started for. Keep the 250 ms debounce. Never call
`QTimer.start(0)` on the debounce timer, because that sets its interval to 0
for good. Use `QTimer.singleShot(0, ...)` to run something soon.

### G4. Workers report every failure

A worker reports every failure back to the UI as a `ModelError`, never as a
`SystemExit` or a silent exception. Otherwise the UI waits forever on a build.

### G5. No graphics effects on scene items in the zoom views

Never put a `QGraphicsEffect`, such as a drop shadow or a blur, on scene items
in the zoom views. Qt renders the whole item off-screen at the current zoom,
which makes deep zoom take seconds per frame. Paint such effects in the item's
`paint()` instead.

### G6. Style sheets are scoped

Child widgets inherit style sheets. Scope every style sheet with `#ObjectName`
or a class selector, especially on widgets that open dialogs.

### G7. Hide spin box buttons with style rules

A `QSpinBox` with `NoButtons` collapses its text field under a style sheet.
Hide the buttons with zero-width button rules instead.

## Tests

### T1. Risky code is tested

The parts where a mistake costs the most need the most tests:

- the pipeline: geometry, layout, cut paths and bleed;
- loading and saving projects, and their compatibility rules (R8);
- the update check and the release signature;
- sheet packing and the PDF and SVG output;
- creature sizes and how they fill in a figure.

Untested lines in these parts are findings. `just coverage` lists them, and so
does the summary of the Linux Python 3.12 test job in CI. Untested GUI glue
matters less, unless it holds logic.

### T2. Tests check behaviour, not implementation

A test checks what a user or caller can observe, such as return values or
the state of a widget. It doesn't call private methods or check private
attributes, unless there is no other way to reach the behaviour.

A refactor that keeps behaviour the same keeps the tests passing without
editing them. If it doesn't, the tests are checking implementation.

### T3. Tests are easy to find and read

- Test files follow the modules they test, so the tests for `geometry.py` are
  in `test_geometry.py`.
- Split a large test file by feature.
- Put shared setup in fixtures in `conftest.py`, not in copied code.
- A test's name says the behaviour it checks and under what condition.

*Soft trigger:* a test file over about 1,000 lines. `tests/test_gui.py` is
about 2,400 lines.

### T4. Tests run in isolation

- Tests never need the network or the segmentation model. `tests/conftest.py`
  gives every test an empty model cache and blocks `urlopen`, and the GUI tests
  get a fake default model.
- No sleeping, and no dependence on timing.
- Files go in temporary folders, never in the repository or the user's home
  folder.
- Preferences go through `gui.prefs.store()` (G2).
- GUI tests run off-screen.

### T5. The whole suite passes before a change is finished

Run the whole suite, not only the tests near the change.

### T6. Every fixed bug gets a regression test

The test fails without the fix and passes with it. Its name or docstring says
what went wrong.

### T7. Pin behaviour down before refactoring

Before restructuring code that is poorly tested, add characterisation tests.
They record what the code does now, so that the refactor can be checked against
them.

## Docs and writing

### D1. Docs match the code

These must match what the code does:

- the project structure map in this guide;
- the options table and the settings guide in `docs/reference.md`;
- the command line basics and the development setup in `README.md`;
- docstrings and comments.

A mismatch is a finding, whichever side is wrong.

### D2. Each kind of doc has one home

- User-facing behaviour goes in `docs/reference.md`.
- `README.md` stays short: features, usage with screenshots, command line
  basics and development setup.
- How the code is kept maintainable goes in this guide.
- What only coding agents need goes in `AGENTS.md`.

### D3. Pictures and samples follow the code

- After a visible change to the app, regenerate the README screenshots with
  `scripts/screenshots.py`.
- When the output format or a default changes, regenerate the samples in
  `examples/dragons/samples/` with `papermini batch
  examples/dragons/samples.yaml` and `papermini batch
  examples/dragons/samples-machine.yaml`.

### D4. A newcomer can get started

- The development section of the README takes a newcomer from a fresh clone to
  running the tests and the app in a few commands.
- The non-obvious designs are explained where a newcomer will look, such as
  the stages of the pipeline and how the app matches builds to their settings
  (G3).

A non-obvious design that is explained nowhere is a finding. Explain it next to
the code, or in this guide when it spans modules.

### D5. Write plainly

This applies to docs, comments, docstrings, user-visible text, commit messages
and pull request descriptions.

- Write plain, direct sentences. Say what a thing is first, then what it does
  or what the reader can do.
- Don't pad lists to three. Name as many items as there really are. One or two
  is fine. Write "a module or class", not "a module, class or function", unless
  all three are meant. When there are exactly three things, as in "applies to
  classes, functions and fields", list them.
- Don't stack qualifiers. Write "the reason" instead of "the reason, and, where
  useful, an example".
- When a list is long or its items are long, use bullet points instead of a
  sentence.

Text that reads like a heading fragment or a riddle gets rewritten.

### D6. User-visible text is plain

Dialog intros, hints, tooltips and error messages follow D5. A dialog opens
with a plain statement of what it is, and then says what the user can do in
short imperative sentences.

### D7. This guide stays current

When a review finds a problem that no rule covers, or a rule that no longer
fits, update this guide in the same pull request.

## Tooling and release

### R1. One command per common task

Common tasks, such as setting up, testing, linting, running the app and
building, each have a recipe in the `justfile`. CI and the docs use the same
commands, so that what passes locally passes in CI.

### R2. CI runs every check

CI runs the tests, the lint and format checks, the coverage report and the type
check, on every Python version and platform the project supports.
Run the same checks locally before a change is finished, such as `just test`,
`just lint` and `just format`. The type check (`just typecheck`) doesn't block
a merge until the code passes it; don't add new findings to it.

### R3. Builds are reproducible

Dependencies are locked, and the versions of the development tools are pinned.
A fresh clone on another machine gets the same environment. Python packages are
never installed globally; everything runs in the project's environment.

### R4. Scripts follow the same rules as the app

The code in `scripts/` and `packaging/` is not exempt from this guide.

*Example:* `main()` in `scripts/screenshots.py` is about 300 lines long.

### R5. Updating stays safe

- Never weaken the release signature check in `update.py`.
- Never commit a private release key.
- Try a change to updating with `just try-update` (a real build) or
  `just try-update-source`.
- Try a change to the Windows installer, or to how an installed copy updates,
  with `just try-update-installer`.

### R6. Packaging stays in sync

A new runtime dependency or data file must also work in the PyInstaller build
(`packaging/papermini.spec`). After such a change, build locally and run the
frozen `papermini --version` and a `papermini make`.

### R7. Commits follow Conventional Commits

Every commit message follows
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): description`, for example `feat(gui): add a link bar to the
figure list` or `fix(sheet): keep the scale bar on the first page`.

- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
  `ci`, `chore`, `revert`.
- The scope is optional (`gui`, `cli`, `sheet`, `segment`, ...).
- Mark a breaking change with `!` after the type or scope (`feat(cli)!: ...`)
  or with a `BREAKING CHANGE:` footer.
- Make one logical change per commit.
- A commit that only reformats code changes nothing else, and its hash goes
  in `.git-blame-ignore-revs`.
- Pull request titles follow the same format.

### R8. What released versions depend on stays stable

- **Project files.** Project files saved by 1.0 must keep opening in every 1.x
  version. From 1.0, renaming or removing an option, CLI flag or YAML key needs
  a migration, or must wait for 2.0. Before 1.0, no compatibility code is kept
  (S12).
- **The bug report form.** The app's *Report a problem* fills in fields of
  `.github/ISSUE_TEMPLATE/bug_report.yml` through the URL, by their ids:
  `version`, `os`, `runs-as` and `traceback`. Released versions rely on them.
  Never rename or remove those ids, and keep them text fields.

### R9. The version comes from git tags

Never hard-code a version number. The version comes from git tags through
setuptools-scm, and `src/papermini/_version.py` is generated and ignored.
Releases are cut by the maintainer, either by running the release workflow
with a version, which tags the commit, or by pushing a `vMAJOR.MINOR.PATCH`
tag.

### R10. The repository holds source, not bulk

Never commit virtual environments, caches, model weights, `debug/` output or
other generated files. Model weights are downloaded to `~/.cache/papermini/` on
first use.

Respect the model licences. The default segmentation model, BRIA RMBG-1.4, is
for non-commercial use only. BiRefNet is MIT licensed.

## Proving a change is safe

A clean-up must not change behaviour. Each clean-up proves that:

1. **The whole test suite passes.**
2. **The samples come out the same.** Regenerate the samples (D3). The outputs
   must be identical. Explain every intended difference.
3. **The window looks the same.** Render the window off-screen in the light and
   dark themes, before and after the change, and compare the images.
4. **Weakly tested code is pinned down first** with characterisation tests
   (T7).

A clean-up that changes nothing the user can see needs no design approval. A
change that alters how anything looks or works does: the maintainer tries it
before it is finished.

## Reporting findings

A review reports each finding with these fields:

| Field | What it holds |
|-------|---------------|
| Rule | The id of the rule it breaks, such as S2. |
| Where | `path:line`, or a list of them. |
| Problem | What is wrong, in one or two sentences. |
| Why it matters | How it slows down or misleads a newcomer or the maintainer. |
| Change | What to change, concretely enough to start on. |
| Benefit | High, medium or low: how much easier maintenance gets. |
| Effort | Small (under an hour), medium (a few hours) or large (a day or more). |
| Risk | What could break, and which check from the section above would catch it. |
| Batch | The theme it belongs to, so that related findings are fixed together. |

Rank findings by benefit for effort: high benefit and small effort first.

A batch is one coherent change in one area, such as "move export handling out
of `MainWindow`". It is reviewed and merged as one pull request.

## What not to report

- Anything ruff or ty checks.
- Personal taste that no rule supports.
- Rewrites of working code without a clear gain for a maintainer.
- Renaming an option, CLI flag or project file key without the migration that
  R8 requires.
