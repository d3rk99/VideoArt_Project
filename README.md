# AI Portrait Gallery Automation

Production-minded prototype for an interactive video art installation that captures a visitor portrait, feeds it into themed ComfyUI workflows, and reveals outputs through OBS.

## Project Overview

This repository is structured as a modular orchestration system (not a single script). It focuses on reliability, recoverability, and operator-friendly controls for gallery usage.

Current implementation status:
- **Phase 1 implemented**: camera loop, face detection, stable trigger, capture burst selection, session folder + manifest persistence.
- **Phases 2-5 scaffolded**: ComfyUI integration interfaces, OBS interfaces, workflow injection logic, and extension points.

## Architecture Overview

Core components:
- `camera/`: camera connection, frame reading, face detection, burst-frame selection.
- `sessions/`: explicit state machine + session lifecycle manager.
- `storage/`: input/output directories, session archive files, manifest writing.
- `comfy/`: workflow loading/injection and API client scaffolds.
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
requirements.txt
.env.example
```

## Setup Instructions

### 1) Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment variables

```bash
cp .env.example .env
# edit values as needed
```

### 3) Configure settings

Edit `app/config/settings.yaml`:
- camera index, preview mode, trigger/cooldown thresholds
- ComfyUI URL and timeouts
- OBS host/port/password and scene/source names
- enabled workflow names and files

### 4) Camera setup

- Attach USB webcam.
- Verify `camera.index` (usually `0`).
- Keep `preview_enabled: true` while tuning thresholds.

### 5) ComfyUI connection (Phase 2)

- Start ComfyUI API server.
- Confirm `COMFYUI_BASE_URL` in `.env`.
- Use `--test-comfy` placeholder (full healthcheck wiring is scaffolded).

### 6) OBS websocket setup (Phase 3)

- Enable obs-websocket in OBS.
- Configure host/port/password in `.env` + `settings.yaml`.
- Keep scene names aligned with your OBS project file.

## Running the App

### Dev mode (preview + tune thresholds)

```bash
python -m app.main --config app/config/settings.yaml
```

### Installation mode (recommended tweaks)

- Set `camera.preview_enabled: false`
- Set `app.debug: false`
- Adjust cooldown and stability thresholds for your gallery traffic.

### Manual controls (current)

- `--manual-reset`: returns immediately; placeholder for operator reset flow.
- `--manual-trigger`: reserved flag for explicit trigger mode.
- `--test-comfy`: reserved Phase 2 command path.
- `--test-obs`: reserved Phase 3 command path.

## State Machine

States:
- `IDLE`
- `DETECTING`
- `CAPTURING`
- `PREPARING_INPUT`
- `GENERATING`
- `COLLECTING_OUTPUTS`
- `DISPLAYING`
- `COOLDOWN`
- `ERROR`

Rules:
- only one active session at a time
- no trigger during active capture/generation/display/cooldown states
- every transition is logged

## Adding New ComfyUI Workflows

1. Place new workflow JSON in `workflows/`.
2. Add key/path mapping under `workflows.files` in `settings.yaml`.
3. Enable it in `workflows.enabled`.
4. Ensure workflow includes nodes with `image` input and `filename_prefix` output fields for automatic injection.


## Windows `.bat` Operator Scripts

Located in `scripts/`:
- `setup_env.bat`: creates `.venv` and installs dependencies.
- `run_tests.bat`: runs `pytest -q` in local venv.
- `run_app.bat`: launches the app with project config.
- `run_all.bat`: full local+container sanity pass (setup, tests, image build, container tests).
- `run_container.bat`: starts the app service through Docker Compose.

All `.bat` scripts pause before exiting so operators can read error output when launched by double-click. Pass `--no-pause` when chaining scripts.
`setup_env.bat` verifies `python --version`, falls back to `py -3 --version`, and if both fail it attempts a `winget` install of Python 3.11 before failing with instructions.

All batch scripts resolve the project root from the script location, so they can be launched from any working directory.
`run_all.bat` performs local checks first and, if Docker is missing, attempts automatic Docker Desktop install via `winget` before asking for a rerun.
`run_container.bat` also attempts Docker Desktop auto-install if Docker CLI is missing.

Example:

```bat
scripts\run_all.bat
```

## Contained Environment (Docker)

This project now includes `Dockerfile` and `docker-compose.yml` so checks can run in a clean isolated runtime.

### Build container

```bash
docker compose build
```

### Run tests inside container

```bash
docker compose run --rm tests
```

### Start app service inside container

```bash
docker compose up --build ai-portrait-gallery
```

> Note: Direct camera access from containers depends on host OS and Docker device permissions. For gallery deployment, local host execution is typically used for camera capture while containerized checks validate reproducibility.

## Troubleshooting

- **Camera unavailable**: verify index and device permissions.
- **No triggers**: lower `minimum_face_size`, adjust stable frame/seconds thresholds.
- **Too many accidental triggers**: raise stability thresholds and cooldown.
- **ComfyUI failures**: check base URL and API route availability.
- **OBS failures**: verify websocket enabled and password matches.

## Testing

Run:

```bash
pytest -q
```

Included tests cover:
- state transition logic
- session folder/session ID flow
- workflow JSON injection
- output path resolution
