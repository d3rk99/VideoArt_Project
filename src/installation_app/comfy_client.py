from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from requests import HTTPError

from installation_app.config import ComfyUIConfig


class ComfyUIClient:
    def __init__(self, config: ComfyUIConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def health_check(self, timeout: float = 3.0) -> bool:
        resp = self.session.get(f"{self.config.server_url}/system_stats", timeout=timeout)
        resp.raise_for_status()
        return True

    def _load_prompt_payload(self) -> dict[str, Any]:
        with self.config.workflow_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        if "prompt" in payload:
            return payload

        return {"prompt": payload}

    def queue_prompt(self, client_id: str) -> str:
        payload = self._load_prompt_payload()
        payload["client_id"] = client_id

        resp = self.session.post(f"{self.config.server_url}/prompt", json=payload, timeout=10)
        try:
            resp.raise_for_status()
        except HTTPError as exc:
            raise RuntimeError(self._format_prompt_error(resp)) from exc
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI response missing prompt_id: {data}")
        return str(prompt_id)

    def _format_prompt_error(self, resp: requests.Response) -> str:
        body = resp.text.strip()
        default_detail = body[:400] if body else "<empty response>"

        try:
            payload = resp.json()
        except ValueError:
            return f"ComfyUI /prompt failed with HTTP {resp.status_code}. Response: {default_detail}"

        error_block = payload.get("error", {}) if isinstance(payload, dict) else {}
        error_message = error_block.get("message") if isinstance(error_block, dict) else None
        node_errors = payload.get("node_errors", {}) if isinstance(payload, dict) else {}

        if isinstance(node_errors, dict) and node_errors:
            first_node_id, first_node_data = next(iter(node_errors.items()))
            errors = first_node_data.get("errors", []) if isinstance(first_node_data, dict) else []
            if errors and isinstance(errors[0], dict):
                first_error = errors[0]
                detail = str(first_error.get("details", "")).strip()
                message = str(first_error.get("message", "")).strip()
                combined = detail or message or "unknown validation error"
                return (
                    f"ComfyUI /prompt failed with HTTP {resp.status_code}. "
                    f"Workflow validation failed at node {first_node_id}: {combined}"
                )

        if error_message:
            return (
                f"ComfyUI /prompt failed with HTTP {resp.status_code}. "
                f"Error: {error_message}"
            )

        return f"ComfyUI /prompt failed with HTTP {resp.status_code}. Response: {default_detail}"

    def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        start = time.monotonic()
        history_url = f"{self.config.server_url}/history/{prompt_id}"

        while True:
            if time.monotonic() - start > self.config.completion_timeout_seconds:
                raise TimeoutError(f"ComfyUI run timed out for prompt_id={prompt_id}")

            resp = self.session.get(history_url, timeout=10)
            resp.raise_for_status()
            history = resp.json()
            if prompt_id in history:
                return history[prompt_id]

            time.sleep(self.config.poll_interval_seconds)

    def shutdown(self) -> None:
        self.session.close()
