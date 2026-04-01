"""Logging utilities for the AI Portrait Gallery."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path, debug: bool = False) -> None:
    """Configure console and file logging once for the app."""
    log_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(file_handler)
