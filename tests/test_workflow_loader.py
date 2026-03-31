from pathlib import Path

from app.comfy.workflow_loader import WorkflowLoader


def test_workflow_injection(tmp_path: Path) -> None:
    loader = WorkflowLoader(tmp_path)
    workflow = {
        "1": {"inputs": {"image": "old.png"}},
        "2": {"inputs": {"filename_prefix": "old_prefix"}},
    }
    injected = loader.inject_io(workflow, "new_input.jpg", "session_123")
    assert injected["1"]["inputs"]["image"] == "new_input.jpg"
    assert injected["2"]["inputs"]["filename_prefix"] == "session_123"
