"""Crash-conscious publication of verified job-private export artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4
from glyphs_mcp_protocol import canonical_json, validate_artifact_manifest
from .source import SourceError, source_hash


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _destination(value, error_type) -> Path:
    if not isinstance(value, str) or not value:
        raise error_type("destination_required", "artifact acceptance requires an absolute destination directory")
    path = Path(value)
    if not path.is_absolute():
        raise error_type("invalid_destination", "artifact destination must be absolute")
    if path.exists() or path.is_symlink():
        raise error_type("destination_exists", "artifact destination already exists")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise error_type("destination_parent_missing", "artifact destination parent must be an existing real directory")
    return path


def _validate_source(service, job, error_type):
    document = service._document(job["document"]["id"])
    if document.get("path") != job["document"].get("path"):
        raise error_type("stale_document", "the document path changed after export")
    if document.get("dirty") is not False:
        raise error_type("document_not_clean", "save the document before publishing its export")
    if document.get("generation") != job["document"].get("generation"):
        raise error_type("stale_document", "the document changed after export")
    try:
        observed = source_hash(Path(document["path"]))
    except SourceError as exc:
        raise error_type("source_unavailable", str(exc)) from exc
    if observed != job.get("sourceHash"):
        raise error_type("stale_source", "the saved source changed after export")
    return observed


def _validate_staging(service, job, manifest, error_type):
    root = service.jobs.path(job["id"]) / "artifacts"
    if not root.is_dir() or root.is_symlink():
        raise error_type("artifact_unavailable", "private artifact staging is unavailable")
    expected = {item["path"] for item in manifest["files"]}
    observed = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise error_type("artifact_conflict", "private staging contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise error_type("artifact_conflict", "private staging contains a special file")
        observed.add(path.relative_to(root).as_posix())
    if observed != expected:
        raise error_type("artifact_conflict", "private staging files differ from the verified manifest")
    for item in manifest["files"]:
        path = root / item["path"]
        if path.stat().st_size != item["size"] or _sha256(path) != item["sha256"]:
            raise error_type("artifact_conflict", "a staged artifact changed after verification")
    return root


def _manifest_hash(manifest) -> str:
    encoded = canonical_json(manifest).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _manifest_from_files(files):
    if not isinstance(files, list):
        raise ValueError("receipt files are unavailable")
    total = sum(item.get("size", -1) if isinstance(item, dict) else -1
                for item in files)
    return validate_artifact_manifest({"files": files, "totalBytes": total})


def _validate_published_tree(root: Path, manifest) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    expected = {item["path"] for item in manifest["files"]}
    observed = set()
    try:
        for path in root.rglob("*"):
            if path.is_symlink():
                return False
            if path.is_dir():
                continue
            if not path.is_file():
                return False
            observed.add(path.relative_to(root).as_posix())
        if observed != expected:
            return False
        return all(
            (root / item["path"]).stat().st_size == item["size"]
            and _sha256(root / item["path"]) == item["sha256"]
            for item in manifest["files"]
        )
    except (OSError, ValueError):
        return False


def valid_receipt(job, receipt) -> bool:
    """Validate a durable publication receipt against its immutable destination."""
    if not isinstance(receipt, dict):
        return False
    try:
        manifest = _manifest_from_files(receipt.get("files"))
        destination = Path(receipt.get("destination", ""))
    except (TypeError, ValueError):
        return False
    checks = (
        receipt.get("jobId") == job.get("id"),
        receipt.get("documentId") == job.get("document", {}).get("id"),
        receipt.get("sourceHash") == job.get("sourceHash"),
        receipt.get("verification") == "staged_artifacts_and_source_hash",
        destination.is_absolute(), receipt.get("manifestHash") == _manifest_hash(manifest),
    )
    return all(checks) and _validate_published_tree(destination, manifest)


def _recover_receipt(service, job):
    request = job.get("publishRequest")
    if not isinstance(request, dict):
        return None
    destination = Path(request.get("destination", ""))
    if not destination.is_absolute():
        return None
    try:
        manifest = validate_artifact_manifest(service.jobs.read_json(job["id"], "manifest.json"))
    except Exception:
        return None
    if not _validate_published_tree(destination, manifest):
        return None
    return {
        "jobId": job["id"], "documentId": job["document"]["id"],
        "destination": str(destination), "sourceHash": job.get("sourceHash"),
        "manifestHash": _manifest_hash(manifest), "files": manifest["files"],
        "verification": "staged_artifacts_and_source_hash",
        "publishedAt": destination.stat().st_mtime, "recovered": True,
    }


def reconcile(service, job):
    """Resolve an interrupted artifact publication without replaying export or copy."""
    receipt = None
    receipt_path = service.jobs.path(job["id"]) / "receipt.json"
    if receipt_path.is_file():
        try:
            candidate = service.jobs.read_json(job["id"], "receipt.json")
        except Exception:
            candidate = None
        if valid_receipt(job, candidate):
            receipt = candidate
    if receipt is None:
        receipt = _recover_receipt(service, job)
        if receipt is not None:
            service.jobs.write_json(job["id"], "receipt.json", receipt)
    if receipt is not None:
        accepted = service.jobs.update(job["id"], status="accepted", receipt=receipt,
                                       publishRequest=None, error=None)
        service.jobs.release_bulk_artifacts(job["id"])
        return accepted
    return service.jobs.update(job["id"], status="accept_uncertain", error={
        "code": "artifact_publication_unverified",
        "message": "Artifact publication was interrupted and its destination could not "
                   "be verified exactly. No export or publication was replayed.",
        "details": {
            "previousStatus": "accepting", "outcome": "unverified",
            "writeAttempted": True,
        },
    })


def _fsync_tree(root: Path) -> None:
    directories = {root}
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
            directories.add(path.parent)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        descriptor = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def accept(service, error_type, job, *, destination, include_preview=True):
    if job["status"] == "accepted":
        return service._public(job, include_preview=include_preview)
    if job["status"] != "ready":
        raise error_type("job_not_acceptable", "the artifact job is not ready")
    target = _destination(destination, error_type)
    observed_source = _validate_source(service, job, error_type)
    try:
        manifest = validate_artifact_manifest(service.jobs.read_json(job["id"], "manifest.json"))
    except Exception as exc:
        raise error_type("artifact_unavailable", "the verified artifact manifest is unavailable") from exc
    staging = _validate_staging(service, job, manifest, error_type)
    temporary = target.parent / (
        "." + target.name + ".glyphs-mcp-" + job["id"] + "-" + uuid4().hex)
    service.jobs.update(job["id"], status="accepting", error=None,
                        publishRequest={"destination": str(target)})
    try:
        temporary.mkdir(mode=0o700)
        for item in manifest["files"]:
            source = staging / item["path"]
            output = temporary / item["path"]
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source, output, follow_symlinks=False)
            output.chmod(0o600)
            if output.stat().st_size != item["size"] or _sha256(output) != item["sha256"]:
                raise error_type("artifact_publish_failed", "published copy failed hash verification")
        _fsync_tree(temporary)
        if target.exists() or target.is_symlink():
            raise error_type("destination_exists", "artifact destination appeared during publication")
        os.replace(temporary, target)
        parent_descriptor = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        receipt = {
            "jobId": job["id"], "documentId": job["document"]["id"],
            "destination": str(target), "sourceHash": observed_source,
            "manifestHash": _manifest_hash(manifest), "files": manifest["files"],
            "verification": "staged_artifacts_and_source_hash",
            "publishedAt": time.time(),
        }
        service.jobs.write_json(job["id"], "receipt.json", receipt)
        accepted = service.jobs.update(
            job["id"], status="accepted", receipt=receipt, publishRequest=None, error=None
        )
        service.jobs.release_bulk_artifacts(job["id"])
        return service._public(accepted, include_preview=include_preview)
    except Exception as exc:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        service.jobs.update(job["id"], status="ready", publishRequest=None)
        if isinstance(exc, error_type):
            raise
        raise error_type("artifact_publish_failed", str(exc) or type(exc).__name__) from exc
