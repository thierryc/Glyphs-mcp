"""Native save-operation coordination kept separate from patch application."""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from typing import Any, Mapping


def request(value: Any, error_type) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise error_type("invalid_request", "save request must be an object")
    fields = {"saveId", "documentId", "saveMode", "previousPath", "path"}
    if set(value) != fields:
        raise error_type("invalid_request", "save request fields are incomplete or unexpected")
    save_id = str(value.get("saveId") or "").strip()
    document_id = str(value.get("documentId") or "").strip()
    mode = str(value.get("saveMode") or "")
    previous = value.get("previousPath")
    target = str(value.get("path") or "").strip()
    if not save_id or len(save_id) > 100 or not document_id or len(document_id) > 100:
        raise error_type("invalid_request", "saveId and documentId are required")
    if mode not in {"save", "save_as"}:
        raise error_type("invalid_request", "saveMode must be save or save_as")
    if previous is not None:
        previous = str(previous).strip()
        if not previous:
            raise error_type("invalid_request", "previousPath must be nonempty or null")
    path = Path(target)
    if not path.is_absolute() or path.suffix.lower() not in {".glyphs", ".glyphspackage"}:
        raise error_type(
            "invalid_destination",
            "save path must be an absolute .glyphs or .glyphspackage path",
        )
    return {
        "saveId": save_id,
        "documentId": document_id,
        "saveMode": mode,
        "previousPath": previous,
        "path": str(path.resolve(strict=False)),
    }


def same_path(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return left in (None, "") and right in (None, "")
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(
        os.path.realpath(str(right))
    )


def preflight(core, value, error_type, *, accepting_job_id=None, generic=False):
    document_id = value["documentId"]
    with core._lock:
        core._check_owner(document_id, ignore_job_id=accepting_job_id)
        if generic and any(
            item["documentId"] == document_id
            and item["status"] in {"applied", "accepting", "saved", "accept_uncertain"}
            for item in core._operations.values()
        ):
            raise error_type(
                "job_acceptance_required",
                "This document has an applied job; use accept_job instead",
            )
    state = core.adapter.document_state(document_id)
    if not same_path(state.get("path"), value.get("previousPath")):
        raise error_type("stale_document", "the document path changed before saving")
    if state.get("dirty") not in (True, False):
        raise error_type(
            "document_dirty_state_unavailable",
            "Glyphs did not expose a reliable document dirty state",
        )
    target = value["path"]
    same = same_path(state.get("path"), target)
    if value["saveMode"] == "save" and not same:
        raise error_type("stale_document", "a current-path save no longer targets the document path")
    if value["saveMode"] == "save_as" and same:
        raise error_type("stale_document", "the Save As destination became the current document path")
    for document in core.adapter.list_documents():
        other_id, other_path = str(document.get("id") or ""), document.get("path")
        if other_id == document_id or not other_path:
            continue
        if same_path(other_path, target):
            raise error_type(
                "destination_open_in_glyphs",
                "the save destination belongs to another open Glyphs document",
            )
        other = Path(str(other_path)).resolve(strict=False)
        wanted = Path(str(target)).resolve(strict=False)
        if other.suffix.lower() == ".glyphspackage":
            try:
                wanted.relative_to(other)
            except ValueError:
                pass
            else:
                raise error_type(
                    "destination_open_in_glyphs",
                    "the save destination is inside another open Glyphs package",
                )
        if wanted.suffix.lower() == ".glyphspackage":
            try:
                other.relative_to(wanted)
            except ValueError:
                pass
            else:
                raise error_type(
                    "destination_open_in_glyphs",
                    "the Save As package would contain another open Glyphs document",
                )
    if value["saveMode"] == "save_as" and os.path.lexists(target):
        raise error_type("destination_exists", "the Save As destination already exists")
    return state


def public(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "saveId": operation["saveId"],
        "documentId": operation["documentId"],
        "status": operation["status"],
        "native": copy.deepcopy(operation.get("native")),
        "error": copy.deepcopy(operation.get("error")),
    }


def begin_save(core, value: Any, error_type) -> dict[str, Any]:
    save_request = request(value, error_type)
    save_id = save_request["saveId"]
    with core._lock:
        existing = core._saves.get(save_id)
        if existing is not None:
            if existing["request"] != save_request:
                raise error_type("save_conflict", "save ID belongs to another request")
            return public(existing)
    preflight(core, save_request, error_type, generic=True)
    operation = {
        "saveId": save_id,
        "documentId": save_request["documentId"],
        "request": save_request,
        "status": "saving",
        "native": None,
        "error": None,
        "startedAt": time.time(),
        "finishedAt": None,
    }
    with core._lock:
        existing = core._saves.get(save_id)
        if existing is not None:
            if existing["request"] != save_request:
                raise error_type("save_conflict", "save ID belongs to another request")
            return public(existing)
        preflight(core, save_request, error_type, generic=True)
        finished = [key for key, item in core._saves.items() if item["status"] != "saving"]
        for key in finished[:-7]:
            del core._saves[key]
        core._saves[save_id] = operation
    try:
        native = core.adapter.save_document(
            save_request["documentId"], save_request["path"], save_request["saveMode"]
        )
        status = "saved" if native.get("nativeSaveSucceeded") is True else "save_unverified"
        error = None if status == "saved" else {
            "code": "save_verification_failed",
            "message": str(native.get("nativeError") or "the native save did not report success"),
            "details": dict(native),
        }
    except Exception as exc:
        error_value = core._error(exc)
        native = dict(error_value.details)
        status = "save_unverified" if native.get("writeAttempted") else "failed"
        error = error_value.as_dict()
    with core._lock:
        operation.update(status=status, native=native, error=error, finishedAt=time.time())
    return public(operation)


def operation(core, save_id: str, error_type) -> dict[str, Any]:
    with core._lock:
        value = core._saves.get(str(save_id))
        if value is None:
            raise error_type("save_not_found", "the bridge does not know this save")
        return public(value)


def begin_accept(core, job_id: str, value: Any, error_type) -> dict[str, Any]:
    save_request = request(value, error_type)
    identity = str(job_id)
    with core._lock:
        job = core._operations.get(identity)
        if job is None:
            raise error_type("job_not_found", "the bridge does not know this job")
        if save_request["saveId"] != identity or save_request["documentId"] != job["documentId"]:
            raise error_type("job_conflict", "the save request does not belong to this job")
        if job["status"] in {"accepting", "saved", "accepted", "accept_uncertain"}:
            existing = job.get("saveRequest")
            if existing is not None and existing != save_request:
                raise error_type("save_conflict", "the job is already accepting another destination")
            return core._public(job)
        if job["status"] != "applied":
            raise error_type("job_not_acceptable", "the job is not applied")
    preflight(core, save_request, error_type, accepting_job_id=identity)
    with core._lock:
        job = core._operations.get(identity)
        if job is None:
            raise error_type("job_not_found", "the bridge does not know this job")
        if job["status"] != "applied":
            return core._public(job)
        preflight(core, save_request, error_type, accepting_job_id=identity)
        job.update(
            status="accepting", saveRequest=save_request, acceptIndex=0,
            nativeSave=None, receipt=None, error=None, finishedAt=None,
        )
    core._schedule(job)
    return core._public(job)


def complete_accept(core, job_id, error_type, *, verified, receipt=None, error=None):
    with core._lock:
        job = core._operations.get(str(job_id))
        if job is None:
            raise error_type("job_not_found", "the bridge does not know this job")
        if job["status"] == "accepted":
            return core._public(job)
        if job["status"] not in {"saved", "accept_uncertain"}:
            raise error_type("job_not_acceptable", "the job has no completed native save")
        if verified:
            if not isinstance(receipt, Mapping):
                raise error_type("invalid_request", "verified acceptance requires a receipt")
            job.update(status="accepted", receipt=copy.deepcopy(dict(receipt)), error=None,
                       resolved=[], nativeStateBytes=0, finishedAt=time.time())
        else:
            failure = dict(error or {})
            job.update(status="accept_uncertain", error={
                "code": str(failure.get("code") or "save_verification_failed"),
                "message": str(failure.get("message") or "saved output could not be verified"),
                "details": dict(failure.get("details") or {}),
            }, resolved=[], nativeStateBytes=0, finishedAt=time.time())
        return core._public(job)


def run_accept_chunk(core, job, error_type) -> bool:
    changes = job["resolved"]
    deadline = time.perf_counter() + core.chunk_seconds
    processed = 0
    while processed < core.chunk_limit and time.perf_counter() < deadline:
        index = int(job.get("acceptIndex") or 0)
        if index >= len(changes):
            save_request = job["saveRequest"]
            preflight(core, save_request, error_type, accepting_job_id=job["jobId"])
            try:
                native = core.adapter.save_document(
                    job["documentId"], save_request["path"], save_request["saveMode"]
                )
                if native.get("nativeSaveSucceeded") is not True:
                    failure = error_type(
                        "save_verification_failed",
                        str(native.get("nativeError") or "the native save did not report success"),
                        details=dict(native),
                    )
                    with core._lock:
                        job.update(status="accept_uncertain", nativeSave=native,
                                   error=failure.as_dict(), finishedAt=time.time())
                    return True
            except Exception as exc:
                failure = core._error(exc)
                attempted = bool(failure.details.get("writeAttempted"))
                with core._lock:
                    job.update(
                        status="accept_uncertain" if attempted else "applied",
                        nativeSave=dict(failure.details), error=failure.as_dict(),
                        finishedAt=time.time() if attempted else None,
                        acceptIndex=0 if not attempted else job.get("acceptIndex", 0),
                        saveRequest=job.get("saveRequest") if attempted else None,
                    )
                return True
            with core._lock:
                job.update(status="saved", nativeSave=native, error=None, finishedAt=time.time())
            return True

        change = changes[index]
        expected = (
            change["afterHash"]
            if change["kind"] in {"translate", "start_node", "outline", "native_action"}
            else change["after"]
        )
        observed = core.adapter.current_value(job["documentId"], change)
        if not core._same_value(observed, expected):
            target = {key: value for key, value in change.items()
                      if key not in {"before", "after", "beforeHash", "afterHash", "nativeBefore", "nativeAfter"}}
            raise error_type(
                "target_conflict", "an applied target changed before the job could be accepted",
                details={"target": target, "expected": expected, "observed": observed},
            )
        job["acceptIndex"] = index + 1
        processed += 1
    return False
