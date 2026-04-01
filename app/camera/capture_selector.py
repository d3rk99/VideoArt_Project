"""Capture burst scoring and best-frame selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.utils.image_tools import sharpness_score


@dataclass
class CaptureResult:
    frame: np.ndarray
    score: float


class CaptureSelector:
    def select_best(self, frames: list[np.ndarray]) -> CaptureResult:
        if not frames:
            raise ValueError("No frames supplied for selection")
        scored = [CaptureResult(frame=f, score=sharpness_score(f)) for f in frames]
        return max(scored, key=lambda c: c.score)
