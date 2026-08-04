# encoding: utf-8

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


GITHUB_LATEST_RELEASE_API = (
    "https://api.github.com/repos/thierryc/Glyphs-mcp/releases/latest"
)
GITHUB_RELEASE_PAGE_ROOT = (
    "https://github.com/thierryc/Glyphs-mcp/releases/tag"
)
UPDATE_API_URL_ENV = "GLYPHS_MCP_UPDATE_API_URL"
UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
UPDATE_CHECK_TIMEOUT_SECONDS = 10
MAX_RELEASE_METADATA_BYTES = 256 * 1024
UPDATE_USER_AGENT = "Glyphs-MCP-update-checker"

UPDATE_CHECKS_ENABLED_KEY = "com.ap.cx.glyphs-mcp.updateChecksEnabled"
UPDATE_LAST_ATTEMPTED_AT_KEY = "com.ap.cx.glyphs-mcp.updateLastAttemptedAt"
UPDATE_LAST_CHECKED_AT_KEY = "com.ap.cx.glyphs-mcp.updateLastCheckedAt"
UPDATE_LATEST_VERSION_KEY = "com.ap.cx.glyphs-mcp.updateLatestVersion"
UPDATE_LAST_NOTIFIED_VERSION_KEY = (
    "com.ap.cx.glyphs-mcp.updateLastNotifiedVersion"
)

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_RELEASE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_LOOPBACK_HOSTS = frozenset(("127.0.0.1", "::1", "localhost"))


class UpdateCheckError(RuntimeError):
    """Raised when release metadata cannot be trusted or compared."""


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    release_url: str
    update_available: bool
    checked_at: float


def parse_version(value: Any) -> Tuple[int, int, int]:
    text = str(value or "").strip()
    match = _VERSION_RE.fullmatch(text)
    if not match:
        raise UpdateCheckError(
            "Version {!r} is not a stable MAJOR.MINOR.PATCH version.".format(text)
        )
    return tuple(int(part) for part in match.groups())


def parse_release_tag(value: Any) -> Tuple[str, Tuple[int, int, int]]:
    text = str(value or "").strip()
    match = _RELEASE_TAG_RE.fullmatch(text)
    if not match:
        raise UpdateCheckError(
            "Release tag {!r} is not a stable vMAJOR.MINOR.PATCH tag.".format(text)
        )
    version = ".".join(match.groups())
    return version, tuple(int(part) for part in match.groups())


def release_url_for_version(version: str) -> str:
    parsed = parse_version(version)
    normalized = "{}.{}.{}".format(*parsed)
    return "{}/v{}".format(GITHUB_RELEASE_PAGE_ROOT, normalized)


def parse_release_metadata(
    payload: Any,
    current_version: str,
    *,
    checked_at: Optional[float] = None,
) -> UpdateCheckResult:
    if not isinstance(payload, Mapping):
        raise UpdateCheckError("GitHub release metadata is not an object.")
    if payload.get("draft") is not False:
        raise UpdateCheckError("GitHub returned a draft or incomplete release.")
    if payload.get("prerelease") is not False:
        raise UpdateCheckError("GitHub returned a prerelease.")
    published_at = payload.get("published_at")
    if not isinstance(published_at, str) or not published_at.strip():
        raise UpdateCheckError("GitHub returned an unpublished release.")

    latest_version, latest_key = parse_release_tag(payload.get("tag_name"))
    current_key = parse_version(current_version)
    return UpdateCheckResult(
        current_version=str(current_version),
        latest_version=latest_version,
        release_url=release_url_for_version(latest_version),
        update_available=latest_key > current_key,
        checked_at=float(time.time() if checked_at is None else checked_at),
    )


def cached_update_result(
    current_version: str,
    latest_version: str,
    *,
    checked_at: Optional[float] = None,
) -> UpdateCheckResult:
    payload = {
        "tag_name": "v{}".format(str(latest_version).strip()),
        "draft": False,
        "prerelease": False,
        "published_at": "cached",
    }
    return parse_release_metadata(
        payload,
        current_version,
        checked_at=checked_at,
    )


def _validated_endpoint(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise UpdateCheckError("The update API URL must not contain credentials.")
    if parsed.fragment:
        raise UpdateCheckError("The update API URL must not contain a fragment.")
    if parsed.scheme == "https" and parsed.hostname:
        return value
    if parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS:
        return value
    raise UpdateCheckError(
        "The update API URL must use HTTPS, except for a loopback test server."
    )


def update_api_url(environ: Optional[Mapping[str, str]] = None) -> str:
    values = os.environ if environ is None else environ
    override = str(values.get(UPDATE_API_URL_ENV, "") or "").strip()
    return _validated_endpoint(override or GITHUB_LATEST_RELEASE_API)


def fetch_update(
    current_version: str,
    *,
    endpoint: Optional[str] = None,
    timeout: float = UPDATE_CHECK_TIMEOUT_SECONDS,
    opener: Callable[..., Any] = urlopen,
    checked_at: Optional[float] = None,
) -> UpdateCheckResult:
    url = _validated_endpoint(endpoint or update_api_url())
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": UPDATE_USER_AGENT,
        },
        method="GET",
    )
    try:
        with opener(request, timeout=float(timeout)) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if int(status) != 200:
                raise UpdateCheckError(
                    "GitHub returned HTTP {}.".format(int(status))
                )
            raw = response.read(MAX_RELEASE_METADATA_BYTES + 1)
    except UpdateCheckError:
        raise
    except Exception as error:
        raise UpdateCheckError(
            "Could not retrieve GitHub release metadata: {}".format(error)
        ) from error

    if len(raw) > MAX_RELEASE_METADATA_BYTES:
        raise UpdateCheckError("GitHub release metadata is unexpectedly large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise UpdateCheckError(
            "GitHub release metadata is not valid UTF-8 JSON."
        ) from error
    return parse_release_metadata(
        payload,
        current_version,
        checked_at=checked_at,
    )


class UpdatePreferences:
    """Small adapter around Glyphs.defaults or a test dictionary."""

    def __init__(self, store: MutableMapping[str, Any]):
        self.store = store

    def _get(self, key: str, default: Any = None) -> Any:
        try:
            value = self.store[key]
        except Exception:
            return default
        return default if value is None else value

    @property
    def enabled(self) -> bool:
        value = self._get(UPDATE_CHECKS_ENABLED_KEY, True)
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off", "")
        return bool(value)

    def set_enabled(self, enabled: bool) -> None:
        self.store[UPDATE_CHECKS_ENABLED_KEY] = bool(enabled)

    @property
    def last_attempted_at(self) -> Optional[float]:
        value = self._get(UPDATE_LAST_ATTEMPTED_AT_KEY)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def last_checked_at(self) -> Optional[float]:
        value = self._get(UPDATE_LAST_CHECKED_AT_KEY)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def latest_version(self) -> Optional[str]:
        value = str(self._get(UPDATE_LATEST_VERSION_KEY, "") or "").strip()
        return value or None

    @property
    def last_notified_version(self) -> Optional[str]:
        value = str(
            self._get(UPDATE_LAST_NOTIFIED_VERSION_KEY, "") or ""
        ).strip()
        return value or None

    def check_is_due(
        self,
        *,
        now: Optional[float] = None,
        interval: float = UPDATE_CHECK_INTERVAL_SECONDS,
    ) -> bool:
        if not self.enabled:
            return False
        last_attempt = self.last_attempted_at
        if last_attempt is None:
            last_attempt = self.last_checked_at
        if last_attempt is None:
            return True
        current_time = float(time.time() if now is None else now)
        return current_time - last_attempt >= float(interval)

    def record_attempt(self, *, now: Optional[float] = None) -> None:
        attempted_at = float(time.time() if now is None else now)
        self.store[UPDATE_LAST_ATTEMPTED_AT_KEY] = attempted_at

    def record_result(self, result: UpdateCheckResult) -> None:
        self.store[UPDATE_LAST_ATTEMPTED_AT_KEY] = float(result.checked_at)
        self.store[UPDATE_LAST_CHECKED_AT_KEY] = float(result.checked_at)
        self.store[UPDATE_LATEST_VERSION_KEY] = result.latest_version

    def should_notify(self, latest_version: str) -> bool:
        return self.last_notified_version != str(latest_version)

    def mark_notified(self, latest_version: str) -> None:
        self.store[UPDATE_LAST_NOTIFIED_VERSION_KEY] = str(latest_version)
