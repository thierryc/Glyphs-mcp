"""Temporary Glyphs 4 execution policy for exact floating-point geometry.

Glyphs rounds some layer-owned scalar setters against ``GSFont.grid``.  The
native ``GSLayer.temporarilyDisableRounding`` flag is transient and is
neither copied with ``GSFont.copy()`` nor inherited by newly-created layers.
Every scope therefore combines that flag with a short-lived zero grid before
any transformation executes.

The scope owns execution state only.  It never changes the canonical target,
never disables automatic alignment, and restores all protected host settings
before callers perform their canonical read-back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..ports import HostAccessError


_MISSING = object()


def _maybe_call(value: Any) -> Any:
    return value() if callable(value) else value


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return default


def _sequence_values(value: Any) -> tuple[Any, ...]:
    value = _maybe_call(value)
    if value is None:
        return ()
    try:
        return tuple(value)
    except Exception:
        try:
            return tuple(value[index] for index in range(len(value)))
        except Exception:
            return ()


def _read_property(owner: Any, name: str) -> Any:
    value = _safe_getattr(owner, name, _MISSING)
    if value is _MISSING:
        return _MISSING
    try:
        return _maybe_call(value)
    except Exception:
        return _MISSING


def _write_property(owner: Any, name: str, value: Any) -> bool:
    selector = _safe_getattr(
        owner,
        "set{}_".format(name[0].upper() + name[1:]),
        None,
    )
    if callable(selector):
        try:
            selector(value)
            return True
        except Exception:
            pass
    try:
        setattr(owner, name, value)
        return True
    except Exception:
        return False


def _layer_rounding_value(layer: Any) -> Any:
    return _read_property(layer, "temporarilyDisableRounding")


def _set_layer_rounding(layer: Any, value: bool) -> bool:
    setter = _safe_getattr(layer, "setTemporarilyDisableRounding_", None)
    if callable(setter):
        try:
            setter(bool(value))
            return True
        except Exception:
            pass
    try:
        setattr(layer, "temporarilyDisableRounding", bool(value))
        return True
    except Exception:
        return False


def _font_layers(font: Any) -> tuple[Any, ...]:
    """Return every current foreground and background layer exactly once."""

    result: list[Any] = []
    seen: set[int] = set()
    for glyph in _sequence_values(_safe_getattr(font, "glyphs")):
        for layer in _sequence_values(_safe_getattr(glyph, "layers")):
            for candidate in (
                layer,
                _maybe_call(_safe_getattr(layer, "background")),
            ):
                if candidate is None or id(candidate) in seen:
                    continue
                seen.add(id(candidate))
                result.append(candidate)
    return tuple(result)


@dataclass
class _LayerState:
    layer: Any
    original: bool


@dataclass
class _FontState:
    font: Any
    original_grid: Any
    original_subdivision: Any
    original_auto_alignment: Any
    layers: dict[int, _LayerState] = field(default_factory=dict)
    grid_zero: bool = False
    grid_available: bool = False
    execution_settings_owned: bool = True


class FloatingGeometryScope:
    """Nest-safe per-invocation floating-geometry execution scope.

    Nested scopes naturally restore to the state observed at their own entry.
    An outer structural or Python scope therefore keeps grid zero active while
    a nested verified transaction runs, then restores the user's state only at
    the outer boundary.
    """

    def __init__(
        self,
        fonts: Iterable[Any],
        *,
        require_grid_zero: bool = True,
    ) -> None:
        unique: list[Any] = []
        seen: set[int] = set()
        for font in fonts:
            if font is None or id(font) in seen:
                continue
            seen.add(id(font))
            unique.append(font)
        self._fonts = tuple(unique)
        # Retain the argument for call-site compatibility, but zero-grid
        # execution is now an invariant for every geometry-capable scope.
        self._require_grid_zero = True
        self._states: dict[int, _FontState] = {}
        self._active = False
        self._prepared_for_readback = False

    @property
    def active(self) -> bool:
        return self._active

    def begin(self) -> "FloatingGeometryScope":
        if self._active:
            return self
        initialized: list[_FontState] = []
        try:
            for font in self._fonts:
                grid = _read_property(font, "grid")
                subdivision = _read_property(font, "gridSubDivision")
                auto_alignment = _read_property(
                    font, "disablesAutomaticAlignment"
                )
                state = _FontState(
                    font=font,
                    original_grid=grid,
                    original_subdivision=subdivision,
                    original_auto_alignment=auto_alignment,
                    grid_available=grid is not _MISSING,
                )
                self._states[id(font)] = state
                initialized.append(state)
                missing_rounding_flag = self._protect_layers(state)
                if self._require_grid_zero or missing_rounding_flag:
                    self._enable_grid_zero(state)
            self._active = True
            return self
        except BaseException:
            for state in reversed(initialized):
                self._restore_state(state)
            self._states.clear()
            raise

    def _protect_layers(self, state: _FontState) -> bool:
        missing = False
        for layer in _font_layers(state.font):
            identity = id(layer)
            if identity in state.layers:
                continue
            original = _layer_rounding_value(layer)
            if original is _MISSING or not _set_layer_rounding(layer, True):
                missing = True
                continue
            state.layers[identity] = _LayerState(layer, bool(original))
        return missing

    def _enable_grid_zero(self, state: _FontState) -> None:
        observed = _read_property(state.font, "grid")
        try:
            already_zero = float(observed) == 0.0
        except (TypeError, ValueError):
            already_zero = False
        if not already_zero and (
            not state.grid_available
            or not _write_property(state.font, "grid", 0)
        ):
            raise HostAccessError(
                "Glyphs exposes neither layer rounding suppression nor a writable grid fallback"
            )
        observed = _read_property(state.font, "grid")
        try:
            accepted = float(observed) == 0.0
        except (TypeError, ValueError):
            accepted = False
        if not accepted:
            raise HostAccessError("Glyphs rejected the temporary zero-grid precision scope")
        state.grid_zero = True
        state.execution_settings_owned = True
        self._prepared_for_readback = False

    def require_grid_zero(self) -> None:
        if not self._active:
            raise RuntimeError("floating geometry scope is not active")
        for state in self._states.values():
            self._enable_grid_zero(state)

    def rescan_layers(self) -> None:
        if not self._active:
            return
        for state in self._states.values():
            missing = self._protect_layers(state)
            if missing and not state.grid_zero:
                self._enable_grid_zero(state)

    def release_execution_settings_ownership(self) -> None:
        """Retain reviewed settings written after exact entry restoration.

        Callers may use this only after component settlement, exact entry
        restoration, and verified application of an explicit document-level
        grid change. Until then, cleanup continues to own and restore the
        immutable entry settings on every exit path.
        """

        if not self._active or not self._prepared_for_readback:
            raise RuntimeError(
                "execution settings can be released only after entry restoration"
            )
        for state in self._states.values():
            state.execution_settings_owned = False

    def protected_setting_changes(self) -> tuple[Mapping[str, Any], ...]:
        """Report script attempts to change protected execution settings."""

        changes: list[Mapping[str, Any]] = []
        for state in self._states.values():
            current_grid = _read_property(state.font, "grid")
            current_subdivision = _read_property(state.font, "gridSubDivision")
            current_auto_alignment = _read_property(
                state.font, "disablesAutomaticAlignment"
            )
            expected_grid = 0 if state.grid_zero else state.original_grid
            if (
                expected_grid is not _MISSING
                and current_grid is not _MISSING
                and current_grid != expected_grid
            ):
                changes.append(
                    {
                        "setting": "grid",
                        "before": state.original_grid,
                        "attempted": current_grid,
                    }
                )
            if (
                state.original_subdivision is not _MISSING
                and current_subdivision is not _MISSING
                and current_subdivision != state.original_subdivision
            ):
                changes.append(
                    {
                        "setting": "gridSubDivision",
                        "before": state.original_subdivision,
                        "attempted": current_subdivision,
                    }
                )
            if (
                state.original_auto_alignment is not _MISSING
                and current_auto_alignment is not _MISSING
                and current_auto_alignment != state.original_auto_alignment
            ):
                changes.append(
                    {
                        "setting": "disablesAutomaticAlignment",
                        "before": state.original_auto_alignment,
                        "attempted": current_auto_alignment,
                    }
                )
        return tuple(changes)

    def prepare_for_readback(self) -> None:
        """Restore canonical settings while retaining layer precision flags."""

        if not self._active or self._prepared_for_readback:
            return
        self.rescan_layers()
        for state in self._states.values():
            self._restore_execution_settings(state)
        self._prepared_for_readback = True

    def _restore_execution_settings(self, state: _FontState) -> None:
        errors: list[BaseException] = []
        for name, target, label in (
            ("grid", state.original_grid, "document grid"),
            (
                "gridSubDivision",
                state.original_subdivision,
                "grid subdivision",
            ),
            (
                "disablesAutomaticAlignment",
                state.original_auto_alignment,
                "automatic-alignment setting",
            ),
        ):
            if target is _MISSING:
                continue
            try:
                current = _read_property(state.font, name)
                # In the common path this avoids touching a protected global
                # setting merely to assign its existing value.
                if current is _MISSING or current != target:
                    if not _write_property(state.font, name, target):
                        raise HostAccessError(
                            "Glyphs did not restore the {}".format(label)
                        )
                observed = _read_property(state.font, name)
                if observed is _MISSING or observed != target:
                    raise HostAccessError(
                        "Glyphs did not restore the {}".format(label)
                    )
                if name == "grid":
                    state.grid_zero = False
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    def _restore_state(self, state: _FontState) -> None:
        try:
            if state.execution_settings_owned:
                self._restore_execution_settings(state)
        finally:
            for layer_state in reversed(tuple(state.layers.values())):
                _set_layer_rounding(layer_state.layer, layer_state.original)

    def end(self) -> None:
        if not self._active:
            return
        errors: list[BaseException] = []
        try:
            self.rescan_layers()
        except BaseException as exc:
            errors.append(exc)
        for state in reversed(tuple(self._states.values())):
            try:
                self._restore_state(state)
            except BaseException as exc:
                errors.append(exc)
        self._active = False
        self._states.clear()
        if errors:
            raise errors[0]

    def __enter__(self) -> "FloatingGeometryScope":
        return self.begin()

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> bool:
        self.end()
        return False


__all__ = ["FloatingGeometryScope"]
