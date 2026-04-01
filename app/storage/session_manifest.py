"""Persist session metadata to a manifest JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.sessions.models import SessionRecord


def _serialize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def write_manifest(session: SessionRecord) -> Path:
    if not session.archive_dir:
        raise ValueError("archive_dir is required to write manifest")
    manifest_path = session.archive_dir / "manifest.json"
    data = asdict(session)
    manifest_path.write_text(json.dumps(_serialize(data), indent=2), encoding="utf-8")
    return manifest_path
