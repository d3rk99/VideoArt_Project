# AI Portrait Gallery Automation

Production-minded prototype for an interactive video art installation that captures a visitor portrait, feeds it into themed ComfyUI workflows, and prepares outputs for OBS reveal.

## Project Overview

Current implementation status:
- **Phase 1 implemented**: camera loop, face detection, stable trigger, burst selection, session folder + manifest persistence.
- **Phase 2 implemented**: real ComfyUI API submission, completion polling, output collection, archive/latest sync, and session-linked generation records.
- **Phases 3-5 scaffolded**: OBS reveal/display behaviors and advanced orchestration extensions.

## Architecture Overview

Core components:
- `camera/`: camera connection, frame reading, face detection, burst-frame selection.
- `sessions/`: explicit state machine + session lifecycle manager.
- `storage/`: input/output directories, session archive files, manifest writing.
- `comfy/`: workflow loading/injection and ComfyUI API integration.
- `obs/`: websocket client and scene controller scaffolds.
- `utils/`: logging, timers, and image quality helpers.

## Folder Structure

```text
app/
  main.py
  config/
    settings.py
    settings.yaml
  camera/
  comfy/
  obs/
  sessions/
  storage/
  utils/
workflows/
input/
  live_capture/
  comfy_input/
output/
  latest/
  archive/
logs/
tests/
```


## Camera Reliability (Windows)

Camera backend settings live in `app/config/settings.yaml` under `camera:`.

- `backend`: `auto`, `dshow`, or `msmf`
- `reconnect_fail_threshold`: consecutive read failures before forced reconnect
- `reconnect_attempts` and `reconnect_delay_seconds`: reconnect policy
- `buffer_size`: OpenCV buffer size hint (default `1`)

On Windows, `backend: auto` resolves to DirectShow (`CAP_DSHOW`) for improved stability over MSMF in long-running gallery sessions.

### Camera self-test

```bash
python -m app.main --config app/config/settings.yaml --test-camera
```

This runs a short capture check, reports read failures, and prints pass/fail status.

## ComfyUI Configuration (Phase 2)

### Environment variables

Copy `.env.example` to `.env` and set:

```bash
COMFYUI_BASE_URL=http://127.0.0.1:8188
```

### `settings.yaml` keys used by Phase 2

```yaml
comfy:
  base_url: ${COMFYUI_BASE_URL}
  request_timeout_seconds: 10
  generation_timeout_seconds: 180
  poll_interval_seconds: 2
  output_filename_prefix_pattern: "{session_id}_{workflow}"

workflows:
  enabled:
    - mona_lisa
  files:
    mona_lisa: workflows/mona_lisa.json
```

## Workflow Injection Rules

When generation starts:
1. The app loads each workflow listed in `workflows.enabled`.
2. It injects the captured processed image path into every node that has `inputs.image`.
3. It injects a session/workflow prefix into every node that has `inputs.filename_prefix`.
4. It injects the processed capture filename (from `input/comfy_input/`) into workflow image input nodes.
5. It submits each injected workflow to ComfyUI `/prompt`.
6. After generation completes and expected outputs are collected (default 5), it clears `input/comfy_input/`.

Workflow templates must contain:
- at least one node with `inputs.image` (string value)
- at least one node with `inputs.filename_prefix`

If either field is missing, generation fails with a clear validation error.

## Running ComfyUI Health Check

```bash
python -m app.main --config app/config/settings.yaml --test-comfy
```

This command:
- loads configuration and environment variables
- checks `GET /system_stats`
- validates all enabled workflow JSON files are present and parseable

## Optional Developer Command

Generate from most recent processed image (without waiting for live camera trigger):

```bash
python -m app.main --config app/config/settings.yaml --generate-latest
```

## Phase 2 Session Flow

State usage:
- `PREPARING_INPUT`: image preprocessing + workflow payload preparation
- `GENERATING`: workflow submission + completion wait
- `COLLECTING_OUTPUTS`: output extraction/storage handoff

On success, flow transitions to `DISPLAYING` then `COOLDOWN` to preserve Phase 3 integration points.
On failure, flow transitions to `ERROR` then `COOLDOWN` with logged error details.

## Output Storage Layout

For each session:
- source captures and manifest are stored in `output/archive/<session_id>/`
- generated images are stored in `output/archive/<session_id>/generated/<workflow_name>/`
- `output/latest/` is refreshed with copies named `latest_1.*`, `latest_2.*`, ... for stable OBS consumption

Manifest (`manifest.json`) includes session info plus per-workflow generation records:
- prompt ID
- workflow name
- source input image
- generated output files
- started/finished timestamps
- error message (if any)

## Troubleshooting (ComfyUI)

- **Healthcheck fails**: verify ComfyUI is running and `COMFYUI_BASE_URL` is reachable.
- **Submission errors (HTTP 400)**: verify workflow JSON is valid API prompt format and image nodes receive a filename that exists in ComfyUI input.
- **Timeout waiting for completion**: increase `generation_timeout_seconds` or inspect ComfyUI queue load.
- **No outputs found**: check workflow output nodes and history payload content.
- **Downloaded file errors**: verify ComfyUI `/view` endpoint can serve generated output files.

## Testing

```bash
pytest -q
```

Unit tests cover workflow injection, Comfy output extraction, timeout/error handling, state machine behavior, and session manifest persistence behavior.
