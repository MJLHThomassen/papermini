# Common tasks, the same on Windows, macOS and Linux (https://just.systems):
#
#   just                 list the recipes
#   just try-update      build papermini, then try its automatic update on a copy
#
# Every recipe uses the project venv (~/.venvs/papermini, made by `just setup`).

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

venv := home_directory() / ".venvs" / "papermini"
python := if os_family() == "windows" { venv / "Scripts" / "python.exe" } else { venv / "bin" / "python" }
system_python := if os_family() == "windows" { "python" } else { "python3" }
# PowerShell runs a quoted program path only after "&"
run := if os_family() == "windows" { "& " } else { "" }

# list the recipes
default:
    @just --list

# make or update the venv, with the test and build tools
setup:
    {{ system_python }} scripts/setup_venv.py --dev --build

# run the tests (extra arguments go to pytest, e.g. `just test -k sheet`)
test *args:
    {{ run }}"{{ python }}" -m pytest {{ args }}

# start the app from source (e.g. `just gui examples/dragons/dragons.yaml`)
gui *args:
    {{ run }}"{{ python }}" -m papermini gui {{ args }}

# build the standalone app into dist/
build:
    {{ run }}"{{ python }}" -m PyInstaller packaging/papermini.spec --noconfirm

# build the Windows installer of the build in dist/ (needs Inno Setup 6)
installer:
    {{ run }}"{{ python }}" scripts/build_installer.py

# build, then update a copy of the build to a fake signed release (see scripts/try_update.py)
try-update:
    {{ run }}"{{ python }}" scripts/try_update.py

# the same with the last build of try-update (it builds in the temp folder)
try-update-nobuild:
    {{ run }}"{{ python }}" scripts/try_update.py --no-build

# Windows: install the build with its installer, then update it with a newer installer
try-update-installer:
    {{ run }}"{{ python }}" scripts/try_update.py --installer

# quick: papermini from source updates a pretend installed copy (no build)
try-update-source:
    {{ run }}"{{ python }}" scripts/try_update.py --source

# regenerate the README screenshots (needs the three models)
screenshots:
    {{ run }}"{{ python }}" scripts/screenshots.py

# rebuild the sample outputs in examples/dragons/samples
samples:
    {{ run }}"{{ python }}" -m papermini batch examples/dragons/samples.yaml
    {{ run }}"{{ python }}" -m papermini batch examples/dragons/samples-machine.yaml
