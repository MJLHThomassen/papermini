# PyInstaller spec: one program that is both the desktop app and the command line.
#
#   pip install -e ".[gui,build]"
#   pyinstaller packaging/papermini.spec --noconfirm
#
# Output in dist/:
#   Windows / Linux: papermini/ with papermini(.exe)
#   macOS:           papermini.app (the program is papermini.app/Contents/MacOS/papermini)
#
# Started without a command (double-clicked, or with files) it opens the desktop app;
# with a command (make, sheet, batch, --help) it runs the command line. On Windows it is
# a console program whose console is hidden when papermini owns it (started from
# Explorer), so a terminal keeps its output, waits for it and gets its exit code.
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

ICON = str(HERE / "icon.png")  # from make_icon.py; PyInstaller converts it to .ico / .icns (needs Pillow)

a = Analysis(  # noqa: F821
    [str(HERE / "entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("reportlab")  # fonts used for the PDF sheet
    + [(str(ROOT / "src" / "papermini" / "gui" / "logo.svg"), "papermini/gui")],
    hiddenimports=["papermini._version"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="papermini",
    console=True,  # a terminal keeps its output, waits for it and gets its exit code
    # started from Explorer, papermini owns its console: hide it before Python starts
    hide_console="hide-early" if sys.platform == "win32" else None,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="papermini")  # noqa: F821

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name="papermini.app",
        icon=ICON,
        bundle_identifier="io.github.mjlhthomassen.papermini",
        version=__version__,
        info_plist={
            "CFBundleExecutable": "papermini",  # opened from Finder: the desktop app
            # a regular app with a Dock icon and a menu bar: PyInstaller makes the bundle
            # background-only when its executable is a console one (as papermini is)
            "LSBackgroundOnly": False,
            "CFBundleName": "papermini",
            "CFBundleDisplayName": "papermini",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # follow the system dark mode
        },
    )
