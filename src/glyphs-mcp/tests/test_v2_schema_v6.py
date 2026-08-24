"""Canonical schema-v6 coverage, provenance, and representation gates."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.document import native_font_to_model, native_layer_to_model  # noqa: E402
from glyphs_mcp_v2.canonical_schema import (  # noqa: E402
    CANONICAL_FONT_SCALAR_FIELDS,
    CANONICAL_SCHEMA,
    GLYPHS_FORMAT_REVISION,
    KNOWLEDGE_REVISION,
    CanonicalCoverage,
    CoverageStatus,
    FieldRole,
    audit_official_schema,
    canonical_coverage_summary,
    deterministic_occurrence_id,
    official_schema_inventory,
    render_canonical_coverage_markdown,
)
from glyphs_mcp_v2.mutation import classify_change_path  # noqa: E402
from glyphs_mcp_v2.canonical_sources import (  # noqa: E402
    LiveGlyphsSource,
    SerializedMappingSource,
    canonical_root_from_serialized_records,
    canonical_record_value,
)
from glyphs_mcp_v2.canonical_tree import CANONICAL_MODEL_SCHEMA_VERSION  # noqa: E402
from glyphs_mcp_v2.semantic import complete_models_equal, fingerprint_model  # noqa: E402


THIRD_PARTY = REPO / "third_party" / "glyphs-file-format-v4"


class _Collection(list):
    def keys(self):
        return range(len(self))


class SchemaV6Tests(unittest.TestCase):
    def test_font_scalars_share_one_registry_driven_replay_contract(self) -> None:
        self.assertEqual(
            CANONICAL_SCHEMA.role_for("document.date"), FieldRole.WRITABLE
        )
        self.assertIn("date", CANONICAL_FONT_SCALAR_FIELDS)
        self.assertEqual(classify_change_path(("font", "date")), "writable")

    def test_legacy_parts_settings_use_native_template_replay_only(self) -> None:
        parts = CANONICAL_SCHEMA.field_spec_for_canonical(
            "definition.glyph", "partsSettings"
        )
        axes = CANONICAL_SCHEMA.field_spec_for_canonical(
            "definition.glyph", "smartAxes"
        )

        self.assertEqual(parts.role, FieldRole.READ_ONLY)
        self.assertEqual(parts.replay, "native_template_only")
        self.assertEqual(
            CANONICAL_SCHEMA.default_for_canonical(
                "definition.glyph", "partsSettings"
            ),
            [],
        )
        self.assertEqual(
            parts.native_path, "GSGlyph.propertyList.partsSettings"
        )
        self.assertEqual(axes.role, FieldRole.WRITABLE)
        self.assertEqual(classify_change_path(("glyphs", "A", "smartAxes")), "writable")
        self.assertEqual(
            classify_change_path(("glyphs", "A", "partsSettings")),
            "unsupported",
        )

    def test_pinned_knowledge_dependencies_match_bytes(self) -> None:
        manifest = json.loads(
            (THIRD_PARTY / "knowledge-dependencies.json").read_text(encoding="utf-8")
        )
        dependencies = {item["id"]: item for item in manifest["dependencies"]}
        pinned = [
            dependency
            for dependency in dependencies.values()
            if dependency["role"] != "explanatory_online"
        ]
        self.assertEqual(len(pinned), 5)
        for dependency in pinned:
            digest = hashlib.sha256(
                (THIRD_PARTY / dependency["localPath"]).read_bytes()
            ).hexdigest()
            self.assertEqual(digest, dependency["sha256"])
            self.assertRegex(dependency["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(dependency["path"])
            self.assertTrue(dependency["license"])
            self.assertTrue(dependency["auditedAt"])
        for identity in (
            "glyphs-file-format-v4-schema",
            "glyphs-file-format-v4-specification",
        ):
            self.assertEqual(dependencies[identity]["commit"], GLYPHS_FORMAT_REVISION)
        self.assertEqual(
            KNOWLEDGE_REVISION,
            "GlyphsSDK:569244a7181e08fc7c5230bcdfad6b9f7e5ea11f",
        )

    def test_every_official_schema_property_is_explicitly_classified(self) -> None:
        schema = json.loads(
            (THIRD_PARTY / "glyphs-4.schema.json").read_text(encoding="utf-8")
        )
        inventory = official_schema_inventory(schema)
        audit = audit_official_schema(schema, CANONICAL_SCHEMA)
        self.assertGreater(len(inventory), 150)
        self.assertEqual(audit.unclassified, ())
        self.assertEqual(audit.stale_registry_entries, ())
        self.assertEqual(audit.classified_count, len(inventory))
        self.assertTrue(
            all(
                spec.normalizer
                and spec.value_type
                and spec.impact
                and spec.replay
                and spec.public_redaction
                for spec in CANONICAL_SCHEMA.objects
            )
        )
        self.assertTrue(
            all(CANONICAL_SCHEMA.role_for(path) is not None for path in inventory)
        )
        self.assertEqual(
            CANONICAL_SCHEMA.role_for("definition.shapeAttr.*"),
            FieldRole.WRITABLE,
        )
        flattened = {
            spec.official_path: spec for spec in CANONICAL_SCHEMA.field_specs
        }
        self.assertEqual(set(flattened), set(inventory))
        self.assertTrue(
            all(
                spec.native_path
                and spec.serialized_path
                and spec.canonical_path
                and spec.normalizer
                and spec.impact
                and spec.replay
                for spec in flattened.values()
            )
        )
        self.assertEqual(
            flattened["definition.component.pos"].native_path,
            "GSComponent.position",
        )
        self.assertEqual(
            flattened["definition.component.pos"].canonical_path[-1],
            "position",
        )
        self.assertEqual(
            CANONICAL_SCHEMA.native_field_for_canonical(
                "definition.component", "piece"
            ),
            "smartComponentValues",
        )
        self.assertEqual(
            CANONICAL_SCHEMA.native_field_for_canonical(
                "definition.component", "masterId"
            ),
            "componentMasterId",
        )
        self.assertEqual(
            flattened["definition.hint.origin"].native_path,
            "GSHint.originIndex",
        )
        self.assertEqual(
            flattened["definition.glyph.case"].native_presence_path,
            "GSGlyph.storeCase",
        )
        self.assertEqual(
            flattened["definition.glyph.production"].native_presence_path,
            "GSGlyph.storeProductionName",
        )
        self.assertEqual(
            flattened["definition.glyph.sortName"].native_presence_path,
            "GSGlyph.storeSortName",
        )
        self.assertEqual(
            flattened["definition.glyph.sortNameKeep"].native_presence_path,
            "GSGlyph.storeSortName",
        )
        summary = canonical_coverage_summary(schema)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["unclassifiedPropertyCount"], 0)
        report = render_canonical_coverage_markdown(schema)
        self.assertIn("Knowledge revision: `GlyphsSDK:569244a7181", report)
        self.assertIn("Unclassified: 0", report)

    def test_new_official_property_never_falls_through_to_opaque(self) -> None:
        schema = json.loads(
            (THIRD_PARTY / "glyphs-4.schema.json").read_text(encoding="utf-8")
        )
        changed = copy.deepcopy(schema)
        changed["properties"]["futureGlyphsField"] = {"type": "string"}
        audit = audit_official_schema(changed, CANONICAL_SCHEMA)
        self.assertIn("document.futureGlyphsField", audit.unclassified)

    def test_model_schema_and_bounded_coverage_are_v6(self) -> None:
        self.assertEqual(CANONICAL_MODEL_SCHEMA_VERSION, 6)
        coverage = CanonicalCoverage.complete().to_public_dict()
        self.assertEqual(
            coverage,
            {
                "modelSchemaVersion": 6,
                "status": CoverageStatus.COMPLETE.value,
                "opaqueChangeCount": 0,
                "unsupportedChangeCount": 0,
                "knowledgeRevision": KNOWLEDGE_REVISION,
            },
        )
        with self.assertRaises(ValueError):
            CanonicalCoverage(
                status=CoverageStatus.COMPLETE,
                opaque_paths=(("glyphs", "A", "private"),),
            )

    def test_occurrence_id_is_deterministic_and_duplicate_safe(self) -> None:
        self.assertEqual(
            deterministic_occurrence_id("anchor", "top", 0), "anchor:top:0"
        )
        self.assertEqual(
            deterministic_occurrence_id("anchor", "top", 1), "anchor:top:1"
        )
        self.assertEqual(
            deterministic_occurrence_id("shape", "path", 0), "shape:path:0"
        )

    def test_layer_capture_uses_ordered_anchors_and_unified_shapes(self) -> None:
        anchors = [
            SimpleNamespace(
                name="top",
                position=(10, 20),
                locked=False,
                orientation=0,
                attributes={"role": "mark"},
                userData={"source": "test"},
            ),
            SimpleNamespace(
                name="top",
                position=(30, 40),
                locked=True,
                orientation=1,
                attributes={},
                userData={},
            ),
        ]
        path = SimpleNamespace(
            nodes=[
                SimpleNamespace(
                    position=(0, 0),
                    type="line",
                    smooth=False,
                    name=None,
                    orientation=0,
                    locked=False,
                    attributes={"test": 1},
                )
            ],
            closed=True,
            locked=False,
            attributes={"strokeWidth": 2},
        )
        component = SimpleNamespace(
            componentName="acute",
            position=(10, 20),
            scale=(1.2, 0.9),
            rotation=12,
            slant=(3, 0),
            transform=(1, 0, 0, 1, 10, 20),
            automaticAlignment=True,
            alignment=1,
            anchor="top",
            locked=False,
            attributes={},
            smartComponentValues=SimpleNamespace(),
        )
        layer = SimpleNamespace(
            layerId="L1",
            associatedMasterId="M1",
            name="Regular",
            isMasterLayer=True,
            isSpecialLayer=False,
            hasAlignedWidth=False,
            attributes={},
            anchors=anchors,
            shapes=[path, component],
            paths=[path],
            components=[component],
            width=600,
            leftMetricsKey=None,
            rightMetricsKey=None,
            widthMetricsKey=None,
            bottomMetricsKey=None,
            topMetricsKey=None,
            vertOriginMetricsKey=None,
            vertWidthMetricsKey=None,
            userData={},
            guides=[],
            hints=[],
            annotations=[],
            background=None,
            backgroundImage=None,
            visible=True,
            color=None,
            vertOrigin=None,
            vertWidth=None,
            partSelection={},
        )
        model = native_layer_to_model(layer)
        self.assertEqual([item["id"] for item in model["anchors"]], ["anchor:top:0", "anchor:top:1"])
        self.assertEqual([item["kind"] for item in model["shapes"]], ["path", "component"])
        # Master visibility belongs to the font-master record. Glyphs exposes
        # the inherited value on every master layer even when no layer-level
        # `visible` key exists in the saved document.
        self.assertFalse(model["visible"])
        self.assertNotIn("paths", model)
        self.assertNotIn("components", model)
        self.assertEqual(model["shapes"][0]["value"]["nodes"][0]["attributes"], {"test": 1})
        component_model = model["shapes"][1]["value"]
        self.assertEqual(component_model["position"], [10.0, 20.0])
        self.assertEqual(component_model["scale"], [1.2, 0.9])
        self.assertEqual(component_model["angle"], 12)
        self.assertEqual(component_model["slant"], [3.0, 0.0])
        self.assertEqual(component_model["piece"], {})
        self.assertEqual(model["vertOrigin"], 0)
        self.assertEqual(model["vertWidth"], 0)

    def test_all_saved_document_roots_are_present_and_kerning_is_directional(self) -> None:
        font = SimpleNamespace(
            familyName="Schema V6",
            upm=1000,
            versionMajor=1,
            versionMinor=0,
            note="",
            date="2026-08-22",
            grid=1,
            gridSubDivision=1,
            axes=[],
            masters=[],
            instances=[],
            glyphs=[],
            kerning={"M1": {"A": {"V": -80}}},
            kerningRTL={"M1": {"alef": {"lam": -40}}},
            kerningVertical={"M1": {"A": {"V": -20}}},
            kerningContext={"M1": {}},
            features=[],
            classes=[],
            featurePrefixes=[],
            customParameters=[],
            properties=[],
            metrics=[],
            stems=[],
            numbers=[],
            userData={},
            settings={},
        )
        model = native_font_to_model(font)
        self.assertTrue(
            {
                "font",
                "axes",
                "masters",
                "instances",
                "glyphs",
                "kerning",
                "features",
                "classes",
                "featurePrefixes",
                "metrics",
                "stems",
                "numbers",
                "settings",
            }.issubset(model)
        )
        self.assertEqual(set(model["kerning"]), {"ltr", "rtl", "vertical", "context"})

    def test_selector_backed_official_fields_resolve_to_values(self) -> None:
        feature = SimpleNamespace(
            name="liga",
            tag=lambda: "liga",
            code="sub f i by fi;",
            automatic=False,
            disabled=False,
            notes=None,
            labels=[],
        )
        font = SimpleNamespace(
            familyName="Schema V6 Selectors",
            upm=1000,
            versionMajor=1,
            versionMinor=0,
            note="",
            date=None,
            grid=1,
            gridSubDivision=1,
            axes=[],
            masters=[],
            instances=[],
            glyphs=[],
            kerning={},
            kerningRTL={},
            kerningVertical={},
            kerningContext={},
            features=[feature],
            classes=[],
            featurePrefixes=[],
            customParameters=[],
            properties=[],
            metrics=[],
            stems=[],
            numbers=[],
            userData={},
            settings={},
        )

        model = native_font_to_model(font)

        self.assertEqual(model["features"][0]["tag"], "liga")
        self.assertNotIn("selector", model["features"][0]["tag"])

    def test_source_seam_uses_one_canonical_fingerprint(self) -> None:
        model = {
            "font": {"familyName": "Source"},
            "axes": [],
            "masters": [],
            "instances": [],
            "glyphs": {},
            "kerning": {"ltr": {}, "rtl": {}, "vertical": {}, "context": {}},
            "features": [],
            "classes": [],
            "featurePrefixes": [],
            "metrics": [],
            "stems": [],
            "numbers": [],
            "settings": {},
        }
        serialized = SerializedMappingSource(model).capture()
        live = LiveGlyphsSource(object(), capture=lambda _font: copy.deepcopy(model)).capture()
        self.assertEqual(fingerprint_model(serialized), fingerprint_model(live))

    def test_flat_package_and_live_sources_converge(self) -> None:
        flat = {
            ".appVersion": "4012",
            ".formatVersion": 4,
            "axes": [{"tag": "wght", "name": "Weight"}],
            "fontMaster": [
                {"id": "M1", "name": "Regular", "axesValues": [400]}
            ],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "properties": [{"key": "familyNames", "value": "Fixture"}],
            "settings": {"gridLength": 1, "gridSubDivision": 1},
            "glyphs": [
                {
                    "glyphname": "A",
                    # Glyphs' v4 serializer stores code points as decimal
                    # numbers while the live API exposes uppercase hex.
                    "unicode": 65,
                    "layers": [
                        {
                            "layerId": "M1",
                            "width": 600,
                            "anchors": [
                                {"name": "top", "pos": [300, 700]},
                                {"name": "top", "pos": [300, 710]},
                            ],
                            "shapes": [
                                {
                                    "closed": 1,
                                    "nodes": [
                                        [0, 0, "l"],
                                        [300, 700, "ls"],
                                        [600, 0, "l"],
                                    ],
                                },
                                {"ref": "acute", "pos": [10, 20]},
                            ],
                        }
                    ],
                }
            ],
            "kerningLTR": {"M1": {"A": {"V": -80}}},
        }
        package = {
            "fontinfo.plist": {
                key: copy.deepcopy(value)
                for key, value in flat.items()
                if key not in {"glyphs", "kerningLTR"}
            },
            "glyphs": {"A": copy.deepcopy(flat["glyphs"][0])},
            "order.plist": ["A"],
            "kerning.plist": {"kerningLTR": copy.deepcopy(flat["kerningLTR"])},
            "UIState.plist": {"displayStrings": ["ignored"]},
        }
        canonical_flat = SerializedMappingSource(flat).capture()
        canonical_package = SerializedMappingSource(package).capture()
        defaulted_master = copy.deepcopy(flat)
        defaulted_master["fontMaster"][0].pop("name")
        canonical_defaulted_master = SerializedMappingSource(
            defaulted_master
        ).capture()
        expanded = copy.deepcopy(flat)
        expanded["glyphs"][0]["layers"][0]["shapes"][0]["nodes"] = [
            {"pos": [0, 0], "type": "LINE", "smooth": "0"},
            {
                "pos": [300, 700],
                "type": "LINE",
                "connection": "SMOOTH",
                "smooth": "1",
            },
            {"pos": [600, 0], "type": "LINE", "smooth": "0"},
        ]
        canonical_expanded = SerializedMappingSource(expanded).capture()
        native_expanded = copy.deepcopy(expanded)
        native_expanded["glyphs"][0]["layers"][0]["shapes"][0]["nodes"][1].pop(
            "connection"
        )
        native_expanded["glyphs"][0]["layers"][0]["shapes"][0]["nodes"][1].pop(
            "smooth"
        )
        native_expanded["glyphs"][0]["layers"][0]["shapes"][0]["nodes"][1][
            "conn"
        ] = "smooth"
        canonical_native_expanded = SerializedMappingSource(
            native_expanded
        ).capture()
        borrowed_expanded = SerializedMappingSource(
            expanded, copy_source=False
        ).capture()
        canonical_live = LiveGlyphsSource(
            object(), capture=lambda _font: copy.deepcopy(canonical_flat)
        ).capture()
        self.assertEqual(
            fingerprint_model(canonical_flat),
            fingerprint_model(canonical_package),
        )
        self.assertEqual(
            fingerprint_model(canonical_flat),
            fingerprint_model(canonical_defaulted_master),
        )
        self.assertEqual(
            fingerprint_model(canonical_flat),
            fingerprint_model(canonical_expanded),
        )
        self.assertEqual(
            fingerprint_model(canonical_flat),
            fingerprint_model(canonical_native_expanded),
        )
        self.assertEqual(canonical_expanded, borrowed_expanded)
        borrowed_expanded["glyphs"]["A"]["layers"][0]["width"] = 999
        self.assertNotEqual(expanded["glyphs"][0]["layers"][0]["width"], 999)
        self.assertEqual(
            fingerprint_model(canonical_flat),
            fingerprint_model(canonical_live),
        )
        anchors = canonical_flat["glyphs"]["A"]["layers"][0]["anchors"]
        self.assertEqual(canonical_flat["glyphs"]["A"]["unicode"], "0041")
        self.assertEqual(canonical_flat["glyphs"]["A"]["unicodes"], ["0041"])
        self.assertEqual(
            canonical_flat["glyphs"]["A"]["layers"][0]["name"], "Regular"
        )
        self.assertEqual(
            [anchor["id"] for anchor in anchors],
            ["anchor:top:0", "anchor:top:1"],
        )
        self.assertEqual(
            [shape["kind"] for shape in canonical_flat["glyphs"]["A"]["layers"][0]["shapes"]],
            ["path", "component"],
        )
        component = canonical_flat["glyphs"]["A"]["layers"][0]["shapes"][1]["value"]
        self.assertEqual(component["position"], [10, 20])
        self.assertEqual(component["scale"], [1.0, 1.0])
        self.assertEqual(component["slant"], [0.0, 0.0])

    def test_foundation_numeric_unicode_strings_keep_decimal_semantics(self) -> None:
        serialized = SerializedMappingSource(
            {
                "fontMaster": [],
                "glyphs": [
                    {"glyphname": "A", "unicode": "65", "layers": []},
                    {
                        "glyphname": "amacron",
                        "unicode": "257",
                        "layers": [],
                    },
                ],
            },
            copy_source=False,
        ).capture()

        self.assertEqual(serialized["glyphs"]["A"]["unicode"], "0041")
        self.assertEqual(serialized["glyphs"]["amacron"]["unicode"], "0101")

    def test_glyph_sort_name_keep_preserves_the_official_string_type(self) -> None:
        serialized = SerializedMappingSource(
            {
                "fontMaster": [],
                "glyphs": [
                    {
                        "glyphname": "A.alt",
                        "sortName": "A",
                        "sortNameKeep": "A.keep",
                        "layers": [],
                    }
                ],
            },
            copy_source=False,
        ).capture()

        glyph = serialized["glyphs"]["A.alt"]
        self.assertEqual(glyph["sortName"], "A")
        self.assertEqual(glyph["sortNameKeep"], "A.keep")
        self.assertIsInstance(glyph["sortNameKeep"], str)

    def test_serialized_feature_identity_is_its_official_tag(self) -> None:
        serialized = SerializedMappingSource(
            {
                "fontMaster": [],
                "glyphs": [],
                "features": [
                    {
                        "tag": "cv99",
                        "code": "sub A by A;",
                        "automatic": 0,
                        "disabled": 0,
                    }
                ],
            },
            copy_source=False,
        ).capture()

        self.assertEqual(serialized["features"][0]["id"], "cv99")
        self.assertEqual(serialized["features"][0]["name"], "cv99")
        self.assertEqual(serialized["features"][0]["tag"], "cv99")
        feature_spec = CANONICAL_SCHEMA.object_for("definition.feature")
        self.assertEqual(feature_spec.canonical_path, ("features",))
        self.assertEqual(feature_spec.identity, "tag")
        self.assertTrue(feature_spec.ordered)

    def test_borrowed_flat_source_does_not_copy_excluded_provenance(self) -> None:
        class DeepcopyTrap:
            def __deepcopy__(self, memo):
                raise AssertionError("excluded source provenance was deep-copied")

        model = SerializedMappingSource(
            {
                ".appVersion": DeepcopyTrap(),
                "fontMaster": [],
                "glyphs": [],
            },
            copy_source=False,
        ).capture()

        self.assertEqual(model["masters"], [])
        self.assertEqual(model["glyphs"], {})

    def test_foundation_numeric_atoms_match_native_numeric_values(self) -> None:
        numeric = {
            "axes": [{"tag": "wght", "default": 400}],
            "fontMaster": [{
                "id": "M1",
                "italicAngle": -12.5,
                "axesValues": [400],
                "metricValues": [{"pos": 700, "over": 12}],
            }],
            "instances": [{
                "id": "I1",
                "axesValues": [400],
                "weightClass": 400,
                "widthClass": 5,
            }],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "settings": {
                "gridLength": 1,
                "gridSubDivision": 1,
                "keyboardIncrement": 0.5,
            },
            "glyphs": [{
                "glyphname": "A",
                "unicode": 65,
                "color": 5,
                "groupIdx": 3,
                "layers": [{
                    "layerId": "M1",
                    "width": 600,
                    "vertOrigin": 800,
                    "anchors": [{"name": "top", "pos": [300, 700]}],
                    "annotations": [{"angle": 12.5, "pos": [10, 20], "width": 40}],
                    "shapes": [{
                        "closed": 1,
                        "nodes": [[0, 0, "l"], [300.5, 700, "ls"]],
                    }],
                }],
            }],
            "kerningLTR": {"M1": {"A": {"V": -80}}},
        }

        def foundation_atoms(value):
            if isinstance(value, dict):
                return {key: foundation_atoms(item) for key, item in value.items()}
            if isinstance(value, list):
                return [foundation_atoms(item) for item in value]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return str(value)
            return value

        foundation = foundation_atoms(numeric)
        self.assertEqual(
            SerializedMappingSource(numeric).capture(),
            SerializedMappingSource(foundation).capture(),
        )

    def test_serialized_kerning_uses_semantic_glyph_identity(self) -> None:
        model = SerializedMappingSource(
            {
                "glyphs": [
                    {"glyphname": "A", "layers": []},
                    {"glyphname": "V", "layers": []},
                ],
                "kerningLTR": {
                    "M1": {
                        "A": {"V": -80},
                        "@MMK_L_A": {"@MMK_R_V": -70},
                        "missing": {"V": -20},
                    }
                },
            }
        ).capture()

        self.assertEqual(
            model["kerning"]["ltr"],
            {
                "M1": {
                    "glyph_A": {"glyph_V": -80},
                    "@MMK_L_A": {"@MMK_R_V": -70},
                    "missing": {"glyph_V": -20},
                }
            },
        )

    def test_serialized_master_values_bind_to_semantic_root_definitions(self) -> None:
        model = SerializedMappingSource(
            {
                "fontMaster": [
                    {
                        "id": "M1",
                        "metricValues": [{"pos": 700, "over": 12}],
                        "stemValues": [86],
                        "numberValues": [14],
                    }
                ],
                "metrics": [{"type": 1}],
                "stems": [{"name": "Primary Vertical Stem"}],
                "numbers": [{"name": "Overshoot Amount"}],
                "glyphs": [],
            },
            copy_source=False,
        ).capture()

        master = model["masters"][0]
        self.assertEqual(
            master["metricValues"],
            [{"id": model["metrics"][0]["id"], "pos": 700, "over": 12}],
        )
        self.assertEqual(
            master["stemValues"],
            [{"id": model["stems"][0]["id"], "value": 86}],
        )
        self.assertEqual(
            master["numberValues"],
            [{"id": model["numbers"][0]["id"], "value": 14}],
        )

    def test_saved_and_native_clone_spellings_share_semantic_state(self) -> None:
        document_path = Path("/Fonts/Family/Source.glyphspackage")
        saved = {
            "axes": [
                {"tag": "wght"},
                {"tag": "wdth"},
                {"tag": "ital"},
            ],
            "fontMaster": [{"id": "M1", "stemValues": [86]}],
            "stems": [{"name": "Primary Vertical Stem"}],
            "instances": [
                {
                    "id": "static",
                    "axesValues": [400, 100, 0],
                    # Glyphs persists this calculated cache, but the format
                    # explicitly says it is inactive without the manual flag.
                    "instanceInterpolations": {"M1": 1},
                },
                {"id": "variable", "type": "variable"},
            ],
            "glyphs": [
                {
                    "glyphname": "E",
                    "layers": [
                        {"layerId": "M1"},
                        {
                            "layerId": "backup",
                            "associatedMasterId": "M1",
                            # The file record's layer ownership carries the
                            # local-key bit that the live API spells as `==`.
                            "metricLeft": "=H",
                        },
                    ],
                },
                {
                    "glyphname": "t",
                    "layers": [
                        {
                            "layerId": "M1",
                            "backgroundImage": {
                                "imagePath": "Images/t.tif",
                            },
                        }
                    ],
                },
            ],
        }
        native_clone = copy.deepcopy(saved)
        native_clone["fontMaster"][0]["stemValues"] = [
            {"width": 86, "id": "native-stem-id"}
        ]
        native_clone["instances"][0]["instanceInterpolations"] = {}
        native_clone["instances"][1]["axesValues"] = [0, 0, 0]
        native_clone["glyphs"][0]["layers"][1]["metricLeft"] = "==H"
        native_clone["glyphs"][1]["layers"][0]["backgroundImage"][
            "imagePath"
        ] = "/Fonts/Family/Images/t.tif"

        saved_model = SerializedMappingSource(
            saved, document_path=document_path
        ).capture()
        clone_model = SerializedMappingSource(
            native_clone, document_path=document_path
        ).capture()

        self.assertEqual(saved_model, clone_model)
        self.assertEqual(
            saved_model["glyphs"]["E"]["layers"][1]["leftMetricsKey"],
            "==H",
        )
        self.assertEqual(
            saved_model["glyphs"]["t"]["layers"][0]["backgroundImage"][
                "imagePath"
            ],
            "Images/t.tif",
        )
        self.assertEqual(saved_model["instances"][0]["instanceInterpolations"], {})
        self.assertEqual(
            [axis["internal"] for axis in saved_model["instances"][1]["axes"]],
            [0, 0, 0],
        )

    def test_serialized_instance_axes_values_are_effective_external_coordinates(self) -> None:
        model = SerializedMappingSource(
            {
                "axes": [{"tag": "wght"}, {"tag": "wdth"}],
                "fontMaster": [{"id": "M1", "axesValues": [400, 100]}],
                "instances": [{"axesValues": [650, 82]}],
                "glyphs": [],
            },
            copy_source=False,
        ).capture()

        self.assertEqual(
            model["instances"][0]["axes"],
            [
                {"tag": "wght", "internal": 650, "external": 650},
                {"tag": "wdth", "internal": 82, "external": 82},
            ],
        )

    def test_manual_instance_interpolations_remain_meaningful(self) -> None:
        first = {
            "fontMaster": [{"id": "M1"}],
            "instances": [
                {
                    "manualInterpolation": 1,
                    "instanceInterpolations": {"M1": 1},
                }
            ],
            "glyphs": [],
        }
        second = copy.deepcopy(first)
        second["instances"][0]["instanceInterpolations"]["M1"] = 0.5

        first_model = SerializedMappingSource(first).capture()
        second_model = SerializedMappingSource(second).capture()

        self.assertNotEqual(first_model, second_model)
        self.assertEqual(
            first_model["instances"][0]["instanceInterpolations"], {"M1": 1}
        )

    def test_serialized_instance_name_comes_from_official_style_names(self) -> None:
        model = SerializedMappingSource(
            {
                "fontMaster": [{"id": "M1"}],
                "instances": [
                    {
                        # A top-level name is not part of the official v4
                        # instance record and must not override styleNames.
                        "name": "Noncanonical projection",
                        "properties": [
                            {
                                "key": "styleNames",
                                "values": [
                                    {"language": "FRA", "value": "Graisse"},
                                    {"language": "dflt", "value": "Bold"},
                                ],
                            }
                        ],
                    }
                ],
                "glyphs": [],
            }
        ).capture()

        self.assertEqual(model["instances"][0]["name"], "Bold")

    def test_bounded_instance_records_preserve_the_canonical_identity_context(self) -> None:
        instances = canonical_root_from_serialized_records(
            "instances",
            [
                {
                    "properties": [
                        {
                            "key": "styleNames",
                            "values": [
                                {"language": "dflt", "value": "Bold"}
                            ],
                        }
                    ]
                }
            ],
            context={
                "axes": [],
                "instances": [{"id": "instance_review_local"}],
            },
        )

        self.assertEqual(instances[0]["id"], "instance_review_local")
        self.assertEqual(instances[0]["name"], "Bold")

    def test_extension_numeric_atoms_are_source_neutral(self) -> None:
        numeric = {
            "fontMaster": [{"id": "M1"}],
            "userData": {
                "backdropGlyphLib": {"A": [["A", 1, 0], ["B", -2, 0.5]]},
                "intentionalCode": "001",
            },
            "customParameters": [
                {"name": "Extension", "value": {"coordinates": [1, 0.5]}},
            ],
            "glyphs": [
                {
                    "glyphname": "A",
                    "userData": {"coordinates": [1, 0.5]},
                    "layers": [
                        {
                            "layerId": "M1",
                            "attr": {"extension": [1, 0.5]},
                        }
                    ],
                }
            ],
        }
        flattened = copy.deepcopy(numeric)
        flattened["userData"]["backdropGlyphLib"]["A"][0][1:] = ["1", "0"]
        flattened["userData"]["backdropGlyphLib"]["A"][1][1:] = ["-2", "0.5"]
        flattened["customParameters"][0]["value"]["coordinates"] = ["1", "0.5"]
        flattened["glyphs"][0]["userData"]["coordinates"] = ["1", "0.5"]
        flattened["glyphs"][0]["layers"][0]["attr"]["extension"] = ["1", "0.5"]

        canonical_numeric = SerializedMappingSource(numeric).capture()
        canonical_flattened = SerializedMappingSource(flattened).capture()
        self.assertEqual(canonical_numeric, canonical_flattened)
        self.assertEqual(
            canonical_flattened["font"]["userData"]["intentionalCode"],
            "001",
        )

    def test_editor_derived_verdicts_do_not_change_document_identity(self) -> None:
        before = SerializedMappingSource(
            {
                "fontMaster": [{"id": "M1", "name": "Regular"}],
                "glyphs": [
                    {
                        "glyphname": "A",
                        "layers": [{"layerId": "M1", "width": 600}],
                    }
                ],
            }
        ).capture()
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["mastersCompatible"] = False
        after["glyphs"]["A"]["layers"][0]["hasAlignedWidth"] = True

        self.assertEqual(fingerprint_model(before), fingerprint_model(after))
        self.assertFalse(complete_models_equal(before, after))

    def test_official_string_enums_share_the_native_canonical_representation(self) -> None:
        serialized = {
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "metrics": [{"type": "ascender"}],
            "glyphs": [
                {
                    "glyphname": "A",
                    "case": "upper",
                    "direction": "RTL",
                    "layers": [
                        {
                            "layerId": "M1",
                            "annotations": [{"type": "Text"}],
                            "guides": [
                                {"type": "Circle", "orientation": "right"}
                            ],
                            "hints": [{"type": "Corner"}],
                        }
                    ],
                }
            ],
        }

        model = SerializedMappingSource(serialized).capture()
        glyph = model["glyphs"]["A"]
        layer = glyph["layers"][0]

        self.assertEqual(glyph["case"], 1)
        self.assertEqual(glyph["direction"], 2)
        self.assertEqual(layer["annotations"][0]["type"], 1)
        self.assertEqual(layer["guides"][0]["type"], 1)
        self.assertEqual(layer["guides"][0]["orientation"], 2)
        self.assertEqual(layer["hints"][0]["type"], 16)
        self.assertEqual(model["metrics"][0]["type"], 1)

    def test_provenance_ui_and_numeric_spelling_do_not_create_false_diff(self) -> None:
        first = {
            ".appVersion": "4004",
            ".formatVersion": 4,
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "settings": {"gridLength": 1},
            "glyphs": [],
        }
        second = copy.deepcopy(first)
        second[".appVersion"] = "4999"
        second["DisplayStrings"] = ["A/V"]
        second["unitsPerEm"] = 1000.0
        self.assertEqual(
            fingerprint_model(SerializedMappingSource(first).capture()),
            fingerprint_model(SerializedMappingSource(second).capture()),
        )

    def test_omitted_format_defaults_do_not_create_false_diffs(self) -> None:
        omitted = {
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "glyphs": [{
                "glyphname": "A",
                "layers": [{
                    "layerId": "M1",
                    "width": 600,
                    "shapes": [{"ref": "acute"}],
                }],
            }],
        }
        explicit = copy.deepcopy(omitted)
        explicit["fontMaster"][0].update({
            "active": True,
            "visible": True,
            "iconName": "Regular",
            "axesValues": [],
            "customParameters": [],
            "guides": [],
            "metricValues": [],
            "numberValues": [],
            "properties": [],
            "stemValues": [],
            "userData": {},
        })
        explicit["glyphs"][0].update({
            "export": True,
            "groupIdx": 0,
            "locked": False,
            "note": "",
            "partsSettings": [],
            "tags": [],
            "userData": {},
        })
        explicit_layer = explicit["glyphs"][0]["layers"][0]
        explicit_layer.update({
            "active": True,
            "anchors": [],
            "annotations": [],
            "attr": {},
            "guides": [],
            "hints": [],
            "name": "",
            "userData": {},
            "vertOrigin": 0,
            "vertWidth": 0,
            "visible": False,
        })
        explicit_layer["shapes"][0].update({
            "alignment": 0,
            "angle": 0,
            "attr": {},
            "keepWeight": 0,
            "locked": False,
            "orientation": 0,
            "piece": {},
            "pos": [0, 0],
            "scale": [1, 1],
            "slant": [0, 0],
            "traverseAnchors": True,
        })
        self.assertEqual(
            SerializedMappingSource(omitted).capture(),
            SerializedMappingSource(explicit).capture(),
        )

    def test_anchor_orientation_and_layer_vertical_defaults_are_source_neutral(self) -> None:
        omitted = {
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "glyphs": [{
                "glyphname": "A",
                "layers": [{
                    "layerId": "M1",
                    "width": 600,
                    "anchors": [{"name": "top", "pos": [300, 700]}],
                }],
            }],
        }
        explicit = copy.deepcopy(omitted)
        explicit_layer = explicit["glyphs"][0]["layers"][0]
        explicit_layer.update({"vertOrigin": 0, "vertWidth": 0})
        explicit_layer["anchors"][0]["orientation"] = "left"

        self.assertEqual(
            SerializedMappingSource(omitted).capture(),
            SerializedMappingSource(explicit).capture(),
        )

    def test_native_hint_not_found_stem_is_canonical_absence(self) -> None:
        self.assertIsNone(canonical_record_value("hint", "stem", 2**63 - 1))

    def test_meaningful_glyph_order_is_observable(self) -> None:
        flat = {
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "glyphs": [{"glyphname": "A"}, {"glyphname": "B"}],
        }
        reversed_flat = copy.deepcopy(flat)
        reversed_flat["glyphs"].reverse()
        self.assertNotEqual(
            fingerprint_model(SerializedMappingSource(flat).capture()),
            fingerprint_model(SerializedMappingSource(reversed_flat).capture()),
        )

    def test_omitted_and_empty_layer_backgrounds_are_one_semantic_state(self) -> None:
        omitted = {
            "fontMaster": [{"id": "M1"}],
            "unitsPerEm": 1000,
            "versionMajor": 1,
            "versionMinor": 0,
            "glyphs": [
                {
                    "glyphname": "A",
                    "layers": [{"layerId": "M1", "shapes": []}],
                }
            ],
        }
        explicit = copy.deepcopy(omitted)
        explicit["glyphs"][0]["layers"][0]["background"] = {}

        self.assertEqual(
            SerializedMappingSource(omitted).capture(),
            SerializedMappingSource(explicit).capture(),
        )

    def test_independent_schema_v6_audit_passes_offline(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "audit_canonical_schema_v6.py"),
                "--repo-root",
                str(REPO),
            ],
            cwd=REPO,
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["coverage"]["modelSchemaVersion"], 6)
        self.assertEqual(payload["coverage"]["unclassifiedPropertyCount"], 0)
        self.assertEqual(
            payload["flattenedFieldSpecCount"],
            payload["coverage"]["officialPropertyCount"],
        )
        architecture = payload["architecturalChecks"]
        self.assertTrue(architecture["singleNativeReplayAdapter"])
        self.assertTrue(architecture["singleVerifiedMutationKernel"])
        self.assertTrue(architecture["nativeImportsBoundedToAdaptersAndUI"])
        self.assertFalse(architecture["reporterCanonicalWork"])
        self.assertTrue(architecture["independentTransitionRoundTrip"])
        self.assertTrue(all(architecture["registryConsumers"].values()))


if __name__ == "__main__":
    unittest.main()
