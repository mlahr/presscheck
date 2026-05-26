from __future__ import annotations

from pathlib import Path
from threading import Event
from time import sleep

from fastapi.testclient import TestClient

from presscheck.api import JobStore, create_app


def test_preflight_job_returns_result(monkeypatch) -> None:
    def fake_run_preflight(pdf: Path, _target_config) -> dict:
        return _result(str(pdf), [])

    monkeypatch.setattr("presscheck.api.run_preflight", fake_run_preflight)
    client = TestClient(create_app(JobStore()))

    response = client.post(
        "/v1/preflight-jobs",
        files={
            "pdf": ("upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "target": ("target.yml", _target_yaml(), "application/x-yaml"),
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] in {"queued", "running"}
    assert body["result_url"] == f"/v1/jobs/{body['job_id']}/result"

    job = _wait_for_job(client, body["job_id"], "done")
    assert job["status"] == "done"
    result = client.get(body["result_url"])
    assert result.status_code == 200
    assert result.json()["input"] == "upload.pdf"


def test_compare_job_returns_comparison_without_output_paths(monkeypatch) -> None:
    def fake_run_preflight(pdf: Path, _target_config) -> dict:
        if pdf.name == "before.pdf":
            return _result(str(pdf), [_check("fonts", "fonts.non_embedded", "error", 1, [1])])
        return _result(str(pdf), [])

    monkeypatch.setattr("presscheck.api.run_preflight", fake_run_preflight)
    client = TestClient(create_app(JobStore()))

    response = client.post(
        "/v1/compare-jobs",
        files={
            "before_pdf": ("before-upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "after_pdf": ("after-upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "target": ("target.yml", _target_yaml(), "application/x-yaml"),
        },
    )

    assert response.status_code == 202
    body = response.json()
    _wait_for_job(client, body["job_id"], "done")

    result = client.get(body["result_url"]).json()
    assert result["regressed"] is False
    assert result["before"]["input"] == "before-upload.pdf"
    assert result["after"]["input"] == "after-upload.pdf"
    assert "output" not in result["before"]
    assert "output" not in result["after"]


def test_invalid_target_returns_bad_request() -> None:
    client = TestClient(create_app(JobStore()))

    response = client.post(
        "/v1/preflight-jobs",
        files={
            "pdf": ("upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "target": ("target.yml", b"fail_at: error\n", "application/x-yaml"),
        },
    )

    assert response.status_code == 400
    assert "checks" in response.json()["detail"]


def test_unknown_job_returns_not_found() -> None:
    client = TestClient(create_app(JobStore()))

    response = client.get("/v1/jobs/not-a-job")

    assert response.status_code == 404


def test_result_conflicts_until_job_is_done(monkeypatch) -> None:
    release = Event()

    def fake_run_preflight(pdf: Path, _target_config) -> dict:
        release.wait(timeout=5)
        return _result(str(pdf), [])

    monkeypatch.setattr("presscheck.api.run_preflight", fake_run_preflight)
    client = TestClient(create_app(JobStore()))
    response = client.post(
        "/v1/preflight-jobs",
        files={
            "pdf": ("upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "target": ("target.yml", _target_yaml(), "application/x-yaml"),
        },
    )
    job_id = response.json()["job_id"]

    result = client.get(f"/v1/jobs/{job_id}/result")

    assert result.status_code == 409
    release.set()
    _wait_for_job(client, job_id, "done")


def test_worker_exception_records_error(monkeypatch) -> None:
    def fake_run_preflight(_pdf: Path, _target_config) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr("presscheck.api.run_preflight", fake_run_preflight)
    client = TestClient(create_app(JobStore()))
    response = client.post(
        "/v1/preflight-jobs",
        files={
            "pdf": ("upload.pdf", b"%PDF-1.4\n", "application/pdf"),
            "target": ("target.yml", _target_yaml(), "application/x-yaml"),
        },
    )
    job_id = response.json()["job_id"]

    job = _wait_for_job(client, job_id, "error")

    assert job["status"] == "error"
    assert job["error"] == "boom"


def test_healthz() -> None:
    client = TestClient(create_app(JobStore()))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_openapi_documents_job_response_fields() -> None:
    client = TestClient(create_app(JobStore()))

    schema = client.get("/openapi.json").json()

    create_response = schema["paths"]["/v1/preflight-jobs"]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"]
    assert create_response == {"$ref": "#/components/schemas/JobCreatedResponse"}
    assert set(schema["components"]["schemas"]["JobCreatedResponse"]["properties"]) == {
        "job_id",
        "status",
        "result_url",
    }
    result_response = schema["paths"]["/v1/jobs/{job_id}/result"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "anyOf" in result_response


def _wait_for_job(client: TestClient, job_id: str, status: str) -> dict:
    for _ in range(100):
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] == status:
            return job
        sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach status {status}")


def _target_yaml() -> bytes:
    return b"""
fail_at: error
checks:
  fonts.non_embedded:
    enabled: true
    severity: error
"""


def _result(input_path: str, checks: list[dict]) -> dict:
    by_severity = {"info": 0, "warning": 0, "error": 0}
    for check in checks:
        by_severity[check["severity"]] += check["count"]
    failed = by_severity["error"] > 0
    return {
        "ok": not failed,
        "failed": failed,
        "input": input_path,
        "fail_at": "error",
        "summary": {
            "total_findings": sum(by_severity.values()),
            "by_severity": by_severity,
            "by_check": checks,
            "color": {"image_color_space_findings_by_family": {}},
        },
        "findings": [],
    }


def _check(category: str, check_id: str, severity: str, count: int, pages: list[int]) -> dict:
    return {
        "category": category,
        "check_id": check_id,
        "severity": severity,
        "count": count,
        "pages": pages,
    }
