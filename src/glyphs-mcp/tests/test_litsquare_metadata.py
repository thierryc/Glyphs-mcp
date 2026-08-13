"""LitSquare metadata contract, projection, inheritance, and role tests."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


def _load():
    path = RESOURCES / "litsquare_metadata.py"
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_litsquare_metadata", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LitSquareMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load()

    def valid_root(self):
        return {
            "schemaVersion": 1,
            "updatedAt": "2026-08-11T18:30:00Z",
            "settings": {"grid": 24},
            "notes": [{"id": "n1", "text": "Review joins"}],
        }

    def test_missing_empty_valid_and_unsupported_states(self):
        self.assertEqual(self.module.validate_metadata(None, present=False)["state"], "missing")
        self.assertEqual(self.module.validate_metadata({}, present=True)["state"], "empty")
        self.assertEqual(self.module.validate_metadata(self.valid_root())["state"], "valid")
        future = self.valid_root()
        future["schemaVersion"] = 2
        self.assertEqual(self.module.validate_metadata(future)["state"], "unsupported_schema")
        self.assertEqual(
            self.module.validate_metadata({"schemaVersion": 2, "futureField": True})["state"],
            "unsupported_schema",
        )

    def test_invalid_known_fields_and_property_list_values(self):
        invalid = self.valid_root()
        invalid["settings"] = []
        self.assertEqual(self.module.validate_metadata(invalid)["state"], "invalid")

        invalid = self.valid_root()
        invalid["memory"] = {"bad": None}
        result = self.module.validate_metadata(invalid)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("null_not_allowed", {error["code"] for error in result["errors"]})

        invalid = self.valid_root()
        invalid["status"] = {"bad": float("inf")}
        result = self.module.validate_metadata(invalid)
        self.assertIn("non_finite_number", {error["code"] for error in result["errors"]})

        invalid = self.valid_root()
        invalid["updatedAt"] = "2026-99-99T18:30:00Z"
        result = self.module.validate_metadata(invalid)
        self.assertIn("invalid_updated_at", {error["code"] for error in result["errors"]})

    def test_notes_require_id_text_and_string_metadata(self):
        invalid = self.valid_root()
        invalid["notes"] = [{"id": "", "text": 12, "author": False}]
        result = self.module.validate_metadata(invalid)
        self.assertEqual(result["state"], "invalid")
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_json_projection_is_stable_unicode_and_binary_aware(self):
        value = self.valid_root()
        value["zeta"] = "café"
        value["alpha"] = b"\x00\xff"
        text = self.module.canonical_json(value)
        self.assertTrue(text.endswith("\n"))
        self.assertIn("café", text)
        self.assertLess(text.index('"schemaVersion"'), text.index('"settings"'))
        self.assertLess(text.index('"alpha"'), text.index('"zeta"'))
        parsed = json.loads(text)
        self.assertEqual(parsed["alpha"]["$binary"]["data"], "AP8=")
        self.assertEqual(self.module.from_json_projection(parsed)["alpha"], b"\x00\xff")
        with self.assertRaisesRegex(ValueError, "base64"):
            self.module.from_json_projection({"$binary": {"encoding": "base64", "data": "%%%"}})

    def test_native_inspection_projection_preserves_values_and_marks_diagnostics(self):
        class NativeThing:
            def __str__(self):
                return "native description"

        source = {
            "binary": b"\x00\xff",
            "date": datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc),
            "nested": ["café", True, 3.5],
            "unsupported": NativeThing(),
        }
        projected = self.module.native_inspection_projection(source)
        self.assertEqual(projected["value"]["binary"]["$binary"]["data"], "AP8=")
        self.assertEqual(projected["value"]["date"], {"$date": "2026-08-12T14:30:00Z"})
        self.assertEqual(projected["value"]["nested"], ["café", True, 3.5])
        self.assertEqual(
            projected["value"]["unsupported"]["$nativeObject"],
            {"type": "NativeThing", "description": "native description"},
        )
        self.assertEqual(
            [warning["code"] for warning in projected["warnings"]],
            ["unsupported_native_object"],
        )
        json.loads(self.module.canonical_json(projected["value"]))

    def test_native_inspection_projection_survives_non_json_native_shapes(self):
        recursive = []
        recursive.append(recursive)
        projected = self.module.native_inspection_projection(
            {"null": None, "infinite": float("inf"), "recursive": recursive}
        )
        codes = {warning["code"] for warning in projected["warnings"]}
        self.assertEqual(
            codes,
            {"native_null", "non_finite_number", "recursive_value"},
        )
        self.assertIn("$nativeObject", projected["value"]["recursive"][0])

        keyed = self.module.native_inspection_projection({1: "one"})
        self.assertIn("$nativeDictionary", keyed["value"])
        self.assertEqual(keyed["warnings"][0]["code"], "non_string_key")

    def test_editable_json_parser_accepts_valid_roots_and_rejects_invalid_input(self):
        native, validation = self.module.parse_metadata_json(
            self.module.canonical_json(self.valid_root())
        )
        self.assertEqual(native["settings"], {"grid": 24})
        self.assertEqual(validation["state"], "valid")
        self.assertEqual(self.module.parse_metadata_json("{}\n")[0], {})
        for text in ("mixedvalue", "[]", '{"schemaVersion": 2}', '{"settings": null}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "Invalid input"):
                self.module.parse_metadata_json(text)

    def test_path_role_editor_projection_is_json_object_or_blank(self):
        self.assertEqual(
            self.module.parse_path_role_json('{"role": "  My Custom Role  "}'),
            "My Custom Role",
        )
        self.assertIsNone(self.module.parse_path_role_json(""))
        self.assertIsNone(self.module.parse_path_role_json("{}"))
        self.assertIsNone(self.module.parse_path_role_json('{"role": null}'))
        for text in ('{"role": 3}', '{"role": "body", "other": true}', "body"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "Invalid input"):
                self.module.parse_path_role_json(text)

    def test_canonical_json_sorts_nested_content_without_root_field_bias(self):
        value = self.valid_root()
        value["settings"] = {"status": 2, "alpha": 1}
        parsed_pairs = json.loads(
            self.module.canonical_json(value), object_pairs_hook=lambda pairs: pairs
        )
        self.assertEqual(parsed_pairs[0][0], "schemaVersion")
        settings = dict(parsed_pairs)["settings"]
        self.assertEqual([key for key, _value in settings], ["alpha", "status"])

    def test_merge_patch_preserves_unknowns_and_uses_null_as_delete(self):
        current = self.valid_root()
        current["unknown"] = {"keep": True, "remove": 3}
        proposed = self.module.merge_patch(
            current,
            {"settings": {"grid": 32}, "unknown": {"remove": None}},
        )
        self.assertEqual(proposed["settings"]["grid"], 32)
        self.assertEqual(proposed["unknown"], {"keep": True})
        self.assertEqual(current["unknown"]["remove"], 3)

    def test_effective_settings_are_shallow_and_provenanced(self):
        scopes = {
            "font": {"value": {"settings": {"grid": 24, "nested": {"font": True}}}},
            "glyph": {"value": {"settings": {"nested": {"glyph": True}}}},
            "layer": {"value": {"settings": {"grid": 20}}},
        }
        result = self.module.effective_settings(scopes)
        self.assertEqual(result["values"], {"grid": 20, "nested": {"glyph": True}})
        self.assertEqual(result["provenance"], {"grid": "layer", "nested": "glyph"})

    def test_role_normalization_accepts_open_strings_and_distinguishes_invalid(self):
        self.assertEqual(self.module.normalize_role(None, False)["state"], "unassigned")
        self.assertEqual(self.module.normalize_role("body", True)["state"], "valid")
        custom = self.module.normalize_role("  My Custom Role  ", True)
        self.assertEqual(custom["state"], "valid")
        self.assertEqual(custom["role"], "My Custom Role")
        self.assertEqual(custom["description"], "Custom semantic path role.")
        self.assertEqual(self.module.normalize_role("   ", True)["state"], "invalid")
        self.assertEqual(self.module.normalize_role(object(), True)["state"], "invalid")
        self.assertEqual(self.module.normalize_role_input("  logo part  "), "logo part")
        self.assertIsNone(self.module.normalize_role_input("   "))
        self.assertIsNone(self.module.normalize_role_input(None))
        with self.assertRaisesRegex(ValueError, "string or null"):
            self.module.normalize_role_input(1)
        result = self.module.aggregate_roles(
            [
                {"rolePresent": True, "rawRole": "body"},
                {"rolePresent": False, "rawRole": None},
                {"rolePresent": True, "rawRole": "not-a-role"},
            ]
        )
        self.assertEqual(result["state"], "mixed")
        self.assertEqual(result["counts"], {"body": 1, "unassigned": 1, "not-a-role": 1})
        case_mixed = self.module.aggregate_roles(
            [
                {"rolePresent": True, "rawRole": "Body"},
                {"rolePresent": True, "rawRole": "body"},
            ]
        )
        self.assertEqual(case_mixed["state"], "mixed")
        self.assertEqual(case_mixed["counts"], {"Body": 1, "body": 1})

    def test_role_field_presentation_is_value_only(self):
        self.assertEqual(
            self.module.role_field_presentation(
                {"state": "valid", "sharedRole": "logo-part", "selectedPathCount": 2}
            ),
            {
                "enabled": True,
                "value": "logo-part",
                "placeholder": "",
                "copyValue": "logo-part",
                "warning": False,
            },
        )
        mixed = self.module.role_field_presentation(
            {"state": "mixed", "selectedPathCount": 2}
        )
        self.assertEqual(mixed["value"], "")
        self.assertEqual(mixed["placeholder"], "mixed")
        self.assertEqual(mixed["copyValue"], "mixed")
        unassigned = self.module.role_field_presentation(
            {"state": "unassigned", "selectedPathCount": 1}
        )
        self.assertTrue(unassigned["enabled"])
        self.assertEqual(unassigned["value"], "")
        invalid = self.module.role_field_presentation(
            {"state": "invalid", "selectedPathCount": 1}
        )
        self.assertEqual(invalid["placeholder"], "invalid")
        self.assertTrue(invalid["warning"])
        self.assertFalse(self.module.role_field_presentation({})["enabled"])

    def test_path_fingerprint_is_stable_and_sensitive(self):
        path = {"closed": True, "nodes": [{"type": "line", "x": 1.0, "y": 2.0}]}
        first = self.module.path_fingerprint(path)
        self.assertEqual(first, self.module.path_fingerprint(dict(path)))
        changed = {"closed": True, "nodes": [{"type": "line", "x": 2.0, "y": 2.0}]}
        self.assertNotEqual(first, self.module.path_fingerprint(changed))

    def test_migration_is_explicit_sequential_and_preserves_unknowns(self):
        source = self.valid_root()
        source["unknown"] = {"keep": True}

        def one_to_two(value):
            value["status"] = {"migrated": True}
            return value

        migrated = self.module.migrate_metadata(
            source,
            target_version=2,
            migrations={1: one_to_two},
            updated_at="2026-08-11T19:00:00Z",
        )
        self.assertEqual(migrated["schemaVersion"], 2)
        self.assertEqual(migrated["unknown"], {"keep": True})
        self.assertEqual(migrated["updatedAt"], "2026-08-11T19:00:00Z")
        with self.assertRaisesRegex(ValueError, "No LitSquare migration"):
            self.module.migrate_metadata(
                source, target_version=2, migrations={}, updated_at="2026-08-11T19:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
