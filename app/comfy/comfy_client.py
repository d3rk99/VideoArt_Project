"""ComfyUI API client (Phase 2 integration)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
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

    def _read_http_error(self, exc: HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        return f"HTTP {exc.code}: {body or exc.reason}"

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise ComfyClientError(f"GET {path} failed: {self._read_http_error(exc)}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
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
        except HTTPError as exc:
            raise ComfyClientError(f"POST {path} failed: {self._read_http_error(exc)}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ComfyClientError(f"POST {path} failed: {exc}") from exc

    def _get_bytes(self, path: str, params: dict[str, str]) -> bytes:
        query = urlencode(params)
        try:
            with urlopen(f"{self.base_url}{path}?{query}", timeout=self.timeout_seconds) as resp:
                return resp.read()
        except HTTPError as exc:
            raise ComfyClientError(f"GET {path} failed: {self._read_http_error(exc)}") from exc
        except (URLError, TimeoutError) as exc:
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
        return self.run_workflow(workflow_payload)

    def run_workflow(self, workflow_payload: dict[str, Any], client_id: str | None = None) -> str:
        payload: dict[str, Any] = {"prompt": workflow_payload}
        if client_id:
            payload["client_id"] = client_id
        try:
            response = self._post_json("/prompt", payload)
        except ComfyClientError as exc:
            # Some ComfyUI deployments expose API routes under /api/*.
            if "HTTP 404" not in str(exc):
                raise
            response = self._post_json("/api/prompt", payload)
        prompt_id = str(response.get("prompt_id", "")).strip()
        if not prompt_id:
            raise ComfyClientError("ComfyUI response missing prompt_id")
        self.logger.info("Triggered ComfyUI run workflow", extra={"prompt_id": prompt_id})
        return prompt_id

    def upload_input_image(self, local_path: Path) -> str:
        if not local_path.exists():
            raise ComfyClientError(f"Input file missing: {local_path}")
        boundary = f"----comfyupload{uuid4().hex}"
        image_bytes = local_path.read_bytes()
        parts = [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                'Content-Disposition: form-data; name="image"; '
                f'filename="{local_path.name}"\r\n'
            ).encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            image_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
        body = b"".join(parts)
        request = Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise ComfyClientError(f"POST /upload/image failed: {self._read_http_error(exc)}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ComfyClientError(f"POST /upload/image failed: {exc}") from exc

        uploaded_name = str(payload.get("name", "")).strip()
        if not uploaded_name:
            raise ComfyClientError("POST /upload/image response missing uploaded filename")
        return uploaded_name

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
