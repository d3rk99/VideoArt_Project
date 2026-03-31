"""Main orchestration entrypoint for AI Portrait Gallery Automation."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from app.camera.camera_manager import CameraConfig, CameraManager
from app.camera.capture_selector import CaptureSelector
from app.camera.face_detector import FaceDetector
from app.config.settings import load_settings
from app.sessions.models import SessionState
from app.sessions.session_manager import SessionManager
from app.sessions.state_machine import SessionStateMachine
from app.storage.file_manager import FileManager
from app.storage.session_manifest import write_manifest
from app.utils.image_tools import resize_to
from app.utils.logger import configure_logging
from app.utils.timers import CooldownTimer

LOGGER = logging.getLogger("app.main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Portrait Gallery Orchestrator")
    parser.add_argument("--config", default="app/config/settings.yaml")
    parser.add_argument("--manual-trigger", action="store_true", help="Trigger capture without waiting for stable face")
    parser.add_argument("--manual-reset", action="store_true", help="Reset state to IDLE and exit")
    parser.add_argument("--test-comfy", action="store_true", help="Reserved Phase 2 healthcheck")
    parser.add_argument("--test-obs", action="store_true", help="Reserved Phase 3 healthcheck")
    return parser.parse_args()


def run_phase1(settings: dict) -> None:
    configure_logging(Path(settings["paths"]["logs_dir"]), bool(settings["app"]["debug"]))

    file_manager = FileManager(
        live_capture_dir=Path(settings["paths"]["live_capture_dir"]),
        comfy_input_dir=Path(settings["paths"]["comfy_input_dir"]),
        output_latest_dir=Path(settings["paths"]["output_latest_dir"]),
        output_archive_dir=Path(settings["paths"]["output_archive_dir"]),
    )
    session_manager = SessionManager(file_manager)
    machine = SessionStateMachine()
    cooldown = CooldownTimer(settings["trigger"]["post_session_cooldown_seconds"])

    cam_cfg = CameraConfig(
        index=settings["camera"]["index"],
        width=settings["camera"]["width"],
        height=settings["camera"]["height"],
        fps=settings["camera"]["fps"],
        reconnect_attempts=settings["camera"]["reconnect_attempts"],
        reconnect_delay_seconds=settings["camera"]["reconnect_delay_seconds"],
        preview_enabled=settings["camera"]["preview_enabled"],
    )
    camera = CameraManager(cam_cfg)
    if not camera.connect():
        raise RuntimeError("Camera unavailable")

    detector = FaceDetector(
        minimum_face_size=settings["trigger"]["minimum_face_size"],
        stable_detection_frames=settings["trigger"]["stable_detection_frames"],
        stable_detection_seconds=settings["trigger"]["stable_detection_seconds"],
        max_faces_allowed=settings["trigger"]["max_faces_allowed"],
    )
    selector = CaptureSelector()

    machine.transition_to(SessionState.DETECTING)
    LOGGER.info("Phase 1 loop started")

    try:
        while True:
            frame = camera.read_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            faces = detector.detect(frame)
            chosen = detector.select_face(frame, faces)
            stable = detector.is_stable(chosen)

            if stable and machine.can_trigger_capture() and not cooldown.active() and not session_manager.has_active_session():
                _capture_session(frame, camera, selector, session_manager, machine, file_manager, settings)
                cooldown.start()
                machine.transition_to(SessionState.COOLDOWN)
                while cooldown.active():
                    time.sleep(0.1)
                machine.transition_to(SessionState.IDLE)
                machine.transition_to(SessionState.DETECTING)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()


def _capture_session(
    current_frame,
    camera: CameraManager,
    selector: CaptureSelector,
    session_manager: SessionManager,
    machine: SessionStateMachine,
    file_manager: FileManager,
    settings: dict,
) -> None:
    machine.transition_to(SessionState.CAPTURING)
    session = session_manager.start_session()

    burst = [current_frame]
    for _ in range(settings["capture"]["burst_count"] - 1):
        frame = camera.read_frame()
        if frame is not None:
            burst.append(frame)
        time.sleep(settings["capture"]["burst_interval_seconds"])

    best = selector.select_best(burst)
    LOGGER.info("Selected best frame score=%.3f", best.score)

    raw_path = file_manager.session_raw_path(session.session_id)
    cv2.imwrite(str(raw_path), best.frame)
    session.raw_capture_path = raw_path

    machine.transition_to(SessionState.PREPARING_INPUT)
    processed = resize_to(best.frame, settings["capture"]["resize_width"], settings["capture"]["resize_height"])
    processed_path = file_manager.session_comfy_input_path(session.session_id)
    cv2.imwrite(str(processed_path), processed)
    session.processed_input_path = processed_path

    if session.archive_dir:
        cv2.imwrite(str(session.archive_dir / "raw_capture.jpg"), best.frame)
        cv2.imwrite(str(session.archive_dir / "processed_input.jpg"), processed)
    write_manifest(session)
    session_manager.end_session()


def main() -> None:
    args = parse_args()
    settings = load_settings(Path(args.config))
    if args.manual_reset:
        print("Manual reset complete; state would be set to IDLE.")
        return
    run_phase1(settings)


if __name__ == "__main__":
    main()
