# Interactive Photo/Art Installation Pipeline (Python)

A Windows-first Python application for installation workflows:

1. Detect face from webcam preview.
2. Capture a still image once face lock is stable.
3. Save capture into a configured ComfyUI input folder.
4. Trigger an existing ComfyUI workflow via API.
5. Wait for generation completion.
6. Update OBS image sources and trigger transition.
7. Clean up run-specific input/output files safely.

## Project Structure

```text
VideoArt_Project/
├── config.example.yaml
├── install.bat
├── run.bat
├── requirements.txt
├── README.md
└── src/
    └── installation_app/
        ├── __init__.py
        ├── main.py
        ├── config.py
        ├── logging_utils.py
        ├── models.py
        ├── camera.py
        ├── comfy_client.py
        ├── obs_client.py
        ├── output_watcher.py
        ├── cleanup.py
        └── controller.py
```

## Requirements

- Windows 10/11
- Python 3.11+
- OBS Studio with obs-websocket enabled (optional but recommended)
- ComfyUI running with existing workflow file

## Setup

1. Run installer:
   ```bat
   install.bat
   ```
2. Copy and edit config:
   ```bat
   copy config.example.yaml config.yaml
   ```
3. Update values in `config.yaml` (see **Required Customization** below).
- Windows path tip: in YAML, prefer forward slashes (`C:/...`) or single-quoted backslash paths (`'C:\\...'`). Avoid double-quoted unescaped backslashes like `"C:\something"` because YAML treats backslashes as escapes.

## Run

```bat
run.bat
```

## Batch Script Crash Visibility

Both `install.bat` and `run.bat` now pause on errors so the terminal stays open and operator-visible crash messages can be read before closing the window.

## Connectivity Tests

Use these before live operation:

- ComfyUI test:
  ```bat
  .venv\Scripts\activate
  set PYTHONPATH=%CD%\src
  python -m installation_app.main --config config.yaml --test-comfy
  ```

- OBS test:
  ```bat
  .venv\Scripts\activate
  set PYTHONPATH=%CD%\src
  python -m installation_app.main --config config.yaml --test-obs
  ```

## Required Customization

### 1) ComfyUI workflow file path
Set in `comfyui.workflow_file`.

- Must point to your existing ComfyUI API prompt/workflow JSON file.
- The app **does not** redesign your workflow.

### 2) ComfyUI input/output folders
Set in `folders.capture_input_dir` and `folders.comfy_output_dir`.

- `capture_input_dir`: where this app writes captured faces.
- `comfy_output_dir`: where ComfyUI writes generated output images.

### 3) OBS source names
Set in `obs.image_sources`.

- Must match existing OBS image source names exactly.
- If multiple sources are configured but fewer images are generated, the last image is reused.

### 4) Camera device index
Set in `camera.primary_index`.

- Use camera scan logs at startup to identify available indices.
- For Windows capture stability/noise, you can set:
  - `camera.backend`: `dshow` (recommended), `msmf`, or `auto`
  - `camera.read_retry_count` and `camera.read_retry_delay_ms`
  - `camera.reconnect_on_read_failure` to auto-reopen camera if frame grabbing fails
  - `camera.black_frame_luma_threshold` and `camera.black_frame_max_consecutive` to detect/recover from black-screen camera feeds

## Pipeline State Machine

Implemented states:

- IDLE
- DETECTING
- FACE_LOCKED
- CAPTURING
- SAVING
- TRIGGERING_COMFY
- WAITING_FOR_COMFY
- CLEANING_INPUTS
- COLLECTING_OUTPUTS
- UPDATING_OBS
- TRIGGERING_TRANSITION
- CLEANING_OUTPUTS
- COOLDOWN
- READY

## Cleanup and File Lifecycle (Critical Behavior)

This project uses **per-run file manifests** (stored in memory via `RunContext`) and does not perform blind folder deletion by default.

### Input cleanup
- Captured face image is saved as `<run_id>_face.jpg` in input folder.
- After ComfyUI run completion is confirmed, app waits `cleanup.input_cleanup_delay_ms` then deletes only that run's input files.

### Output cleanup
- App snapshots output folder before trigger.
- After run completion, app collects only newly appeared output files.
- OBS updates image sources and triggers transition.
- App waits `cleanup.output_cleanup_delay_ms` to allow OBS refresh, then deletes only run output files.

### Safety controls
- Retry delete operations using:
  - `cleanup.cleanup_retry_count`
  - `cleanup.cleanup_retry_delay_ms`
- Failures are logged and app attempts to continue toward ready state.
- `cleanup.allow_full_folder_cleanup` is reserved and defaults to false.

## Runtime Controls

- `q`: quit app (`app.quit_key`)
- `c`: manual capture override (`app.manual_override_key`)

## Notes for Production Reliability

- Use a dedicated ComfyUI input/output subfolder for this installation.
- Keep ComfyUI workflow deterministic on where outputs are written.
- Verify OBS source names and target scene before showtime.
- Prefer running app in dedicated operator account/session.
- Keep logs visible in terminal for rapid troubleshooting.

## Known First-Version Scope

- Multi-camera architecture is prepared (camera scanning + configurable indices), but first pass runs a single primary stream.
- Face detector currently uses OpenCV Haar cascade for reliability and minimal dependencies.
- Designed for sequential single-job flow unless explicitly changed in config.

## Camera Failure Recovery Notes

- Transient camera read errors are retried and no longer crash the full app loop.
- If enabled, camera reconnect is attempted automatically on read failures.
- On reconnect, the app advances to the next backend candidate (on Windows: `dshow` → `msmf` → `auto`) to recover from backend-specific failures.
- If a camera opens but only returns dark/black frames, the app treats this as a read failure after a threshold and automatically cycles camera/backend candidates.
- If you see backend-specific OpenCV warnings, switch `camera.backend` between `dshow` and `msmf`.

## ComfyUI Failure Behavior

- If ComfyUI returns an error when queueing `/prompt`, the app now logs a concise HTTP+response summary.
- The app enters cooldown (using capture cooldown timing) before another trigger attempt, avoiding rapid-fire request spam.
- A dedicated Comfy backoff window is applied after Comfy failures to avoid hammering the server when it is unhealthy.
  - Base: `app.comfy_error_backoff_seconds`
  - Max cap: `app.comfy_error_backoff_max_seconds`
  - Backoff increases exponentially with repeated failures and resets after a successful run.
- Any input image captured for the failed run is cleaned up immediately so failed attempts do not accumulate files.
