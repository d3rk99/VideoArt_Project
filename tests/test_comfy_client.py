import pytest

from app.comfy.comfy_client import ComfyClient, ComfyTimeoutError


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
