"""Shared native observation collection for reads and verified constraints."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .generic_tools import constraint_observation_request


_LAYER_OBSERVATIONS = frozenset(
    {
        "alignment",
        "bounds",
        "inheritance.metrics",
        "spacing.horizontal",
        "spacing.vertical",
    }
)


def _inspect(
    callback: Any,
    *arguments: Any,
    suppressed_errors: tuple[type[BaseException], ...],
    **keywords: Any,
) -> Any:
    if not callable(callback):
        return None
    try:
        return callback(*arguments, **keywords)
    except Exception as error:
        if suppressed_errors and isinstance(error, suppressed_errors):
            return None
        raise


def collect_native_observations(
    host: Any,
    document_id: str,
    fields: Sequence[str],
    glyph_names: Sequence[str] = (),
    *,
    suppressed_errors: tuple[type[BaseException], ...] = (),
) -> tuple[
    Mapping[tuple[str, str], Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
]:
    """Collect the exact native sources required by registry-backed fields."""

    requested = {str(value) for value in fields}
    names = tuple(str(value) for value in glyph_names)
    observations: dict[tuple[str, str], Mapping[str, Any]] = {}
    if requested.intersection(_LAYER_OBSERVATIONS):
        captured = _inspect(
            getattr(host, "inspect_layers", None),
            document_id,
            names,
            include_metrics=bool(
                requested.intersection(
                    {
                        "inheritance.metrics",
                        "spacing.horizontal",
                        "spacing.vertical",
                    }
                )
            ),
            resolve_metrics="inheritance.metrics" in requested,
            include_geometry=bool(
                requested.intersection(
                    {"bounds", "spacing.horizontal", "spacing.vertical"}
                )
            ),
            suppressed_errors=suppressed_errors,
        )
        if isinstance(captured, Mapping):
            observations.update(captured)
    if "compilation.diagnostics" in requested:
        diagnostics = _inspect(
            getattr(host, "inspect_compilation_diagnostics", None),
            document_id,
            suppressed_errors=suppressed_errors,
        )
        if isinstance(diagnostics, Mapping):
            observations[("__document__", "compilation.diagnostics")] = dict(
                diagnostics
            )
    if "persistence" in requested:
        capture_persistence = getattr(host, "capture_source_file_state", None)
        try:
            persistence = _inspect(
                capture_persistence,
                document_id,
                include_model=True,
                suppressed_errors=suppressed_errors,
            )
        except TypeError:
            persistence = _inspect(
                capture_persistence,
                document_id,
                suppressed_errors=suppressed_errors,
            )
        if isinstance(persistence, Mapping):
            observations[("__document__", "persistence")] = dict(persistence)
    effective_metadata: Mapping[str, Mapping[str, Any]] = {}
    if "metadata.effective" in requested:
        metadata = _inspect(
            getattr(host, "inspect_glyph_metadata", None),
            document_id,
            names,
            suppressed_errors=suppressed_errors,
        )
        if isinstance(metadata, Mapping):
            effective_metadata = metadata
    return observations, effective_metadata


def collect_constraint_context(
    host: Any,
    document_id: str,
    model: Mapping[str, Any],
    constraints: Sequence[Mapping[str, Any]],
    *,
    phase: str,
    suppressed_errors: tuple[type[BaseException], ...] = (),
) -> tuple[
    Mapping[tuple[str, str], Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
    Mapping[str, Any],
]:
    """Collect one constraint phase through the shared observation registry."""

    request = constraint_observation_request(model, constraints, phase=phase)
    observations, metadata = collect_native_observations(
        host,
        document_id,
        request["fields"],
        request["glyphNames"],
        suppressed_errors=suppressed_errors,
    )
    return observations, metadata, request


__all__ = ["collect_constraint_context", "collect_native_observations"]
