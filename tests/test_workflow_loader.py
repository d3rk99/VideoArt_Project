from pathlib import Path
import json

import pytest

from app.comfy.workflow_loader import WorkflowLoader, WorkflowValidationError


def test_workflow_injection(tmp_path: Path) -> None:
    loader = WorkflowLoader(tmp_path)
    workflow = {
        "1": {"inputs": {"image": "old.png"}},
        "2": {"inputs": {"filename_prefix": "old_prefix"}},
    }
    injected = loader.inject_io(workflow, "new_input.jpg", "session_123")
    assert injected["1"]["inputs"]["image"] == "new_input.jpg"
    assert injected["2"]["inputs"]["filename_prefix"] == "session_123"


def test_workflow_validate_raises_when_missing_fields(tmp_path: Path) -> None:
    loader = WorkflowLoader(tmp_path)
    with pytest.raises(WorkflowValidationError):
        loader.validate({"1": {"inputs": {"foo": "bar"}}})


def test_load_enabled_workflows_supports_multiple(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(parents=True)
    workflow_payload = {
        "1": {"inputs": {"image": "input.jpg"}},
        "2": {"inputs": {"filename_prefix": "prefix"}},
    }
    (workflows_dir / "a.json").write_text(json.dumps(workflow_payload), encoding="utf-8")
    (workflows_dir / "b.json").write_text(json.dumps(workflow_payload), encoding="utf-8")

    loader = WorkflowLoader(workflows_dir)
    loaded = loader.load_enabled_workflows(
        workflow_names=["a", "b"],
        workflow_files={"a": "workflows/a.json", "b": "workflows/b.json"},
        input_image="/tmp/input.jpg",
        prefix_pattern="{session_id}_{workflow}",
        session_id="session_1",
    )

    assert len(loaded) == 2
    assert loaded[0][0] == "a"
    assert loaded[0][1]["1"]["inputs"]["image"] == "/tmp/input.jpg"
    assert loaded[1][1]["2"]["inputs"]["filename_prefix"] == "session_1_b"
