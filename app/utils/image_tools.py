"""Image processing helpers used by capture selection pipeline."""

from __future__ import annotations

import cv2
import numpy as np


def sharpness_score(frame: np.ndarray) -> float:
    """Return a simple sharpness metric using Laplacian variance."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def resize_to(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
