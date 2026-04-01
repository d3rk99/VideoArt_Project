import pytest

from app.comfy.comfy_client import ComfyClient, ComfyClientError, ComfyTimeoutError


def test_invalid_base_url_raises() -> None:
    with pytest.raises(ComfyClientError):
        ComfyClient("")


def test_extract_output_paths() -> None:
    client = ComfyClient("http://localhost:8188")
    history_payload = {
        "outputs": {
            "9": {
                "images": [
                    {"filename": "a.png", "subfolder": "", "type": "output"},
                    {"filename": "b.png", "subfolder": "x", "type": "output"},
                ]
            }
        }
    }
    refs = client.extract_output_paths(history_payload)
    assert [r.filename for r in refs] == ["a.png", "b.png"]


def test_wait_for_completion_times_out(monkeypatch) -> None:
    client = ComfyClient("http://localhost:8188")

    def fake_get_history(prompt_id: str):
        return {}

    monkeypatch.setattr(client, "get_history", fake_get_history)

    with pytest.raises(ComfyTimeoutError):
        client.wait_for_completion("abc", timeout_seconds=0.15, poll_interval_seconds=0.05)


def test_submit_workflow_returns_prompt_id(monkeypatch) -> None:
    client = ComfyClient("http://localhost:8188")

    def fake_post_json(path: str, payload: dict):
        return {"prompt_id": "prompt-1"}

    monkeypatch.setattr(client, "_post_json", fake_post_json)
    assert client.submit_workflow({"1": {"inputs": {}}}) == "prompt-1"


def test_run_workflow_falls_back_to_api_prefix_on_404(monkeypatch) -> None:
    client = ComfyClient("http://localhost:8188")
    calls: list[str] = []

    def fake_post_json(path: str, payload: dict):
        calls.append(path)
        if path == "/prompt":
            raise ComfyClientError("POST /prompt failed: HTTP 404: not found")
        return {"prompt_id": "prompt-2"}

    monkeypatch.setattr(client, "_post_json", fake_post_json)
    assert client.run_workflow({"1": {"inputs": {}}}) == "prompt-2"
    assert calls == ["/prompt", "/api/prompt"]


def test_upload_input_image_returns_uploaded_name(tmp_path, monkeypatch) -> None:
    client = ComfyClient("http://localhost:8188")
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"data")

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"name":"uploaded.png"}'

    def fake_urlopen(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr("app.comfy.comfy_client.urlopen", fake_urlopen)
    assert client.upload_input_image(image_path) == "uploaded.png"
