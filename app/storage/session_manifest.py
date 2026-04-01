"""Persist session metadata to a manifest JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.sessions.models import SessionRecord


def write_manifest(session: SessionRecord) -> Path:
    if not session.archive_dir:
        raise ValueError("archive_dir is required to write manifest")
    manifest_path = session.archive_dir / "manifest.json"
    data = asdict(session)
    data["archive_dir"] = str(session.archive_dir)
    data["raw_capture_path"] = str(session.raw_capture_path) if session.raw_capture_path else None
    data["processed_input_path"] = (
        str(session.processed_input_path) if session.processed_input_path else None
    )
    data["output_paths"] = [str(p) for p in session.output_paths]
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return manifest_path
