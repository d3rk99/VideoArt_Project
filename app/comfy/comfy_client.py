"""ComfyUI API client (Phase 2 integration)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ComfyClientError(RuntimeError):
    """Raised when ComfyUI API requests fail."""


class ComfyTimeoutError(TimeoutError):
    """Raised when generation does not complete in time."""


@dataclass
class ComfyImageRef:
    filename: str
    subfolder: str
    type: str = "output"


@dataclass
class ComfyPromptResult:
    prompt_id: str
    history_payload: dict[str, Any]


class ComfyClient:
    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ComfyClientError(
                f"Invalid ComfyUI base URL '{base_url}'. "
                "Set COMFYUI_BASE_URL (for example: http://127.0.0.1:8188)."
            )
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ComfyClientError(f"GET {path} failed: {exc}") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ComfyClientError(f"POST {path} failed: {exc}") from exc

    def _get_bytes(self, path: str, params: dict[str, str]) -> bytes:
        query = urlencode(params)
        try:
            with urlopen(f"{self.base_url}{path}?{query}", timeout=self.timeout_seconds) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ComfyClientError(f"GET {path} failed: {exc}") from exc

    def healthcheck(self) -> bool:
        self.logger.info("ComfyUI healthcheck started", extra={"base_url": self.base_url})
        try:
            self._get_json("/system_stats")
            self.logger.info("ComfyUI healthcheck finished", extra={"ok": True})
            return True
        except ComfyClientError as exc:
            self.logger.error("ComfyUI healthcheck failed: %s", exc)
            return False

    def submit_workflow(self, workflow_payload: dict[str, Any]) -> str:
        response = self._post_json("/prompt", {"prompt": workflow_payload})
        prompt_id = str(response.get("prompt_id", "")).strip()
        if not prompt_id:
            raise ComfyClientError("ComfyUI response missing prompt_id")
        self.logger.info("Submitted workflow", extra={"prompt_id": prompt_id})
        return prompt_id

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        return self._get_json(f"/history/{prompt_id}")

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> ComfyPromptResult:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            history = self.get_history(prompt_id)
            prompt_history = history.get(prompt_id)
            if prompt_history:
                status = prompt_history.get("status", {})
                status_str = status.get("status_str", "")
                if status_str and status_str not in {"success", "completed"}:
                    raise ComfyClientError(f"Prompt {prompt_id} failed with status: {status_str}")
                self.logger.info("Prompt completed", extra={"prompt_id": prompt_id})
                return ComfyPromptResult(prompt_id=prompt_id, history_payload=prompt_history)
            time.sleep(max(poll_interval_seconds, 0.1))
        raise ComfyTimeoutError(f"Timed out waiting for prompt {prompt_id} after {timeout_seconds} seconds")

    def extract_output_paths(self, history_payload: dict[str, Any]) -> list[ComfyImageRef]:
        outputs = history_payload.get("outputs", {})
        image_refs: list[ComfyImageRef] = []
        for node_payload in outputs.values():
            for image in node_payload.get("images", []):
                filename = image.get("filename")
                if not filename:
                    continue
                image_refs.append(
                    ComfyImageRef(
                        filename=filename,
                        subfolder=image.get("subfolder", ""),
                        type=image.get("type", "output"),
                    )
                )
        return image_refs

    def download_output(self, image_ref: ComfyImageRef) -> bytes:
        params = {
            "filename": image_ref.filename,
            "subfolder": image_ref.subfolder,
            "type": image_ref.type,
        }
        return self._get_bytes("/view", params)
