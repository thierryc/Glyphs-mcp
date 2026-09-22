"""Filesystem preflight and verification for explicit native document saves."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .bridge_client import BridgeClientError
from .source import SourceError, source_hash


SUPPORTED_SUFFIXES = frozenset({".glyphs", ".glyphspackage"})


class SaveError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        write_attempted: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.details = dict(details or {})
        self.write_attempted = bool(write_attempted)


def _absolute(value: str, label: str) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        raise SaveError("invalid_destination", f"{label} must be an absolute path")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SaveError(
            "unsupported_source_format",
            f"{label} must end in .glyphs or .glyphspackage",
        )
    if path.is_symlink():
        raise SaveError("unsafe_path", f"{label} must not be a symbolic link")
    return path.resolve(strict=False)


def _same_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return left is right
    try:
        if left.exists() and right.exists():
            return os.path.samefile(left, right)
    except OSError:
        pass
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
        str(right.resolve(strict=False))
    )


def _hash(path: Path, label: str) -> str:
    try:
        return source_hash(path)
    except SourceError as exc:
        raise SaveError("source_unavailable", f"{label}: {exc}") from exc


def prepare_save(
    save_id: str,
    document: Mapping[str, Any],
    destination: str | None,
    documents: Sequence[Mapping[str, Any]],
    *,
    job_id: str | None = None,
    job_source_hash: str | None = None,
) -> dict[str, Any]:
    document_id = str(document.get("id") or "")
    if not document_id:
        raise SaveError("invalid_request", "documentId is required")
    if document.get("dirty") not in (True, False):
        raise SaveError(
            "document_dirty_state_unavailable",
            "Glyphs did not expose a reliable document dirty state",
        )

    current_value = document.get("path")
    current = _absolute(str(current_value), "the current document path") if current_value else None
    if destination is None:
        if current is None:
            raise SaveError(
                "document_path_required",
                "A pathless document requires an explicit Save As destination",
            )
        target = current
        mode = "save"
    else:
        target = _absolute(str(destination), "destination")
        mode = "save_as"
    if mode == "save_as":
        if not target.parent.is_dir():
            raise SaveError(
                "destination_parent_missing",
                "The Save As destination parent directory does not exist",
            )
        if current is not None and current.suffix.lower() == ".glyphspackage":
            try:
                target.relative_to(current)
            except ValueError:
                pass
            else:
                raise SaveError(
                    "invalid_destination",
                    "The Save As destination cannot be inside the current Glyphs package",
                )

    for other in documents:
        if str(other.get("id") or "") == document_id or not other.get("path"):
            continue
        other_path = _absolute(str(other["path"]), "an open document path")
        if _same_path(other_path, target):
            raise SaveError(
                "destination_open_in_glyphs",
                "The save destination belongs to another open Glyphs document",
            )
        if other_path.suffix.lower() == ".glyphspackage":
            try:
                target.relative_to(other_path)
            except ValueError:
                pass
            else:
                raise SaveError(
                    "destination_open_in_glyphs",
                    "The save destination is inside another open Glyphs package",
                )
        if target.suffix.lower() == ".glyphspackage":
            try:
                other_path.relative_to(target)
            except ValueError:
                pass
            else:
                raise SaveError(
                    "destination_open_in_glyphs",
                    "The Save As package would contain another open Glyphs document",
                )

    if mode == "save_as" and os.path.lexists(target):
        raise SaveError(
            "destination_exists",
            "The Save As destination already exists; v2 never replaces it",
            details={"destination": str(target)},
        )

    before_hash = _hash(current, "the current Glyphs source is unavailable") if current else None
    return {
        "saveId": str(save_id),
        "jobId": str(job_id) if job_id else None,
        "documentId": document_id,
        "saveMode": mode,
        "previousPath": str(current) if current else None,
        "path": str(target),
        "dirtyBefore": bool(document.get("dirty")),
        "generationBefore": document.get("generation"),
        "sourceHashBefore": before_hash,
        "jobSourceHash": job_source_hash,
        "sourceChangedSinceJob": bool(
            job_source_hash is not None and before_hash is not None and before_hash != job_source_hash
        ),
    }


def verify_save(request: Mapping[str, Any], native: Mapping[str, Any]) -> dict[str, Any]:
    target = Path(str(request["path"]))
    previous = Path(str(request["previousPath"])) if request.get("previousPath") else None
    observed_path = native.get("path")
    details = {
        "saveId": request.get("saveId"),
        "jobId": request.get("jobId"),
        "expectedPath": str(target),
        "observedPath": observed_path,
        "dirtyAfter": native.get("dirty"),
        "nativeSaveSucceeded": native.get("nativeSaveSucceeded") is True,
        "writeAttempted": native.get("writeAttempted") is True,
        "saveMode": request.get("saveMode"),
        "previousPath": request.get("previousPath"),
        "sourceHashBefore": request.get("sourceHashBefore"),
        "sourceChangedSinceJob": bool(request.get("sourceChangedSinceJob")),
    }
    if native.get("nativeSaveSucceeded") is not True:
        raise SaveError(
            "save_verification_failed",
            str(native.get("nativeError") or "The native save did not report success"),
            details=details,
            write_attempted=bool(native.get("writeAttempted")),
        )
    if not observed_path or not _same_path(Path(str(observed_path)), target):
        raise SaveError(
            "save_verification_failed",
            "Glyphs did not retain the expected path after saving",
            details=details,
            write_attempted=True,
        )
    if native.get("dirty") is not False:
        raise SaveError(
            "save_verification_failed",
            "Glyphs still reports unsaved document changes after saving",
            details=details,
            write_attempted=True,
        )

    try:
        after_hash = _hash(target, "the saved Glyphs source is unavailable")
        original_after = _hash(previous, "the original Glyphs source is unavailable") if previous else None
    except SaveError as exc:
        exc.details.update(details)
        exc.write_attempted = True
        raise
    original_unchanged = None
    if request.get("saveMode") == "save_as" and previous is not None:
        original_unchanged = original_after == request.get("sourceHashBefore")
        if not original_unchanged:
            raise SaveError(
                "save_verification_failed",
                "Save As changed the original Glyphs source",
                details={**details, "originalSourceHashAfter": original_after},
                write_attempted=True,
            )

    return {
        "saveId": request["saveId"],
        "jobId": request.get("jobId"),
        "documentId": request["documentId"],
        "saveMode": request["saveMode"],
        "previousPath": request.get("previousPath"),
        "path": str(target),
        "dirtyBefore": request.get("dirtyBefore"),
        "dirtyAfter": False,
        "nativeSaveSucceeded": True,
        "writeAttempted": True,
        "sourceHashBefore": request.get("sourceHashBefore"),
        "sourceHashAfter": after_hash,
        "sourceChangedSinceJob": bool(request.get("sourceChangedSinceJob")),
        "originalSourceHashAfter": original_after,
        "originalSourceUnchanged": original_unchanged,
        "verification": "native_and_source_hash",
        "savedAt": time.time(),
    }


def bridge_request(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in ("saveId", "documentId", "saveMode", "previousPath", "path")
    }


def service_error(error: SaveError, error_type):
    details = dict(error.details)
    details.setdefault("writeAttempted", error.write_attempted)
    return error_type(error.code, error.message, details=details)


def find_document(documents, document_id, error_type):
    for document in documents:
        if document.get("id") == str(document_id):
            return document
    raise error_type("document_not_found", "the Glyphs document is no longer open")


def observed_details(service, request, native=None):
    details = {
        "saveId": request.get("saveId"),
        "jobId": request.get("jobId"),
        "documentId": request.get("documentId"),
        "saveMode": request.get("saveMode"),
        "previousPath": request.get("previousPath"),
        "expectedPath": request.get("path"),
        "sourceHashBefore": request.get("sourceHashBefore"),
        "sourceChangedSinceJob": bool(request.get("sourceChangedSinceJob")),
    }
    if isinstance(native, Mapping):
        details.update({
            "observedPath": native.get("path"),
            "dirtyAfter": native.get("dirty"),
            "nativeSaveSucceeded": native.get("nativeSaveSucceeded") is True,
            "writeAttempted": native.get("writeAttempted") is True,
        })
    try:
        document = next(
            (item for item in service.list_documents()
             if item.get("id") == request.get("documentId")),
            None,
        )
    except Exception:
        document = None
    if isinstance(document, Mapping):
        observed_path = document.get("path")
        details["observedPath"] = observed_path
        details["dirtyAfter"] = document.get("dirty")
        if observed_path:
            try:
                details["sourceHashObserved"] = source_hash(Path(str(observed_path)))
            except SourceError as exc:
                details["sourceHashObservedError"] = str(exc)
    return details


def reconcile_accepted(service, job):
    receipt = job.get("receipt")
    if not isinstance(receipt, Mapping):
        return job
    try:
        operation = service.bridge.complete_accept(
            job["id"], verified=True, receipt=dict(receipt)
        )
    except Exception:
        return job
    return service.jobs.update(job["id"], bridgeOperation=operation)


def valid_job_receipt(job, receipt):
    return bool(
        isinstance(receipt, Mapping)
        and receipt.get("saveId") == job.get("id")
        and receipt.get("jobId") == job.get("id")
        and receipt.get("documentId") == job.get("document", {}).get("id")
        and receipt.get("nativeSaveSucceeded") is True
        and receipt.get("verification") == "native_and_source_hash"
        and str(receipt.get("sourceHashAfter") or "").startswith("sha256:")
    )


def accept_job(service, error_type, job_id, *, destination=None, include_preview=True):
    job = service._job(job_id)
    service._require_available_operation(job)
    if job["status"] in {"accepted", "accept_uncertain"}:
        if job["status"] == "accepted":
            job = reconcile_accepted(service, job)
        return service._public(job, include_preview=include_preview)
    if job["status"] in {"applying", "accepting"}:
        current = service.get_job(job_id, include_preview=include_preview)
        job = service._job(job_id)
        if job["status"] != "applied":
            return current
    if job["status"] != "applied":
        raise error_type("job_not_acceptable", "the job is not applied")

    documents = service.list_documents()
    document = find_document(documents, job["document"]["id"], error_type)
    try:
        save_request = prepare_save(
            job["id"], document, destination, documents, job_id=job["id"],
            job_source_hash=job.get("sourceHash"),
        )
    except SaveError as exc:
        raise service_error(exc, error_type) from exc
    service.jobs.update(job["id"], status="accepting", saveRequest=save_request, error=None)
    try:
        operation = service.bridge.accept(job["id"], bridge_request(save_request))
    except Exception as exc:
        certain = isinstance(exc, BridgeClientError) and exc.details.get("execution") != "uncertain"
        service.jobs.update(
            job["id"], status="applied" if certain else "accepting",
            saveRequest=None if certain else save_request,
            error=service._error(exc).as_dict(),
        )
        raise service._error(exc) from exc
    job = service.jobs.update(
        job["id"],
        status={
            "applied": "applied", "accepting": "accepting", "saved": "accepting",
            "accepted": "accepted", "accept_uncertain": "accept_uncertain",
        }.get(operation.get("status"), "accepting"),
        bridgeOperation=operation, error=operation.get("error"),
    )
    if operation.get("status") == "saved":
        return complete_acceptance(service, job, operation, include_preview=include_preview)
    return service._public(job, include_preview=include_preview)


def complete_acceptance(service, job, operation, *, include_preview=True):
    save_request = job.get("saveRequest")
    if not isinstance(save_request, Mapping):
        error = {
            "code": "save_verification_failed",
            "message": "The durable save request is unavailable",
            "details": {"writeAttempted": True},
        }
        try:
            operation = service.bridge.complete_accept(job["id"], verified=False, error=error)
        except Exception:
            pass
        failed = service.jobs.update(
            job["id"], status="accept_uncertain", error=error, bridgeOperation=operation,
        )
        return service._public(failed, include_preview=include_preview)
    try:
        receipt = verify_save(save_request, operation.get("nativeSave") or {})
    except SaveError as exc:
        details = observed_details(
            service, save_request, operation.get("nativeSave") or {}
        )
        details.update(exc.details)
        details["writeAttempted"] = True
        error = {"code": exc.code, "message": exc.message, "details": details}
        try:
            operation = service.bridge.complete_accept(job["id"], verified=False, error=error)
        except Exception:
            pass
        failed = service.jobs.update(
            job["id"], status="accept_uncertain", error=error, bridgeOperation=operation,
        )
        return service._public(failed, include_preview=include_preview)

    service.jobs.write_json(job["id"], "receipt.json", receipt)
    try:
        confirmed = service.bridge.complete_accept(job["id"], verified=True, receipt=receipt)
    except Exception:
        confirmed = {**dict(operation), "status": "accepted", "receipt": receipt, "error": None}
    accepted = service.jobs.update(
        job["id"], status="accepted", receipt=receipt, error=None,
        bridgeOperation=confirmed,
    )
    service.jobs.release_bulk_artifacts(job["id"])
    return service._public(accepted, include_preview=include_preview)


def save_document(service, error_type, document_id, *, destination=None, on_prepared=None):
    identity = str(document_id)
    for job in service.jobs.records():
        if job.get("document", {}).get("id") != identity:
            continue
        if job["status"] == "applied":
            raise error_type(
                "job_acceptance_required", "This document has an applied job; use accept_job instead",
                details={"jobId": job["id"]},
            )
        if job["status"] in {"applying", "accepting", "discarding"}:
            raise error_type(
                "document_busy", "An MCP job is still changing this document",
                details={"jobId": job["id"]},
            )
        if job["status"] == "accepted":
            reconcile_accepted(service, job)
    documents = service.list_documents()
    document = find_document(documents, identity, error_type)
    save_id = "save_" + uuid4().hex
    try:
        save_request = prepare_save(save_id, document, destination, documents)
    except SaveError as exc:
        raise service_error(exc, error_type) from exc
    if on_prepared is not None:
        on_prepared(save_request)
    try:
        operation = service.bridge.save(bridge_request(save_request))
    except Exception as exc:
        if isinstance(exc, BridgeClientError) and exc.details.get("execution") == "uncertain":
            try:
                operation = service.bridge.save_operation(save_id)
            except Exception:
                error = service._error(exc)
                error.details.update(observed_details(service, save_request))
                error.details.update({"saveId": save_id, "writeAttempted": True})
                raise error from exc
        else:
            raise service._error(exc) from exc
    if operation.get("status") != "saved":
        error = operation.get("error") or {}
        details = dict(error.get("details") or {})
        details.update(observed_details(service, save_request, operation.get("native")))
        raise error_type(
            str(error.get("code") or "save_verification_failed"),
            str(error.get("message") or "The document was not verifiably saved"),
            details=details,
        )
    try:
        return verify_save(save_request, operation.get("native") or {})
    except SaveError as exc:
        details = observed_details(
            service, save_request, operation.get("native") or {}
        )
        details.update(exc.details)
        details.update({"saveId": save_id, "writeAttempted": True})
        raise error_type(exc.code, exc.message, details=details) from exc
