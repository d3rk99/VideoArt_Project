from __future__ import annotations

import io
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

from installation_app.config import Config

from .job_cleanup import JobCleanupManager
from .job_runner import JobRunner
from .job_store import JobStatus, JobStore


def create_bridge_app(config: Config, logger) -> FastAPI:
    job_store = JobStore(config.bridge.jobs_root_dir)
    runner = JobRunner(config, job_store, logger)
    cleanup_manager = JobCleanupManager(job_store, config.bridge, config.cleanup, logger)

    app = FastAPI(title="VideoArt Remote Bridge")

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        expected = config.bridge.api_key.strip()
        if expected and x_api_key != expected:
            raise HTTPException(status_code=401, detail="Invalid API key")

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("Starting bridge cleanup manager and validating ComfyUI connectivity")
        cleanup_manager.start()
        runner.comfy_client.health_check()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        logger.info("Stopping bridge services")
        cleanup_manager.stop()
        runner.shutdown()

    @app.get("/api/health")
    def health() -> dict[str, str | int]:
        return {"status": "ok", "jobs": len(job_store.list_job_ids())}

    @app.get("/api/health/comfy")
    def comfy_health() -> dict[str, str]:
        try:
            runner.comfy_client.health_check()
        except Exception as exc:  # pylint: disable=broad-except
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"status": "ok"}

    @app.post("/api/jobs")
    async def create_job(
        face_image: UploadFile = File(...),
        run_id: str | None = Form(default=None),
        _: None = Depends(require_api_key),
    ) -> JSONResponse:
        job_id = uuid.uuid4().hex
        record = job_store.create_job(job_id, run_id)
        upload_path = _save_upload(record.job_dir, face_image)
        job_store.update(job_id, upload_path=upload_path)
        runner.enqueue(job_id)
        logger.info("Accepted bridge job %s (run_id=%s)", job_id, run_id)
        return JSONResponse({"job_id": job_id, "status": JobStatus.QUEUED.value})

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, _: None = Depends(require_api_key)) -> JSONResponse:
        try:
            record = job_store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return JSONResponse(record.to_payload())

    @app.get("/api/jobs/{job_id}/results")
    def get_results(job_id: str, _: None = Depends(require_api_key)) -> StreamingResponse:
        try:
            record = job_store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if record.status != JobStatus.COMPLETED:
            raise HTTPException(status_code=409, detail=f"Job {job_id} is not complete")
        if not record.result_files:
            raise HTTPException(status_code=404, detail="Job results not found")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zipf:
            for path in record.result_files:
                if path.exists():
                    zipf.write(path, arcname=path.name)
        buffer.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="{job_id}_results.zip"'}
        return StreamingResponse(buffer, media_type="application/zip", headers=headers)

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str, _: None = Depends(require_api_key)) -> JSONResponse:
        try:
            deleted = cleanup_manager.cleanup_job(job_id, reason="client_request")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Job not found")
        return JSONResponse({"job_id": job_id, "deleted": True})

    return app


def _save_upload(job_dir: Path, upload: UploadFile) -> Path:
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    target = input_dir / "face_capture.jpg"
    with target.open("wb") as fout:
        shutil.copyfileobj(upload.file, fout)
    upload.file.close()
    return target


def run_bridge_server(config: Config, logger) -> None:
    app = create_bridge_app(config, logger)
    uvicorn.run(app, host=config.bridge.host, port=config.bridge.port)
