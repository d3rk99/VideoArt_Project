from __future__ import annotations

import time
import uuid
from pathlib import Path
from threading import Thread
import traceback

import cv2

from installation_app.camera import FaceDetector, FaceStatus, WebcamManager
from installation_app.cleanup import CleanupManager
from installation_app.comfy_browser_trigger import ComfyUIBrowserTrigger
from installation_app.comfy_client import ComfyUIClient
from installation_app.config import Config
from installation_app.models import AppState, RunContext, build_run_id
from installation_app.obs_client import OBSClient
from installation_app.output_watcher import OutputWatcher
from installation_app.remote_client import RemoteBridgeClient


class PipelineController:
    def __init__(self, config: Config, logger) -> None:
        self.config = config
        self.logger = logger
        self.state = AppState.IDLE

        self._remote_mode = config.mode.execution_mode == "remote_bridge"
        self.webcam = WebcamManager(config.camera)
        self.detector = FaceDetector(config.camera)
        self.remote_client = RemoteBridgeClient(config.remote, config.local_paths, logger) if self._remote_mode else None
        self.comfy = ComfyUIClient(config.comfyui) if not self._remote_mode else None
        self.comfy_browser = None
        if not self._remote_mode and config.comfyui.trigger_mode == "browser_ui":
            self.comfy_browser = ComfyUIBrowserTrigger(config.comfyui, logger)
        self.obs = OBSClient(config.obs)
        self.cleanup = CleanupManager(config.cleanup, logger)
        self.output_watcher = OutputWatcher(config.folders.comfy_output_dir) if not self._remote_mode else None

        self._last_capture_time = 0.0
        self._status_message = "Waiting for face"
        self._comfy_backoff_until = 0.0
        self._comfy_failure_count = 0
        self._pending_output_cleanup: list[Path] = []
        self._pipeline_thread: Thread | None = None
        self._pipeline_error: Exception | None = None
        self._pipeline_error_traceback: str | None = None

    def run(self) -> None:
        self._initialize()
        try:
            self.state = AppState.DETECTING
            while True:
                self._poll_pipeline_completion()
                try:
                    frame = self.webcam.read()
                except Exception as exc:  # pylint: disable=broad-except
                    self.logger.warning("Camera read failed: %s", exc)
                    self._status_message = "Camera read failed; retrying"
                    if self.config.camera.reconnect_on_read_failure:
                        try:
                            self.webcam.reopen(advance_backend=True)
                            self.logger.info(
                                "Camera reopened after read failure using camera %s backend %s",
                                self.webcam.current_camera_index(),
                                self.webcam.current_backend_name(),
                            )
                        except Exception as reopen_exc:  # pylint: disable=broad-except
                            self.logger.error("Camera reopen failed: %s", reopen_exc)
                    time.sleep(self.config.app.idle_reset_seconds)
                    continue
                face_status = self.detector.evaluate(frame)

                key_code = cv2.waitKey(1) & 0xFF if self.config.camera.preview_enabled else -1
                if key_code == ord(self.config.app.quit_key.lower()):
                    self.logger.info("Quit key pressed, exiting.")
                    break

                pipeline_active = self._pipeline_active()
                should_capture = self.detector.should_capture(face_status) if not pipeline_active else False
                manual_capture = (
                    self.detector.key_pressed(key_code, self.config.app.manual_override_key)
                    if not pipeline_active
                    else False
                )

                if face_status.detected and not should_capture and not pipeline_active:
                    self.state = AppState.FACE_LOCKED
                    self._status_message = "Face locked"

                if pipeline_active:
                    self._status_message = "Run in progress"
                elif self._cooldown_active():
                    self.state = AppState.COOLDOWN
                    self._status_message = "Cooldown active"
                elif self._comfy_backoff_active():
                    self.state = AppState.COOLDOWN
                    remaining = max(0.0, self._comfy_backoff_until - time.monotonic())
                    self._status_message = f"ComfyUI backoff active ({remaining:.1f}s)"
                elif should_capture or manual_capture:
                    try:
                        # Start cooldown immediately to avoid rapid re-trigger loops on downstream failures.
                        self._last_capture_time = time.monotonic()
                        self._start_pipeline(frame.copy())
                    except Exception as exc:  # pylint: disable=broad-except
                        self._handle_pipeline_failure(exc)

                self._render_preview(frame, face_status)
        finally:
            self.shutdown()

    def _initialize(self) -> None:
        available = self.webcam.scan_available_cameras()
        self.logger.info("Detected cameras: %s", available)

        self.webcam.open()
        self.logger.info(
            "Opened camera index %s with backend %s",
            self.webcam.current_camera_index(),
            self.webcam.current_backend_name(),
        )

        if self._remote_mode:
            if not self.remote_client:
                raise RuntimeError("Remote execution mode enabled but remote client is not configured")
            self.remote_client.health_check()
            self.logger.info("Remote bridge connectivity check passed")
        else:
            if not self.comfy:
                raise RuntimeError("Local execution mode requires ComfyUI client")
            self.comfy.health_check()
            self.logger.info("ComfyUI connectivity check passed")
            if self.comfy_browser:
                self.comfy_browser.initialize()
                self.logger.info("ComfyUI browser_ui trigger initialized")

        if self.config.obs.enabled:
            self.obs.connect()
            self.obs.health_check()
            self.logger.info("OBS connectivity check passed")

    def _run_pipeline(self, frame) -> None:
        run = RunContext(run_id=build_run_id())
        self.logger.info("Starting run: %s (mode=%s)", run.run_id, self.config.mode.execution_mode)

        self.state = AppState.CAPTURING
        self._status_message = "Capturing face"
        input_file = self._save_capture(frame, run.run_id)
        run.input_files.append(input_file)
        try:
            if self._remote_mode:
                self._run_remote_job(run)
            else:
                self._run_local_job(run)
            self._finalize_run(run)
        except Exception:
            self.cleanup.delete_files(run.input_files, delay_ms=0, label="input_failed_run")
            raise

    def _run_local_job(self, run: RunContext) -> None:
        if not self.output_watcher or not self.comfy:
            raise RuntimeError("Local mode requires ComfyUI client and output watcher")
        output_baseline = self.output_watcher.snapshot()
        self.state = AppState.TRIGGERING_COMFY
        self._status_message = "Triggering ComfyUI"
        if self.config.comfyui.trigger_mode == "api":
            run.comfy_prompt_id = self.comfy.queue_prompt(client_id=str(uuid.uuid4()))
            self.logger.info("Queued ComfyUI prompt_id=%s", run.comfy_prompt_id)
            self.state = AppState.WAITING_FOR_COMFY
            self._status_message = "Generating images"
            self.comfy.wait_for_completion(run.comfy_prompt_id)
            self.logger.info("ComfyUI run complete prompt_id=%s", run.comfy_prompt_id)
            if self.config.cleanup.cleanup_input_after_comfy:
                self.state = AppState.CLEANING_INPUTS
                self._status_message = "Cleaning input files"
                self.cleanup.delete_files(
                    run.input_files,
                    delay_ms=self.config.cleanup.input_cleanup_delay_ms,
                    label="input",
                )
        else:
            if not self.comfy_browser:
                raise RuntimeError("browser_ui trigger_mode selected but browser trigger is not initialized")
            self.comfy_browser.queue_current_workflow()
            self.state = AppState.WAITING_FOR_COMFY
            self._status_message = "Generating images"

        self.state = AppState.COLLECTING_OUTPUTS
        self._status_message = "Collecting output files"
        run.output_files = self.output_watcher.wait_for_new_files(
            baseline=output_baseline,
            timeout_seconds=self.config.comfyui.completion_timeout_seconds,
            poll_interval_seconds=self.config.comfyui.poll_interval_seconds,
        )
        self.logger.info("Detected output files: %s", [str(p) for p in run.output_files])

        if self.config.comfyui.trigger_mode == "browser_ui" and self.config.cleanup.cleanup_input_after_comfy:
            self.state = AppState.CLEANING_INPUTS
            self._status_message = "Cleaning input files"
            self.cleanup.delete_files(
                run.input_files,
                delay_ms=self.config.cleanup.input_cleanup_delay_ms,
                label="input",
            )

    def _run_remote_job(self, run: RunContext) -> None:
        if not self.remote_client:
            raise RuntimeError("Remote execution mode enabled without remote client")
        capture_path = run.input_files[-1]
        self.state = AppState.TRIGGERING_COMFY
        self._status_message = "Uploading capture to bridge"
        job_id = self.remote_client.submit_job(capture_path, run.run_id)
        run.remote_job_id = job_id
        self.state = AppState.WAITING_FOR_COMFY
        self._status_message = "Waiting for remote generation"
        self.remote_client.wait_for_completion(job_id, self.config.comfyui.completion_timeout_seconds)
        self.logger.info("Remote bridge job %s completed", job_id)
        self.state = AppState.COLLECTING_OUTPUTS
        self._status_message = "Downloading remote results"
        run.output_files = self.remote_client.download_results(job_id, run.run_id)
        if self.config.cleanup.cleanup_input_after_comfy:
            self.state = AppState.CLEANING_INPUTS
            self._status_message = "Cleaning input files"
            self.cleanup.delete_files(
                run.input_files,
                delay_ms=self.config.cleanup.input_cleanup_delay_ms,
                label="input_remote",
            )
        try:
            self.remote_client.delete_job(job_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Remote bridge cleanup failed for %s: %s", job_id, exc)

    def _finalize_run(self, run: RunContext) -> None:
        if self.config.obs.enabled and len(run.output_files) < len(self.config.obs.image_sources):
            raise RuntimeError(
                "Not enough generated output files for OBS slots: "
                f"needed={len(self.config.obs.image_sources)} got={len(run.output_files)}"
            )

        if self.config.obs.enabled:
            self.state = AppState.UPDATING_OBS
            self._status_message = "Updating OBS sources"
            assignments = self.obs.update_image_sources(run.output_files[: len(self.config.obs.image_sources)])
            self.logger.info(
                "OBS source assignments: %s",
                [f"{source}<-{path}" for source, path in assignments],
            )
            if len(assignments) != len(self.config.obs.image_sources):
                raise RuntimeError(
                    f"Failed to assign all OBS sources: expected={len(self.config.obs.image_sources)} got={len(assignments)}"
                )
            self.obs.set_preview_scene(self.config.obs.staging_scene)
            self.logger.info("Set preview scene to %s", self.config.obs.staging_scene)

            self.state = AppState.TRIGGERING_TRANSITION
            self._status_message = "Triggering transition"
            self.obs.trigger_transition()
            self.logger.info("Triggered OBS transition: %s", self.config.obs.transition_name)
            transition_wait = (
                self.config.obs.transition_duration_ms + self.config.obs.post_transition_delay_ms
            ) / 1000
            time.sleep(transition_wait)

        if self.config.cleanup.cleanup_output_after_obs:
            self.state = AppState.CLEANING_OUTPUTS
            self._status_message = "Cleaning previous output files"
            if self._pending_output_cleanup:
                self.cleanup.delete_files(
                    self._pending_output_cleanup,
                    delay_ms=self.config.cleanup.output_cleanup_delay_ms,
                    label="output_previous_run",
                )
            self._pending_output_cleanup = list(run.output_files)
            self.logger.info(
                "Deferred cleanup armed with %s files from current run",
                len(self._pending_output_cleanup),
            )

        self.state = AppState.READY
        self._status_message = "Ready for next participant"
        self._comfy_failure_count = 0
        self._comfy_backoff_until = 0.0
        post_cycle_delay_ms = self.config.app.post_cycle_detection_delay_ms
        self.logger.info("Post-cycle detection delay: %sms", post_cycle_delay_ms)
        time.sleep(post_cycle_delay_ms / 1000)
        self.state = AppState.DETECTING

    def _start_pipeline(self, frame) -> None:
        if self._pipeline_active():
            return
        self._pipeline_error = None
        self._pipeline_error_traceback = None
        self._pipeline_thread = Thread(target=self._run_pipeline_thread, args=(frame,), daemon=True)
        self._pipeline_thread.start()

    def _run_pipeline_thread(self, frame) -> None:
        try:
            self._run_pipeline(frame)
        except Exception as exc:  # pylint: disable=broad-except
            self._pipeline_error = exc
            self._pipeline_error_traceback = traceback.format_exc()

    def _pipeline_active(self) -> bool:
        return self._pipeline_thread is not None and self._pipeline_thread.is_alive()

    def _poll_pipeline_completion(self) -> None:
        if self._pipeline_thread and not self._pipeline_thread.is_alive():
            self._pipeline_thread.join()
            self._pipeline_thread = None
            if self._pipeline_error:
                exc = self._pipeline_error
                self._pipeline_error = None
                self._handle_pipeline_failure(exc, self._pipeline_error_traceback)
                self._pipeline_error_traceback = None

    def _handle_pipeline_failure(self, exc: Exception, trace: str | None = None) -> None:
        if self.config.app.debug_logging and trace:
            self.logger.error("Pipeline run failed: %s\n%s", exc, trace)
        else:
            self.logger.error("Pipeline run failed: %s", exc)
        self._register_pipeline_failure(exc)
        self.state = AppState.READY
        self._status_message = "Run failed; cooldown active"
        time.sleep(self.config.app.idle_reset_seconds)
        self.state = AppState.DETECTING
        self._status_message = "Waiting for face"

    def _save_capture(self, frame, run_id: str) -> Path:
        self.state = AppState.SAVING
        self._status_message = "Saving capture"

        filename_template = self.config.folders.capture_input_filename
        filename = filename_template.replace("{run_id}", run_id)
        target = self._capture_target_dir() / filename
        ok = cv2.imwrite(str(target), frame)
        if not ok:
            raise RuntimeError(f"Failed to write capture image: {target}")

        self.logger.info("Saved capture: %s", target)
        return target

    def _capture_target_dir(self) -> Path:
        if self._remote_mode:
            return self.config.local_paths.capture_temp_dir
        return self.config.folders.capture_input_dir

    def _cooldown_active(self) -> bool:
        elapsed = time.monotonic() - self._last_capture_time
        return elapsed < self.config.camera.capture_cooldown_seconds

    def _comfy_backoff_active(self) -> bool:
        return time.monotonic() < self._comfy_backoff_until

    def _register_pipeline_failure(self, exc: Exception) -> None:
        message = str(exc)
        if (
            "ComfyUI /prompt failed" in message
            or "ComfyUI run timed out" in message
            or "ComfyUI browser trigger failed" in message
        ):
            self._comfy_failure_count += 1
            base = self.config.app.comfy_error_backoff_seconds
            max_backoff = self.config.app.comfy_error_backoff_max_seconds
            backoff_seconds = min(max_backoff, base * (2 ** (self._comfy_failure_count - 1)))
            self._comfy_backoff_until = time.monotonic() + backoff_seconds
            self.logger.warning(
                "Applying ComfyUI backoff for %.1fs after failure (failure count=%s)",
                backoff_seconds,
                self._comfy_failure_count,
            )

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
        if self._pipeline_thread:
            self._pipeline_thread.join(timeout=1.0)
        self.webcam.close()
        if self.comfy:
            self.comfy.shutdown()
        if self.remote_client:
            self.remote_client.close()
        if self.comfy_browser:
            self.comfy_browser.shutdown()
        if self.config.obs.enabled:
            self.obs.disconnect()
        cv2.destroyAllWindows()
