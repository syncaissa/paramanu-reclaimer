"""Array backend: CuPy on a GPU when requested and available, else NumPy."""
from __future__ import annotations

import numpy as np


def xp_for(use_gpu: bool = False):
    if use_gpu:
        try:
            import cupy as cp

            cp.cuda.runtime.getDeviceCount()
            return cp
        except Exception:  # no CuPy or no device: fall back quietly
            pass
    return np


def gpu_available() -> bool:
    return xp_for(True) is not np
