"""Regression tests for designspace/UFO export helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "export_designspace_ufo.py"
    )


class _DefaultDict(dict):
    def __getitem__(self, key):
        return self.get(key)


class _AxisDescriptor:
    def __init__(self) -> None:
        self.map = []
        self.maximum = None
        self.minimum = None
        self.default = None
        self.name = None
        self.tag = None


class _DesignSpaceDocument:
    def __init__(self) -> None:
        self.axes = []
        self.instances = []
        self.locationLabels = []

    def addAxis(self, descriptor) -> None:
        self.axes.append(descriptor)

    def addInstance(self, descriptor) -> None:
        self.instances.append(descriptor)


class _InstanceDescriptor:
    pass


class _LocationLabelDescriptor:
    def __init__(self, name=None, userLocation=None, elidable=False) -> None:
        self.name = name
        self.userLocation = userLocation
        self.elidable = elidable

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, _LocationLabelDescriptor)
            and self.name == other.name
            and self.userLocation == other.userLocation
            and self.elidable == other.elidable
        )

    def __hash__(self) -> int:
        return hash((self.name, tuple(sorted((self.userLocation or {}).items())), self.elidable))


class _RuleDescriptor:
    pass


class _SourceDescriptor:
    pass


class ExportDesignspaceUFOTests(unittest.TestCase):
    def _load_module(self):
        designspace = types.SimpleNamespace(
            AxisDescriptor=_AxisDescriptor,
            DesignSpaceDocument=_DesignSpaceDocument,
            InstanceDescriptor=_InstanceDescriptor,
            LocationLabelDescriptor=_LocationLabelDescriptor,
            RuleDescriptor=_RuleDescriptor,
            SourceDescriptor=_SourceDescriptor,
        )
        empty_module = types.SimpleNamespace(
            RAnchor=object,
            RComponent=object,
            RContour=object,
            RFont=object,
            RGlyph=object,
            RGuideline=object,
            RLayer=object,
            RLib=object,
            NewFont=lambda: object(),
        )
        modules = {
            "GlyphsApp": types.SimpleNamespace(GSFont=object, GSFontMaster=object, GSInstance=object, GSLayer=object),
            "fontTools": types.SimpleNamespace(),
            "fontTools.designspaceLib": designspace,
            "fontParts": types.SimpleNamespace(),
            "fontParts.fontshell": types.SimpleNamespace(),
            "fontParts.fontshell.anchor": types.SimpleNamespace(RAnchor=object),
            "fontParts.fontshell.component": types.SimpleNamespace(RComponent=object),
            "fontParts.fontshell.contour": types.SimpleNamespace(RContour=object),
            "fontParts.fontshell.font": types.SimpleNamespace(RFont=object),
            "fontParts.fontshell.glyph": types.SimpleNamespace(RGlyph=object),
            "fontParts.fontshell.guideline": types.SimpleNamespace(RGuideline=object),
            "fontParts.fontshell.layer": types.SimpleNamespace(RLayer=object),
            "fontParts.fontshell.lib": types.SimpleNamespace(RLib=object),
            "fontParts.world": types.SimpleNamespace(NewFont=empty_module.NewFont),
        }

        module_name = "glyphs_mcp_test_export_designspace_ufo"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, modules):
            sys.modules.pop(module_name, None)
            sys.modules[module_name] = module
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def _fake_exporter(self):
        module = self._load_module()
        axis = types.SimpleNamespace(name="Weight", axisTag="wght")
        masters = [
            types.SimpleNamespace(id="m1", axes=[100.0]),
            types.SimpleNamespace(id="m2", axes=[400.0]),
        ]
        instance = types.SimpleNamespace(
            active=True,
            type=0,
            axes=[200.0],
            name="Light",
            variableStyleName="",
            customParameters=_DefaultDict(),
            fontName="Test-Light",
            isBold=False,
            isItalic=False,
            preferredFamily=None,
        )
        font = types.SimpleNamespace(
            axes=[axis],
            masters=masters,
            instances=[instance],
            customParameters=_DefaultDict({"Axis Mappings": {"wght": {100.0: 10.0, 400.0: 70.0}}}),
            familyName="Test",
        )
        exporter = module.ExportDesignspaceAndUFO(font)
        exporter.font = font
        exporter.axis_map_to_build = {}
        exporter.origin_coords = [200.0]
        exporter.to_build = {"static": True, "variable": True}
        exporter.variable_font_family = "Test VF"
        return exporter, module

    def test_axis_mapping_interpolates_missing_instance_coordinate(self) -> None:
        exporter, _module = self._fake_exporter()

        self.assertEqual(exporter._mapped_axis_coord("wght", 200.0), 30)

        labels = exporter.getLabels("variable")
        self.assertEqual(labels[0].userLocation, {"Weight": 30})

        doc = _DesignSpaceDocument()
        exporter.addAxes(doc)
        self.assertEqual(doc.axes[0].minimum, 10.0)
        self.assertEqual(doc.axes[0].maximum, 70.0)
        self.assertEqual(doc.axes[0].default, 30)

        instances = exporter.getInstances("static")
        self.assertEqual(instances[0].userLocation, {"Weight": 30})

    def test_component_offset_uses_transform_when_xy_properties_are_missing(self) -> None:
        exporter, _module = self._fake_exporter()
        component = types.SimpleNamespace(
            componentName="period",
            transform=(1.0, 0.0, 0.0, 1.0, 123.0, 45.0),
            rotation=0.0,
        )

        self.assertEqual(exporter._component_base_glyph_name(component), "period")
        self.assertEqual(exporter._component_scale(component), (1.0, 1.0))
        self.assertEqual(exporter._component_offset(component), (123.0, 45.0))

    def test_kerning_export_skips_stale_glyph_ids(self) -> None:
        exporter, _module = self._fake_exporter()
        font = types.SimpleNamespace(
            glyphs=[types.SimpleNamespace(id="idA", name="A")],
            kerning={
                "m1": {
                    "idA": {"idA": -20, "missingRight": -30},
                    "missingLeft": {"idA": -40},
                }
            },
            customParameters=_DefaultDict({"Use Extension Kerning": False}),
        )
        exporter.font = font

        kerning = exporter.getKerning()

        self.assertEqual(kerning["ufo"]["m1"], [["A", "A", -20]])
        self.assertTrue(
            any("Skipping kerning pair 'idA missingRight'" in message for message in exporter._logger.messages)
        )
        self.assertTrue(
            any("Skipping kerning left key 'missingLeft'" in message for message in exporter._logger.messages)
        )

    def test_decompose_corners_only_calls_layers_with_corner_hints(self) -> None:
        exporter, module = self._fake_exporter()
        module.GLYPHS_CORNER = 99

        class FakeLayer:
            def __init__(self, hints):
                self.isMasterLayer = True
                self.isSpecialLayer = False
                self.hints = hints
                self.decompose_calls = 0
                self.change_log = []

            def beginChanges(self):
                self.change_log.append("beginChanges")

            def endChanges(self):
                self.change_log.append("endChanges")

            def decomposeCorners(self):
                self.decompose_calls += 1

        plain_layer = FakeLayer([])
        corner_layer = FakeLayer([types.SimpleNamespace(type=99, name="_corner.inktrap")])
        name_only_corner_layer = FakeLayer([types.SimpleNamespace(type=None, name="_corner.round")])
        non_corner_layer = FakeLayer([types.SimpleNamespace(type=42, name="hint")])
        exporter.font = types.SimpleNamespace(
            glyphs=[
                types.SimpleNamespace(layers=[plain_layer, corner_layer]),
                types.SimpleNamespace(layers=[name_only_corner_layer, non_corner_layer]),
            ]
        )

        exporter.decomposeCorners()

        self.assertEqual(plain_layer.decompose_calls, 0)
        self.assertEqual(non_corner_layer.decompose_calls, 0)
        self.assertEqual(corner_layer.decompose_calls, 1)
        self.assertEqual(name_only_corner_layer.decompose_calls, 1)
        self.assertEqual(corner_layer.change_log, ["beginChanges", "endChanges"])
        self.assertTrue(any("Decomposed corner hints on 2" in message for message in exporter._logger.messages))


if __name__ == "__main__":
    unittest.main()
