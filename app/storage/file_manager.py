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
        comfy_runtime_input_dir: Path | None = None,
    ) -> None:
        self.live_capture_dir = live_capture_dir
        self.comfy_input_dir = comfy_input_dir
        self.output_latest_dir = output_latest_dir
        self.output_archive_dir = output_archive_dir
        self.comfy_runtime_input_dir = comfy_runtime_input_dir or comfy_input_dir
        self.ensure_dirs()

    def ensure_dirs(self) -> None:
        for folder in [
            self.live_capture_dir,
            self.comfy_input_dir,
            self.output_latest_dir,
            self.output_archive_dir,
            self.comfy_runtime_input_dir,
        ]:
            folder.mkdir(parents=True, exist_ok=True)

    def create_session_dir(self, session_id: str) -> Path:
        session_dir = self.output_archive_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def session_raw_path(self, session_id: str) -> Path:
        return self.live_capture_dir / f"{session_id}_raw.jpg"

    def session_comfy_input_path(self, session_id: str) -> Path:
        return self.comfy_input_dir / f"{session_id}_input.png"

    def stage_for_comfy_runtime(self, input_path: Path) -> str:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file missing: {input_path}")
        target = self.comfy_runtime_input_dir / input_path.name
        if input_path.resolve() != target.resolve():
            shutil.copy2(input_path, target)
        return target.name

    def stage_for_comfy_inputs(
        self,
        input_path: Path,
        input_folders: list[Path],
        fixed_filename: str | None = None,
    ) -> str:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file missing: {input_path}")
        target_name = fixed_filename or input_path.name
        for folder in input_folders:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, folder / target_name)
        return target_name

    def clear_staged_comfy_inputs(self, input_folders: list[Path], filename: str) -> None:
        for folder in input_folders:
            candidate = folder / filename
            if candidate.exists() and candidate.is_file():
                candidate.unlink()

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
        folders = [self.comfy_input_dir]
        if self.comfy_runtime_input_dir != self.comfy_input_dir:
            folders.append(self.comfy_runtime_input_dir)
        for folder in folders:
            for candidate in folder.glob("*"):
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
