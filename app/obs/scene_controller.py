"""Scene flow helpers for OBS transitions."""

from __future__ import annotations

from app.obs.obs_client import OBSClient


class SceneController:
    def __init__(self, obs_client: OBSClient, scenes: dict[str, str]) -> None:
        self.obs_client = obs_client
        self.scenes = scenes

    def go_idle(self) -> None:
        self.obs_client.switch_scene(self.scenes["idle"])

    def go_capture(self) -> None:
        self.obs_client.switch_scene(self.scenes["capture"])

    def go_processing(self) -> None:
        self.obs_client.switch_scene(self.scenes["processing"])

    def go_reveal(self) -> None:
        self.obs_client.switch_scene(self.scenes["reveal"])
