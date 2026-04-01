"""Filesystem manager for session input/output paths."""

from __future__ import annotations

import shutil
from pathlib import Path


class FileManager:
    def __init__(
        self,
        live_capture_dir: Path,
        comfy_input_dir: Path,
        output_latest_dir: Path,
        output_archive_dir: Path,
    ) -> None:
        self.live_capture_dir = live_capture_dir
        self.comfy_input_dir = comfy_input_dir
        self.output_latest_dir = output_latest_dir
        self.output_archive_dir = output_archive_dir
        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        for folder in [
            self.live_capture_dir,
            self.comfy_input_dir,
            self.output_latest_dir,
            self.output_archive_dir,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

    def create_session_dir(self, session_id: str) -> Path:
        session_dir = self.output_archive_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def session_raw_path(self, session_id: str) -> Path:
        return self.live_capture_dir / f"{session_id}_raw.jpg"

    def session_comfy_input_path(self, session_id: str) -> Path:
        return self.comfy_input_dir / f"{session_id}_input.jpg"

    def write_workflow_outputs(self, session_id: str, workflow_name: str, outputs: list[tuple[str, bytes]]) -> list[Path]:
        session_dir = self.output_archive_dir / session_id
        workflow_dir = session_dir / "generated" / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for idx, (filename, blob) in enumerate(outputs, start=1):
            suffix = Path(filename).suffix or ".png"
            target = workflow_dir / f"{workflow_name}_{idx}{suffix}"
            target.write_bytes(blob)
            written.append(target)
        return written

    def clear_comfy_input_images(self) -> None:
        for candidate in self.comfy_input_dir.glob("*"):
            if candidate.is_file():
                candidate.unlink()

    def copy_to_latest(self, source_paths: list[Path]) -> list[Path]:
        for old_file in self.output_latest_dir.glob("*"):
            if old_file.is_file():
                old_file.unlink()

        latest_paths: list[Path] = []
        for idx, source in enumerate(source_paths, start=1):
            target = self.output_latest_dir / f"latest_{idx}{source.suffix}"
            shutil.copy2(source, target)
            latest_paths.append(target)
        return latest_paths
