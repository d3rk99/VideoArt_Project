"""Camera manager for continuous frame acquisition with reconnect support."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class CameraConfig:
    index: int
    width: int
    height: int
    fps: int
    reconnect_attempts: int
    reconnect_delay_seconds: float
    preview_enabled: bool


class CameraManager:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.cap: cv2.VideoCapture | None = None

    def connect(self) -> bool:
        self.cap = cv2.VideoCapture(self.config.index)
        if not self.cap.isOpened():
            self.logger.error("Camera index %s unavailable", self.config.index)
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        self.logger.info("Camera connected at index %s", self.config.index)
        return True

    def read_frame(self) -> np.ndarray | None:
        if not self.cap or not self.cap.isOpened():
            if not self._attempt_reconnect():
                return None
        assert self.cap is not None
        ok, frame = self.cap.read()
        if not ok:
            self.logger.warning("Camera read failed")
            return None
        if self.config.preview_enabled:
            cv2.imshow("AI Portrait Preview", frame)
            cv2.waitKey(1)
        return frame

    def _attempt_reconnect(self) -> bool:
        for attempt in range(1, self.config.reconnect_attempts + 1):
            self.logger.warning("Reconnect attempt %s/%s", attempt, self.config.reconnect_attempts)
            time.sleep(self.config.reconnect_delay_seconds)
            if self.connect():
                return True
        return False

    def release(self) -> None:
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
