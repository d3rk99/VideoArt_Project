import json
from pathlib import Path

from app.sessions.models import SessionRecord, WorkflowRunRecord
from app.storage.session_manifest import write_manifest


def test_manifest_contains_generation_metadata(tmp_path: Path) -> None:
    session = SessionRecord(session_id="session_1", archive_dir=tmp_path)
    session.processed_input_path = tmp_path / "input.jpg"
    session.output_paths = [tmp_path / "latest_1.png"]
    session.workflow_runs.append(
        WorkflowRunRecord(
            workflow_name="mona_lisa",
            prompt_id="prompt_123",
            source_input_image=str(tmp_path / "input.jpg"),
            generated_output_files=[str(tmp_path / "generated.png")],
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:03+00:00",
        )
    )

    manifest_path = write_manifest(session)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["workflow_runs"][0]["prompt_id"] == "prompt_123"
    assert payload["workflow_runs"][0]["workflow_name"] == "mona_lisa"
