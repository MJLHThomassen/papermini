# Maintainability guide

This guide describes what makes papermini easy to maintain, and how to check
it. It is written for two readers: a newcomer who has to understand and change
the code from the code and docs alone, and the maintainer, who reads code that
was mostly written by coding agents.

The guide is used in three ways:

- **When you write or change code.** Follow the rules below.
- **When you review a branch.** Before opening a pull request, check the
  branch's changes against these rules.
- **In a periodic audit.** Check the whole repository against these rules, rank
  what you find, and fix it in small batches.

The hard rules in [AGENTS.md](../AGENTS.md) come first. Where this guide and
AGENTS.md disagree, AGENTS.md wins and this guide should be corrected.

## What a maintainer needs

Every rule below serves one of these four needs:

1. **Understand one part without reading everything.** A module, class or
   function can be read on its own, and its name says what it does.
2. **Change one thing in one place.** A piece of knowledge, such as an option, a
   unit or a default, lives in one place, or in a fixed set of places that a
   rule names.
3. **Know when something broke.** The tests fail when behaviour changes, and
   they keep passing when only the structure changes.
4. **Trust the docs.** What the docs, comments and agent rules say matches what
   the code does.

## How to apply the rules

Each rule has an id (S1, T2 and so on), a statement of what good looks like, the
reason, and, where useful, an example from this repository.

**Soft triggers** are numbers such as "a function over about 60 lines". A
trigger is a reason to look closer, not a finding by itself. A 90-line function
that reads top to bottom as one clear sequence is fine. A 40-line function that
mixes three jobs is not. The few hard limits are enforced by the tools.

**Leave mechanical checks to the tools.** Formatting, import order, unused names,
simple bug patterns and type errors are the job of ruff and ty. Don't report
them by hand. Report what needs judgement.

**A finding must cite a rule.** If you can't tie a problem to a rule in this
guide, either it isn't a maintainability problem, or this guide is missing a
rule. In the second case, propose the rule.

## Code structure and readability

### S1. A module or class has one reason to change

Group code by what it is responsible for, so that a change to one feature touches
one module or class. A module that holds unrelated jobs forces every reader to
skip past the jobs they don't care about.

*Soft triggers:* a file over about 800 lines, a class over about 400 lines or
about 40 methods.

*Example:* `MainWindow` in `gui/window.py` builds the layout, queues builds and
handles their results, exports, prints, manages recent files and folders,
handles drag and drop, and checks for updates. Someone who wants to change how
exporting works has to find their way through a class of about 2,000 lines.
Better: separate collaborators, such as an export controller or an update
controller, that the window creates and wires together.

### S2. A function does one thing at one level of detail

A function either coordinates steps or does one step, not both. Its body should
read as a short sequence of named steps.

*Soft triggers:* a function over about 60 lines, nesting deeper than about three
levels, more than about six parameters.

*Example:* `make_mini` in `mini.py` takes twenty keyword arguments and runs
the whole pipeline in one body. Related parameters, such as the segmentation
options or the text options, could travel together in small dataclasses, the way
`geo.Params` and `Style` already do.

### S3. Names say what things are

A name should tell a newcomer what a value is without reading where it was made.
Short names are fine in a tight scope (`x`, `y`, `i`, a loop over pixels) and for
well-known maths. They are not fine for values that travel across a long
function or between functions.

Keep abbreviations consistent across modules. Put the unit in the name when a
number could be in more than one unit (`width_mm`, `close_px`). The code already
does this well; keep it that way.

*Example:* `prm`, `fm`, `lay` and `s` stand for parameters, figure mask, layout
and settings, and they are used across long functions.

### S4. Put structure in types, not in strings and tuples

When data has fields, give it a dataclass, a `NamedTuple` or an `Enum`, so that
the fields have names, editors can complete them, and ty can check them. Avoid
lists of positional tuples and one-letter codes that only a comment explains.

*Example:* the field specs in `gui/panels.py` are tuples of
`(field, label, kind, extra)`, where `kind` is a code such as `"f"`, `"i"` or
`"col"`, explained in a long comment above `STEPS`. Build callbacks pass
`(uid, gen, key)` positionally through several methods.

### S5. One source of truth

A piece of knowledge lives in one place. Copies of a constant, a default, a
list of choices or a calculation drift apart over time.

Where knowledge must live in several places, a rule must say so, and say where.
AGENTS.md does this for options, which live in five places. Proposing to derive
some of those places from `FigureSettings` is a valid finding. Until then,
follow the rule.

### S6. Dependencies point one way

The core modules (`settings`, `sizes`, `mini`, `geometry`, `segment`, `sheet`,
`svg`, `token` and the rest outside `gui/`) never import `gui` or Qt. The GUI
depends on the core, never the other way round. This keeps the pipeline usable
from the command line and testable without a display.

Inside `gui/`, widgets and panels don't reach into the main window. They emit
signals, and the window connects them.

### S7. Failures are explicit

Don't catch bare exceptions, and don't swallow errors silently. Catch the
exceptions you expect, and let the rest reach the error dialog or the command
line's error output. Workers report every failure back to the UI (see AGENTS.md).

An error message says what went wrong in the user's terms and what they can do
about it.

### S8. No dead code

Remove unused functions, options, parameters, branches and commented-out code.
Git keeps the history. Before 1.0, don't keep compatibility code for old project
files or old flags. From 1.0, keep the migrations that AGENTS.md requires, and
nothing else.

### S9. Comments explain behaviour and reasons

Docstrings say what a function or class does, as an action or a purpose ("Build
the cut path for…"). Comments explain why the code does something that would
otherwise surprise a reader. Comments don't repeat what the code already says.

- Don't quote user-interface text or use example version numbers in comments
  and docstrings. Describe formats in words instead.
- Don't write comments about history ("now", "new", "used to"). Describe the
  code as it is.
- Give public functions in the core modules a docstring. Private helpers need
  one only when their name and signature aren't enough.

### S10. Keep GUI construction apart from GUI behaviour

Code that builds widgets and layouts is long and flat. Code that reacts to events
holds the logic. Keep them in separate methods, so that the logic can be read
and tested without wading through layout code. Split a long `__init__` that
builds a whole panel into one builder method per section.

Follow the GUI pitfalls in AGENTS.md. A change that breaks one of them is a
finding, even if it works today.

*Soft trigger:* an `__init__` over about 60 lines.

### S11. Name the numbers

A number that means something, such as a size, a margin, a timeout or a
threshold, gets a named constant with its unit, unless it is used once and its
meaning is obvious from the line it is on.

## Tests

### T1. Risky code is tested

The parts where a mistake costs the most need the most tests:

- the pipeline: geometry, layout, cut paths and bleed;
- loading and saving projects, and their compatibility rules;
- the update check and the release signature;
- sheet packing and the PDF and SVG output;
- creature sizes and how they fill in a figure.

Untested branches in these parts are findings. Use the coverage report to find
them. Untested GUI glue is lower priority, unless it holds logic.

### T2. Tests check behaviour, not implementation

A test checks what a user or caller can observe: return values, files written,
the text and state of widgets, signals emitted. It doesn't call private methods
or check private attributes, unless there is no other way to reach the
behaviour.

The test of this rule: a refactor that keeps behaviour the same keeps the tests
passing without editing them.

### T3. Tests are easy to find and read

- Test files follow the modules they test, so the tests for `geometry.py` are
  in `test_geometry.py`.
- Split a large test file by feature.
- Put shared setup in fixtures in `conftest.py`, not in copied code.
- A test's name says the behaviour it checks and under what condition.

*Soft trigger:* a test file over about 1,000 lines. `tests/test_gui.py` is about
2,400 lines.

### T4. Tests are fast, isolated and repeatable

- No network and no segmentation model. `tests/conftest.py` enforces this.
- No sleeping and no dependence on timing.
- Temporary folders, not the repository or the user's home folder.
- Preferences go through `gui.prefs.store()`.
- GUI tests run off-screen.

### T5. Every fixed bug gets a regression test

The test fails without the fix and passes with it. Its name or docstring says
what went wrong.

### T6. Pin behaviour down before refactoring

Before restructuring code that is poorly tested, add characterisation tests:
tests that record what the code does now, so that the refactor can be checked
against them.

## Docs and agent rules

### D1. Docs match the code

These must match what the code does:

- the layout map in AGENTS.md;
- the options table and the settings guide in `docs/reference.md`;
- the command line basics and the development setup in `README.md`;
- docstrings and comments.

A mismatch is a finding, whichever side is wrong.

### D2. A newcomer can get started

- The development section of the README takes a newcomer from a fresh clone to
  running the tests and the app in a few commands.
- The non-obvious designs are explained somewhere a newcomer will look: the
  stages of the pipeline, how the app runs builds on a worker thread and matches
  them to the settings they were started for, and how the caches work.

A non-obvious design that is explained nowhere is a finding. Explain it next to
the code, or in AGENTS.md when it spans modules.

### D3. Agent rules are current and give their reasons

Every rule in AGENTS.md is still true, doesn't contradict another rule, and says
why when the reason isn't obvious. Remove a rule, or make it point to the tool,
once a tool enforces it.

### D4. User-visible text is plain

Dialog intros, hints, tooltips and error messages are plain, direct sentences.
They first say what the thing is, then what the user can do. Text that reads
like a heading fragment or a riddle gets rewritten.

### D5. This guide stays current

When a review finds a problem that no rule covers, or a rule that no longer
fits, update this guide in the same pull request.

## Tooling and release

### R1. One command per common task

Common tasks (set up, test, lint, format, type-check, run the app, build) each
have a recipe in the `justfile`. CI and the docs use the same commands, so that
what passes locally passes in CI.

### R2. CI runs every check

CI runs the tests, the lint and format checks, the coverage report and the type
check, on every Python version and platform the project supports.

### R3. Builds are reproducible

Dependencies are locked, and the versions of the development tools are pinned.
A fresh clone on another machine gets the same environment.

### R4. Scripts follow the same rules as the app

The code in `scripts/` and `packaging/` is maintained like the rest. It isn't
exempt from the rules above.

*Example:* `main()` in `scripts/screenshots.py` is about 300 lines long.

### R5. The release and update path is documented and tested

Signing, the update check and the installer each have a way to try them locally
(see AGENTS.md). A change to them that skips that path is a finding.

### R6. Packaging stays in sync

A new runtime dependency or data file is added to the PyInstaller spec, and
tried in a local build.

## Proving a change is safe

A clean-up must not change behaviour. Each clean-up proves that:

1. **The whole test suite passes.**
2. **The samples come out the same.** Regenerate `examples/dragons/samples/`
   with the two sample batches. The outputs must be identical. If a difference
   is intended, explain each one.
3. **The window looks the same.** Render the window off-screen in the light and
   dark themes, before and after the change, and compare the images.
4. **Weakly tested code is pinned down first** with characterisation tests
   (T6).

A clean-up that changes nothing the user can see doesn't need the design
approval that AGENTS.md asks for new features. A change that alters how
anything looks or works does: stop and ask the maintainer to try it.

## Reporting findings

A review reports each finding with these fields:

| Field | What it holds |
|-------|---------------|
| Rule | The id of the rule it breaks, such as S2. |
| Where | `path:line`, or a list of them. |
| Problem | What is wrong, in one or two sentences. |
| Why it matters | How it slows down or misleads a maintainer: a newcomer, the maintainer, or both. |
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
- Renaming an option, command line flag or project file key without the
  migration that AGENTS.md requires from 1.0.
