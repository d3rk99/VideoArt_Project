"""Run Phase 2 generation against ComfyUI and sync outputs to session storage."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.comfy.comfy_client import ComfyClient, ComfyClientError
from app.comfy.workflow_loader import WorkflowLoader
from app.sessions.models import WorkflowRunRecord
from app.storage.file_manager import FileManager


@dataclass
class WorkflowGenerationResult:
    workflow_name: str
    prompt_id: str
    archive_outputs: list[Path]


class GenerationService:
    def __init__(self, client: ComfyClient, loader: WorkflowLoader, file_manager: FileManager) -> None:
        self.client = client
        self.loader = loader
        self.file_manager = file_manager
        self.logger = logging.getLogger(__name__)

    def run_for_session(self, session, settings: dict) -> list[Path]:
        input_path = session.processed_input_path
        if not input_path or not input_path.exists():
            raise ComfyClientError("Processed input image missing for generation")

        comfy_settings = settings["comfy"]
        input_dirs = [Path(p) for p in comfy_settings.get("input_folders", [comfy_settings.get("input_dir")]) if p]
        output_dirs = [Path(p) for p in comfy_settings.get("output_folders", []) if p]
        if not input_dirs:
            raise ComfyClientError("No Comfy input folder configured (comfy.input_folders)")
        if not output_dirs:
            raise ComfyClientError("No Comfy output folder configured (comfy.output_folders)")

        staged_name = self.file_manager.stage_for_comfy_inputs(
            input_path=input_path,
            input_folders=input_dirs,
            fixed_filename=comfy_settings.get("fixed_input_filename"),
        )

        inject_input_name = bool(comfy_settings.get("inject_input_filename", False))
        loaded = self.loader.load_enabled_workflows(
            workflow_names=list(settings["workflows"]["enabled"]),
            workflow_files=dict(settings["workflows"]["files"]),
            input_image=staged_name if inject_input_name else "",
            prefix_pattern=settings["comfy"].get("output_filename_prefix_pattern", "{session_id}_{workflow}"),
            session_id=session.session_id,
            inject_image=inject_input_name,
            inject_prefix=bool(comfy_settings.get("inject_output_prefix", False)),
        )
        all_archive_outputs: list[Path] = []
        for workflow_name, workflow_payload, _ in loaded:
            run_record = WorkflowRunRecord(
                workflow_name=workflow_name,
                source_input_image=str(input_path),
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            try:
                before_outputs = self._snapshot_outputs(output_dirs)
                prompt_id = self._run_with_fallback_upload(
                    workflow_payload=workflow_payload,
                    input_path=input_path,
                    inject_input_name=inject_input_name,
                )
                run_record.prompt_id = prompt_id
                self.logger.info("ComfyUI prompt submitted", extra={"workflow": workflow_name, "prompt_id": prompt_id})

                self.client.wait_for_completion(
                    prompt_id=prompt_id,
                    timeout_seconds=float(settings["comfy"]["generation_timeout_seconds"]),
                    poll_interval_seconds=float(settings["comfy"]["poll_interval_seconds"]),
                )
                discovered = self._detect_new_outputs(output_dirs, before_outputs)
                if not discovered:
                    raise ComfyClientError(f"No output images detected in configured output folders for {workflow_name}")

                archive_outputs = self._archive_detected_outputs(session.session_id, workflow_name, discovered)
                run_record.generated_output_files = [str(p) for p in archive_outputs]
                all_archive_outputs.extend(archive_outputs)
            except Exception as exc:
                run_record.error = str(exc)
                self.logger.exception("Workflow generation failed", extra={"workflow": workflow_name})
                session.errors.append(f"{workflow_name}: {exc}")
                raise
            finally:
                run_record.finished_at = datetime.now(timezone.utc).isoformat()
                session.workflow_runs.append(run_record)

        latest = self.file_manager.copy_to_latest(all_archive_outputs)
        session.output_paths = latest
        session.workflows = [workflow_name for workflow_name, _, _ in loaded]

        expected_output_count = int(settings["comfy"].get("expected_output_count", 5))
        if len(all_archive_outputs) >= expected_output_count:
            self.file_manager.clear_comfy_input_images()
        if bool(comfy_settings.get("delete_inputs_after_success", True)):
            self.file_manager.clear_staged_comfy_inputs(input_dirs, staged_name)

        return latest

    def _run_with_fallback_upload(self, workflow_payload: dict, input_path: Path, inject_input_name: bool) -> str:
        try:
            return self.client.run_workflow(workflow_payload)
        except ComfyClientError as exc:
            message = str(exc)
            if inject_input_name or "Invalid image file" not in message:
                raise
            self.logger.warning("Folder-staged input not visible to ComfyUI; retrying with upload fallback")
            uploaded_name = self.client.upload_input_image(input_path)
            retry_payload = self.loader.inject_io(
                workflow_payload,
                input_image=uploaded_name,
                output_prefix="",
                inject_image=True,
                inject_prefix=False,
            )
            return self.client.run_workflow(retry_payload)

    def _snapshot_outputs(self, output_dirs: list[Path]) -> set[Path]:
        existing: set[Path] = set()
        for folder in output_dirs:
            folder.mkdir(parents=True, exist_ok=True)
            existing.update(p.resolve() for p in folder.glob("*") if p.is_file())
        return existing

    def _detect_new_outputs(self, output_dirs: list[Path], before_outputs: set[Path]) -> list[Path]:
        discovered: list[Path] = []
        for folder in output_dirs:
            for candidate in sorted(folder.glob("*")):
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if resolved in before_outputs:
                    continue
                discovered.append(candidate)
        return discovered

    def _archive_detected_outputs(self, session_id: str, workflow_name: str, outputs: list[Path]) -> list[Path]:
        session_dir = self.file_manager.create_session_dir(session_id)
        workflow_dir = session_dir / "generated" / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)
        archived: list[Path] = []
        for idx, source in enumerate(outputs, start=1):
            suffix = source.suffix or ".png"
            target = workflow_dir / f"{workflow_name}_{idx}{suffix}"
            shutil.copy2(source, target)
            archived.append(target)
        return archived
