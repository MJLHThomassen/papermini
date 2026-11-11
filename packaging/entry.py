"""PyInstaller entry point: papermini, the desktop app and the command line in one.

Without a command it opens the desktop app; with one it runs the command line (see
papermini.cli.route).
"""

import sys

from papermini.cli import main

if __name__ == "__main__":
    sys.exit(main())
