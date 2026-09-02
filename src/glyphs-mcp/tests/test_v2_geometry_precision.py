"""Floating-point geometry execution invariants."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.geometry_precision import (  # noqa: E402
    FloatingGeometryScope,
)
from glyphs_mcp_v2.adapters.document import (  # noqa: E402
    _component_dependency_glyph_names,
    _settle_component_dependencies,
)
from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.ports import HostAccessError  # noqa: E402
from glyphs_mcp_v2.activity import ActivityCancelled  # noqa: E402
from glyphs_mcp_v2.semantic import diff_models  # noqa: E402


class _Layer:
    def __init__(self, font, *, background=None):
        self.font = font
        self._rounding_disabled = False
        self._width = 500.0
        self.background = background

    def temporarilyDisableRounding(self):
        return self._rounding_disabled

    def setTemporarilyDisableRounding_(self, value):
        self._rounding_disabled = bool(value)

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        if self.font.grid and not self._rounding_disabled:
            value = round(float(value) / self.font.grid) * self.font.grid
        self._width = float(value)


class _UnflaggableLayer:
    __slots__ = ("font", "_width", "background")

    def __init__(self, font):
        self.font = font
        self._width = 500.0
        self.background = None

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        if self.font.grid:
            value = round(float(value) / self.font.grid) * self.font.grid
        self._width = float(value)


class _Glyph:
    def __init__(self, layers):
        self.layers = list(layers)


class _Font:
    def __init__(self, *, layer_class=_Layer):
        self.grid = 1
        self.gridSubDivision = 2
        self.disablesAutomaticAlignment = False
        background = (
            _Layer(self) if layer_class is _Layer else None
        )
        self.layer = layer_class(self)
        if background is not None:
            self.layer.background = background
        self.glyphs = [_Glyph([self.layer])]


class _NoGridFont:
    __slots__ = ("glyphs", "gridSubDivision", "disablesAutomaticAlignment")

    def __init__(self):
        self.gridSubDivision = 1
        self.disablesAutomaticAlignment = False
        self.glyphs = [_Glyph([_UnflaggableLayer(self)])]


class _RejectRestoreFont(_Font):
    def __init__(self):
        self._grid = 1
        self.reject_entry_grid = False
        super().__init__()

    @property
    def grid(self):
        return self._grid

    @grid.setter
    def grid(self, value):
        if self.reject_entry_grid and value == 1:
            raise RuntimeError("grid restore rejected")
        self._grid = value


class FloatingGeometryScopeTests(unittest.TestCase):
    def test_existing_and_background_layer_flags_preserve_fractional_width(self):
        font = _Font()
        background = font.layer.background

        scope = FloatingGeometryScope((font,)).begin()
        self.assertEqual(font.grid, 0)
        font.layer.width = 500.375
        background.width = 400.625
        scope.prepare_for_readback()

        self.assertEqual(font.layer.width, 500.375)
        self.assertEqual(background.width, 400.625)
        self.assertEqual(font.grid, 1)
        self.assertFalse(font.disablesAutomaticAlignment)
        self.assertTrue(font.layer.temporarilyDisableRounding())
        scope.end()
        self.assertFalse(font.layer.temporarilyDisableRounding())
        self.assertFalse(background.temporarilyDisableRounding())

    def test_structural_scope_protects_new_layers_and_restores_grid(self):
        font = _Font()
        scope = FloatingGeometryScope(
            (font,), require_grid_zero=True
        ).begin()
        self.assertEqual(font.grid, 0)
        created = _Layer(font)
        font.glyphs[0].layers.append(created)
        created.width = 612.375
        scope.rescan_layers()
        self.assertTrue(created.temporarilyDisableRounding())

        scope.prepare_for_readback()
        self.assertEqual(font.grid, 1)
        self.assertEqual(created.width, 612.375)
        scope.end()
        self.assertFalse(created.temporarilyDisableRounding())

    def test_missing_layer_flag_uses_grid_fallback(self):
        font = _Font(layer_class=_UnflaggableLayer)
        scope = FloatingGeometryScope((font,)).begin()
        self.assertEqual(font.grid, 0)
        font.layer.width = 510.375
        scope.prepare_for_readback()
        self.assertEqual(font.layer.width, 510.375)
        self.assertEqual(font.grid, 1)
        scope.end()

    def test_nested_scope_restores_to_outer_precision_state(self):
        font = _Font()
        outer = FloatingGeometryScope(
            (font,), require_grid_zero=True
        ).begin()
        self.assertEqual(font.grid, 0)
        with FloatingGeometryScope((font,), require_grid_zero=True):
            self.assertEqual(font.grid, 0)
        self.assertEqual(font.grid, 0)
        outer.end()
        self.assertEqual(font.grid, 1)

    def test_preexisting_disabled_rounding_flag_is_preserved(self):
        font = _Font()
        font.layer.setTemporarilyDisableRounding_(True)
        with FloatingGeometryScope((font,)):
            self.assertEqual(font.grid, 0)
            self.assertTrue(font.layer.temporarilyDisableRounding())
        self.assertEqual(font.grid, 1)
        self.assertTrue(font.layer.temporarilyDisableRounding())

    def test_false_legacy_option_cannot_disable_zero_grid_invariant(self):
        font = _Font()
        with FloatingGeometryScope((font,), require_grid_zero=False):
            self.assertEqual(font.grid, 0)
        self.assertEqual(font.grid, 1)

    def test_exception_restores_grid_subdivision_alignment_and_flags(self):
        font = _Font()
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            with FloatingGeometryScope(
                (font,), require_grid_zero=True
            ):
                font.gridSubDivision = 9
                font.disablesAutomaticAlignment = True
                raise RuntimeError("cancelled")

        self.assertEqual(font.grid, 1)
        self.assertEqual(font.gridSubDivision, 2)
        self.assertFalse(font.disablesAutomaticAlignment)
        self.assertFalse(font.layer.temporarilyDisableRounding())

    def test_reviewed_grid_change_is_isolated_after_entry_restoration(self):
        font = _Font()
        scope = FloatingGeometryScope(
            (font,), require_grid_zero=True
        ).begin()
        scope.prepare_for_readback()
        self.assertEqual(font.grid, 1)
        self.assertEqual(font.gridSubDivision, 2)
        font.gridSubDivision = 4
        font.grid = 2
        scope.release_execution_settings_ownership()
        self.assertEqual(font.grid, 2)
        self.assertEqual(font.gridSubDivision, 4)
        scope.end()
        self.assertEqual(font.grid, 2)
        self.assertEqual(font.gridSubDivision, 4)

    def test_uncommitted_post_restoration_settings_are_restored_on_failure(self):
        font = _Font()
        scope = FloatingGeometryScope((font,)).begin()
        scope.prepare_for_readback()
        font.gridSubDivision = 7
        font.grid = 3
        scope.end()
        self.assertEqual(font.grid, 1)
        self.assertEqual(font.gridSubDivision, 2)

    def test_require_grid_zero_reasserts_after_a_script_attempt(self):
        font = _Font()
        scope = FloatingGeometryScope((font,)).begin()
        font.grid = 9
        scope.require_grid_zero()
        self.assertEqual(font.grid, 0)
        scope.end()
        self.assertEqual(font.grid, 1)

    def test_abort_style_base_exception_restores_exact_entry_settings(self):
        class Abort(BaseException):
            pass

        font = _Font()
        font.grid = 1.25
        font.gridSubDivision = 7
        with self.assertRaises(Abort):
            with FloatingGeometryScope((font,)):
                font.gridSubDivision = 3
                raise Abort()
        self.assertEqual(font.grid, 1.25)
        self.assertEqual(font.gridSubDivision, 7)

    def test_activity_cancellation_restores_exact_entry_settings(self):
        font = _Font()
        font.grid = 0.75
        font.gridSubDivision = 5
        with self.assertRaises(ActivityCancelled):
            with FloatingGeometryScope((font,)):
                raise ActivityCancelled("cancelled")
        self.assertEqual(font.grid, 0.75)
        self.assertEqual(font.gridSubDivision, 5)

    def test_failed_restoration_fails_closed_and_still_cleans_layer_flags(self):
        font = _RejectRestoreFont()
        scope = FloatingGeometryScope((font,)).begin()
        font.reject_entry_grid = True
        with self.assertRaises(HostAccessError):
            scope.end()
        self.assertEqual(font.grid, 0)
        self.assertFalse(font.layer.temporarilyDisableRounding())

    def test_protected_script_settings_are_reported_before_restoration(self):
        font = _Font()
        scope = FloatingGeometryScope(
            (font,), require_grid_zero=True
        ).begin()
        font.grid = 3
        font.gridSubDivision = 8
        font.disablesAutomaticAlignment = True
        changed = {item["setting"] for item in scope.protected_setting_changes()}
        self.assertEqual(
            changed,
            {"grid", "gridSubDivision", "disablesAutomaticAlignment"},
        )
        scope.prepare_for_readback()
        scope.end()
        self.assertEqual(font.grid, 1)
        self.assertEqual(font.gridSubDivision, 2)
        self.assertFalse(font.disablesAutomaticAlignment)

    def test_missing_flag_and_grid_fails_before_mutation(self):
        font = _NoGridFont()
        with self.assertRaises(HostAccessError):
            FloatingGeometryScope((font,)).begin()
        self.assertEqual(font.gridSubDivision, 1)
        self.assertFalse(font.disablesAutomaticAlignment)


class ComponentDependencyImpactTests(unittest.TestCase):
    @staticmethod
    def _layer(*shapes):
        return {"id": "M1", "shapes": list(shapes)}

    @staticmethod
    def _component(name):
        return {
            "id": "component:{}".format(name),
            "kind": "component",
            "value": {"name": name},
        }

    def test_source_path_change_includes_composite_of_composite(self):
        path = {
            "id": "path:0",
            "kind": "path",
            "value": {"nodes": [{"x": 0.25, "y": 0.0}]},
        }
        source = {
            "glyphs": {
                "base": {"layers": [self._layer(path)]},
                "composite": {
                    "layers": [self._layer(self._component("base"))]
                },
                "nested": {
                    "layers": [self._layer(self._component("composite"))]
                },
            }
        }
        intended = copy.deepcopy(source)
        intended["glyphs"]["base"]["layers"][0]["shapes"][0]["value"][
            "nodes"
        ][0]["x"] = 11.375
        changes = diff_models(source, intended)

        self.assertEqual(
            _component_dependency_glyph_names(source, intended, changes),
            ("base", "composite", "nested"),
        )

    def test_intended_model_covers_inserted_component_dependencies(self):
        source = {
            "glyphs": {
                "base": {"layers": [self._layer()]},
                "composite": {"layers": [self._layer()]},
                "nested": {
                    "layers": [self._layer(self._component("composite"))]
                },
            }
        }
        intended = copy.deepcopy(source)
        intended["glyphs"]["composite"]["layers"][0]["shapes"].append(
            self._component("base")
        )
        changes = diff_models(source, intended)

        self.assertEqual(
            _component_dependency_glyph_names(source, intended, changes),
            ("composite", "nested"),
        )

    def test_settlement_requires_two_agreeing_observations_after_quiet_window(self):
        observations = iter(({"revision": 1}, {"revision": 2}, {"revision": 2}))
        with mock.patch.object(document_adapter.time, "sleep") as pause:
            settled = _settle_component_dependencies(lambda: next(observations))
        self.assertEqual(settled, {"revision": 2})
        self.assertEqual(
            pause.call_args_list,
            [
                mock.call(0.100),
                mock.call(0.100),
            ],
        )

    def test_unstable_dependency_settlement_fails_closed_at_budget(self):
        revision = 0

        def capture():
            nonlocal revision
            revision += 1
            return {"revision": revision}

        with mock.patch.object(
            document_adapter.time,
            "monotonic",
            side_effect=(0.0, 0.0, 0.7),
        ), mock.patch.object(document_adapter.time, "sleep"):
            with self.assertRaisesRegex(
                HostAccessError, "component dependency closure did not settle"
            ):
                _settle_component_dependencies(capture)


if __name__ == "__main__":
    unittest.main()
