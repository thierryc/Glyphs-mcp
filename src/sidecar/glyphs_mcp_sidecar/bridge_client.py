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
        uncertain = {"execution": "uncertain", "jobId": (value or {}).get("jobId") or (value or {}).get("patch", {}).get("jobId")} if path in ("/v1/apply", "/v1/discard") else {}
        body = json.dumps(value or {}, separators=(",", ":")).encode("utf-8")
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

    def apply(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/apply", {"patch": patch})

    def operation(self, job_id: str) -> dict[str, Any]:
        return self._post("/v1/operation", {"jobId": job_id})

    def discard(self, job_id: str) -> dict[str, Any]:
        return self._post("/v1/discard", {"jobId": job_id})
