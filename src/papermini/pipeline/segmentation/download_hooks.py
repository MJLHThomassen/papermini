from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadHooks:
    """What a build calls when it needs a built-in model that is not downloaded yet.

    ``confirm(model)`` is asked first, and False refuses the download. Without it the
    model downloads without asking, as on the command line. ``progress(done_bytes,
    total_bytes_or_None, message)`` hears how the download goes.
    """

    confirm: Callable[[str], bool] | None = None
    progress: Callable[[int, int | None, str], None] | None = None
