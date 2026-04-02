from __future__ import annotations

from pathlib import Path

from obsws_python import ReqClient

from installation_app.config import OBSConfig


class OBSClient:
    def __init__(self, config: OBSConfig) -> None:
        self.config = config
        self.client: ReqClient | None = None

    def connect(self, timeout: int = 3) -> None:
        self.client = ReqClient(
            host=self.config.host,
            port=self.config.port,
            password=self.config.password,
            timeout=timeout,
        )

    def health_check(self) -> bool:
        if not self.client:
            raise RuntimeError("OBS client is not connected")
        self.client.get_version()
        return True

    def update_image_sources(self, image_paths: list[Path]) -> list[tuple[str, Path]]:
        if not self.client:
            raise RuntimeError("OBS client is not connected")

        if not image_paths:
            raise ValueError("No image paths supplied for OBS update")

        self._validate_sources_in_scene(self.config.staging_scene, self.config.image_sources)
        assignments: list[tuple[str, Path]] = []
        for idx, source_name in enumerate(self.config.image_sources):
            image_path = image_paths[min(idx, len(image_paths) - 1)]
            self.client.set_input_settings(
                name=source_name,
                settings={"file": str(image_path.resolve())},
                overlay=True,
            )
            assignments.append((source_name, image_path))
        return assignments

    def _validate_sources_in_scene(self, scene_name: str, source_names: list[str]) -> None:
        if not self.client:
            raise RuntimeError("OBS client is not connected")
        scene_items = self.client.get_scene_item_list(scene_name).scene_items
        present = {item.get("sourceName") for item in scene_items}
        missing = [name for name in source_names if name not in present]
        if missing:
            raise RuntimeError(f"Missing expected sources in scene '{scene_name}': {missing}")

    def set_preview_scene(self, scene_name: str) -> None:
        if not self.client:
            raise RuntimeError("OBS client is not connected")
        self.client.set_current_preview_scene(scene_name)

    def trigger_transition(self) -> None:
        if not self.client:
            raise RuntimeError("OBS client is not connected")

        self.client.set_current_scene_transition(self.config.transition_name)
        self.client.set_current_scene_transition_duration(self.config.transition_duration_ms)
        try:
            self.client.trigger_studio_mode_transition()
        except Exception:  # pylint: disable=broad-except
            # Fallback for non-studio mode environments.
            self.client.set_current_program_scene(self.config.target_scene)

    def disconnect(self) -> None:
        self.client = None
