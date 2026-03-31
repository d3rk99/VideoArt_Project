"""ComfyUI API client (Phase 2 integration scaffold)."""

from __future__ import annotations

import logging
from typing import Any

import requests


class ComfyClient:
    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

    def healthcheck(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/system_stats", timeout=self.timeout_seconds)
            return resp.ok
        except requests.RequestException:
            return False

    def submit_workflow(self, prompt: dict[str, Any]) -> str:
        resp = requests.post(f"{self.base_url}/prompt", json={"prompt": prompt}, timeout=self.timeout_seconds)
        resp.raise_for_status()
        prompt_id = resp.json().get("prompt_id", "")
        self.logger.info("Submitted workflow prompt_id=%s", prompt_id)
        return prompt_id
