"""Floating-point geometry execution invariants."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.geometry_precision import (  # noqa: E402
    FloatingGeometryScope,
)
from glyphs_mcp_v2.ports import HostAccessError  # noqa: E402


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


class FloatingGeometryScopeTests(unittest.TestCase):
    def test_existing_and_background_layer_flags_preserve_fractional_width(self):
        font = _Font()
        background = font.layer.background

        scope = FloatingGeometryScope((font,)).begin()
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
            self.assertTrue(font.layer.temporarilyDisableRounding())
        self.assertTrue(font.layer.temporarilyDisableRounding())

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

    def test_reviewed_grid_target_survives_temporary_fallback(self):
        font = _Font()
        scope = FloatingGeometryScope(
            (font,), require_grid_zero=True
        ).begin()
        scope.set_restoration_target(font, grid=2, subdivision=4)
        scope.prepare_for_readback()
        self.assertEqual(font.grid, 2)
        self.assertEqual(font.gridSubDivision, 4)
        scope.end()
        self.assertEqual(font.grid, 2)
        self.assertEqual(font.gridSubDivision, 4)

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
        with self.assertRaises(HostAccessError):
            FloatingGeometryScope((_NoGridFont(),)).begin()


if __name__ == "__main__":
    unittest.main()
