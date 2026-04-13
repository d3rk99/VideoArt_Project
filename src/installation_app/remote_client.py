from __future__ import annotations

import io
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

import requests
from requests import Response

from installation_app.config import LocalPathsConfig, RemoteConfig


class RemoteBridgeError(RuntimeError):
    pass


class RemoteBridgeClient:
    def __init__(self, remote_config: RemoteConfig, paths: LocalPathsConfig, logger) -> None:
        self.config = remote_config
        self.paths = paths
        self.logger = logger
        self.session = requests.Session()
        if self.config.api_key:
            self.session.headers.update({"X-API-Key": self.config.api_key})

    def close(self) -> None:
        self.session.close()

    def _url(self, path: str) -> str:
        base = self.config.bridge_base_url.rstrip("/")
        return f"{base}{path}"

    def health_check(self) -> bool:
        self._request("GET", "/api/health")
        self._request("GET", "/api/health/comfy")
        return True

    def submit_job(self, image_path: Path, run_id: str) -> str:
        if not image_path.exists():
            raise RemoteBridgeError(f"Capture file not found: {image_path}")
        files = {
            "face_image": (image_path.name, image_path.open("rb"), "image/jpeg"),
        }
        data = {"run_id": run_id}
        try:
            response = self.session.post(
                self._url("/api/jobs"),
                files=files,
                data=data,
                timeout=self.config.request_timeout_seconds,
            )
        finally:
            files["face_image"][1].close()
        payload = self._parse_json(response)
        job_id = payload.get("job_id")
        if not job_id:
            raise RemoteBridgeError(f"Bridge /api/jobs response missing job_id: {payload}")
        self.logger.info("Uploaded capture to remote bridge job_id=%s", job_id)
        return str(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/api/jobs/{job_id}")
        return self._parse_json(response)

    def wait_for_completion(self, job_id: str, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_status = ""
        while True:
            job = self.get_job(job_id)
            status = str(job.get("status", "")).lower()
            if status != last_status:
                self.logger.info("Remote job %s status -> %s", job_id, status)
                last_status = status
            if status in {"completed", "failed", "timed_out"}:
                if status != "completed":
                    error = job.get("error_message") or f"Remote job {job_id} failed with status {status}"
                    raise RemoteBridgeError(error)
                return job
            if time.monotonic() > deadline:
                raise RemoteBridgeError(f"Remote job {job_id} timed out waiting for completion")
            time.sleep(self.config.poll_interval_seconds)

    def download_results(self, job_id: str, run_id: str) -> list[Path]:
        response = self._request("GET", f"/api/jobs/{job_id}/results")
        job_dir = self.paths.downloaded_results_dir / job_id
        self._reset_job_dir(job_dir)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archive.extractall(job_dir)
        files = sorted(job_dir.glob("*"))
        if not files:
            raise RemoteBridgeError(f"No result files downloaded for job {job_id}")
        self.logger.info("Downloaded %s remote outputs to %s", len(files), job_dir)
        return files

    def delete_job(self, job_id: str) -> None:
        try:
            self._request("DELETE", f"/api/jobs/{job_id}")
            self.logger.info("Requested remote cleanup for job %s", job_id)
        except RemoteBridgeError as exc:
            self.logger.warning("Remote job cleanup failed for %s: %s", job_id, exc)

    def _reset_job_dir(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)

    def _request(self, method: str, path: str) -> Response:
        response = self.session.request(
            method,
            self._url(path),
            timeout=self.config.request_timeout_seconds,
        )
        if response.status_code >= 400:
            detail = response.text[:400]
            raise RemoteBridgeError(f"Bridge request {method} {path} failed: HTTP {response.status_code} {detail}")
        return response

    def _parse_json(self, response: Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:  # pylint: disable=broad-except
            raise RemoteBridgeError(f"Bridge response was not valid JSON: {response.text[:200]}") from exc
