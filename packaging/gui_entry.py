"""PyInstaller entry point for the desktop app (papermini-gui)."""

import sys

from papermini.gui import main

if __name__ == "__main__":
    sys.exit(main())
