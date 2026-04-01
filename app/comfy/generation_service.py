"""Run Phase 2 generation against ComfyUI and sync outputs to session storage."""

from __future__ import annotations

import logging
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

        loaded = self.loader.load_enabled_workflows(
            workflow_names=list(settings["workflows"]["enabled"]),
            workflow_files=dict(settings["workflows"]["files"]),
            input_image=self.file_manager.stage_for_comfy_runtime(input_path),
            prefix_pattern=settings["comfy"].get("output_filename_prefix_pattern", "{session_id}_{workflow}"),
            session_id=session.session_id,
        )
        all_archive_outputs: list[Path] = []
        for workflow_name, workflow_payload, _ in loaded:
            run_record = WorkflowRunRecord(
                workflow_name=workflow_name,
                source_input_image=str(input_path),
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            try:
                prompt_id = self.client.submit_workflow(workflow_payload)
                run_record.prompt_id = prompt_id
                self.logger.info("ComfyUI prompt submitted", extra={"workflow": workflow_name, "prompt_id": prompt_id})

                result = self.client.wait_for_completion(
                    prompt_id=prompt_id,
                    timeout_seconds=float(settings["comfy"]["generation_timeout_seconds"]),
                    poll_interval_seconds=float(settings["comfy"]["poll_interval_seconds"]),
                )
                image_refs = self.client.extract_output_paths(result.history_payload)
                if not image_refs:
                    raise ComfyClientError(f"No output images found for workflow {workflow_name}")

                archive_outputs = self.file_manager.write_workflow_outputs(
                    session_id=session.session_id,
                    workflow_name=workflow_name,
                    outputs=[(img.filename, self.client.download_output(img)) for img in image_refs],
                )
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

        return latest
