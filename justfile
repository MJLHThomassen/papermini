# Common tasks, the same on Windows, macOS and Linux (https://just.systems):
#
#   just                 list the recipes
#   just try-update      build papermini, then try its automatic update on a copy
#
# Every recipe runs in the project environment through uv (https://docs.astral.sh/uv/).
# The environment lives outside the clone, in ~/.venvs/papermini, because a venv holds
# thousands of files that a synced folder (OneDrive, Dropbox) should not sync. Set
# UV_PROJECT_ENVIRONMENT yourself to put it somewhere else.

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

export UV_PROJECT_ENVIRONMENT := env("UV_PROJECT_ENVIRONMENT", home_directory() / ".venvs" / "papermini")

# run a command in the environment, with the desktop app's dependencies
uv_run := "uv run --all-extras"

# list the recipes
default:
    @just --list

# make or update the environment, with the test and build tools
setup:
    uv sync --all-extras --all-groups

# run the tests (extra arguments go to pytest, e.g. `just test -k sheet`)
test *args:
    {{ uv_run }} python -m pytest {{ args }}

# check the code with ruff (extra arguments go to ruff, e.g. `just lint --fix`)
lint *args:
    uv run ruff check {{ args }}

# format the code with ruff (extra arguments go to ruff, e.g. `just format --check`)
format *args:
    uv run ruff format {{ args }}

# start the app from source (e.g. `just gui examples/dragons/dragons.yaml`)
gui *args:
    {{ uv_run }} python -m papermini gui {{ args }}

# build the standalone app into dist/
build:
    {{ uv_run }} --group build python -m PyInstaller packaging/papermini.spec --noconfirm

# build the Windows installer of the build in dist/ (needs Inno Setup 6)
installer:
    {{ uv_run }} python scripts/build_installer.py

# build, then update a copy of the build to a fake signed release (see scripts/try_update.py)
try-update:
    {{ uv_run }} --group build python scripts/try_update.py

# the same with the last build of try-update (it builds in the temp folder)
try-update-nobuild:
    {{ uv_run }} python scripts/try_update.py --no-build

# Windows: install the build with its installer, then update it with a newer installer
try-update-installer:
    {{ uv_run }} --group build python scripts/try_update.py --installer

# quick: papermini from source updates a pretend installed copy (no build)
try-update-source:
    {{ uv_run }} python scripts/try_update.py --source

# regenerate the README screenshots (needs the three models)
screenshots:
    {{ uv_run }} python scripts/screenshots.py

# rebuild the sample outputs in examples/dragons/samples
samples:
    {{ uv_run }} python -m papermini batch examples/dragons/samples.yaml
    {{ uv_run }} python -m papermini batch examples/dragons/samples-machine.yaml
