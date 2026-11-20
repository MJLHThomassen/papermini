from __future__ import annotations

import numpy as np


class ReadOnly:
    """Makes arrays read-only, so a cached stage can never be modified by accident."""

    @staticmethod
    def array(a: np.ndarray) -> np.ndarray:
        """Return ``a`` as a read-only array."""
        a = np.asarray(a)
        if a.flags.writeable:
            a = a.copy() if not a.flags.owndata else a
            a.setflags(write=False)
        return a
