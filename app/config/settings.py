"""Configuration loading from YAML + environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_settings(path: Path) -> dict[str, Any]:
    load_dotenv()
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _resolve_env(raw)
