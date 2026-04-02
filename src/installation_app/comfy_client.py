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
            body = resp.text.strip()
            detail = body[:400] if body else "<empty response>"
            raise RuntimeError(
                f"ComfyUI /prompt failed with HTTP {resp.status_code}. "
                f"Response: {detail}"
            ) from exc
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI response missing prompt_id: {data}")
        return str(prompt_id)

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
