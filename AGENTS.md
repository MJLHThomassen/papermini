# AGENTS.md

Extra rules for coding agents working in this repository.

[docs/maintainability.md](docs/maintainability.md) is the single source of
truth for how the code is kept maintainable: its structure, tests, docs,
tooling and releases, and where things are in the repository. Read it before
changing code, and follow it. This file only adds what agents need on top of
it.

## Hard rules

- **Never edit the top of `README.md`.** Everything from the first line up to
  and including `*Disclaimer: This tool is 100% vibecoded!*` belongs to the
  maintainer. Leave those lines byte for byte as they are (wording, spacing,
  line endings). Edit only what comes after them.
- **Run everything in the project environment.** Never install Python
  packages globally, and never with pip. Run tasks through `just` (`just setup`,
  `just test`, `just gui`), which runs uv with the environment in
  `~/.venvs/papermini`. Run other commands with `uv run --all-extras ...`, with
  `UV_PROJECT_ENVIRONMENT` set to `~/.venvs/papermini`. Add dependencies with
  `uv add`.
- **Do not commit, push or open pull requests unless asked.** When you do
  commit, follow rule R7 of the guide.
- **Never start a release, or create or push tags, unless asked.** Releases
  are cut by the maintainer (rule R9 of the guide).

## How to work

- **New features: get the design approved first.** After building a new
  feature, stop and ask the maintainer to run the app and try it. Say how to
  start it (for example `just gui examples/dragons/dragons.yaml`) and what to
  look at. Only once they approve
  how the feature looks and works, run the test suite, update the docs and
  regenerate the samples and screenshots (rule D3). Until then, leave those
  steps undone, so they are not redone after every change to the design.
- **Look at GUI changes yourself.** Render the window off-screen
  (`WA_DontShowOnScreen` plus `grab()`) and check the image, in both the light
  and the dark theme.

## Mistakes agents often make

Check your work for these before you finish. Each one breaks a rule in the
guide.

- **Padding lists to three** (rule D5). Name as many items as there really
  are. This applies to code comments, docs, commit messages, pull request
  descriptions and your replies.
- **Explaining what a result is used for elsewhere** (rule S13). A docstring
  says what its function does, not that a caller several calls away needs the
  output in a certain shape.
- **Quoting user-interface text or example version numbers in comments**
  (rule S13).
- **Commenting on a change made for a review** (rule S13). When you change code
  to answer a review comment, change only the code. Don't add a comment about
  what used to be there.
