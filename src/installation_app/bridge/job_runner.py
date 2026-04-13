from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from installation_app.cleanup import CleanupManager
from installation_app.comfy_client import ComfyUIClient
from installation_app.config import Config
from installation_app.output_watcher import OutputWatcher

from .job_store import JobRecord, JobStatus, JobStore


class JobRunner:
    def __init__(self, config: Config, job_store: JobStore, logger) -> None:
        self.config = config
        self.job_store = job_store
        self.logger = logger
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.output_watcher = OutputWatcher(config.folders.comfy_output_dir)
        self.cleanup = CleanupManager(config.cleanup, logger)
        self.comfy_client = ComfyUIClient(config.comfyui)

    def enqueue(self, job_id: str) -> None:
        self.executor.submit(self._execute_job, job_id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)
        self.comfy_client.shutdown()

    def _execute_job(self, job_id: str) -> None:
        self.logger.info("Starting bridge job %s", job_id)
        self.job_store.set_status(job_id, JobStatus.RUNNING)
        try:
            record = self.job_store.get(job_id)
            result_files, source_files = self._run_job(record)
            self.job_store.update(
                job_id,
                result_files=result_files,
                source_output_files=source_files,
            )
            self.job_store.set_status(job_id, JobStatus.COMPLETED)
            self.logger.info("Bridge job %s completed", job_id)
        except TimeoutError as exc:
            self.logger.error("Bridge job %s timed out: %s", job_id, exc)
            self.job_store.set_status(job_id, JobStatus.TIMED_OUT, str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Bridge job %s failed: %s", job_id, exc)
            self.job_store.set_status(job_id, JobStatus.FAILED, str(exc))

    def _run_job(self, record: JobRecord) -> tuple[list[Path], list[Path]]:
        if not record.upload_path or not record.upload_path.exists():
            raise RuntimeError(f"Upload for job {record.job_id} is missing")

        comfy_input = self._write_comfy_input(record)
        self.job_store.update(record.job_id, comfy_input_path=comfy_input)

        baseline = self.output_watcher.snapshot()
        prompt_id = self.comfy_client.queue_prompt(client_id=record.job_id)
        self.logger.info("Queued ComfyUI prompt_id=%s for job %s", prompt_id, record.job_id)
        self.job_store.update(record.job_id, comfy_prompt_id=prompt_id)

        self.comfy_client.wait_for_completion(prompt_id)
        self.logger.info("ComfyUI prompt %s completed", prompt_id)

        new_files = self.output_watcher.wait_for_new_files(
            baseline=baseline,
            timeout_seconds=self.config.comfyui.completion_timeout_seconds,
            poll_interval_seconds=self.config.comfyui.poll_interval_seconds,
        )
        if len(new_files) < self.config.bridge.expected_output_count:
            raise RuntimeError(
                f"Bridge job {record.job_id} expected {self.config.bridge.expected_output_count} outputs "
                f"but received {len(new_files)}"
            )
        source_subset = new_files[: self.config.bridge.expected_output_count]
        result_files = self._copy_results(record, source_subset)

        if self.config.cleanup.cleanup_input_after_comfy and comfy_input.exists():
            self.cleanup.delete_files(
                [comfy_input],
                delay_ms=self.config.cleanup.input_cleanup_delay_ms,
                label="bridge_input",
            )
            self.job_store.update(record.job_id, comfy_input_path=None)

        return result_files, source_subset

    def _write_comfy_input(self, record: JobRecord) -> Path:
        run_id = record.run_id or record.job_id
        filename_template = self.config.folders.capture_input_filename
        filename = filename_template.replace("{run_id}", run_id)
        destination = self.config.folders.capture_input_dir / filename
        shutil.copy2(record.upload_path, destination)
        self.logger.info("Copied job %s capture to %s", record.job_id, destination)
        return destination

    def _copy_results(self, record: JobRecord, source_files: Iterable[Path]) -> list[Path]:
        if not record.result_dir:
            raise RuntimeError("Job result directory not initialized")
        result_paths: list[Path] = []
        for idx, path in enumerate(source_files, start=1):
            target = record.result_dir / f"{idx:02d}_{path.name}"
            shutil.copy2(path, target)
            result_paths.append(target)
        self.logger.info("Job %s copied %s outputs into %s", record.job_id, len(result_paths), record.result_dir)
        return result_paths
