"""Asynchronous external and ephemeral-live job preparation."""

from pathlib import Path

from glyphs_mcp_protocol import validate_patch, validate_worker_result

from .source import snapshot_source, source_hash
from .worker import WorkerError


def prepare_live_compile(service, job_id, cancel):
    try:
        job = service.jobs.get(job_id)
        service.jobs.update(job_id, phase="compiling_live")
        if cancel.is_set():
            raise WorkerError("job cancelled")
        fingerprint = source_hash(Path(job["document"]["path"]))
        report = service.bridge.compile_features({
            "jobId": job_id, "documentId": job["document"]["id"],
            "sourcePath": job["document"]["path"], "sourceHash": fingerprint,
            "generation": job["document"]["generation"],
        })
        result = validate_worker_result({
            "version": 1, "resultKind": "diagnostic", "jobId": job_id,
            "documentId": job["document"]["id"], "sourcePath": job["document"]["path"],
            "sourceHash": fingerprint, "generation": job["document"]["generation"],
            "summary": "OpenType compilation succeeded" if report.get("success") else "OpenType compilation failed",
            "report": report,
        })
        report_path = service.jobs.write_json(job_id, "report.json", result["report"])
        with service._lock:
            if cancel.is_set() or service.jobs.get(job_id)["status"] != "preparing":
                raise WorkerError("job cancelled")
            public_report = dict(result["report"]); public_report["path"] = str(report_path)
            service.jobs.update(
                job_id, status="completed", resultKind="diagnostic", sourceHash=fingerprint,
                summary=result["summary"], changeCount=0, sample=[], report=public_report,
            )
    except Exception as exc:
        _fail(service, job_id, cancel, exc)
    finally:
        _finish(service, job_id)


def prepare_external(service, job_id, cancel):
    try:
        job = service.jobs.get(job_id)
        service.jobs.update(job_id, phase="copying_source")
        if cancel.is_set():
            raise WorkerError("job cancelled")
        source_path, fingerprint = snapshot_source(
            Path(job["document"]["path"]), service.jobs.path(job_id)
        )
        if cancel.is_set():
            raise WorkerError("job cancelled")
        service.jobs.update(job_id, phase="preparing")
        prepared = service.worker.prepare(
            service.jobs.path(job_id), job["document"], job["request"],
            source_path, fingerprint, cancel,
        )
        result = validate_worker_result(prepared)
        report_path = service.jobs.path(job_id) / "report.json"
        report = result.get("report")
        if report is not None:
            service.jobs.write_json(job_id, "report.json", report)
        elif report_path.is_file():
            report = service.jobs.read_json(job_id, "report.json")
        if result["resultKind"] in ("diagnostic", "artifact"):
            _publish_nonmutation(service, job_id, cancel, result, report, report_path, fingerprint)
            return
        if result["resultKind"] != "mutation":
            raise WorkerError("unsupported prepared result")
        patch = validate_patch(result["patch"])
        service.jobs.write_json(job_id, "patch.json", patch)
        summary = _mutation_report(report, report_path)
        with service._lock:
            if cancel.is_set() or service.jobs.get(job_id)["status"] != "preparing":
                raise WorkerError("job cancelled")
            service.jobs.update(
                job_id, status="ready", resultKind="mutation", sourceHash=fingerprint,
                summary=patch["summary"], changeCount=len(patch["changes"]),
                sample=patch["changes"][:10], report=summary,
            )
    except Exception as exc:
        _fail(service, job_id, cancel, exc)
    finally:
        _finish(service, job_id)


def _publish_nonmutation(service, job_id, cancel, result, report, report_path, fingerprint):
    public_report = dict(report or {}); public_report["path"] = str(report_path)
    fields = dict(
        sourceHash=fingerprint, summary=result["summary"], changeCount=0,
        sample=[], report=public_report, resultKind=result["resultKind"],
    )
    status = "completed" if result["resultKind"] == "diagnostic" else "ready"
    if result["resultKind"] == "artifact":
        service.jobs.write_json(job_id, "manifest.json", result["manifest"])
        fields["manifest"] = result["manifest"]
    with service._lock:
        if cancel.is_set() or service.jobs.get(job_id)["status"] != "preparing":
            raise WorkerError("job cancelled")
        service.jobs.update(job_id, status=status, **fields)


def _mutation_report(report, path):
    if not report:
        return None
    rows = report.get("layers", report.get("pairs", report.get("targets", [])))
    summary = {
        "path": str(path), "claim": report["claim"],
        "layerCount" if "layers" in report else "pairCount" if "pairs" in report else "targetCount": len(rows),
        "sample": rows[:10],
        "unavailableCount": sum(row["status"] == "unavailable" for row in rows),
    }
    for name in ("action", "scope", "targetCount", "changedCount", "noChangeCount"):
        if name in report:
            summary[name] = report[name]
    if report.get("kind") == "dimensions_edit":
        # At most 100 entries: never hide an overwrite behind the sample limit.
        summary["targets"] = rows
        summary["requiredOverwrites"] = report["requiredOverwrites"]
    if report.get("warnings"):
        summary["warnings"] = list(report["warnings"])
    elif report.get("warning"):
        summary["warnings"] = [report["warning"]]
    return summary


def _fail(service, job_id, cancel, exc):
    with service._lock:
        cancelled = cancel.is_set() or str(exc) == "job cancelled"
        service.jobs.update(
            job_id, status="cancelled" if cancelled else "failed",
            error={"code": "cancelled" if cancelled else "job_failed", "message": str(exc)},
        )


def _finish(service, job_id):
    with service._lock:
        if service.jobs.get(job_id)["status"] in {"cancelled", "failed"}:
            service.jobs.release_bulk_artifacts(job_id)
        service._cancellations.pop(job_id, None)
