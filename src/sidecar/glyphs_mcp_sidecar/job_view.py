"""Bounded public job evidence shared by tools and chat workflows."""
from typing import Any, Mapping
from .lifecycle import activity

def public_job(job: Mapping[str, Any], *, include_preview: bool = True) -> dict[str, Any]:
    status = str(job["status"])
    result = {
        "id": job["id"],
        "checkpointEnabled": bool(job.get("checkpointPolicy")),
        "status": status,
        "summary": job.get("summary"),
        "resultKind": job.get("resultKind") or "mutation",
        "changeCount": int(job.get("changeCount") or 0),
        "sample": list(job.get("sample") or []),
        "report": job.get("report"),
        "manifest": job.get("manifest"),
        "error": job.get("error"),
        "outcome": job.get("outcome"),
        "receipt": job.get("receipt"),
        "entryPoint": job.get("entryPoint"),
        "inputKind": job.get("inputKind", "document"),
        "bridgeOperation": job.get("bridgeOperation"),
        "activity": activity(job),
        "message": (
            "Review the change in Glyphs. Call accept_job to verify and save it; Undo is per glyph. Revert or discard_job restores the whole job."
            if status == "applied"
            else "Review the verified manifest and report. Call accept_job with a new absolute destination directory to publish it."
            if status == "ready" and job.get("resultKind") == "artifact"
            else None
        ),
    }
    if status == "applied" and job.get("request", {}).get("kind") == "dimensions_edit":
        result["message"] = "Dimensions changed without saving. Native document Undo/Redo or discard_job restores the notes. Save separately when authorized."
    if job.get('resultKind') == 'historical_restore':
        result['changeCount'] = None
        result['message'] = 'Whole-font historical reload. Keep or save separately; selective Undo is unavailable.'
    if job.get('resultKind') == 'script':
        evidence = (job.get('bridgeOperation') or {}).get('scriptResult') or {}
        result['changeCount'] = None
        result['message'] = ('Script ready. Use the conversation Run action when execution is authorized.' if status == 'ready'
                             else 'Execution evidence does not verify the intended result. Restore saved version reloads the whole font.')
    if not include_preview:
        result.pop("sample")
        if isinstance(result["report"], dict):
            result["report"] = {k: v for k, v in result["report"].items() if k not in {"sample", "review", "output", "manifest", "targets"}}
        result["previewIncluded"] = False
    return result
