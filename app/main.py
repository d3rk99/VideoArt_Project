"""Main orchestration entrypoint for AI Portrait Gallery Automation."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2

from app.camera.camera_manager import CameraConfig, CameraManager
from app.camera.capture_selector import CaptureSelector
from app.camera.face_detector import FaceDetector
from app.comfy.comfy_client import ComfyClient
from app.comfy.generation_service import GenerationService
from app.comfy.workflow_loader import WorkflowLoader
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
    parser.add_argument("--test-comfy", action="store_true", help="Run ComfyUI connectivity + workflow parse checks")
    parser.add_argument("--generate-latest", action="store_true", help="Generate from most recent processed input")
    parser.add_argument("--test-camera", action="store_true", help="Run camera self-test")
    parser.add_argument("--test-obs", action="store_true", help="Reserved Phase 3 healthcheck")
    return parser.parse_args()


def run_phase1(settings: dict) -> None:
    configure_logging(Path(settings["paths"]["logs_dir"]), bool(settings["app"]["debug"]))

    file_manager = FileManager(
        live_capture_dir=Path(settings["paths"]["live_capture_dir"]),
        comfy_input_dir=Path(settings["paths"]["comfy_input_dir"]),
        output_latest_dir=Path(settings["paths"]["output_latest_dir"]),
        output_archive_dir=Path(settings["paths"]["output_archive_dir"]),
        comfy_runtime_input_dir=Path(settings["comfy"].get("input_dir") or settings["paths"]["comfy_input_dir"]),
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
        backend=settings["camera"].get("backend", "auto"),
        reconnect_fail_threshold=int(settings["camera"].get("reconnect_fail_threshold", 5)),
        buffer_size=int(settings["camera"].get("buffer_size", 1)),
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
                while cooldown.active():
                    time.sleep(0.1)
                machine.transition_to(SessionState.IDLE)
                machine.transition_to(SessionState.DETECTING)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()


def _build_generation_service(settings: dict, file_manager: FileManager) -> GenerationService:
    client = ComfyClient(
        base_url=str(settings["comfy"]["base_url"]),
        timeout_seconds=int(settings["comfy"]["request_timeout_seconds"]),
    )
    loader = WorkflowLoader(Path(settings["paths"]["workflows_dir"]))
    return GenerationService(client=client, loader=loader, file_manager=file_manager)


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

    try:
        service = _build_generation_service(settings, file_manager)
        machine.transition_to(SessionState.GENERATING)
        service.run_for_session(session, settings)
        machine.transition_to(SessionState.COLLECTING_OUTPUTS)
        machine.transition_to(SessionState.DISPLAYING)
        machine.transition_to(SessionState.COOLDOWN)
    except Exception as exc:
        LOGGER.exception("Phase 2 generation failed: %s", exc)
        session.errors.append(str(exc))
        machine.transition_to(SessionState.ERROR)
        machine.transition_to(SessionState.COOLDOWN)
    finally:
        write_manifest(session)
        session_manager.end_session()


def run_test_comfy(settings: dict) -> int:
    configure_logging(Path(settings["paths"]["logs_dir"]), bool(settings["app"]["debug"]))
    file_manager = FileManager(
        live_capture_dir=Path(settings["paths"]["live_capture_dir"]),
        comfy_input_dir=Path(settings["paths"]["comfy_input_dir"]),
        output_latest_dir=Path(settings["paths"]["output_latest_dir"]),
        output_archive_dir=Path(settings["paths"]["output_archive_dir"]),
        comfy_runtime_input_dir=Path(settings["comfy"].get("input_dir") or settings["paths"]["comfy_input_dir"]),
    )
    try:
        service = _build_generation_service(settings, file_manager)
    except Exception as exc:
        print(f"ComfyUI connectivity test FAILED: {exc}")
        return 1

    healthy = service.client.healthcheck()
    if not healthy:
        print("ComfyUI connectivity test FAILED")
        return 1

    workflow_names = list(settings["workflows"]["enabled"])
    workflow_files = dict(settings["workflows"]["files"])
    for workflow_name in workflow_names:
        workflow_path = service.loader.resolve_workflow_path(workflow_files[workflow_name])
        workflow = service.loader.load(workflow_path)
        service.loader.validate(workflow)
    print("ComfyUI connectivity test PASSED; enabled workflow files are valid")
    return 0


def run_generate_latest(settings: dict) -> int:
    configure_logging(Path(settings["paths"]["logs_dir"]), bool(settings["app"]["debug"]))
    file_manager = FileManager(
        live_capture_dir=Path(settings["paths"]["live_capture_dir"]),
        comfy_input_dir=Path(settings["paths"]["comfy_input_dir"]),
        output_latest_dir=Path(settings["paths"]["output_latest_dir"]),
        output_archive_dir=Path(settings["paths"]["output_archive_dir"]),
        comfy_runtime_input_dir=Path(settings["comfy"].get("input_dir") or settings["paths"]["comfy_input_dir"]),
    )
    candidates = sorted(file_manager.comfy_input_dir.glob("*_input.jpg"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        print("No processed input image found in comfy input directory")
        return 1

    session_manager = SessionManager(file_manager)
    machine = SessionStateMachine()
    machine.transition_to(SessionState.DETECTING)
    machine.transition_to(SessionState.CAPTURING)
    machine.transition_to(SessionState.PREPARING_INPUT)

    session = session_manager.start_session()
    session.processed_input_path = candidates[-1]
    try:
        service = _build_generation_service(settings, file_manager)
        machine.transition_to(SessionState.GENERATING)
        service.run_for_session(session, settings)
        machine.transition_to(SessionState.COLLECTING_OUTPUTS)
        machine.transition_to(SessionState.DISPLAYING)
        machine.transition_to(SessionState.COOLDOWN)
    except Exception as exc:
        session.errors.append(str(exc))
        machine.transition_to(SessionState.ERROR)
        machine.transition_to(SessionState.COOLDOWN)
        write_manifest(session)
        session_manager.end_session()
        print(f"Generation from latest input FAILED: {exc}")
        return 1

    write_manifest(session)
    session_manager.end_session()
    print("Generation from latest input PASSED")
    return 0


def run_test_camera(settings: dict) -> int:
    configure_logging(Path(settings["paths"]["logs_dir"]), bool(settings["app"]["debug"]))
    cam_cfg = CameraConfig(
        index=settings["camera"]["index"],
        width=settings["camera"].get("width", 1280),
        height=settings["camera"].get("height", 720),
        fps=settings["camera"].get("fps", 30),
        reconnect_attempts=settings["camera"].get("reconnect_attempts", 5),
        reconnect_delay_seconds=settings["camera"].get("reconnect_delay_seconds", 1.0),
        preview_enabled=False,
        backend=settings["camera"].get("backend", "auto"),
        reconnect_fail_threshold=int(settings["camera"].get("reconnect_fail_threshold", 5)),
        buffer_size=int(settings["camera"].get("buffer_size", 1)),
    )
    camera = CameraManager(cam_cfg)
    if not camera.connect():
        print("Camera self-test FAILED: unable to open camera")
        return 1

    duration_seconds = int(settings["camera"].get("self_test_duration_seconds", 10))
    start = time.monotonic()
    total_frames = 0
    failed_reads = 0
    try:
        while time.monotonic() - start < duration_seconds:
            frame = camera.read_frame()
            if frame is None:
                failed_reads += 1
            else:
                total_frames += 1
            time.sleep(0.01)
    finally:
        camera.release()

    status = "PASSED" if total_frames > 0 and failed_reads == 0 else "WARNING"
    print(f"Camera self-test {status}: frames={total_frames} failed_reads={failed_reads} duration={duration_seconds}s")
    return 0 if total_frames > 0 else 1


def main() -> None:
    args = parse_args()
    settings = load_settings(Path(args.config))
    if args.manual_reset:
        print("Manual reset complete; state would be set to IDLE.")
        return
    if args.test_comfy:
        sys.exit(run_test_comfy(settings))
    if args.generate_latest:
        sys.exit(run_generate_latest(settings))
    if args.test_camera:
        sys.exit(run_test_camera(settings))
    run_phase1(settings)


if __name__ == "__main__":
    main()
