"""Small timer helpers for stable trigger and cooldown tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class CooldownTimer:
    duration_seconds: float
    _last_start: float = field(default=0.0)

    def start(self) -> None:
        self._last_start = monotonic()

    def active(self) -> bool:
        if self._last_start == 0.0:
            return False
        return monotonic() - self._last_start < self.duration_seconds


@dataclass
class StabilityTimer:
    required_seconds: float
    _started_at: float | None = None

    def reset(self) -> None:
        self._started_at = None

    def tick(self, valid_signal: bool) -> bool:
        now = monotonic()
        if not valid_signal:
            self.reset()
            return False
        if self._started_at is None:
            self._started_at = now
        return (now - self._started_at) >= self.required_seconds
