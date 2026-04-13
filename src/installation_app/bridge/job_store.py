from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class JobRecord:
    job_id: str
    job_dir: Path
    status: JobStatus = JobStatus.QUEUED
    run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    upload_path: Path | None = None
    comfy_input_path: Path | None = None
    comfy_prompt_id: str | None = None
    result_dir: Path | None = None
    result_files: list[Path] = field(default_factory=list)
    source_output_files: list[Path] = field(default_factory=list)
    error_message: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "prompt_id": self.comfy_prompt_id,
            "result_files": [str(p.name) for p in self.result_files],
            "error_message": self.error_message,
        }


class JobStore:
    def __init__(self, jobs_root: Path) -> None:
        self.jobs_root = jobs_root
        self._records: dict[str, JobRecord] = {}
        self._lock = RLock()

    def create_job(self, job_id: str, run_id: str | None) -> JobRecord:
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        record = JobRecord(
            job_id=job_id,
            job_dir=job_dir,
            run_id=run_id,
            result_dir=job_dir / "results",
        )
        record.result_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._records[job_id] = record
            self._write_manifest(record)
        return record

    def get(self, job_id: str) -> JobRecord:
        with self._lock:
            if job_id not in self._records:
                raise KeyError(job_id)
            return self._records[job_id]

    def update(self, job_id: str, **fields: Any) -> JobRecord:
        with self._lock:
            record = self.get(job_id)
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc)
            self._write_manifest(record)
            return record

    def set_status(self, job_id: str, status: JobStatus, error: str | None = None) -> JobRecord:
        return self.update(job_id, status=status, error_message=error)

    def delete(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._records.pop(job_id, None)
            if record:
                manifest = self._manifest_path(record)
                if manifest.exists():
                    manifest.unlink()
        return record

    def list_job_ids(self) -> list[str]:
        with self._lock:
            return list(self._records.keys())

    def _manifest_path(self, record: JobRecord) -> Path:
        return record.job_dir / "job.json"

    def _write_manifest(self, record: JobRecord) -> None:
        payload = {
            **record.to_payload(),
            "upload_path": str(record.upload_path) if record.upload_path else None,
            "comfy_input_path": str(record.comfy_input_path) if record.comfy_input_path else None,
            "result_dir": str(record.result_dir) if record.result_dir else None,
            "source_output_files": [str(p) for p in record.source_output_files],
        }
        with self._manifest_path(record).open("w", encoding="utf-8") as fout:
            json.dump(payload, fout, indent=2)
