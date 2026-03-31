"""OBS websocket client wrapper (Phase 3 integration scaffold)."""

from __future__ import annotations

import logging


class OBSClient:
    def __init__(self, host: str, port: int, password: str) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        self.logger.info("OBS connection check stub host=%s port=%s", self.host, self.port)
        return True

    def switch_scene(self, scene_name: str) -> None:
        self.logger.info("OBS switch scene: %s", scene_name)
