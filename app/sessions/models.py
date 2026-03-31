"""Session domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class SessionState(str, Enum):
    IDLE = "IDLE"
    DETECTING = "DETECTING"
    CAPTURING = "CAPTURING"
    PREPARING_INPUT = "PREPARING_INPUT"
    GENERATING = "GENERATING"
    COLLECTING_OUTPUTS = "COLLECTING_OUTPUTS"
    DISPLAYING = "DISPLAYING"
    COOLDOWN = "COOLDOWN"
    ERROR = "ERROR"


@dataclass
class SessionRecord:
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    archive_dir: Path | None = None
    raw_capture_path: Path | None = None
    processed_input_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
