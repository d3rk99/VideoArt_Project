from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError


@dataclass(frozen=True)
class CameraConfig:
    primary_index: int
    indices: list[int]
    frame_width: int
    frame_height: int
    preview_enabled: bool
    scan_max_index: int
    face_stability_seconds: float
    min_face_area_ratio: float
    capture_cooldown_seconds: float
    backend: str
    read_retry_count: int
    read_retry_delay_ms: int
    reconnect_on_read_failure: bool
    black_frame_luma_threshold: float
    black_frame_max_consecutive: int


@dataclass(frozen=True)
class FolderConfig:
    capture_input_dir: Path
    comfy_output_dir: Path
    archive_dir: Path


@dataclass(frozen=True)
class ComfyUIConfig:
    server_url: str
    workflow_file: Path
    poll_interval_seconds: float
    completion_timeout_seconds: float


@dataclass(frozen=True)
class OBSConfig:
    enabled: bool
    host: str
    port: int
    password: str
    target_scene: str
    transition_name: str
    transition_duration_ms: int
    image_sources: list[str]


@dataclass(frozen=True)
class CleanupConfig:
    cleanup_input_after_comfy: bool
    cleanup_output_after_obs: bool
    input_cleanup_delay_ms: int
    output_cleanup_delay_ms: int
    cleanup_retry_count: int
    cleanup_retry_delay_ms: int
    allow_full_folder_cleanup: bool


@dataclass(frozen=True)
class AppConfig:
    debug_logging: bool
    auto_cleanup_old_files: bool
    manual_override_key: str
    quit_key: str
    idle_reset_seconds: float
    allow_concurrent_jobs: bool
    comfy_error_backoff_seconds: float
    comfy_error_backoff_max_seconds: float


@dataclass(frozen=True)
class Config:
    camera: CameraConfig
    folders: FolderConfig
    comfyui: ComfyUIConfig
    obs: OBSConfig
    cleanup: CleanupConfig
    app: AppConfig


class ConfigError(ValueError):
    pass


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        raise ConfigError(f"Missing '{key}' in '{section_name}' section")
    return section[key]


def _parse_config(raw: dict[str, Any]) -> Config:
    camera_raw = _require(raw, "camera", "root")
    folders_raw = _require(raw, "folders", "root")
    comfy_raw = _require(raw, "comfyui", "root")
    obs_raw = _require(raw, "obs", "root")
    cleanup_raw = _require(raw, "cleanup", "root")
    app_raw = _require(raw, "app", "root")

    camera = CameraConfig(
        primary_index=int(_require(camera_raw, "primary_index", "camera")),
        indices=[int(i) for i in camera_raw.get("indices", [_require(camera_raw, "primary_index", "camera")])],
        frame_width=int(_require(camera_raw, "frame_width", "camera")),
        frame_height=int(_require(camera_raw, "frame_height", "camera")),
        preview_enabled=bool(_require(camera_raw, "preview_enabled", "camera")),
        scan_max_index=int(camera_raw.get("scan_max_index", 6)),
        face_stability_seconds=float(_require(camera_raw, "face_stability_seconds", "camera")),
        min_face_area_ratio=float(_require(camera_raw, "min_face_area_ratio", "camera")),
        capture_cooldown_seconds=float(_require(camera_raw, "capture_cooldown_seconds", "camera")),
        backend=str(camera_raw.get("backend", "auto")).lower(),
        read_retry_count=int(camera_raw.get("read_retry_count", 3)),
        read_retry_delay_ms=int(camera_raw.get("read_retry_delay_ms", 120)),
        reconnect_on_read_failure=bool(camera_raw.get("reconnect_on_read_failure", True)),
        black_frame_luma_threshold=float(camera_raw.get("black_frame_luma_threshold", 8.0)),
        black_frame_max_consecutive=int(camera_raw.get("black_frame_max_consecutive", 10)),
    )
    if camera.backend not in {"auto", "dshow", "msmf"}:
        raise ConfigError("camera.backend must be one of: auto, dshow, msmf")
    if camera.black_frame_max_consecutive < 1:
        raise ConfigError("camera.black_frame_max_consecutive must be >= 1")

    folders = FolderConfig(
        capture_input_dir=Path(_require(folders_raw, "capture_input_dir", "folders")).expanduser(),
        comfy_output_dir=Path(_require(folders_raw, "comfy_output_dir", "folders")).expanduser(),
        archive_dir=Path(_require(folders_raw, "archive_dir", "folders")).expanduser(),
    )

    comfy = ComfyUIConfig(
        server_url=str(_require(comfy_raw, "server_url", "comfyui")).rstrip("/"),
        workflow_file=Path(_require(comfy_raw, "workflow_file", "comfyui")).expanduser(),
        poll_interval_seconds=float(_require(comfy_raw, "poll_interval_seconds", "comfyui")),
        completion_timeout_seconds=float(_require(comfy_raw, "completion_timeout_seconds", "comfyui")),
    )

    obs = OBSConfig(
        enabled=bool(_require(obs_raw, "enabled", "obs")),
        host=str(_require(obs_raw, "host", "obs")),
        port=int(_require(obs_raw, "port", "obs")),
        password=str(obs_raw.get("password", "")),
        target_scene=str(_require(obs_raw, "target_scene", "obs")),
        transition_name=str(_require(obs_raw, "transition_name", "obs")),
        transition_duration_ms=int(_require(obs_raw, "transition_duration_ms", "obs")),
        image_sources=[str(v) for v in _require(obs_raw, "image_sources", "obs")],
    )

    cleanup = CleanupConfig(
        cleanup_input_after_comfy=bool(_require(cleanup_raw, "cleanup_input_after_comfy", "cleanup")),
        cleanup_output_after_obs=bool(_require(cleanup_raw, "cleanup_output_after_obs", "cleanup")),
        input_cleanup_delay_ms=int(_require(cleanup_raw, "input_cleanup_delay_ms", "cleanup")),
        output_cleanup_delay_ms=int(_require(cleanup_raw, "output_cleanup_delay_ms", "cleanup")),
        cleanup_retry_count=int(_require(cleanup_raw, "cleanup_retry_count", "cleanup")),
        cleanup_retry_delay_ms=int(_require(cleanup_raw, "cleanup_retry_delay_ms", "cleanup")),
        allow_full_folder_cleanup=bool(_require(cleanup_raw, "allow_full_folder_cleanup", "cleanup")),
    )

    app = AppConfig(
        debug_logging=bool(_require(app_raw, "debug_logging", "app")),
        auto_cleanup_old_files=bool(_require(app_raw, "auto_cleanup_old_files", "app")),
        manual_override_key=str(_require(app_raw, "manual_override_key", "app")),
        quit_key=str(_require(app_raw, "quit_key", "app")),
        idle_reset_seconds=float(_require(app_raw, "idle_reset_seconds", "app")),
        allow_concurrent_jobs=bool(_require(app_raw, "allow_concurrent_jobs", "app")),
        comfy_error_backoff_seconds=float(app_raw.get("comfy_error_backoff_seconds", 15.0)),
        comfy_error_backoff_max_seconds=float(app_raw.get("comfy_error_backoff_max_seconds", 300.0)),
    )

    if not comfy.workflow_file.exists():
        raise ConfigError(f"ComfyUI workflow file not found: {comfy.workflow_file}")

    return Config(camera=camera, folders=folders, comfyui=comfy, obs=obs, cleanup=cleanup, app=app)


def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except YAMLError as exc:
        raise ConfigError(
            "Invalid YAML in config file. On Windows, avoid double-quoted paths with backslashes "
            "(e.g. 'C:/path/to/dir' or 'C:\\\\path\\\\to\\\\dir') unless escaped; "
            "prefer forward slashes or single-quoted backslash paths. "
            f"Original parser error: {exc}"
        ) from exc

    config = _parse_config(raw)
    config.folders.capture_input_dir.mkdir(parents=True, exist_ok=True)
    config.folders.comfy_output_dir.mkdir(parents=True, exist_ok=True)
    config.folders.archive_dir.mkdir(parents=True, exist_ok=True)

    return config
