from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from presscheck.compare import compare_results
from presscheck.runner import run_preflight
from presscheck.target_config import load_target_config

JobStatus = Literal["queued", "running", "done", "error"]
SeverityName = Literal["info", "warning", "error"]


@dataclass
class Job:
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    ok: bool


class JobCreatedResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running"]
    result_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class BySeverity(BaseModel):
    info: int
    warning: int
    error: int


class CheckSummary(BaseModel):
    check_id: str
    category: str
    severity: SeverityName
    count: int
    pages: list[int]


class ColorSummary(BaseModel):
    image_color_space_findings_by_family: dict[str, int]


class ReportSummary(BaseModel):
    total_findings: int
    by_severity: BySeverity
    by_check: list[CheckSummary]
    color: ColorSummary


class FindingResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    check_id: str
    category: str
    severity: SeverityName
    message: str
    analyzer: str
    evidence_type: str
    source_tool: str | None = None
    page: int | None = None
    object_ref: str | None = None
    observed: dict[str, Any] | None = None
    threshold: dict[str, Any] | None = None


class PreflightReportResponse(BaseModel):
    ok: bool
    failed: bool
    input: str
    fail_at: SeverityName
    summary: ReportSummary
    findings: list[FindingResponse]


class SummaryDelta(BaseModel):
    total_findings: int
    by_severity: BySeverity


class ComparisonSide(BaseModel):
    input: str
    ok: bool
    failed: bool
    summary: ReportSummary
    output: str | None = None


class ChangeEntry(BaseModel):
    category: str
    check_id: str
    severity: SeverityName
    before_count: int
    after_count: int
    delta: int
    before_pages: list[int]
    after_pages: list[int]
    added_pages: list[int]
    removed_pages: list[int]


class ComparisonChanges(BaseModel):
    added: list[ChangeEntry]
    resolved: list[ChangeEntry]
    worsened: list[ChangeEntry]
    improved: list[ChangeEntry]
    changed_pages: list[ChangeEntry]


class ComparisonReportResponse(BaseModel):
    ok: bool
    failed: bool
    regressed: bool
    fail_at: SeverityName
    before: ComparisonSide
    after: ComparisonSide
    summary_delta: SummaryDelta
    changes: ComparisonChanges


class JobStore:
    def __init__(self, max_workers: int = 1, ttl_seconds: int = 3600) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="presscheck-api")
        self._ttl = timedelta(seconds=ttl_seconds)

    def submit(self, work: Callable[[], dict[str, Any]]) -> Job:
        self._purge_expired()
        now = _now()
        job = Job(id=str(uuid.uuid4()), status="queued", created_at=now, updated_at=now)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id, work)
        return job

    def get(self, job_id: str) -> Job | None:
        self._purge_expired()
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str, work: Callable[[], dict[str, Any]]) -> None:
        self._update(job_id, status="running")
        try:
            result = work()
        except Exception as exc:
            self._update(job_id, status="error", error=str(exc))
            return
        self._update(job_id, status="done", result=result)

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.updated_at = _now()
            job.result = result
            job.error = error

    def _purge_expired(self) -> None:
        cutoff = _now() - self._ttl
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"done", "error"} and job.updated_at < cutoff
            ]
            for job_id in expired:
                del self._jobs[job_id]


def create_app(job_store: JobStore | None = None) -> FastAPI:
    store = job_store or JobStore(
        max_workers=int(os.environ.get("PRESSCHECK_API_WORKERS", "1")),
        ttl_seconds=int(os.environ.get("PRESSCHECK_API_JOB_TTL_SECONDS", "3600")),
    )
    app = FastAPI(title="Presscheck API", version="0.1.0")

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return {"ok": True}

    @app.post(
        "/v1/preflight-jobs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=JobCreatedResponse,
    )
    async def create_preflight_job(
        pdf: Annotated[UploadFile, File()],
        target: Annotated[UploadFile, File()],
    ) -> JobCreatedResponse:
        workspace = _new_workspace()
        pdf_path = await _save_upload(pdf, workspace, "input.pdf")
        target_path = await _save_upload(target, workspace, "target.yml")
        try:
            target_config = load_target_config(target_path)
        except ValueError as exc:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        display_name = pdf.filename or "input.pdf"

        def work() -> dict[str, Any]:
            try:
                result = run_preflight(pdf_path, target_config)
                result["input"] = display_name
                return result
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

        return _job_response(store.submit(work))

    @app.post(
        "/v1/compare-jobs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=JobCreatedResponse,
    )
    async def create_compare_job(
        before_pdf: Annotated[UploadFile, File()],
        after_pdf: Annotated[UploadFile, File()],
        target: Annotated[UploadFile, File()],
    ) -> JobCreatedResponse:
        workspace = _new_workspace()
        before_path = await _save_upload(before_pdf, workspace, "before.pdf")
        after_path = await _save_upload(after_pdf, workspace, "after.pdf")
        target_path = await _save_upload(target, workspace, "target.yml")
        try:
            target_config = load_target_config(target_path)
        except ValueError as exc:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        before_name = before_pdf.filename or "before.pdf"
        after_name = after_pdf.filename or "after.pdf"

        def work() -> dict[str, Any]:
            try:
                before_result = run_preflight(before_path, target_config)
                after_result = run_preflight(after_path, target_config)
                before_result["input"] = before_name
                after_result["input"] = after_name
                return compare_results(before_result, after_result)
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

        return _job_response(store.submit(work))

    @app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse, response_model_exclude_none=True)
    def get_job(job_id: str) -> JobStatusResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return _job_payload(job)

    @app.get(
        "/v1/jobs/{job_id}/result",
        response_model=PreflightReportResponse | ComparisonReportResponse,
        response_model_exclude_none=True,
    )
    def get_job_result(job_id: str) -> PreflightReportResponse | ComparisonReportResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.status != "done":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"job is {job.status}")
        assert job.result is not None
        return job.result

    return app


def _job_response(job: Job) -> dict[str, str]:
    return {
        "job_id": job.id,
        "status": job.status,
        "result_url": f"/v1/jobs/{job.id}/result",
    }


def _job_payload(job: Job) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
    if job.error is not None:
        payload["error"] = job.error
    return payload


def _new_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="presscheck-api-"))


async def _save_upload(upload: UploadFile, directory: Path, filename: str) -> Path:
    path = directory / filename
    data = await upload.read()
    if not data:
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"empty upload: {upload.filename}")
    path.write_bytes(data)
    return path


def _now() -> datetime:
    return datetime.now(UTC)


app = create_app()
