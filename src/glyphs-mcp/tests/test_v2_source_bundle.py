"""Deterministic layout-v2 source-bundle and feature normalization tests."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from fontTools.designspaceLib import (  # noqa: E402
    AxisDescriptor,
    DesignSpaceDocument,
    InstanceDescriptor,
    RuleDescriptor,
    SourceDescriptor,
)
from fontTools.feaLib.parser import Parser  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from jsonschema import validate  # noqa: E402
import uharfbuzz as hb  # noqa: E402

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.ports import HostRuntimeSnapshot  # noqa: E402
from glyphs_mcp_v2.source_bundle import (  # noqa: E402
    SOURCE_KERNING_LIB_KEY,
    SourceBundleError,
    build_feature_source,
    render_source_bundle,
    resolve_number_values,
    select_variable_blocks,
    validate_source_bundle,
)


# SourceBundleError is an internal deterministic rendering error.  Its shape is
# tested here without leaking an export-specific error schema into the public
# tool catalog.
EXPORT_ERROR_SCHEMA = {
    "type": "object",
    "required": ["code", "message", "target"],
    "properties": {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string", "minLength": 1},
        "target": {"type": "object"},
    },
    "additionalProperties": False,
}


def _glyph(name: str, script: str = "latin", **values):
    return {
        "id": "glyph_{}".format(name),
        "name": name,
        "script": script,
        "export": True,
        "layers": [],
        **values,
    }


def _model() -> dict:
    glyphs = {
        ".notdef": _glyph(".notdef"),
        "A": _glyph(
            "A", rightKerningGroup="Agrp", bottomKerningGroup="Atop"
        ),
        "Aacute": _glyph("Aacute", rightKerningGroup="Agrp"),
        "V": _glyph("V", leftKerningGroup="Vgrp", topKerningGroup="Vbot"),
        "Vacute": _glyph("Vacute", leftKerningGroup="Vgrp"),
        "alef": _glyph("alef", "arabic"),
        "beh": _glyph("beh", "arabic"),
    }
    masters = [
        {
            "id": "m1",
            "name": "Regular",
            "axes": [{"tag": "wght", "internal": 100}],
            "numberValues": [{"id": "number_padding", "value": 10.25}],
            "customParameters": [],
        },
        {
            "id": "m2",
            "name": "Bold",
            "axes": [{"tag": "wght", "internal": 900}],
            "numberValues": [{"id": "number_padding", "value": 20.25}],
            "customParameters": [],
        },
    ]
    for glyph in glyphs.values():
        glyph["layers"] = [
            {
                "id": master["id"],
                "masterId": master["id"],
                "isMasterLayer": True,
                "isSpecialLayer": False,
                "roles": ["master"],
                "shapes": [],
            }
            for master in masters
        ]
    return {
        "font": {"familyName": "Bundle Test"},
        "axes": [{"id": "wght", "tag": "wght", "name": "Weight", "default": 100}],
        "masters": masters,
        "numbers": [{"id": "number_padding", "name": "padding"}],
        "glyphOrder": list(glyphs),
        "glyphs": glyphs,
        "classes": [],
        "featurePrefixes": [],
        "features": [
            {
                "tag": "test",
                "code": (
                    "#ifdef VARIABLE\n"
                    "condition 600 < wght;\n"
                    "sub A by Aacute;\n"
                    "#endif\n"
                    "#ifndef VARIABLE\n"
                    "pos A V ${padding*2};\n"
                    "#endif"
                ),
            }
        ],
        "kerning": {
            "ltr": {
                "m1": {
                    "@MMK_L_Agrp": {"@MMK_R_Vgrp": -80},
                    "A": {"@MMK_R_Vgrp": -20, "V": 0},
                },
                "m2": {"@MMK_L_Agrp": {"@MMK_R_Vgrp": -100}},
            },
            "rtl": {
                "m1": {"alef": {"beh": -30}},
                "m2": {"alef": {"beh": -50}},
            },
            "vertical": {
                "m1": {"@MMK_L_Atop": {"@MMK_R_Vbot": -40}},
                "m2": {"@MMK_L_Atop": {"@MMK_R_Vbot": -60}},
            },
            "context": {"A * V A": {"m1": -11, "m2": -22}},
        },
        "instances": [],
    }


def _write_ufo(path: Path, model: dict, style_name: str, *, component=False) -> None:
    from defcon import Font

    unicodes = {
        "A": 0x0041,
        "V": 0x0056,
        "Aacute": 0x00C1,
        "Vacute": 0x1E7C,
        "alef": 0x0627,
        "beh": 0x0628,
    }
    font = Font()
    font.info.familyName = "Bundle Test"
    font.info.styleName = style_name
    font.info.unitsPerEm = 1000
    font.lib["com.example.sessionId"] = "volatile-session"
    for name in model["glyphOrder"]:
        glyph = font.newGlyph(name)
        glyph.width = 500
        if name in unicodes:
            glyph.unicode = unicodes[name]
        if name in {".notdef", "A", "Aacute", "V", "Vacute"}:
            pen = glyph.getPen()
            pen.moveTo((50, 0))
            pen.lineTo((450, 0))
            pen.lineTo((450, 700))
            pen.lineTo((50, 700))
            pen.closePath()
    if component:
        glyph = font["Aacute"]
        glyph.clearContours()
        reference = glyph.instantiateComponent()
        reference.baseGlyph = "A"
        reference.transformation = (1, 0, 0, 1, 0, 0)
        glyph.appendComponent(reference)
    font.save(path)


def _feature_pair_x_advance(
    font_path: Path, feature_tag: str, first: str, second: str
) -> int:
    """Read one pair's XAdvance from a compiled GPOS feature."""

    with TTFont(font_path) as font:
        gpos = font["GPOS"].table
        lookup_indices = [
            lookup_index
            for record in gpos.FeatureList.FeatureRecord
            if record.FeatureTag == feature_tag
            for lookup_index in record.Feature.LookupListIndex
        ]
        for lookup_index in lookup_indices:
            lookup = gpos.LookupList.Lookup[lookup_index]
            for subtable in lookup.SubTable:
                lookup_type = lookup.LookupType
                if lookup_type == 9:
                    lookup_type = subtable.ExtensionLookupType
                    subtable = subtable.ExtSubTable
                if lookup_type != 2 or first not in subtable.Coverage.glyphs:
                    continue
                if subtable.Format == 1:
                    coverage_index = subtable.Coverage.glyphs.index(first)
                    records = subtable.PairSet[coverage_index].PairValueRecord
                    record = next(
                        (item for item in records if item.SecondGlyph == second), None
                    )
                elif subtable.Format == 2:
                    class1 = subtable.ClassDef1.classDefs.get(first, 0)
                    class2 = subtable.ClassDef2.classDefs.get(second, 0)
                    record = subtable.Class1Record[class1].Class2Record[class2]
                else:
                    continue
                if record is None:
                    continue
                value1 = getattr(record, "Value1", None)
                return int(getattr(value1, "XAdvance", 0) or 0)
    raise AssertionError(
        "No GPOS pair {} {} found in feature {} of {}".format(
            first, second, feature_tag, font_path
        )
    )


def _shape_advances(
    font_path: Path,
    text: str,
    *,
    features: dict[str, bool],
    variations: dict[str, float] | None = None,
    direction: str | None = None,
) -> list[tuple[int, int]]:
    face = hb.Face(font_path.read_bytes())
    font = hb.Font(face)
    font.scale = (face.upem, face.upem)
    if variations:
        font.set_variations(variations)
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    if direction:
        buffer.direction = direction
    hb.shape(font, buffer, features)
    return [(position.x_advance, position.y_advance) for position in buffer.glyph_positions]


class _Renderer:
    def __init__(self, model: dict, *, component=False, designspace=True):
        self.model = model
        self.component = component
        self.designspace = designspace
        self.calls: list[str] = []

    def __call__(
        self,
        _font,
        *,
        target_kind,
        destination,
        compatibility_mode,
        decompose_glyphs,
    ):
        self.calls.append(target_kind)
        destination.mkdir(parents=True)
        document = DesignSpaceDocument()
        axis = AxisDescriptor()
        axis.name = "Weight"
        axis.tag = "wght"
        axis.minimum = 100
        axis.default = 100
        axis.maximum = 900
        document.addAxis(axis)
        masters = destination / "masters"
        masters.mkdir()
        ufos = []
        for index, master in enumerate(self.model["masters"]):
            ufo = masters / "{}.ufo".format(master["id"])
            _write_ufo(
                ufo,
                self.model,
                master["name"],
                component=self.component,
            )
            source = SourceDescriptor()
            source.name = master["id"]
            source.familyName = "Bundle Test"
            source.styleName = master["name"]
            source.path = str(ufo)
            source.location = {"Weight": master["axes"][0]["internal"]}
            source.copyInfo = index == 0
            document.addSource(source)
            ufos.append(str(ufo))
        instance = InstanceDescriptor()
        instance.name = "Medium"
        instance.familyName = "Bundle Test"
        instance.styleName = "Medium"
        instance.location = {"Weight": 500}
        instance.filename = "instances/BundleTest-Medium.ufo"
        document.addInstance(instance)
        designspace = destination / "BundleTest.designspace"
        if self.designspace:
            document.write(designspace)
        return {
            "designspaceFiles": [str(designspace)] if self.designspace else [],
            "masterUFOs": ufos,
            "braceUFOs": [],
            "supportFiles": [],
        }


class _SpecialLayerRenderer(_Renderer):
    def __init__(
        self,
        model: dict,
        *,
        emit_intermediate=False,
        add_native_rule=False,
    ):
        super().__init__(model)
        self.emit_intermediate = emit_intermediate
        self.add_native_rule = add_native_rule

    def __call__(self, *args, **kwargs):
        result = super().__call__(*args, **kwargs)
        document = DesignSpaceDocument.fromfile(result["designspaceFiles"][0])
        if self.emit_intermediate:
            from defcon import Font

            origin = Path(result["masterUFOs"][0])
            font = Font(origin)
            layer = font.layers.newLayer("{500}")
            glyph = layer.newGlyph("A")
            glyph.width = 500
            pen = glyph.getPen()
            pen.moveTo((60, 0))
            pen.lineTo((440, 0))
            pen.lineTo((440, 700))
            pen.lineTo((60, 700))
            pen.closePath()
            font.save()

            source = SourceDescriptor()
            source.name = "intermediate-500"
            source.path = str(origin)
            source.layerName = "{500}"
            source.location = {"Weight": 500}
            document.addSource(source)
        if self.add_native_rule:
            rule = RuleDescriptor()
            rule.name = "Native Keep"
            rule.conditionSets = [
                [{"name": "Weight", "minimum": 700.0, "maximum": 900.0}]
            ]
            rule.subs = [("V", "Vacute")]
            document.addRule(rule)
        document.write(result["designspaceFiles"][0])
        return result


class V2FeatureNormalizationTests(unittest.TestCase):
    def test_variable_blocks_reject_else_and_unknown_macros(self) -> None:
        with self.assertRaises(SourceBundleError) as raised:
            select_variable_blocks(
                "#ifdef VARIABLE\na\n#else\nb\n#endif\n", variable=True
            )
        self.assertEqual(raised.exception.code, "feature_conditional_malformed")
        with self.assertRaises(SourceBundleError) as raised:
            select_variable_blocks("#ifdef DEBUG\na\n#endif\n", variable=True)
        self.assertEqual(raised.exception.code, "feature_conditional_unsupported")
        with self.assertRaises(SourceBundleError) as raised:
            select_variable_blocks(
                "#ifdef VARIABLE\n#ifdef VARIABLE\na\n#endif\n",
                variable=True,
            )
        self.assertEqual(raised.exception.code, "feature_conditional_malformed")

    def test_number_values_support_braced_arithmetic_and_glyphs_rounding(self) -> None:
        values = {"m1": {"padding": 10.25}, "m2": {"padding": -10.25}}
        self.assertEqual(
            resolve_number_values(
                "pos A V ${padding*2};",
                values_by_master=values,
                master_id="m1",
            ),
            "pos A V 21;",
        )
        self.assertEqual(
            resolve_number_values(
                "pos A V ${padding*2};",
                values_by_master=values,
                master_id="m2",
            ),
            "pos A V -21;",
        )
        with self.assertRaises(SourceBundleError) as raised:
            resolve_number_values(
                "sub $[name endswith '.alt'];",
                values_by_master=values,
                master_id="m1",
            )
        self.assertEqual(raised.exception.code, "unsupported_dollar_token")

    def test_shared_named_locations_and_ufo_inline_sources_are_equivalent(self) -> None:
        model = _model()
        static, _metadata = build_feature_source(
            model, target_kind="static", master_id="m1"
        )
        variable, metadata = build_feature_source(model, target_kind="variable")
        inline, inline_metadata = build_feature_source(
            model,
            target_kind="variable",
            location_syntax="inline",
        )
        materialized, materialized_metadata = build_feature_source(
            model,
            target_kind="variable",
            master_id="m1",
            location_syntax="inline",
        )
        glyphs = tuple(model["glyphOrder"])
        Parser(io.StringIO(static), glyphNames=glyphs).parse()
        Parser(io.StringIO(inline), glyphNames=glyphs).parse()
        Parser(io.StringIO(materialized), glyphNames=glyphs).parse()
        self.assertIn("pos A V 21;", static)
        m1_location = "@GMCP_location_m1_{}".format(
            hashlib.sha256(b"m1").hexdigest()[:8]
        )
        m2_location = "@GMCP_location_m2_{}".format(
            hashlib.sha256(b"m2").hexdigest()[:8]
        )
        self.assertIn("locationDef wght=100 d {};".format(m1_location), variable)
        self.assertIn("locationDef wght=900 d {};".format(m2_location), variable)
        self.assertIn("({}:0 {}:-100)".format(m1_location, m2_location), variable)
        self.assertNotIn("locationDef", inline)
        self.assertIn("(wght=100:0 wght=900:-100)", inline)
        self.assertNotIn("locationDef", materialized)
        self.assertNotRegex(materialized, r"\([A-Za-z0-9]{4}=")
        self.assertIn("pos \\A \\V <0 0 0 0>;", materialized)
        self.assertNotIn("condition ", variable)
        self.assertEqual(metadata, inline_metadata)
        self.assertEqual(
            metadata["conditionRules"], materialized_metadata["conditionRules"]
        )
        self.assertEqual(materialized_metadata["masterId"], "m1")
        self.assertEqual(metadata["conditionRules"][0]["conditions"][0]["minimum"], 600)

    def test_all_kerning_domains_preserve_order_sign_and_context(self) -> None:
        source, _metadata = build_feature_source(
            _model(), target_kind="static", master_id="m1"
        )
        self.assertIn("pos \\alef \\beh <0 0 -30 0>;", source)
        self.assertNotIn("RightToLeft", source)
        self.assertIn("pos \\A \\V <0 0 0 -40>;", source)
        self.assertIn("pos \\A' <0 0 -11 0> \\V \\A;", source)

    def test_specificity_fallback_preserves_explicit_zero(self) -> None:
        static, _metadata = build_feature_source(
            _model(), target_kind="static", master_id="m1"
        )
        self.assertIn("pos \\A \\V <0 0 0 0>;", static)
        self.assertIn("pos \\A \\Vacute <0 0 -20 0>;", static)
        self.assertIn("pos \\Aacute \\V <0 0 -80 0>;", static)
        variable, _metadata = build_feature_source(
            _model(), target_kind="variable", location_syntax="inline"
        )
        self.assertIn("(wght=100:0 wght=900:-100)", variable)

    def test_equal_specificity_collision_is_blocking(self) -> None:
        model = _model()
        model["kerning"]["ltr"]["m1"] = {
            "A": {"@MMK_R_Vgrp": -20},
            "@MMK_L_Agrp": {"V": -30},
        }
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="static", master_id="m1")
        self.assertEqual(raised.exception.code, "kerning_specificity_collision")

    def test_effective_master_link_inherits_kerning(self) -> None:
        model = _model()
        model["masters"][1]["customParameters"] = [
            {"name": "Link Metrics With First Master", "value": True}
        ]
        source, _metadata = build_feature_source(
            model, target_kind="variable", location_syntax="inline"
        )
        self.assertIn("(wght=100:-80 wght=900:-80)", source)

    def test_duplicate_location_with_different_values_is_blocking(self) -> None:
        model = _model()
        model["masters"][1]["axes"][0]["internal"] = 100
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="variable")
        self.assertEqual(raised.exception.code, "variable_location_collision")

    def test_rtl_rules_require_a_mapped_rtl_script_without_dflt_fallback(self) -> None:
        for script in (None, "unmapped-script"):
            with self.subTest(script=script):
                model = _model()
                model["glyphs"]["A"]["script"] = script
                model["glyphs"]["V"]["script"] = script
                model["kerning"] = {
                    "ltr": {},
                    "rtl": {
                        "m1": {"A": {"V": -20}},
                        "m2": {"A": {"V": -30}},
                    },
                    "vertical": {},
                    "context": {},
                }
                with self.assertRaises(SourceBundleError) as raised:
                    build_feature_source(model, target_kind="variable")
                self.assertEqual(raised.exception.code, "rtl_script_unresolved")

        model = _model()
        model["glyphs"]["A"]["script"] = "arabic"
        model["glyphs"]["V"]["script"] = "arabic"
        model["kerning"] = {
            "ltr": {},
            "rtl": {
                "m1": {"A": {"V": -20}},
                "m2": {"A": {"V": -30}},
            },
            "vertical": {},
            "context": {},
        }
        source, _metadata = build_feature_source(model, target_kind="variable")
        self.assertIn("GMCP_kern_rtl_arab", source)
        self.assertNotIn("GMCP_kern_rtl_DFLT", source)

    def test_reserved_lookup_and_unsupported_condition_forms_block(self) -> None:
        model = _model()
        model["featurePrefixes"] = [
            {"name": "User", "code": "lookup GMCP_user { sub A by V; } GMCP_user;"}
        ]
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="static", master_id="m1")
        self.assertEqual(raised.exception.code, "reserved_lookup_collision")
        model = _model()
        model["features"][0]["code"] = (
            "#ifdef VARIABLE\ncondition 600 <= wght;\nsub A by Aacute;\n#endif"
        )
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="variable")
        self.assertEqual(raised.exception.code, "condition_syntax_unsupported")

    def test_nonkerning_automatic_code_is_preserved_and_mmk_collisions_block(self) -> None:
        model = _model()
        model["features"].append(
            {"tag": "liga", "automatic": True, "code": "sub A V by Aacute;"}
        )
        source, _metadata = build_feature_source(
            model, target_kind="static", master_id="m1"
        )
        self.assertIn("feature liga", source)
        self.assertIn("sub A V by Aacute;", source)

        model = _model()
        model["classes"] = [
            {"name": "MMK_L_Agrp", "code": "A - V"}
        ]
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="static", master_id="m1")
        self.assertEqual(raised.exception.code, "feature_class_collision")

    def test_automatic_kern_and_vkrn_preserve_manual_code_around_marker(self) -> None:
        model = _model()
        model["features"].extend(
            [
                {
                    "tag": "kern",
                    "automatic": True,
                    "code": "pos A A -7;\n# Automatic Code\npos V V -9;",
                },
                {
                    "tag": "vkrn",
                    "automatic": True,
                    "code": "pos A A <0 0 0 -3>;\n# Automatic Code\npos V V <0 0 0 -5>;",
                },
            ]
        )
        source, _metadata = build_feature_source(
            model, target_kind="static", master_id="m1"
        )
        for manual_line in (
            "pos A A -7;",
            "pos V V -9;",
            "pos A A <0 0 0 -3>;",
            "pos V V <0 0 0 -5>;",
        ):
            self.assertIn(manual_line, source)
        self.assertNotIn("# Automatic Code", source)
        self.assertEqual(
            len(
                re.findall(
                    r"(?m)^\s+lookup GMCP_kern_ltr_latn_[A-Za-z0-9_]+;$",
                    source,
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                re.findall(
                    r"(?m)^\s+lookup GMCP_vkrn_vertical_latn_[A-Za-z0-9_]+;$",
                    source,
                )
            ),
            1,
        )

    def test_overlapping_contexts_at_one_boundary_fail_closed(self) -> None:
        model = _model()
        model["kerning"]["context"] = {
            "A * V A": {"m1": -11, "m2": -22},
            "[A Aacute] * V A": {"m1": -13, "m2": -24},
        }
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="variable")
        self.assertEqual(raised.exception.code, "context_collision")
        self.assertEqual(raised.exception.target["boundaryIndex"], 1)

        model["kerning"]["context"] = {
            "A * V A": {"m1": -11, "m2": -22},
            "Aacute A * V A": {"m1": -13, "m2": -24},
        }
        with self.assertRaises(SourceBundleError) as raised:
            build_feature_source(model, target_kind="variable")
        self.assertEqual(raised.exception.code, "context_collision")

        model["kerning"]["context"] = {
            "A * V A": {"m1": -11, "m2": -22},
            "V * A V": {"m1": -13, "m2": -24},
        }
        source, _metadata = build_feature_source(model, target_kind="variable")
        self.assertEqual(
            len(
                re.findall(
                    r"(?m)^lookup GMCP_kern_context_latn_[A-Za-z0-9_]+ \{$",
                    source,
                )
            ),
            1,
        )


class V2SourceBundleTests(unittest.TestCase):
    def test_export_error_keeps_private_target_evidence_without_public_schema_coupling(self) -> None:
        error = SourceBundleError(
            "render_failed",
            "The detached renderer failed.",
            target={"entity": "layer", "id": "layer_A_m1", "nativePhase": 2},
        )
        validate(error.to_dict(), EXPORT_ERROR_SCHEMA)
        self.assertEqual(error.to_dict()["target"]["nativePhase"], 2)

    def _render(
        self,
        root: Path,
        *,
        mode="component_preserving",
        renderer=None,
        model=None,
    ):
        model = copy.deepcopy(model) if model is not None else _model()
        return render_source_bundle(
            font=object(),
            model=model,
            destination=root,
            compatibility_mode=mode,
            document_fingerprint=fingerprint_model(model),
            source_fingerprint="sha256:" + "a" * 64,
            runtime_versions={
                "application": "Glyphs",
                "applicationVersion": "4.0",
                "buildNumber": "4000",
                "pythonVersion": "3.14",
            },
            native_renderer=renderer or _Renderer(model),
        )

    def test_layout_manifest_hashes_groups_conditions_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self._render(root / "first")
            second = self._render(root / "second")
            self.assertEqual(first["targetKinds"], ["static", "variable"])
            self.assertEqual(first["bundleFingerprint"], second["bundleFingerprint"])
            self.assertEqual(first["manifestSha256"], second["manifestSha256"])
            self.assertTrue(first["designspaceFiles"])
            self.assertTrue(
                all(
                    len(Path(path).parts) == 2
                    and Path(path).parts[0] in {"static", "variable"}
                    for path in first["designspaceFiles"]
                )
            )
            self.assertTrue(
                all(
                    len(Path(path).parts) == 3
                    and Path(path).parts[1] == "masters"
                    for path in first["masterUFOs"]
                )
            )
            manifest_path = root / "first" / "source-manifest.json"
            payload = manifest_path.read_bytes()
            manifest = json.loads(payload)
            self.assertEqual(
                first["manifestSha256"],
                "sha256:" + hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(first["manifestSize"], len(payload))
            self.assertEqual(
                len(
                    {
                        first["manifestTreeSha256"],
                        first["manifestSha256"],
                        first["bundleFingerprint"],
                    }
                ),
                3,
            )
            self.assertEqual(
                manifest["canonicalModelSchemaVersion"],
                CANONICAL_MODEL_SCHEMA_VERSION,
            )
            self.assertEqual(manifest["sourceFingerprint"], "sha256:" + "a" * 64)
            static_target = next(
                target for target in manifest["targets"] if target["kind"] == "static"
            )
            self.assertEqual(
                static_target["fontmake"]["instanceArguments"],
                [
                    "-i",
                    "--interpolate-binary-layout",
                    "{compiledMasterDirectory}",
                ],
            )
            ufo = root / "first" / first["masterUFOs"][0]
            with (ufo / "groups.plist").open("rb") as handle:
                groups = plistlib.load(handle)
            self.assertEqual(groups["public.kern1.Agrp"], ["A", "Aacute"])
            self.assertEqual(groups["public.kern2.Vgrp"], ["V", "Vacute"])
            with (ufo / "lib.plist").open("rb") as handle:
                lib = plistlib.load(handle)
            self.assertIn(SOURCE_KERNING_LIB_KEY, lib)
            self.assertNotIn("com.example.sessionId", lib)
            designspace = DesignSpaceDocument.fromfile(
                root / "first" / "variable" / "BundleTest.designspace"
            )
            self.assertEqual(designspace.rules[0].subs, [("A", "Aacute")])
            self.assertEqual(designspace.rules[0].conditionSets[0][0]["minimum"], 600.0)
            shared_variable_source = (
                root / "first" / "variable" / "features" / "features.fea"
            ).read_text(encoding="utf-8")
            self.assertIn("locationDef wght=100 d @GMCP_location_m1_", shared_variable_source)
            self.assertIn("locationDef wght=900 d @GMCP_location_m2_", shared_variable_source)
            self.assertNotIn("(wght=100:0 wght=900:-100)", shared_variable_source)
            for relative in first["masterUFOs"]:
                if not relative.startswith("variable/"):
                    continue
                ufo_source = (root / "first" / relative / "features.fea").read_text(
                    encoding="utf-8"
                )
                self.assertNotIn("locationDef", ufo_source)
                self.assertNotRegex(ufo_source, r"\([A-Za-z0-9]{4}=")
                expected = 0 if Path(relative).stem == "m1" else -100
                self.assertIn(
                    "pos \\A \\V <0 0 {} 0>;".format(expected), ufo_source
                )

    def test_intermediate_layers_are_verified_and_silent_omission_blocks(self) -> None:
        model = _model()
        model["glyphs"]["A"]["layers"].append(
            {
                "id": "brace-500",
                "masterId": "m1",
                "name": "{500}",
                "roles": ["intermediate"],
                "isMasterLayer": False,
                "isSpecialLayer": True,
                "interpolation": {
                    "kind": "intermediate",
                    "coordinates": {"wght": 500},
                },
                "shapes": [],
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._render(
                root / "preserved",
                model=model,
                renderer=_SpecialLayerRenderer(model, emit_intermediate=True),
            )
            for relative in result["designspaceFiles"]:
                document = DesignSpaceDocument.fromfile(root / "preserved" / relative)
                intermediate = next(
                    source for source in document.sources if source.layerName == "{500}"
                )
                self.assertEqual(intermediate.location["Weight"], 500)

            with self.assertRaises(SourceBundleError) as raised:
                self._render(
                    root / "omitted",
                    model=model,
                    renderer=_Renderer(model),
                )
        self.assertEqual(raised.exception.code, "export_special_layer_omitted")
        validate(raised.exception.to_dict(), EXPORT_ERROR_SCHEMA)

    def test_unrepresentable_special_layer_domains_block_before_native_export(self) -> None:
        cases = [
            (
                "alternate",
                {
                    "roles": ["alternate"],
                    "interpolation": {
                        "kind": "alternate",
                        "ranges": {"wght": {"min": 400, "max": None}},
                    },
                },
            ),
            ("smart", {"roles": ["smart"], "interpolation": None}),
            ("color", {"roles": ["color"], "interpolation": None}),
            ("unknown", {"roles": [], "interpolation": None}),
        ]
        for kind, values in cases:
            with self.subTest(kind=kind):
                model = _model()
                model["glyphs"]["A"]["layers"].append(
                    {
                        "id": "special-{}".format(kind),
                        "masterId": "m1",
                        "isMasterLayer": False,
                        "isSpecialLayer": True,
                        "shapes": [],
                        **values,
                    }
                )
                renderer = _Renderer(model)
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaises(SourceBundleError) as raised:
                        self._render(
                            Path(temporary) / "blocked",
                            model=model,
                            renderer=renderer,
                        )
                self.assertEqual(raised.exception.code, "special_layer_unsupported")
                self.assertEqual(renderer.calls, [])
                validate(raised.exception.to_dict(), EXPORT_ERROR_SCHEMA)

    def test_native_designspace_rules_survive_canonical_condition_rules(self) -> None:
        model = _model()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bundle"
            result = self._render(
                root,
                model=model,
                renderer=_SpecialLayerRenderer(model, add_native_rule=True),
            )
            for relative in result["designspaceFiles"]:
                document = DesignSpaceDocument.fromfile(root / relative)
                names = [rule.name for rule in document.rules]
                self.assertIn("Native Keep", names)
                if relative.startswith("variable/"):
                    self.assertIn("GMCP Condition 0001", names)
                else:
                    self.assertEqual(names, ["Native Keep"])

    def test_static_only_layout_for_single_master_or_invalid_axis(self) -> None:
        model = _model()
        model["masters"] = model["masters"][:1]
        for glyph in model["glyphs"].values():
            glyph["layers"] = glyph["layers"][:1]
        renderer = _Renderer(model, designspace=False)
        with tempfile.TemporaryDirectory() as temporary:
            result = render_source_bundle(
                font=object(),
                model=model,
                destination=Path(temporary) / "bundle",
                compatibility_mode="component_preserving",
                document_fingerprint=fingerprint_model(model),
                native_renderer=renderer,
            )
            self.assertEqual(renderer.calls, ["static"])
            self.assertEqual(result["targetKinds"], ["static"])
            self.assertEqual(
                result["variableTargetOmittedReason"], "requires_multiple_masters"
            )
            self.assertEqual(len(result["designspaceFiles"]), 1)
            self.assertTrue(result["designspaceFiles"][0].startswith("static/"))
            self.assertTrue(
                all(path.startswith("static/masters/") for path in result["masterUFOs"])
            )

    def test_layout_validation_rejects_flat_ufos_and_missing_static_designspace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._render(root / "flat")
            source = next((root / "flat" / "static" / "masters").glob("*.ufo"))
            shutil.copytree(source, root / "flat" / "static" / source.name)
            with self.assertRaises(SourceBundleError) as raised:
                validate_source_bundle(root / "flat", model=_model())
            self.assertEqual(raised.exception.code, "bundle_layout_invalid")
            validate(raised.exception.to_dict(), EXPORT_ERROR_SCHEMA)

            self._render(root / "extra-alias")
            (root / "extra-alias" / "static" / "legacy-support").mkdir()
            with self.assertRaises(SourceBundleError) as raised:
                validate_source_bundle(root / "extra-alias", model=_model())
            self.assertEqual(raised.exception.code, "bundle_layout_invalid")

            self._render(root / "feature-alias")
            (root / "feature-alias" / "static" / "features" / "legacy.txt").write_text(
                "legacy", encoding="utf-8"
            )
            with self.assertRaises(SourceBundleError) as raised:
                validate_source_bundle(root / "feature-alias", model=_model())
            self.assertEqual(raised.exception.code, "bundle_layout_invalid")
            self._render(root / "missing-designspace")
            static_designspace = next(
                (root / "missing-designspace" / "static").glob("*.designspace")
            )
            static_designspace.unlink()
            with self.assertRaises(SourceBundleError) as raised:
                validate_source_bundle(root / "missing-designspace", model=_model())
            self.assertEqual(raised.exception.code, "bundle_layout_invalid")

            model = _model()
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=root / "native-missing-designspace",
                    compatibility_mode="component_preserving",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model, designspace=False),
                )
            self.assertEqual(raised.exception.code, "bundle_layout_invalid")

    def test_validation_compiles_named_lookups_instead_of_only_parsing(self) -> None:
        model = _model()
        model["featurePrefixes"] = [
            {
                "name": "Mixed lookup",
                "code": (
                    "lookup MixedTypes {\n"
                    "  sub A by Aacute;\n"
                    "  pos A V -10;\n"
                    "} MixedTypes;"
                ),
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                self._render(Path(temporary) / "mixed-lookup", model=model)
        self.assertEqual(raised.exception.code, "feature_compile_failed")
        self.assertIn("same lookup type", str(raised.exception))

    def test_component_preserving_retains_components_and_blocks_topology_drift(
        self,
    ) -> None:
        model = _model()
        model["glyphs"]["Aacute"]["layers"] = [
            {
                "id": master["id"],
                "masterId": master["id"],
                "isMasterLayer": True,
                "roles": ["master"],
                "shapes": [
                    {"kind": "component", "value": {"name": "A"}}
                ],
            }
            for master in model["masters"]
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bundle"
            result = render_source_bundle(
                font=object(),
                model=model,
                destination=root,
                compatibility_mode="component_preserving",
                document_fingerprint=fingerprint_model(model),
                native_renderer=_Renderer(model, component=True),
            )
            for relative in result["masterUFOs"]:
                ufo = root / relative
                with (ufo / "glyphs" / "contents.plist").open("rb") as handle:
                    contents = plistlib.load(handle)
                glif = ufo / "glyphs" / contents["Aacute"]
                self.assertIn("<component", glif.read_text(encoding="utf-8"))

        model["glyphs"]["Aacute"]["layers"][1]["shapes"] = []
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=Path(temporary) / "incompatible",
                    compatibility_mode="component_preserving",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model, component=True),
                )
        self.assertEqual(raised.exception.code, "component_topology_incompatible")
        validate(raised.exception.to_dict(), EXPORT_ERROR_SCHEMA)

        model = _model()
        model["glyphs"]["Aacute"]["layers"] = [
            {
                "id": "m1",
                "masterId": "m1",
                "isMasterLayer": True,
                "roles": ["master"],
                "shapes": [
                    {"kind": "component", "value": {"name": "Missing"}}
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=Path(temporary) / "missing-component",
                    compatibility_mode="component_preserving",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model, component=True),
                )
        self.assertEqual(raised.exception.code, "component_reference_missing")

    def test_manifest_contract_rejects_unknown_metadata_counts_and_self_hashing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bundle"
            self._render(root)
            manifest_path = root / "source-manifest.json"
            original = manifest_path.read_bytes()
            cases = []

            unknown = json.loads(original)
            unknown["unexpected"] = True
            cases.append(unknown)

            wrong_count = json.loads(original)
            wrong_count["fileCount"] += 1
            cases.append(wrong_count)

            self_hashed = json.loads(original)
            self_hashed["manifest"]["selfHashExcluded"] = False
            cases.append(self_hashed)

            wrong_version = json.loads(original)
            wrong_version["versions"]["glyphsMcpServerVersion"] = "0.0.0"
            cases.append(wrong_version)

            includes_manifest = json.loads(original)
            includes_manifest["files"].append(
                {
                    "path": "source-manifest.json",
                    "size": len(original),
                    "sha256": hashlib.sha256(original).hexdigest(),
                }
            )
            includes_manifest["fileCount"] += 1
            cases.append(includes_manifest)

            for payload in cases:
                manifest_path.write_text(
                    json.dumps(payload, sort_keys=True), encoding="utf-8"
                )
                with self.assertRaises(SourceBundleError) as raised:
                    validate_source_bundle(root, model=_model())
                self.assertIn(
                    raised.exception.code,
                    {"manifest_contract_invalid", "manifest_verification_failed"},
                )
                manifest_path.write_bytes(original)
                self.assertEqual(
                    validate_source_bundle(root, model=_model())["manifestFileCount"],
                    json.loads(original)["fileCount"],
                )

    def test_validation_fails_closed_when_fonttools_dependencies_are_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bundle"
            self._render(root)
            real_import = __import__

            def block(name, *args, **kwargs):
                if name.startswith("fontTools.designspaceLib"):
                    raise ImportError("blocked designspaceLib")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=block):
                with self.assertRaises(SourceBundleError) as raised:
                    validate_source_bundle(root, model=_model())
            self.assertEqual(raised.exception.code, "dependency_unavailable")

            def block_fea(name, *args, **kwargs):
                if name.startswith("fontTools.feaLib"):
                    raise ImportError("blocked feaLib")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=block_fea):
                with self.assertRaises(SourceBundleError) as raised:
                    validate_source_bundle(root, model=_model())
            self.assertEqual(raised.exception.code, "dependency_unavailable")

    def test_decomposed_export_blocks_missing_cycles_and_residual_components(self) -> None:
        model = _model()
        model["glyphs"]["Aacute"]["layers"] = [
            {
                "id": "m1",
                "masterId": "m1",
                "isMasterLayer": True,
                "roles": ["master"],
                "shapes": [{"kind": "component", "value": {"name": "A"}}],
            },
            {
                "id": "m2",
                "masterId": "m2",
                "isMasterLayer": True,
                "roles": ["master"],
                "shapes": [],
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            result = self._render(
                Path(temporary) / "decomposed-topology",
                mode="decomposed_export",
                model=model,
            )
        self.assertEqual(result["compatibilityMode"], "decomposed_export")

        model = _model()
        model["glyphs"]["A"]["layers"] = [
            {"shapes": [{"kind": "component", "value": {"name": "Missing"}}]}
        ]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=Path(temporary) / "missing",
                    compatibility_mode="decomposed_export",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model),
                )
        self.assertEqual(raised.exception.code, "component_reference_missing")

        model = _model()
        model["glyphs"]["A"]["layers"] = [
            {"shapes": [{"kind": "component", "value": {"name": "V"}}]}
        ]
        model["glyphs"]["V"]["layers"] = [
            {"shapes": [{"kind": "component", "value": {"name": "A"}}]}
        ]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=Path(temporary) / "cycle",
                    compatibility_mode="decomposed_export",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model),
                )
        self.assertEqual(raised.exception.code, "component_cycle")

        model = _model()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SourceBundleError) as raised:
                render_source_bundle(
                    font=object(),
                    model=model,
                    destination=Path(temporary) / "residual",
                    compatibility_mode="decomposed_export",
                    document_fingerprint=fingerprint_model(model),
                    native_renderer=_Renderer(model, component=True),
                )
        self.assertEqual(raised.exception.code, "decomposition_incomplete")

    @unittest.skipUnless(
        importlib.util.find_spec("fontmake") is not None,
        "fontmake is an optional pinned qualification dependency",
    )
    def test_pinned_fontmake_builds_static_instances_and_variable_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = _model()
            model["features"][0]["code"] = (
                "#ifdef VARIABLE\npos A V $padding;\n#endif\n"
                "#ifndef VARIABLE\npos A V ${padding*2};\n#endif"
            )
            result = self._render(root / "bundle", model=model)
            build = root / "build"
            static_designspace = next(
                path
                for path in result["designspaceFiles"]
                if path.startswith("static/")
            )
            variable_designspace = next(
                path
                for path in result["designspaceFiles"]
                if path.startswith("variable/")
            )
            commands = [
                [
                    sys.executable,
                    "-m",
                    "fontmake",
                    "-m",
                    str(root / "bundle" / static_designspace),
                    "-M",
                    "-o",
                    "ttf",
                    "--output-dir",
                    str(build / "static-masters"),
                ],
                [
                    sys.executable,
                    "-m",
                    "fontmake",
                    "-i",
                    "--interpolate-binary-layout",
                    str(build / "static-masters"),
                    "-m",
                    str(root / "bundle" / static_designspace),
                    "-o",
                    "ttf",
                    "--output-dir",
                    str(build / "static"),
                ],
                [
                    sys.executable,
                    "-m",
                    "fontmake",
                    "-m",
                    str(root / "bundle" / variable_designspace),
                    "-o",
                    "variable",
                    "--output-dir",
                    str(build / "variable"),
                ],
            ]
            for command in commands:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=completed.stdout + "\n" + completed.stderr,
                )
            standalone = build / "standalone"
            standalone.mkdir(parents=True)
            standalone_fonts: list[Path] = []
            for relative in sorted(
                path for path in result["masterUFOs"] if path.startswith("static/")
            ):
                output = standalone / (Path(relative).stem + ".ttf")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fontmake",
                        "-u",
                        str(root / "bundle" / relative),
                        "-o",
                        "ttf",
                        "--output-path",
                        str(output),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=completed.stdout + "\n" + completed.stderr,
                )
                standalone_fonts.append(output)
            self.assertEqual(
                [
                    _feature_pair_x_advance(font, "test", "A", "V")
                    for font in standalone_fonts
                ],
                [21, 41],
            )
            self.assertEqual(
                [
                    _feature_pair_x_advance(font, "kern", "A", "V")
                    for font in standalone_fonts
                ],
                [0, -100],
            )
            variable_standalone_fonts: list[Path] = []
            for relative in sorted(
                path for path in result["masterUFOs"] if path.startswith("variable/")
            ):
                output = standalone / ("variable-" + Path(relative).stem + ".ttf")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "fontmake",
                        "-u",
                        str(root / "bundle" / relative),
                        "-o",
                        "ttf",
                        "--output-path",
                        str(output),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    msg=completed.stdout + "\n" + completed.stderr,
                )
                variable_standalone_fonts.append(output)
            self.assertEqual(
                [
                    _feature_pair_x_advance(font, "test", "A", "V")
                    for font in variable_standalone_fonts
                ],
                [10, 20],
            )
            self.assertEqual(
                [
                    _feature_pair_x_advance(font, "kern", "A", "V")
                    for font in variable_standalone_fonts
                ],
                [0, -100],
            )
            static_fonts = list((build / "static").glob("*.ttf"))
            self.assertEqual([path.name for path in static_fonts], ["BundleTest-Medium.ttf"])
            medium = static_fonts[0]
            self.assertEqual(_feature_pair_x_advance(medium, "test", "A", "V"), 31)
            self.assertEqual(_feature_pair_x_advance(medium, "kern", "A", "V"), -50)
            baseline = _shape_advances(
                medium, "AV", features={"test": False, "kern": False}
            )
            test_positioned = _shape_advances(
                medium, "AV", features={"test": True, "kern": False}
            )
            kerned = _shape_advances(
                medium, "AV", features={"test": False, "kern": True}
            )
            self.assertEqual(test_positioned[0][0] - baseline[0][0], 31)
            self.assertEqual(kerned[0][0] - baseline[0][0], -50)

            variable_fonts = list((build / "variable").glob("*.ttf"))
            self.assertEqual(len(variable_fonts), 1)
            variable_font = variable_fonts[0]
            variable_off = _shape_advances(
                variable_font,
                "AV",
                features={"kern": False},
                variations={"wght": 500},
            )
            variable_on = _shape_advances(
                variable_font,
                "AV",
                features={"kern": True},
                variations={"wght": 500},
            )
            self.assertEqual(variable_on[0][0] - variable_off[0][0], -50)
            variable_test_off = _shape_advances(
                variable_font,
                "AV",
                features={"test": False, "kern": False},
                variations={"wght": 500},
            )
            variable_test_on = _shape_advances(
                variable_font,
                "AV",
                features={"test": True, "kern": False},
                variations={"wght": 500},
            )
            self.assertEqual(
                variable_test_on[0][0] - variable_test_off[0][0], 15
            )

            rtl_off = _shape_advances(
                variable_font,
                "\u0627\u0628",
                features={"kern": False},
                variations={"wght": 500},
            )
            rtl_on = _shape_advances(
                variable_font,
                "\u0627\u0628",
                features={"kern": True},
                variations={"wght": 500},
            )
            self.assertEqual(
                sum(value[0] for value in rtl_on)
                - sum(value[0] for value in rtl_off),
                -40,
            )

            vertical_off = _shape_advances(
                variable_font,
                "AV",
                features={"vkrn": False},
                variations={"wght": 500},
                direction="ttb",
            )
            vertical_on = _shape_advances(
                variable_font,
                "AV",
                features={"vkrn": True},
                variations={"wght": 500},
                direction="ttb",
            )
            self.assertEqual(
                sum(value[1] for value in vertical_on)
                - sum(value[1] for value in vertical_off),
                50,
            )

            context_on = _shape_advances(
                variable_font,
                "AVA",
                features={"kern": True},
                variations={"wght": 500},
            )
            context_off = _shape_advances(
                variable_font,
                "AVA",
                features={"kern": False},
                variations={"wght": 500},
            )
            negative_on = _shape_advances(
                variable_font,
                "AVV",
                features={"kern": True},
                variations={"wght": 500},
            )
            negative_off = _shape_advances(
                variable_font,
                "AVV",
                features={"kern": False},
                variations={"wght": 500},
            )
            positive_delta = sum(value[0] for value in context_on) - sum(
                value[0] for value in context_off
            )
            negative_delta = sum(value[0] for value in negative_on) - sum(
                value[0] for value in negative_off
            )
            self.assertIn(positive_delta - negative_delta, {-17, -16})

            for location, ltr_value, rtl_value, vertical_value, context_value in (
                (100, 0, -30, 40, -11),
                (900, -100, -50, 60, -22),
            ):
                variations = {"wght": location}
                ltr_off = _shape_advances(
                    variable_font, "AV", features={"kern": False}, variations=variations
                )
                ltr_on = _shape_advances(
                    variable_font, "AV", features={"kern": True}, variations=variations
                )
                self.assertEqual(ltr_on[0][0] - ltr_off[0][0], ltr_value)

                rtl_off = _shape_advances(
                    variable_font,
                    "\u0627\u0628",
                    features={"kern": False},
                    variations=variations,
                )
                rtl_on = _shape_advances(
                    variable_font,
                    "\u0627\u0628",
                    features={"kern": True},
                    variations=variations,
                )
                self.assertEqual(
                    sum(value[0] for value in rtl_on)
                    - sum(value[0] for value in rtl_off),
                    rtl_value,
                )

                vertical_off = _shape_advances(
                    variable_font,
                    "AV",
                    features={"vkrn": False},
                    variations=variations,
                    direction="ttb",
                )
                vertical_on = _shape_advances(
                    variable_font,
                    "AV",
                    features={"vkrn": True},
                    variations=variations,
                    direction="ttb",
                )
                self.assertEqual(
                    sum(value[1] for value in vertical_on)
                    - sum(value[1] for value in vertical_off),
                    vertical_value,
                )

                context_on = _shape_advances(
                    variable_font, "AVA", features={"kern": True}, variations=variations
                )
                context_off = _shape_advances(
                    variable_font, "AVA", features={"kern": False}, variations=variations
                )
                negative_on = _shape_advances(
                    variable_font, "AVV", features={"kern": True}, variations=variations
                )
                negative_off = _shape_advances(
                    variable_font, "AVV", features={"kern": False}, variations=variations
                )
                self.assertEqual(
                    (
                        sum(value[0] for value in context_on)
                        - sum(value[0] for value in context_off)
                    )
                    - (
                        sum(value[0] for value in negative_on)
                        - sum(value[0] for value in negative_off)
                    ),
                    context_value,
                )


class _ApplicationExportHost:
    def __init__(self, *, fail_preflight=False):
        self.model = _model()
        for glyph in self.model["glyphs"].values():
            glyph["layers"] = [
                {
                    "id": master["id"],
                    "masterId": master["id"],
                    "isMasterLayer": True,
                    "shapes": [],
                }
                for master in self.model["masters"]
            ]
        self.fail_preflight = fail_preflight
        self.preflight_payloads = []
        self.export_payloads = []

    def runtime_snapshot(self):
        return HostRuntimeSnapshot(
            application="Glyphs",
            application_version="4.0",
            build_number="4000",
            python_version="3.14",
            open_document_count=1,
        )

    def capture_model(self, _document_id):
        return copy.deepcopy(self.model)

    def inspect_export_destination(self, _destination):
        return {"exists": False, "empty": True, "kind": None, "fingerprint": None}

    def preflight_source_bundle(self, payload):
        self.preflight_payloads.append(payload)
        if self.fail_preflight:
            raise SourceBundleError(
                "feature_compile_failed",
                "fixture preflight failure",
                target={"path": "features.fea"},
            )
        self._assert_canonical_payload(payload)
        return {
            "targetKinds": ["static", "variable"],
            "bundleFingerprint": "sha256:" + "1" * 64,
            "manifestTreeSha256": "sha256:" + "2" * 64,
            "manifestSha256": "sha256:" + "3" * 64,
            "manifestSize": 500,
            "manifestFileCount": 20,
            "designspaceFiles": ["static/a.designspace", "variable/a.designspace"],
            "masterUFOs": [
                "static/masters/m1.ufo",
                "variable/masters/m1.ufo",
            ],
            "braceUFOs": [],
            "supportFiles": ["source-manifest.json"],
            "preflight": {"featureFileCount": 4, "ufoCount": 4},
        }

    def export_source_bundle(self, payload):
        self.export_payloads.append(payload)
        self._assert_canonical_payload(payload)
        assert payload["reviewedBundleFingerprint"] == "sha256:" + "1" * 64
        assert payload["reviewedManifestTreeSha256"] == "sha256:" + "2" * 64
        assert payload["reviewedManifestSha256"] == "sha256:" + "3" * 64
        return {
            "bundleLayoutVersion": 2,
            "targetKinds": ["static", "variable"],
            "variableTargetOmittedReason": None,
            "designspaceFiles": ["static/a.designspace", "variable/a.designspace"],
            "masterUFOs": [
                "static/masters/m1.ufo",
                "variable/masters/m1.ufo",
            ],
            "braceUFOs": [],
            "supportFiles": ["source-manifest.json"],
            "buildHelperIncluded": False,
            "compatibilityMode": "component_preserving",
            "manifestTreeSha256": "sha256:" + "2" * 64,
            "manifestFileCount": 20,
            "manifestSize": 500,
            "manifestSha256": "sha256:" + "3" * 64,
            "bundleFingerprint": "sha256:" + "1" * 64,
            "preflight": {
                "bundleLayoutVersion": 2,
                "bundleFingerprint": "sha256:" + "1" * 64,
                "manifestTreeSha256": "sha256:" + "2" * 64,
                "manifestFileCount": 20,
                "featureFileCount": 4,
                "ufoCount": 4,
                "manifestSize": 500,
                "manifestSha256": "sha256:" + "3" * 64,
            },
            "destination": "/tmp/export",
            "publishedFingerprint": "sha256:" + "4" * 64,
            "replacedDestinationFingerprint": None,
            "atomicPublication": True,
        }

    def _assert_canonical_payload(self, payload):
        assert fingerprint_model(payload["canonicalModel"]) == payload["documentFingerprint"]


class V2ExportApplicationPipelineTests(unittest.TestCase):
    def test_review_preflights_then_confirmation_recaptures_and_publishes(self) -> None:
        host = _ApplicationExportHost()
        application = GlyphsMCPApplication(host)
        reviewed = application.invoke(
            "preview_export",
            {
                "documentId": "doc_bundle",
                "destination": "/tmp/export",
                "compatibilityMode": "component_preserving",
            },
        ).to_dict()
        self.assertTrue(reviewed["ok"])
        self.assertTrue(reviewed["data"]["ready"])
        self.assertEqual(reviewed["data"]["preflight"]["status"], "passed")
        self.assertEqual(len(host.preflight_payloads), 1)
        validate(reviewed, TOOL_CATALOG["preview_export"].output_schema)

        exported = application.invoke(
            "apply_export",
            {"previewId": reviewed["data"]["previewId"]},
        ).to_dict()
        self.assertTrue(exported["ok"])
        self.assertEqual(len(host.export_payloads), 1)
        self.assertEqual(exported["data"]["manifestSha256"], "sha256:" + "3" * 64)
        validate(exported, TOOL_CATALOG["apply_export"].output_schema)

    def test_confirmation_rejects_regeneration_drift_and_restored_state_re_reviews(
        self,
    ) -> None:
        host = _ApplicationExportHost()
        original = copy.deepcopy(host.model)
        application = GlyphsMCPApplication(host)
        reviewed = application.invoke(
            "preview_export",
            {
                "documentId": "doc_bundle",
                "destination": "/tmp/export",
                "compatibilityMode": "component_preserving",
            },
        ).to_dict()
        host.model["numbers"][0]["name"] = "changed_after_review"
        rejected = application.invoke(
            "apply_export",
            {"previewId": reviewed["data"]["previewId"]},
        ).to_dict()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "stale_document")
        self.assertEqual(host.export_payloads, [])

        host.model = original
        refreshed = application.invoke(
            "preview_export",
            {
                "documentId": "doc_bundle",
                "destination": "/tmp/export",
                "compatibilityMode": "component_preserving",
            },
        ).to_dict()
        exported = application.invoke(
            "apply_export",
            {"previewId": refreshed["data"]["previewId"]},
        ).to_dict()
        self.assertTrue(exported["ok"])
        self.assertEqual(len(host.export_payloads), 1)

    def test_preflight_failure_is_a_review_blocker_without_persisted_staging(self) -> None:
        host = _ApplicationExportHost(fail_preflight=True)
        application = GlyphsMCPApplication(host)
        reviewed = application.invoke(
            "preview_export",
            {
                "documentId": "doc_bundle",
                "destination": "/tmp/export",
                "compatibilityMode": "component_preserving",
            },
        ).to_dict()
        self.assertTrue(reviewed["ok"])
        self.assertFalse(reviewed["data"]["ready"])
        self.assertEqual(reviewed["data"]["preflight"]["status"], "failed")
        self.assertIn("source_bundle_preflight_failed", reviewed["data"]["blockingCodes"])
        self.assertNotIn("canonicalModel", reviewed["data"])
        validate(reviewed, TOOL_CATALOG["preview_export"].output_schema)


if __name__ == "__main__":
    unittest.main()
