# PyInstaller spec: one folder with the desktop app and the command line.
#
#   pip install -e ".[gui,build]"
#   pyinstaller packaging/papermini.spec --noconfirm
#
# Output in dist/:
#   Windows / Linux: papermini/ with papermini-gui(.exe) and papermini(.exe)
#   macOS:           papermini.app (the CLI is papermini.app/Contents/MacOS/papermini)
#
# The segmentation model is not bundled (its licence is non-commercial); the app
# downloads it to ~/.cache/papermini/ on first use, as it does when run from source.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HERE = Path(SPECPATH)  # noqa: F821 - provided by PyInstaller
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
from papermini import __version__  # noqa: E402  (written by setuptools-scm on install)

ICON = str(HERE / "icon.png")  # converted to .ico / .icns by PyInstaller (needs Pillow)

a = Analysis(  # noqa: F821
    [str(HERE / "gui_entry.py"), str(HERE / "cli_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("reportlab"),  # fonts used for the PDF sheet
    hiddenimports=["papermini._version"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "rembg"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821


def scripts_without(other):
    # a.scripts holds PyInstaller's runtime hooks followed by both entry scripts;
    # each executable gets the hooks plus its own entry script only
    return [s for s in a.scripts if s[0] != other]


gui = EXE(  # noqa: F821
    pyz,
    scripts_without("cli_entry"),
    [],
    exclude_binaries=True,
    name="papermini-gui",
    console=False,  # no console window on Windows
    icon=ICON,
)
cli = EXE(  # noqa: F821
    pyz,
    scripts_without("gui_entry"),
    [],
    exclude_binaries=True,
    name="papermini",
    console=True,
    icon=ICON,
)
coll = COLLECT(gui, cli, a.binaries, a.datas, name="papermini")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="papermini.app",
        icon=ICON,
        bundle_identifier="io.github.mjlhthomassen.papermini",
        version=__version__,
        info_plist={
            "CFBundleExecutable": "papermini-gui",  # the GUI starts when the app opens
            "CFBundleName": "papermini",
            "CFBundleDisplayName": "papermini",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # follow the system dark mode
        },
    )
