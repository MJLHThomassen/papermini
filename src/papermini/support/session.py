from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass
class Session:
    """The running session's files."""

    log: Path
    crash: Path
    handler: logging.Handler
    crash_file: IO | None = None
