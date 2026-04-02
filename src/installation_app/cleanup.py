from __future__ import annotations

import time
from pathlib import Path

from installation_app.config import CleanupConfig


class CleanupManager:
    def __init__(self, config: CleanupConfig, logger) -> None:
        self.config = config
        self.logger = logger

    def delete_files(self, files: list[Path], delay_ms: int, label: str) -> None:
        if not files:
            return

        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

        for file_path in files:
            self._delete_with_retry(file_path, label)

    def _delete_with_retry(self, file_path: Path, label: str) -> None:
        for attempt in range(1, self.config.cleanup_retry_count + 2):
            try:
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    self.logger.info("Deleted %s file: %s", label, file_path)
                return
            except Exception as exc:  # pylint: disable=broad-except
                if attempt > self.config.cleanup_retry_count:
                    self.logger.error(
                        "Failed to delete %s file after %s attempts: %s (%s)",
                        label,
                        attempt,
                        file_path,
                        exc,
                    )
                    return

                self.logger.warning(
                    "Retry delete %s file (attempt %s): %s (%s)",
                    label,
                    attempt,
                    file_path,
                    exc,
                )
                time.sleep(self.config.cleanup_retry_delay_ms / 1000)
