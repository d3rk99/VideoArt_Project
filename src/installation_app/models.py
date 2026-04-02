from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class AppState(str, Enum):
    IDLE = "IDLE"
    DETECTING = "DETECTING"
    FACE_LOCKED = "FACE_LOCKED"
    CAPTURING = "CAPTURING"
    SAVING = "SAVING"
    TRIGGERING_COMFY = "TRIGGERING_COMFY"
    WAITING_FOR_COMFY = "WAITING_FOR_COMFY"
    CLEANING_INPUTS = "CLEANING_INPUTS"
    COLLECTING_OUTPUTS = "COLLECTING_OUTPUTS"
    UPDATING_OBS = "UPDATING_OBS"
    TRIGGERING_TRANSITION = "TRIGGERING_TRANSITION"
    CLEANING_OUTPUTS = "CLEANING_OUTPUTS"
    COOLDOWN = "COOLDOWN"
    READY = "READY"


@dataclass
class RunContext:
    run_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    input_files: list[Path] = field(default_factory=list)
    output_files: list[Path] = field(default_factory=list)
    comfy_prompt_id: str | None = None


def build_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S_%f")
