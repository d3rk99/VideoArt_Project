"""Comfy output watcher scaffold for Phase 2."""

from __future__ import annotations

from pathlib import Path


class OutputWatcher:
    def resolve_outputs(self, session_prefix: str, output_root: Path) -> list[Path]:
        return sorted(output_root.glob(f"{session_prefix}*"))
