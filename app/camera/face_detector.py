"""Face detection and stability tracking utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from app.utils.timers import StabilityTimer


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]
    confidence: float


class FaceDetector:
    def __init__(
        self,
        minimum_face_size: int,
        stable_detection_frames: int,
        stable_detection_seconds: float,
        max_faces_allowed: int,
    ) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(cascade_path)
        self.minimum_face_size = minimum_face_size
        self.max_faces_allowed = max_faces_allowed
        self.frame_stability = deque(maxlen=stable_detection_frames)
        self.timer_stability = StabilityTimer(stable_detection_seconds)

    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))
        valid = []
        for (x, y, w, h) in faces:
            if min(w, h) < self.minimum_face_size:
                continue
            valid.append(FaceDetection(bbox=(int(x), int(y), int(w), int(h)), confidence=1.0))
        return valid

    def select_face(self, frame: np.ndarray, faces: list[FaceDetection]) -> FaceDetection | None:
        if not faces:
            return None
        if len(faces) > self.max_faces_allowed:
            return None
        center_x = frame.shape[1] / 2
        center_y = frame.shape[0] / 2
        return max(
            faces,
            key=lambda f: (f.bbox[2] * f.bbox[3]) - abs((f.bbox[0] + f.bbox[2] / 2) - center_x) - abs((f.bbox[1] + f.bbox[3] / 2) - center_y),
        )

    def is_stable(self, face: FaceDetection | None) -> bool:
        valid = face is not None
        self.frame_stability.append(valid)
        frames_ok = len(self.frame_stability) == self.frame_stability.maxlen and all(self.frame_stability)
        seconds_ok = self.timer_stability.tick(valid)
        if not valid:
            self.frame_stability.clear()
        return frames_ok and seconds_ok
