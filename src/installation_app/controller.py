from __future__ import annotations

import time
import uuid
from pathlib import Path

import cv2

from installation_app.camera import FaceDetector, FaceStatus, WebcamManager
from installation_app.cleanup import CleanupManager
from installation_app.comfy_client import ComfyUIClient
from installation_app.config import Config
from installation_app.models import AppState, RunContext, build_run_id
from installation_app.obs_client import OBSClient
from installation_app.output_watcher import OutputWatcher


class PipelineController:
    def __init__(self, config: Config, logger) -> None:
        self.config = config
        self.logger = logger
        self.state = AppState.IDLE

        self.webcam = WebcamManager(config.camera)
        self.detector = FaceDetector(config.camera)
        self.comfy = ComfyUIClient(config.comfyui)
        self.obs = OBSClient(config.obs)
        self.cleanup = CleanupManager(config.cleanup, logger)
        self.output_watcher = OutputWatcher(config.folders.comfy_output_dir)

        self._last_capture_time = 0.0
        self._status_message = "Waiting for face"

    def run(self) -> None:
        self._initialize()
        try:
            self.state = AppState.DETECTING
            while True:
                frame = self.webcam.read()
                face_status = self.detector.evaluate(frame)

                key_code = cv2.waitKey(1) & 0xFF if self.config.camera.preview_enabled else -1
                if key_code == ord(self.config.app.quit_key.lower()):
                    self.logger.info("Quit key pressed, exiting.")
                    break

                should_capture = self.detector.should_capture(face_status)
                manual_capture = self.detector.key_pressed(key_code, self.config.app.manual_override_key)

                if face_status.detected and not should_capture:
                    self.state = AppState.FACE_LOCKED
                    self._status_message = "Face locked"

                if self._cooldown_active():
                    self.state = AppState.COOLDOWN
                    self._status_message = "Cooldown active"
                elif should_capture or manual_capture:
                    try:
                        self._run_pipeline(frame)
                    except Exception as exc:  # pylint: disable=broad-except
                        self.logger.exception("Pipeline run failed: %s", exc)
                        self.state = AppState.READY
                        self._status_message = "Recovered from error; ready"
                        time.sleep(self.config.app.idle_reset_seconds)
                        self.state = AppState.DETECTING
                        self._status_message = "Waiting for face"

                self._render_preview(frame, face_status)
        finally:
            self.shutdown()

    def _initialize(self) -> None:
        available = self.webcam.scan_available_cameras()
        self.logger.info("Detected cameras: %s", available)

        self.webcam.open()
        self.logger.info("Opened camera index %s", self.config.camera.primary_index)

        self.comfy.health_check()
        self.logger.info("ComfyUI connectivity check passed")

        if self.config.obs.enabled:
            self.obs.connect()
            self.obs.health_check()
            self.logger.info("OBS connectivity check passed")

    def _run_pipeline(self, frame) -> None:
        run = RunContext(run_id=build_run_id())
        self.logger.info("Starting run: %s", run.run_id)

        self.state = AppState.CAPTURING
        self._status_message = "Capturing face"
        input_file = self._save_capture(frame, run.run_id)
        run.input_files.append(input_file)

        output_baseline = self.output_watcher.snapshot()

        self.state = AppState.TRIGGERING_COMFY
        self._status_message = "Triggering ComfyUI"
        run.comfy_prompt_id = self.comfy.queue_prompt(client_id=str(uuid.uuid4()))
        self.logger.info("Queued ComfyUI prompt_id=%s", run.comfy_prompt_id)

        self.state = AppState.WAITING_FOR_COMFY
        self._status_message = "Generating images"
        _ = self.comfy.wait_for_completion(run.comfy_prompt_id)
        self.logger.info("ComfyUI run complete prompt_id=%s", run.comfy_prompt_id)

        if self.config.cleanup.cleanup_input_after_comfy:
            self.state = AppState.CLEANING_INPUTS
            self._status_message = "Cleaning input files"
            self.cleanup.delete_files(
                run.input_files,
                delay_ms=self.config.cleanup.input_cleanup_delay_ms,
                label="input",
            )

        self.state = AppState.COLLECTING_OUTPUTS
        self._status_message = "Collecting output files"
        run.output_files = self.output_watcher.wait_for_new_files(
            baseline=output_baseline,
            timeout_seconds=self.config.comfyui.completion_timeout_seconds,
            poll_interval_seconds=self.config.comfyui.poll_interval_seconds,
        )
        self.logger.info("Detected output files: %s", [str(p) for p in run.output_files])

        if self.config.obs.enabled:
            self.state = AppState.UPDATING_OBS
            self._status_message = "Updating OBS sources"
            self.obs.update_image_sources(run.output_files)

            self.state = AppState.TRIGGERING_TRANSITION
            self._status_message = "Triggering transition"
            self.obs.trigger_transition()

        if self.config.cleanup.cleanup_output_after_obs:
            self.state = AppState.CLEANING_OUTPUTS
            self._status_message = "Cleaning output files"
            self.cleanup.delete_files(
                run.output_files,
                delay_ms=self.config.cleanup.output_cleanup_delay_ms,
                label="output",
            )

        self._last_capture_time = time.monotonic()
        self.state = AppState.READY
        self._status_message = "Ready for next participant"
        time.sleep(self.config.app.idle_reset_seconds)
        self.state = AppState.DETECTING

    def _save_capture(self, frame, run_id: str) -> Path:
        self.state = AppState.SAVING
        self._status_message = "Saving capture"

        filename = f"{run_id}_face.jpg"
        target = self.config.folders.capture_input_dir / filename
        ok = cv2.imwrite(str(target), frame)
        if not ok:
            raise RuntimeError(f"Failed to write capture image: {target}")

        self.logger.info("Saved capture: %s", target)
        return target

    def _cooldown_active(self) -> bool:
        elapsed = time.monotonic() - self._last_capture_time
        return elapsed < self.config.camera.capture_cooldown_seconds

    def _render_preview(self, frame, face_status: FaceStatus) -> None:
        if not self.config.camera.preview_enabled:
            return
        annotated = self.detector.draw_overlay(
            frame,
            self.state.value,
            face_status,
            self._status_message,
        )
        cv2.imshow("Installation Preview", annotated)

    def shutdown(self) -> None:
        self.webcam.close()
        self.comfy.shutdown()
        if self.config.obs.enabled:
            self.obs.disconnect()
        cv2.destroyAllWindows()
