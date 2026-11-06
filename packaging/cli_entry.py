"""PyInstaller entry point for the command line (papermini)."""

import sys

from papermini.cli import main

if __name__ == "__main__":
    sys.exit(main())
