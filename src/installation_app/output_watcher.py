from __future__ import annotations

import time
from pathlib import Path


class OutputWatcher:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def snapshot(self) -> set[Path]:
        return {p for p in self.output_dir.iterdir() if p.is_file()}

    def wait_for_new_files(
        self,
        baseline: set[Path],
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> list[Path]:
        start = time.monotonic()
        while True:
            current = self.snapshot()
            new_files = sorted(current - baseline, key=lambda p: p.stat().st_mtime)
            if new_files:
                return new_files

            if time.monotonic() - start > timeout_seconds:
                raise TimeoutError("No new output files were detected before timeout")

            time.sleep(poll_interval_seconds)
