from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from installation_app.config import CameraConfig


@dataclass
class FaceStatus:
    detected: bool
    stable_seconds: float
    bbox: tuple[int, int, int, int] | None


class WebcamManager:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.cap: cv2.VideoCapture | None = None

    def _resolve_backend(self) -> int:
        backend = self.config.backend.lower()
        if backend == "dshow" and hasattr(cv2, "CAP_DSHOW"):
            return cv2.CAP_DSHOW
        if backend == "msmf" and hasattr(cv2, "CAP_MSMF"):
            return cv2.CAP_MSMF
        return cv2.CAP_ANY

    def scan_available_cameras(self) -> list[int]:
        available: list[int] = []
        probe_indices = self.config.indices or list(range(self.config.scan_max_index + 1))
        backend = self._resolve_backend()
        for index in probe_indices:
            cap = cv2.VideoCapture(index, backend)
            if cap is not None and cap.isOpened():
                available.append(index)
                cap.release()
        return available

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.config.primary_index, self._resolve_backend())
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {self.config.primary_index}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)

    def read(self) -> np.ndarray:
        if not self.cap:
            raise RuntimeError("Camera is not open")
        for _ in range(self.config.read_retry_count + 1):
            ok, frame = self.cap.read()
            if ok:
                return frame
            time.sleep(self.config.read_retry_delay_ms / 1000)
        raise RuntimeError("Failed to read frame from camera")

    def reopen(self) -> None:
        self.close()
        self.open()

    def close(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None


class FaceDetector:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.classifier = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._stable_started_at: float | None = None

    def evaluate(self, frame: np.ndarray) -> FaceStatus:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))

        if len(faces) == 0:
            self._stable_started_at = None
            return FaceStatus(detected=False, stable_seconds=0.0, bbox=None)

        largest = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = largest

        frame_area = frame.shape[0] * frame.shape[1]
        face_area = w * h
        face_ratio = face_area / max(1, frame_area)

        if face_ratio < self.config.min_face_area_ratio:
            self._stable_started_at = None
            return FaceStatus(detected=False, stable_seconds=0.0, bbox=None)

        now = time.time()
        if self._stable_started_at is None:
            self._stable_started_at = now
        stable_seconds = now - self._stable_started_at

        return FaceStatus(detected=True, stable_seconds=stable_seconds, bbox=(x, y, w, h))

    def draw_overlay(
        self,
        frame: np.ndarray,
        state_label: str,
        face_status: FaceStatus,
        status_message: str,
    ) -> np.ndarray:
        annotated = frame.copy()
        if face_status.bbox:
            x, y, w, h = face_status.bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(annotated, f"State: {state_label}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(annotated, status_message, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        if face_status.detected:
            remaining = max(0.0, self.config.face_stability_seconds - face_status.stable_seconds)
            cv2.putText(
                annotated,
                f"Face lock: {face_status.stable_seconds:.1f}s / {self.config.face_stability_seconds:.1f}s (remaining {remaining:.1f}s)",
                (20, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

        return annotated

    def key_pressed(self, key_code: int, hotkey: str) -> bool:
        return key_code == ord(hotkey.lower())

    def should_capture(self, face_status: FaceStatus) -> bool:
        return face_status.detected and face_status.stable_seconds >= self.config.face_stability_seconds
