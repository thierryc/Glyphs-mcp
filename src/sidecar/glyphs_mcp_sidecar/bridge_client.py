"""Small standard-library client for the local Glyphs bridge."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BridgeClientError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class BridgeClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, path: str, value: dict[str, Any] | None = None) -> Any:
        request = value or {}
        save = request.get("save") if isinstance(request.get("save"), dict) else {}
        uncertain = {}
        if path in ("/v1/apply", "/v1/discard", "/v1/accept", "/v1/save", "/v1/script/run", "/v1/script/finish", "/v1/script/restore-saved"):
            patch = request.get("patch") if isinstance(request.get("patch"), dict) else {}
            uncertain["execution"] = "uncertain"
            job_id = request.get("jobId") or patch.get("jobId") or (request.get("script") or {}).get("jobId")
            save_id = request.get("saveId") or save.get("saveId")
            if job_id:
                uncertain["jobId"] = job_id
            if save_id:
                uncertain["saveId"] = save_id
        body = json.dumps(value or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > 4 * 1024 * 1024:
            raise BridgeClientError('request_too_large', 'bridge request exceeds 4 MiB; reduce script source or target manifest')
        request = Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read())
            except Exception:
                raise BridgeClientError("bridge_http_error", str(exc), uncertain) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise BridgeClientError("bridge_unavailable", "Glyphs bridge is unavailable", uncertain) from exc
        except (ValueError, TypeError) as exc:
            raise BridgeClientError("bridge_response_invalid", "Glyphs bridge returned an invalid response", uncertain) from exc
        if not isinstance(payload, dict) or not payload.get("ok"):
            error = payload.get("error") if isinstance(payload, dict) else {}
            raise BridgeClientError(
                str((error or {}).get("code") or "bridge_failed"),
                str((error or {}).get("message") or "Glyphs bridge request failed"),
                dict((error or {}).get("details") or {}),
            )
        return payload.get("data")

    def status(self) -> dict[str, Any]:
        return self._post("/v1/status")

    def documents(self) -> list[dict[str, Any]]:
        return self._post("/v1/documents")

    def read_entities(self, document_id: str, entities: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
        return self._post(
            "/v1/entities",
            {"documentId": document_id, "entities": entities, "fields": fields},
        )

    def compile_features(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/compile-features", {"compile": request})

    def apply(self, patch: dict[str, Any], *, approved_overwrites=None) -> dict[str, Any]:
        return self._post("/v1/apply", {"patch": patch, **({"approvedOverwrites": approved_overwrites} if approved_overwrites is not None else {})})

    def review_script(self, request):
        return self._post('/v1/script/review', {'script': request})

    def reviewed_script(self, job_id):
        return self._post('/v1/script/reviewed', {'jobId': job_id})

    def acknowledge_checkpoint_restore(self, identity):
        return self._post('/v1/checkpoint/finish', {'jobId': identity})

    def restore_checkpoint(self, request):
        return self._post('/v1/checkpoint/restore', {'restore': request})

    def restore_saved_script(self, request):
        return self._post('/v1/script/restore-saved', {'script': request})

    def run_script(self, request):
        return self._post('/v1/script/run', {'script': request})

    def finish_script(self, job_id):
        return self._post('/v1/script/finish', {'jobId': job_id})

    def prepare_typed(self, request):
        return self._post("/v1/edit/prepare", {"preparation": request})

    def prepared_typed(self, job_id):
        return self._post("/v1/edit/prepared", {"jobId": job_id})

    def finish_edit(self, job_id):
        return self._post('/v1/edit/finish', {'jobId': job_id})

    def operation(self, job_id: str) -> dict[str, Any]:
        return self._post("/v1/operation", {"jobId": job_id})

    def discard(self, job_id: str) -> dict[str, Any]:
        return self._post("/v1/discard", {"jobId": job_id})

    def accept(self, job_id: str, save: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/accept", {"jobId": job_id, "save": save})

    def complete_accept(
        self,
        job_id: str,
        *,
        verified: bool,
        receipt: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/v1/accept/complete",
            {
                "jobId": job_id,
                "verified": bool(verified),
                "receipt": receipt,
                "error": error,
            },
        )

    def save(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/save", {"save": request})

    def save_operation(self, save_id: str) -> dict[str, Any]:
        return self._post("/v1/save-operation", {"saveId": save_id})
