"""ComfyUI workflow template loading and input/output injection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class WorkflowLoader:
    def __init__(self, workflows_dir: Path) -> None:
        self.workflows_dir = workflows_dir

    def load(self, workflow_path: Path) -> dict[str, Any]:
        with workflow_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def inject_io(self, workflow: dict[str, Any], input_image: str, output_prefix: str) -> dict[str, Any]:
        updated = json.loads(json.dumps(workflow))
        for node in updated.values():
            inputs = node.get("inputs", {})
            if "image" in inputs and isinstance(inputs["image"], str):
                inputs["image"] = input_image
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = output_prefix
        return updated
