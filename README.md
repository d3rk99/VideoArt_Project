# Interactive Photo/Art Installation Pipeline (Python)

A Windows-first Python application for installation workflows:

1. Detect face from webcam preview.
2. Capture a still image once face lock is stable.
3. Save capture into a configured ComfyUI input folder.
4. Trigger an existing ComfyUI workflow via API.
5. Wait for generation completion.
6. Update OBS image sources and trigger transition.
7. Clean up run-specific input/output files safely.

## Split Architecture Overview

The pipeline now supports two execution modes via `mode.execution_mode`:

- **local** (default): matches the original single-machine behavior where the laptop both captures faces and runs ComfyUI locally.
- **remote_bridge**: laptop handles camera/OBS/controller duties while a main PC on the same WireGuard VPN hosts ComfyUI plus a bridge API service.

### Laptop responsibilities
- Face detection/capture and all state machine logic.
- Upload captured faces to the bridge via HTTP over WireGuard.
- Poll job status, download exactly 5 results per run, and update the existing OBS `Art_Staging` scene before triggering transitions.
- Cache downloaded results locally under `local_paths.downloaded_results_dir` so OBS never reads directly from network shares.

### Main PC responsibilities
- Run ComfyUI in API mode with the existing workflow JSON.
- Run the FastAPI-based bridge server (`python -m installation_app.main --config config.yaml --run-bridge`).
- Accept uploads, copy them into the ComfyUI input folder using the fixed filename expected by the workflow, trigger generation, collect outputs, and expose them per-job.
- Perform safe cleanup of per-job manifests, Comfy outputs, and uploads either when the laptop issues `DELETE /api/jobs/{id}` or when a TTL expires.

### Network & security assumptions
- All HTTP traffic stays on a WireGuard private subnet (e.g., `10.0.0.0/24`). No public exposure or SMB shares are required or supported.
- Optional API key header `X-API-Key` can be enabled in both laptop (`remote.api_key`) and bridge (`bridge.api_key`) configs.
- Keep Windows Firewall scoped to the WireGuard interface/IPs; the README now includes firewall guidance plus troubleshooting notes.

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
        ├── comfy_browser_trigger.py
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

## Execution Modes & Config Sections

Key YAML sections to review:

- `mode.execution_mode`: `"local"` (original behavior) or `"remote_bridge"` (split deployment). Remote mode requires `remote.enabled: true`.
- `remote`: laptop-side HTTP client settings (`bridge_base_url`, optional `api_key`, request timeout/poll intervals).
- `local_paths`: laptop-only storage for temporary captures and downloaded bridge results. OBS always points at files here when running remote mode.
- `bridge`: server-side options (host/port binding, optional API key, job root directory, TTL minutes, expected output count). The bridge keeps per-job manifests under `jobs_root_dir` and never deletes folders blindly.

Both the laptop and bridge can continue to share the same `config.yaml` format; just ensure each machine updates host-specific values (e.g., the bridge's `folders.capture_input_dir` should point at ComfyUI's input folder on the main PC, while the laptop can keep a local capture temp folder for archival/reference).

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

### Remote bridge runtime flow (remote_bridge mode)
1. Laptop detects a stable face, captures a frame, and saves it under `local_paths.capture_temp_dir`.
2. Laptop uploads the capture via `POST /api/jobs` to the bridge IP (WireGuard address such as `http://10.0.0.2:9000`). The request can optionally include `X-API-Key` for authentication.
3. Bridge saves the upload inside `bridge.jobs_root_dir/<job_id>/input/` and copies it into the configured ComfyUI input folder using the fixed filename defined in `folders.capture_input_filename` (e.g., `input_face.jpg`) so existing workflows remain unmodified.
4. Bridge queues the ComfyUI workflow via API mode (`/prompt`) and tracks the resulting `prompt_id`.
5. Bridge waits for completion and collects new output files, copying exactly `bridge.expected_output_count` results into `bridge.jobs_root_dir/<job_id>/results/`.
6. Laptop polls `GET /api/jobs/{job_id}` until status becomes `completed` (statuses: `queued`, `running`, `completed`, `failed`, `timed_out`).
7. Laptop downloads the zipped results from `GET /api/jobs/{job_id}/results`, extracts them into `local_paths.downloaded_results_dir/<job_id>/`, and hands those local files to the OBS update flow.
8. Laptop updates all 5 OBS sources, triggers the existing transition, and executes the same staging sequence as local mode.
9. Laptop optionally calls `DELETE /api/jobs/{job_id}` when the run is finished; otherwise the bridge cleans up automatically after `bridge.result_ttl_minutes`.
10. Bridge removes only the job-specific manifest/input/output files (no blind folder deletion) either on DELETE or TTL expiration.

## Batch Script Crash Visibility

Both `install.bat` and `run.bat` now pause on errors so the terminal stays open and operator-visible crash messages can be read before closing the window.

## Bridge Operations

Main PC (ComfyUI host):

```bat
.venv\Scripts\activate
set PYTHONPATH=%CD%\src
python -m installation_app.main --config config.yaml --run-bridge
```

- The FastAPI server listens on `bridge.host:bridge.port` (default `0.0.0.0:9000`). Bind to your WireGuard interface IP or keep firewall scoped to VPN addresses.
- Health endpoints:
  - `GET /api/health` â†’ basic service heartbeat (no auth required).
  - `GET /api/health/comfy` â†’ tests ComfyUI connectivity from the bridge host.
- Job endpoints require `X-API-Key` when `bridge.api_key` is non-empty.
- Jobs and artifacts are stored under `bridge.jobs_root_dir/<job_id>/` (input, results, manifest). TTL cleanup removes only these per-job directories plus recorded Comfy output files.

Laptop quick test:

```bat
.venv\Scripts\activate
set PYTHONPATH=%CD%\src
python -m installation_app.main --config config.yaml --test-remote-bridge
```

This issues the same health checks the controller performs at startup.

## WireGuard Deployment Notes
- Assign static peer IPs inside your WireGuard config (e.g., laptop `10.0.0.3`, bridge `10.0.0.2`) and use that address in `remote.bridge_base_url`.
- Limit Windows Firewall rules for the bridge port to the WireGuard interface so the FastAPI server is not reachable from public adapters.
- Verify MTU/keepalive settings so large result downloads (zipped 5-image bundle) are not truncated under high latency.
- Keep DNS/hostname resolution localâ€”all API URLs should be direct WireGuard IPs to avoid leaking traffic outside the tunnel.

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

- Remote bridge test (see above).

## Required Customization

### 1) ComfyUI workflow file path
Set in `comfyui.workflow_file`.

- Must point to your existing ComfyUI API prompt/workflow JSON file.
- The app **does not** redesign your workflow.

### ComfyUI trigger mode
Set in `comfyui.trigger_mode`:

- `api` (default): queues `/prompt` directly using workflow JSON.
- `browser_ui` (experimental): opens a visible ComfyUI page via Playwright and triggers queue from the editor UI (Ctrl+Enter).

`browser_ui` notes:
- Requires the correct workflow to already be loaded in the visible ComfyUI editor tab.
- Designed for debug/demo use and is more fragile than API mode.
- Uses Ctrl+Enter first, with a minimal Queue/Run button-click fallback.
- To reduce accidental double-triggering, default config uses:
  - `ui_trigger_retry_count: 0`
  - `ui_click_fallback_enabled: false`

### 2) ComfyUI input/output folders
Set in `folders.capture_input_dir` and `folders.comfy_output_dir`.

- `capture_input_dir`: where this app writes captured faces.
- `capture_input_filename`: filename written into the input directory (default `input_face.jpg`).
  - This is critical: many ComfyUI `LoadImage` nodes are configured for a fixed filename.
  - If your workflow expects fixed input, keep this fixed and **do not** use `{run_id}`.
- `comfy_output_dir`: where ComfyUI writes generated output images.

### 3) OBS source names
Set in `obs.image_sources`.

- Must match existing OBS image source names exactly.
- If multiple sources are configured but fewer images are generated, the last image is reused.
- Required staging architecture:
  - `obs.staging_scene: "Art_Staging"`
  - 5 image sources in that scene:
    - `art_slot_1`
    - `art_slot_2`
    - `art_slot_3`
    - `art_slot_4`
    - `art_slot_5`

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
- App defers deleting current run outputs until after a *later* successful run has loaded replacement images into OBS.
- After replacement is confirmed, app waits `cleanup.output_cleanup_delay_ms` and deletes only the prior run's output files.

### Safety controls
- Retry delete operations using:
  - `cleanup.cleanup_retry_count`
  - `cleanup.cleanup_retry_delay_ms`
- Failures are logged and app attempts to continue toward ready state.
- `cleanup.allow_full_folder_cleanup` is reserved and defaults to false.

## Runtime Controls

- `q`: quit app (`app.quit_key`)
- `c`: manual capture override (`app.manual_override_key`)
- After each fully successful cycle (Comfy complete → OBS update/transition → cleanup/deferred cleanup), the app waits `app.post_cycle_detection_delay_ms` before resuming face detection (default `1000` ms).

## Browser UI Trigger (Experimental)

- Enable with:
  - `comfyui.trigger_mode: "browser_ui"`
  - `comfyui.browser_url` set to your ComfyUI page
- Runtime behavior:
  1) Open visible browser window to ComfyUI.
  2) Bring page to front and focus.
  3) Send `Ctrl+Enter` to queue current workflow.
  4) If shortcut trigger fails, try Queue/Run button fallback selectors.
- Important: in this mode, the app does **not** call `/prompt` directly.

## OBS Staging Transition Sequence

To avoid exposing new images on Program too early, the app uses this sequence:

1. Update all 5 image sources in the dedicated staging scene (`obs.staging_scene`).
2. Verify all 5 source slots were assigned.
3. Set staging scene to **Preview**.
4. Trigger configured transition (Preview → Program).
5. Wait `transition_duration_ms + post_transition_delay_ms`.
6. Delete previous run output files (current run files are retained until next replacement).

This ensures cleanup only happens after transition completion/safety delay.

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

## Troubleshooting (Remote Bridge)

- **Bridge unreachable**: verify the WireGuard tunnel is up on both machines, ensure Windows Firewall scopes the bridge port to WireGuard addresses only, and run `--test-remote-bridge` for a quick health probe. The FastAPI console log will also show inbound requests.
- **ComfyUI unreachable from bridge**: hit `GET http://<bridge>/api/health/comfy`. If it fails, confirm that `comfyui.server_url` resolves correctly on the main PC and that ComfyUI is running in API mode with the workflow JSON accessible to the bridge process.
- **Fewer than 5 outputs detected**: the bridge copies only new files from `folders.comfy_output_dir`. Ensure the existing workflow writes to that directory, confirm `bridge.expected_output_count` matches your OBS slot count (default 5), and review bridge logs for "expected N outputs" errors.
- **Timeout handling**: `comfyui.completion_timeout_seconds` applies to both local and remote execution. A timeout sets the job status to `timed_out`, returns HTTP 409 to the laptop, and keeps manifests for later inspection until TTL cleanup removes them.
- **Cleanup behavior**: the bridge saves everything under `bridge.jobs_root_dir/<job_id>/`. Jobs are deleted only when you call `DELETE /api/jobs/{job_id}` or when `bridge.result_ttl_minutes` expires. This avoids blind folder wipes and keeps artifacts available for debugging until explicitly cleared.
