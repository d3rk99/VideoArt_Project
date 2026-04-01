"""ComfyUI workflow template loading and input/output injection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class WorkflowValidationError(ValueError):
    """Raised when a workflow template cannot be injected safely."""


class WorkflowLoader:
    def __init__(self, workflows_dir: Path) -> None:
        self.workflows_dir = workflows_dir

    def load(self, workflow_path: Path) -> dict[str, Any]:
        with workflow_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def resolve_workflow_path(self, workflow_file: str) -> Path:
        path = Path(workflow_file)
        if not path.is_absolute():
            path = self.workflows_dir.parent / path
        return path

    def validate(self, workflow: dict[str, Any]) -> None:
        image_nodes = 0
        output_nodes = 0
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if isinstance(inputs.get("image"), str):
                image_nodes += 1
            if "filename_prefix" in inputs:
                output_nodes += 1
        if image_nodes == 0:
            raise WorkflowValidationError("Workflow missing an image input field")
        if output_nodes == 0:
            raise WorkflowValidationError("Workflow missing a filename_prefix field")

    def inject_io(self, workflow: dict[str, Any], input_image: str, output_prefix: str) -> dict[str, Any]:
        updated = json.loads(json.dumps(workflow))
        image_replacements = 0
        prefix_replacements = 0
        for node in updated.values():
            inputs = node.get("inputs", {})
            if "image" in inputs and isinstance(inputs["image"], str):
                inputs["image"] = input_image
                image_replacements += 1
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = output_prefix
                prefix_replacements += 1

        if image_replacements == 0:
            raise WorkflowValidationError("No image inputs were injected")
        if prefix_replacements == 0:
            raise WorkflowValidationError("No filename_prefix fields were injected")
        return updated

    def load_enabled_workflows(
        self,
        workflow_names: list[str],
        workflow_files: dict[str, str],
        input_image: str,
        prefix_pattern: str,
        session_id: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        loaded: list[tuple[str, dict[str, Any], str]] = []
        for workflow_name in workflow_names:
            if workflow_name not in workflow_files:
                raise WorkflowValidationError(f"Workflow '{workflow_name}' not found in workflows.files")
            workflow_path = self.resolve_workflow_path(workflow_files[workflow_name])
            if not workflow_path.exists():
                raise WorkflowValidationError(f"Workflow file not found: {workflow_path}")
            workflow = self.load(workflow_path)
            self.validate(workflow)
            prefix = prefix_pattern.format(session_id=session_id, workflow=workflow_name)
            injected = self.inject_io(workflow, input_image=input_image, output_prefix=prefix)
            loaded.append((workflow_name, injected, prefix))
        return loaded
