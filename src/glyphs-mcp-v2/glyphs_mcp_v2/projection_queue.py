"""Pure per-Edit-view scheduling state for Reporter projections.

The AppKit-facing Reporter owns timers and native objects. This module owns
only deterministic state transitions so quiet-window, view-stability, token,
publication, and redraw behavior can be tested with a virtual clock.
"""

from __future__ import annotations

import itertools
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Iterable


LayerKey = tuple[str, str, str]


def _normalized(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, (tuple, list)):
        return tuple(_normalized(item) for item in value)
    return str(value)


@dataclass(frozen=True)
class ViewStamp:
    """Normalized native view state required for safe capture and redraw."""

    controller_identity: Hashable
    active_layer_key: LayerKey | None
    layer_cursor: Any
    scale: float
    viewport: Any
    bounds: Any
    selected_layer_origin: Any

    @classmethod
    def create(
        cls,
        *,
        controller_identity: Hashable,
        active_layer_key: LayerKey | None,
        layer_cursor: Any,
        scale: Any,
        viewport: Any,
        bounds: Any,
        selected_layer_origin: Any,
    ) -> "ViewStamp":
        return cls(
            controller_identity=controller_identity,
            active_layer_key=active_layer_key,
            layer_cursor=_normalized(layer_cursor),
            scale=float(_normalized(scale if scale is not None else 1.0)),
            viewport=_normalized(viewport),
            bounds=_normalized(bounds),
            selected_layer_origin=_normalized(selected_layer_origin),
        )


@dataclass(frozen=True)
class JobToken:
    """Identity of one content projection attempt for one Edit view."""

    session_identity: Hashable
    content_epoch: int
    active_key: LayerKey
    reference_fingerprint: str


@dataclass(frozen=True)
class PlanVersion:
    """Content address for one fully prepared visual plan."""

    active_key: LayerKey
    reference_fingerprint: str
    live_fingerprint: str


@dataclass(frozen=True)
class PreparedPlan:
    """Immutable plan and the content version that produced it."""

    version: PlanVersion
    plan: Any

    @property
    def render_signature(self) -> PlanVersion | None:
        return self.version if bool(getattr(self.plan, "visible", False)) else None


@dataclass(frozen=True)
class StabilityDecision:
    status: str
    token: JobToken | None = None


@dataclass(frozen=True)
class ProjectionSuspension:
    """Work invalidated while an owning presentation adapter is paused."""

    cancelled_tokens: tuple[JobToken, ...]
    invalidated_controllers: tuple[Hashable, ...]


@dataclass
class ViewSession:
    """All mutable scheduling and publication state for one Edit view."""

    controller_identity: Hashable
    session_identity: Hashable
    content_epoch: int = 0
    frame_epoch: int = 0
    active_key: LayerKey | None = None
    reference_fingerprint: str | None = None
    quiet_until: float = 0.0
    capture_requested: bool = False
    capture_token: JobToken | None = None
    capture_stamp: ViewStamp | None = None
    capture_last_stamp: ViewStamp | None = None
    capture_samples: int = 0
    capture_next_sample_at: float | None = None
    published_plan: PreparedPlan | None = None
    render_signature: PlanVersion | None = None
    invalidation_pending: bool = False
    invalidation_last_stamp: ViewStamp | None = None
    invalidation_samples: int = 0
    invalidation_next_sample_at: float | None = None


class PreparedPlanCache:
    """Worker-owned, content-addressed LRU of immutable prepared plans."""

    def __init__(self, *, capacity: int = 128) -> None:
        self.capacity = max(1, int(capacity))
        self._values: "OrderedDict[PlanVersion, PreparedPlan]" = OrderedDict()

    def get(self, version: PlanVersion) -> PreparedPlan | None:
        prepared = self._values.get(version)
        if prepared is not None:
            self._values.move_to_end(version)
        return prepared

    def put(self, prepared: PreparedPlan) -> PreparedPlan:
        self._values.pop(prepared.version, None)
        self._values[prepared.version] = prepared
        while len(self._values) > self.capacity:
            self._values.popitem(last=False)
        return prepared

    def __len__(self) -> int:
        return len(self._values)

    def versions(self) -> tuple[PlanVersion, ...]:
        return tuple(self._values)


class ProjectionRequestQueue:
    """Per-view quiet-window and stable-display state machine.

    A frame event can only re-arm a capture that was already requested by a
    content event. Consequently zooming and scrolling never create diff work.
    """

    def __init__(
        self,
        *,
        delay_seconds: float,
        stability_interval_seconds: float = 0.016,
        maximum_stability_samples: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.stability_interval_seconds = max(
            0.0, float(stability_interval_seconds)
        )
        self.maximum_stability_samples = max(2, int(maximum_stability_samples))
        self._clock = clock
        self._serial = itertools.count(1)
        self._sessions: "OrderedDict[Hashable, ViewSession]" = OrderedDict()

    def ensure_session(self, controller_identity: Hashable) -> ViewSession:
        session = self._sessions.get(controller_identity)
        if session is None:
            session = ViewSession(
                controller_identity=controller_identity,
                session_identity=(controller_identity, next(self._serial)),
            )
            self._sessions[controller_identity] = session
        return session

    def session(self, controller_identity: Hashable) -> ViewSession | None:
        return self._sessions.get(controller_identity)

    def sessions(self) -> tuple[ViewSession, ...]:
        return tuple(self._sessions.values())

    def note_interface_change(
        self,
        controller_identity: Hashable,
        *,
        active_key: LayerKey,
        reference_fingerprint: str,
        delay_seconds: float | None = None,
    ) -> tuple[ViewSession, JobToken | None]:
        session = self.ensure_session(controller_identity)
        cancelled = session.capture_token
        content_identity_changed = (
            session.active_key != active_key
            or session.reference_fingerprint != str(reference_fingerprint)
        )
        previous_signature = session.render_signature
        session.content_epoch += 1
        session.active_key = active_key
        session.reference_fingerprint = str(reference_fingerprint)
        if content_identity_changed:
            session.published_plan = None
            session.render_signature = None
            if previous_signature is not None:
                session.invalidation_pending = True
                self._reset_invalidation_stability(session, at=self._clock())
        settle_delay = (
            self.delay_seconds
            if delay_seconds is None
            else max(0.0, float(delay_seconds))
        )
        session.quiet_until = self._clock() + settle_delay
        session.capture_requested = True
        session.capture_token = None
        session.capture_stamp = None
        self._reset_capture_stability(session, at=session.quiet_until)
        return session, cancelled

    def note_view_frame(
        self, controller_identity: Hashable
    ) -> tuple[ViewSession | None, JobToken | None]:
        session = self.session(controller_identity)
        if session is None:
            return None, None
        session.frame_epoch += 1
        cancelled = session.capture_token
        if session.capture_requested or cancelled is not None:
            session.capture_requested = True
            session.capture_token = None
            session.capture_stamp = None
            self._reset_capture_stability(
                session, at=max(self._clock(), session.quiet_until)
            )
        if session.invalidation_pending:
            self._reset_invalidation_stability(session, at=self._clock())
        return session, cancelled

    def _reset_capture_stability(self, session: ViewSession, *, at: float) -> None:
        session.capture_last_stamp = None
        session.capture_samples = 0
        session.capture_next_sample_at = float(at)

    def _reset_invalidation_stability(
        self, session: ViewSession, *, at: float
    ) -> None:
        session.invalidation_last_stamp = None
        session.invalidation_samples = 0
        session.invalidation_next_sample_at = float(at)

    def sample_capture(
        self,
        controller_identity: Hashable,
        stamp: ViewStamp,
    ) -> StabilityDecision:
        session = self.session(controller_identity)
        if session is None or not session.capture_requested:
            return StabilityDecision("inactive")
        now = self._clock()
        next_at = session.capture_next_sample_at
        if next_at is not None and now < next_at:
            return StabilityDecision("waiting")
        if stamp.controller_identity != controller_identity:
            session.capture_requested = False
            session.capture_next_sample_at = None
            return StabilityDecision("abandoned")

        session.capture_samples += 1
        if session.capture_last_stamp is not None and stamp == session.capture_last_stamp:
            if (
                session.active_key is None
                or session.reference_fingerprint is None
                or stamp.active_layer_key != session.active_key
            ):
                session.capture_requested = False
                session.capture_next_sample_at = None
                return StabilityDecision("abandoned")
            token = JobToken(
                session_identity=session.session_identity,
                content_epoch=session.content_epoch,
                active_key=session.active_key,
                reference_fingerprint=session.reference_fingerprint,
            )
            session.capture_requested = False
            session.capture_token = token
            session.capture_stamp = stamp
            session.capture_next_sample_at = None
            return StabilityDecision("ready", token)

        session.capture_last_stamp = stamp
        if session.capture_samples >= self.maximum_stability_samples:
            session.capture_requested = False
            session.capture_next_sample_at = None
            return StabilityDecision("abandoned")
        session.capture_next_sample_at = now + self.stability_interval_seconds
        return StabilityDecision("waiting")

    def is_current(
        self, token: JobToken, *, stamp: ViewStamp | None = None
    ) -> bool:
        session = self.session_for_token(token)
        if session is None:
            return False
        current = (
            session.capture_token == token
            and session.content_epoch == token.content_epoch
            and session.active_key == token.active_key
            and session.reference_fingerprint == token.reference_fingerprint
        )
        if current and stamp is not None:
            current = session.capture_stamp == stamp
        return bool(current)

    def session_for_token(self, token: JobToken) -> ViewSession | None:
        for session in self._sessions.values():
            if session.session_identity == token.session_identity:
                return session
        return None

    def retry_after_view_change(self, token: JobToken) -> bool:
        session = self.session_for_token(token)
        if session is None or session.capture_token != token:
            return False
        session.capture_token = None
        session.capture_stamp = None
        session.capture_requested = True
        self._reset_capture_stability(session, at=self._clock())
        return True

    def cancel_job(self, token: JobToken, *, retry: bool = False) -> bool:
        session = self.session_for_token(token)
        if session is None or session.capture_token != token:
            return False
        session.capture_token = None
        session.capture_stamp = None
        if retry:
            session.capture_requested = True
            self._reset_capture_stability(session, at=self._clock())
        return True

    def publish(self, token: JobToken, prepared: PreparedPlan) -> bool:
        session = self.session_for_token(token)
        if not self.is_current(token) or session is None:
            return False
        if (
            prepared.version.active_key != token.active_key
            or prepared.version.reference_fingerprint
            != token.reference_fingerprint
        ):
            return False
        previous_signature = session.render_signature
        session.published_plan = prepared
        session.render_signature = prepared.render_signature
        session.capture_token = None
        session.capture_stamp = None
        if session.render_signature != previous_signature:
            session.invalidation_pending = True
            self._reset_invalidation_stability(session, at=self._clock())
            return True
        return False

    def clear_published(
        self, controller_identity: Hashable, *, request_invalidation: bool = True
    ) -> bool:
        session = self.session(controller_identity)
        if session is None:
            return False
        changed = session.render_signature is not None
        session.published_plan = None
        session.render_signature = None
        if changed and request_invalidation:
            session.invalidation_pending = True
            self._reset_invalidation_stability(session, at=self._clock())
        elif not request_invalidation:
            session.invalidation_pending = False
            session.invalidation_next_sample_at = None
        return changed

    def invalidate_content(
        self,
        controller_identity: Hashable,
        *,
        clear_published: bool,
        request_invalidation: bool,
    ) -> JobToken | None:
        """Reject current work after a reference or lifecycle transition."""

        session = self.session(controller_identity)
        if session is None:
            return None
        cancelled = session.capture_token
        session.content_epoch += 1
        session.capture_requested = False
        session.capture_token = None
        session.capture_stamp = None
        session.capture_next_sample_at = None
        if clear_published:
            self.clear_published(
                controller_identity,
                request_invalidation=request_invalidation,
            )
        return cancelled

    def sample_invalidation(
        self, controller_identity: Hashable, stamp: ViewStamp
    ) -> StabilityDecision:
        session = self.session(controller_identity)
        if session is None or not session.invalidation_pending:
            return StabilityDecision("inactive")
        now = self._clock()
        next_at = session.invalidation_next_sample_at
        if next_at is not None and now < next_at:
            return StabilityDecision("waiting")
        session.invalidation_samples += 1
        if (
            session.invalidation_last_stamp is not None
            and stamp == session.invalidation_last_stamp
        ):
            session.invalidation_pending = False
            session.invalidation_next_sample_at = None
            return StabilityDecision("ready")
        session.invalidation_last_stamp = stamp
        if session.invalidation_samples >= self.maximum_stability_samples:
            # A render transition must eventually invalidate, unlike capture.
            self._reset_invalidation_stability(
                session, at=now + self.stability_interval_seconds
            )
        else:
            session.invalidation_next_sample_at = (
                now + self.stability_interval_seconds
            )
        return StabilityDecision("waiting")

    def published_for(
        self, controller_identity: Hashable, active_key: LayerKey
    ) -> PreparedPlan | None:
        session = self.session(controller_identity)
        if (
            session is None
            or session.active_key != active_key
            or session.published_plan is None
            or session.published_plan.version.active_key != active_key
            or session.published_plan.version.reference_fingerprint
            != session.reference_fingerprint
        ):
            return None
        return session.published_plan

    def remaining_delay(self, controller_identity: Hashable) -> float | None:
        session = self.session(controller_identity)
        if session is None:
            return None
        due: list[float] = []
        if session.capture_requested and session.capture_next_sample_at is not None:
            due.append(session.capture_next_sample_at)
        if (
            session.invalidation_pending
            and session.invalidation_next_sample_at is not None
        ):
            due.append(session.invalidation_next_sample_at)
        if not due:
            return None
        return max(0.0, min(due) - self._clock())

    def suspend(self, *, clear_published: bool) -> ProjectionSuspension:
        cancelled: list[JobToken] = []
        invalidated: list[Hashable] = []
        for session in self._sessions.values():
            session.content_epoch += 1
            if session.capture_token is not None:
                cancelled.append(session.capture_token)
            if session.render_signature is not None:
                invalidated.append(session.controller_identity)
            session.capture_requested = False
            session.capture_token = None
            session.capture_stamp = None
            session.capture_next_sample_at = None
            session.invalidation_pending = False
            session.invalidation_next_sample_at = None
            if clear_published:
                session.published_plan = None
                session.render_signature = None
        return ProjectionSuspension(
            cancelled_tokens=tuple(cancelled),
            invalidated_controllers=tuple(invalidated),
        )

    def remove(self, controller_identity: Hashable) -> ViewSession | None:
        return self._sessions.pop(controller_identity, None)

    def retain(self, controller_identities: Iterable[Hashable]) -> tuple[ViewSession, ...]:
        retained = set(controller_identities)
        removed = tuple(
            session
            for identity, session in self._sessions.items()
            if identity not in retained
        )
        for session in removed:
            self._sessions.pop(session.controller_identity, None)
        return removed

    def clear(self) -> tuple[ViewSession, ...]:
        removed = tuple(self._sessions.values())
        self._sessions.clear()
        return removed


__all__ = [
    "JobToken",
    "PlanVersion",
    "PreparedPlan",
    "PreparedPlanCache",
    "ProjectionSuspension",
    "ProjectionRequestQueue",
    "StabilityDecision",
    "ViewSession",
    "ViewStamp",
]
