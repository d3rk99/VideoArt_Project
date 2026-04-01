from pathlib import Path

from app.comfy.generation_service import GenerationService
from app.sessions.models import SessionRecord


class FakeClient:
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
        return [
            ("mona_lisa", {"1": {"inputs": {"image": input_image}}}, "pref"),
            ("pearl_earring", {"1": {"inputs": {"image": input_image}}}, "pref"),
            ("girl_with_hat", {"1": {"inputs": {"image": input_image}}}, "pref"),
            ("american_gothic", {"1": {"inputs": {"image": input_image}}}, "pref"),
            ("pop_art_portrait", {"1": {"inputs": {"image": input_image}}}, "pref"),
        ]


class FakeFileManager:
    def __init__(self) -> None:
        self.cleared = False
        self.staged = ""

    def stage_for_comfy_runtime(self, input_path: Path):
        self.staged = input_path.name
        return input_path.name

    def write_workflow_outputs(self, session_id, workflow_name, outputs):
        return [Path(f"/tmp/{session_id}_{workflow_name}.png")]

    def copy_to_latest(self, source_paths):
        return [Path("/tmp/latest_1.png")]

    def clear_comfy_input_images(self):
        self.cleared = True


def test_generation_service_uses_comfy_input_filename_and_clears_input(tmp_path: Path) -> None:
    input_path = tmp_path / "session_input.jpg"
    input_path.write_bytes(b"data")

    session = SessionRecord(session_id="session_1", archive_dir=tmp_path, processed_input_path=input_path)
    client = FakeClient()
    loader = FakeLoader()
    file_manager = FakeFileManager()
    service = GenerationService(client=client, loader=loader, file_manager=file_manager)

    settings = {
        "workflows": {
            "enabled": ["mona_lisa", "pearl_earring", "girl_with_hat", "american_gothic", "pop_art_portrait"],
            "files": {
                "mona_lisa": "workflows/mona_lisa.json",
                "pearl_earring": "workflows/pearl_earring.json",
                "girl_with_hat": "workflows/girl_with_hat.json",
                "american_gothic": "workflows/american_gothic.json",
                "pop_art_portrait": "workflows/pop_art_portrait.json",
            },
        },
        "comfy": {
            "output_filename_prefix_pattern": "{session_id}_{workflow}",
            "generation_timeout_seconds": 1,
            "poll_interval_seconds": 0.1,
            "expected_output_count": 5,
        },
    }

    outputs = service.run_for_session(session, settings)

    assert file_manager.staged == "session_input.jpg"
    assert loader.injected_input == "session_input.jpg"
    assert outputs[0].name == "latest_1.png"
    assert file_manager.cleared is True
