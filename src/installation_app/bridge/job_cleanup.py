from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from installation_app.cleanup import CleanupManager
from installation_app.config import BridgeConfig, CleanupConfig

from .job_store import JobStatus, JobStore


class JobCleanupManager:
    def __init__(
        self,
        job_store: JobStore,
        bridge_config: BridgeConfig,
        cleanup_config: CleanupConfig,
        logger,
    ) -> None:
        self.job_store = job_store
        self.logger = logger
        self.ttl = timedelta(minutes=bridge_config.result_ttl_minutes)
        self.cleanup = CleanupManager(cleanup_config, logger)
        self._stop = Event()
        self._thread = Thread(target=self._run, name="bridge-job-cleanup", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def cleanup_job(self, job_id: str, reason: str) -> bool:
        try:
            record = self.job_store.get(job_id)
        except KeyError:
            return False
        if record.status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMED_OUT}:
            raise RuntimeError(f"Job {job_id} is not finished yet (status={record.status.value})")
        self.job_store.delete(job_id)
        if record.source_output_files:
            self.cleanup.delete_files(
                record.source_output_files,
                delay_ms=0,
                label=f"bridge_output_{job_id}",
            )
        if record.upload_path and record.upload_path.exists():
            try:
                record.upload_path.unlink()
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.warning("Failed to remove upload for %s: %s", job_id, exc)
        if record.job_dir.exists():
            shutil.rmtree(record.job_dir, ignore_errors=True)
        self.logger.info("Bridge job %s artifacts cleaned (%s)", job_id, reason)
        return True

    def _run(self) -> None:
        while not self._stop.wait(30):
            now = datetime.now(timezone.utc)
            for job_id in list(self.job_store.list_job_ids()):
                try:
                    record = self.job_store.get(job_id)
                except KeyError:
                    continue
                if record.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMED_OUT}:
                    if now - record.updated_at > self.ttl:
                        self.cleanup_job(job_id, "ttl_expired")
