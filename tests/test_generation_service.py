from pathlib import Path

from app.comfy.generation_service import GenerationService
from app.sessions.models import SessionRecord


class FakeClient:
    def __init__(self) -> None:
        self.uploaded: Path | None = None

    def upload_input_image(self, image_path: Path) -> str:
        self.uploaded = image_path
        return "uploaded_input.jpg"

    def submit_workflow(self, workflow_payload):
        return "prompt_1"

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float, poll_interval_seconds: float):
        class Result:
            history_payload = {"outputs": {"1": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}

        return Result()

    def extract_output_paths(self, history_payload):
        from app.comfy.comfy_client import ComfyImageRef

        return [ComfyImageRef(filename="out.png", subfolder="", type="output")]

    def download_output(self, image_ref):
        return b"img"


class FakeLoader:
    def __init__(self) -> None:
        self.injected_input = ""

    def load_enabled_workflows(self, workflow_names, workflow_files, input_image, prefix_pattern, session_id):
        self.injected_input = input_image
        return [("mona_lisa", {"1": {"inputs": {"image": input_image}}}, "pref")]


class FakeFileManager:
    def write_workflow_outputs(self, session_id, workflow_name, outputs):
        return [Path(f"/tmp/{session_id}_{workflow_name}.png")]

    def copy_to_latest(self, source_paths):
        return [Path("/tmp/latest_1.png")]


def test_generation_service_uploads_input_before_injection(tmp_path: Path) -> None:
    input_path = tmp_path / "session_input.jpg"
    input_path.write_bytes(b"data")

    session = SessionRecord(session_id="session_1", archive_dir=tmp_path, processed_input_path=input_path)
    client = FakeClient()
    loader = FakeLoader()
    service = GenerationService(client=client, loader=loader, file_manager=FakeFileManager())

    settings = {
        "workflows": {"enabled": ["mona_lisa"], "files": {"mona_lisa": "workflows/mona_lisa.json"}},
        "comfy": {
            "output_filename_prefix_pattern": "{session_id}_{workflow}",
            "generation_timeout_seconds": 1,
            "poll_interval_seconds": 0.1,
        },
    }

    outputs = service.run_for_session(session, settings)

    assert client.uploaded == input_path
    assert loader.injected_input == "uploaded_input.jpg"
    assert outputs[0].name == "latest_1.png"
