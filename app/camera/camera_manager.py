"""Camera manager for continuous frame acquisition with reconnect support."""

from __future__ import annotations

import logging
import platform
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
    backend: str = "auto"
    reconnect_fail_threshold: int = 5
    buffer_size: int = 1


class CameraManager:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.cap: cv2.VideoCapture | None = None
        self._failed_reads = 0
        self._warned_this_streak = False

    def _resolve_backend(self) -> int:
        backend_name = self.config.backend.lower().strip()
        if backend_name == "dshow":
            return cv2.CAP_DSHOW
        if backend_name == "msmf":
            return cv2.CAP_MSMF
        if backend_name == "auto":
            if platform.system().lower().startswith("win"):
                return cv2.CAP_DSHOW
            return cv2.CAP_ANY
        self.logger.warning("Unknown camera backend '%s'; using auto", self.config.backend)
        return cv2.CAP_DSHOW if platform.system().lower().startswith("win") else cv2.CAP_ANY

    def _backend_label(self, backend: int) -> str:
        if backend == cv2.CAP_DSHOW:
            return "dshow"
        if backend == cv2.CAP_MSMF:
            return "msmf"
        if backend == cv2.CAP_ANY:
            return "auto"
        return str(backend)

    def _apply_properties(self) -> None:
        if not self.cap:
            return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)

    def connect(self) -> bool:
        backend = self._resolve_backend()
        self.logger.info(
            "Opening camera index=%s backend=%s",
            self.config.index,
            self._backend_label(backend),
        )
        self.cap = cv2.VideoCapture(self.config.index, backend)
        if not self.cap.isOpened():
            self.logger.error("Camera open failed index=%s backend=%s", self.config.index, self._backend_label(backend))
            return False

        self._apply_properties()
        self._failed_reads = 0
        self._warned_this_streak = False
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.logger.info(
            "Camera connected index=%s backend=%s resolution=%sx%s fps=%.2f",
            self.config.index,
            self._backend_label(backend),
            actual_w,
            actual_h,
            actual_fps,
        )
        return True

    def read_frame(self) -> np.ndarray | None:
        if not self.cap or not self.cap.isOpened():
            if not self._attempt_reconnect("capture not open"):
                return None

        assert self.cap is not None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self._failed_reads += 1
            if not self._warned_this_streak:
                self.logger.warning("Camera read failure streak started")
                self._warned_this_streak = True

            if self._failed_reads >= self.config.reconnect_fail_threshold:
                reason = f"{self._failed_reads} consecutive read failures"
                if not self._attempt_reconnect(reason):
                    self.logger.error("Camera unrecoverable after repeated reconnect attempts")
                    return None
            return None

        self._failed_reads = 0
        self._warned_this_streak = False
        if self.config.preview_enabled:
            cv2.imshow("AI Portrait Preview", frame)
            cv2.waitKey(1)
        return frame

    def _attempt_reconnect(self, reason: str) -> bool:
        self.logger.warning("Reconnecting camera due to: %s", reason)
        self.release()
        for attempt in range(1, self.config.reconnect_attempts + 1):
            self.logger.warning("Reconnect attempt %s/%s", attempt, self.config.reconnect_attempts)
            time.sleep(self.config.reconnect_delay_seconds)
            if self.connect():
                self.logger.info("Camera reconnect succeeded on attempt %s", attempt)
                return True
        self.logger.error("Camera reconnect failed after %s attempts", self.config.reconnect_attempts)
        return False

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()
