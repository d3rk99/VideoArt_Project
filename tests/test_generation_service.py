from pathlib import Path

from app.comfy.generation_service import GenerationService
from app.sessions.models import SessionRecord


class FakeClient:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.ran = False

    def run_workflow(self, workflow_payload):
        self.ran = True
        (self.output_dir / "generated.png").write_bytes(b"img")
        return "prompt_1"

    def upload_input_image(self, input_path: Path) -> str:
        return input_path.name

    def wait_for_completion(self, prompt_id: str, timeout_seconds: float, poll_interval_seconds: float):
        class Result:
            history_payload = {"outputs": {"1": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}

        return Result()

class FakeLoader:
    def __init__(self) -> None:
        self.injected_input = ""

    def load_enabled_workflows(
        self,
        workflow_names,
        workflow_files,
        input_image,
        prefix_pattern,
        session_id,
        inject_image=True,
        inject_prefix=True,
    ):
        self.injected_input = input_image
        return [(name, {"1": {"inputs": {"image": input_image}}}, "pref") for name in workflow_names]

    def inject_io(self, workflow, input_image, output_prefix, inject_image=True, inject_prefix=True):
        payload = dict(workflow)
        payload["uploaded"] = input_image
        return payload


class FakeFileManager:
    def __init__(self) -> None:
        self.cleared = False
        self.deleted = False
        self.staged_name = ""

    def stage_for_comfy_inputs(self, input_path: Path, input_folders: list[Path], fixed_filename: str | None = None):
        self.staged_name = fixed_filename or input_path.name
        for folder in input_folders:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / self.staged_name).write_bytes(input_path.read_bytes())
        return self.staged_name

    def create_session_dir(self, session_id: str) -> Path:
        path = Path("/tmp") / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copy_to_latest(self, source_paths):
        return [Path("/tmp/latest_1.png")]

    def clear_comfy_input_images(self):
        self.cleared = True

    def clear_staged_comfy_inputs(self, input_folders: list[Path], filename: str):
        self.deleted = True


def test_generation_service_uses_folder_staging_and_clears_input_on_success(tmp_path: Path) -> None:
    input_path = tmp_path / "session_input.jpg"
    input_path.write_bytes(b"data")
    output_dir = tmp_path / "comfy_output"
    output_dir.mkdir(parents=True)
    input_dir = tmp_path / "comfy_input"
    input_dir.mkdir(parents=True)

    session = SessionRecord(session_id="session_1", archive_dir=tmp_path, processed_input_path=input_path)
    client = FakeClient(output_dir=output_dir)
    loader = FakeLoader()
    file_manager = FakeFileManager()
    service = GenerationService(client=client, loader=loader, file_manager=file_manager)

    settings = {
        "workflows": {
            "enabled": ["mona_lisa"],
            "files": {
                "mona_lisa": "workflows/mona_lisa.json",
                "pearl_earring": "workflows/pearl_earring.json",
                "girl_with_hat": "workflows/girl_with_hat.json",
                "american_gothic": "workflows/american_gothic.json",
                "pop_art_portrait": "workflows/pop_art_portrait.json",
            },
        },
        "comfy": {
            "input_folders": [str(input_dir)],
            "output_folders": [str(output_dir)],
            "fixed_input_filename": "input.jpg",
            "delete_inputs_after_success": True,
            "inject_input_filename": False,
            "inject_output_prefix": False,
            "output_filename_prefix_pattern": "{session_id}_{workflow}",
            "generation_timeout_seconds": 1,
            "poll_interval_seconds": 0.1,
            "expected_output_count": 1,
        },
    }

    outputs = service.run_for_session(session, settings)

    assert client.ran is True
    assert file_manager.staged_name == "input.jpg"
    assert loader.injected_input == ""
    assert outputs[0].name == "latest_1.png"
    assert file_manager.cleared is True
    assert file_manager.deleted is True


def test_generation_service_retries_with_upload_when_comfy_cannot_read_staged_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "comfy_output"
    output_dir.mkdir(parents=True)
    input_path = tmp_path / "session_input.jpg"
    input_path.write_bytes(b"data")

    class RetryClient(FakeClient):
        def __init__(self, output_dir: Path) -> None:
            super().__init__(output_dir)
            self.calls = 0

        def run_workflow(self, workflow_payload):
            self.calls += 1
            if self.calls == 1:
                from app.comfy.comfy_client import ComfyClientError

                raise ComfyClientError("POST /prompt failed: HTTP 400: image - Invalid image file: input.jpg")
            return super().run_workflow(workflow_payload)

    session = SessionRecord(session_id="session_2", archive_dir=tmp_path, processed_input_path=input_path)
    service = GenerationService(client=RetryClient(output_dir), loader=FakeLoader(), file_manager=FakeFileManager())
    settings = {
        "workflows": {"enabled": ["mona_lisa"], "files": {"mona_lisa": "workflows/mona_lisa.json"}},
        "comfy": {
            "input_folders": [str(tmp_path / "comfy_input")],
            "output_folders": [str(output_dir)],
            "fixed_input_filename": "input.jpg",
            "delete_inputs_after_success": True,
            "inject_input_filename": False,
            "inject_output_prefix": False,
            "output_filename_prefix_pattern": "{session_id}_{workflow}",
            "generation_timeout_seconds": 1,
            "poll_interval_seconds": 0.1,
            "expected_output_count": 1,
        },
    }
    outputs = service.run_for_session(session, settings)
    assert outputs[0].name == "latest_1.png"
