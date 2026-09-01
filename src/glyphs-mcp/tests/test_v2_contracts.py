"""Hard-reset v2 catalog, schema, and ownership contract tests."""

from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.catalog import TOOL_CATALOG, TOOL_DEFINITIONS  # noqa: E402
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.contracts import ToolResponse  # noqa: E402
from glyphs_mcp_v2.mechanics_registry import (  # noqa: E402
    ENTITY_KINDS,
    OPERATION_DEFINITIONS,
    public_mechanics_registry,
)
from glyphs_mcp_v2.transport.fastmcp import (  # noqa: E402
    ChangeOperation,
    Constraint,
    EntitySelector,
    Projection,
    ToolHandlers,
)


TARGET_TOOLS = {
    "get_server_info",
    "list_documents",
    "read_document",
    "evaluate_constraints",
    "preview_change",
    "apply_change",
    "get_operation",
    "list_history",
    "revert_change",
    "search_knowledge",
    "get_knowledge",
    "execute_python",
    "preview_export",
    "apply_export",
    "save_document",
    "open_document_view",
    "get_runtime_status",
    "repair_runtime",
}

RETIRED_WORKFLOW_TOOLS = {
    "list_open_fonts",
    "get_document_status",
    "list_glyphs",
    "list_layers",
    "list_masters",
    "review_spacing",
    "apply_spacing",
    "apply_kerning_updates",
    "apply_master_updates",
    "apply_layer_updates",
    "review_export",
    "export_source_bundle",
    "rollback_python_execution",
}


def _assert_closed(test: unittest.TestCase, schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            test.assertFalse(schema.get("additionalProperties", True), schema)
        for value in schema.values():
            _assert_closed(test, value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_closed(test, value)


class V2ContractTests(unittest.TestCase):
    def test_catalog_is_exactly_the_hard_reset_surface(self) -> None:
        self.assertEqual(set(TOOL_CATALOG), TARGET_TOOLS)
        self.assertEqual(len(TOOL_DEFINITIONS), len(TARGET_TOOLS))
        self.assertFalse(RETIRED_WORKFLOW_TOOLS.intersection(TOOL_CATALOG))

    def test_every_catalog_entry_has_one_concrete_typed_handler(self) -> None:
        handlers = {
            name
            for name, value in inspect.getmembers(ToolHandlers, inspect.isfunction)
            if not name.startswith("_")
        }
        self.assertEqual(handlers, TARGET_TOOLS)
        self.assertEqual(
            [definition.name for definition in TOOL_DEFINITIONS],
            list(TOOL_CATALOG),
        )
        for definition in TOOL_DEFINITIONS:
            self.assertEqual(definition.handler_name, definition.name)

    def test_application_and_source_tree_do_not_restore_workflow_endpoints(self) -> None:
        for name in RETIRED_WORKFLOW_TOOLS:
            self.assertFalse(hasattr(GlyphsMCPApplication, name), name)
        package = V2_SOURCE / "glyphs_mcp_v2"
        self.assertFalse((package / "workflows.py").exists())
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("from .workflows import", text, path)
            self.assertNotIn("from glyphs_mcp_v2.workflows import", text, path)

    def test_safety_annotations_and_effect_boundaries_are_complete(self) -> None:
        for definition in TOOL_DEFINITIONS:
            self.assertEqual(
                set(definition.annotations),
                {
                    "readOnlyHint",
                    "destructiveHint",
                    "idempotentHint",
                    "openWorldHint",
                },
            )
        self.assertEqual(TOOL_CATALOG["preview_change"].effect, "read")
        self.assertEqual(TOOL_CATALOG["apply_change"].effect, "edit")
        self.assertEqual(TOOL_CATALOG["preview_export"].effect, "read")
        self.assertEqual(TOOL_CATALOG["apply_export"].effect, "files")
        self.assertEqual(TOOL_CATALOG["save_document"].effect, "save")
        self.assertEqual(TOOL_CATALOG["open_document_view"].effect, "ui")
        self.assertTrue(TOOL_CATALOG["execute_python"].annotations["openWorldHint"])

    def test_shared_request_types_are_closed_and_schema_backed(self) -> None:
        for request_type in (EntitySelector, Projection, Constraint, ChangeOperation):
            schema = request_type.model_json_schema()
            _assert_closed(self, schema)
            json.dumps(schema, sort_keys=True)

    def test_selector_owns_relations_ordering_and_pagination(self) -> None:
        selector = EntitySelector.model_validate(
            {
                "entity": "glyph",
                "ids": ["A"],
                "orderBy": "name",
                "pageSize": 25,
                "relations": [
                    {
                        "name": "layers",
                        "selector": {"entity": "layer", "pageSize": 10},
                        "projection": {"fields": ["id", "width"]},
                    }
                ],
            }
        )
        self.assertEqual(selector.pageSize, 25)
        self.assertEqual(selector.relations[0].selector.pageSize, 10)
        read_parameters = inspect.signature(ToolHandlers.read_document).parameters
        self.assertNotIn("pageSize", read_parameters)
        self.assertNotIn("cursor", read_parameters)

        node = EntitySelector.model_validate(
            {
                "entity": "node",
                "ids": ["node:line:0"],
                "parent": {
                    "glyphName": "A",
                    "layerId": "M1",
                    "shapeId": "shape:path:0",
                },
            }
        )
        self.assertEqual(node.entity, "node")

    def test_constraints_support_literals_fields_and_exact_references(self) -> None:
        exact = Constraint.model_validate(
            {
                "phase": "before",
                "left": {
                    "kind": "reference",
                    "selector": {"entity": "glyph", "ids": ["A"]},
                },
                "operator": "eq",
                "right": {
                    "kind": "reference",
                    "selector": {"entity": "glyph", "ids": ["A"]},
                },
            }
        )
        field = Constraint.model_validate(
            {
                "left": {
                    "kind": "field",
                    "selector": {"entity": "layer", "ids": ["L1"]},
                    "field": "width",
                },
                "operator": "within",
                "right": {"kind": "literal", "value": 500},
                "tolerance": 0.5,
            }
        )
        self.assertEqual(exact.left.kind, "reference")
        self.assertEqual(field.left.kind, "field")
        observation = Constraint.model_validate(
            {
                "phase": "after",
                "left": {
                    "kind": "field",
                    "selector": {"entity": "layer", "ids": ["L1"]},
                    "field": "observation.spacing.horizontal.leadingBearing",
                },
                "operator": "eq",
                "right": {"kind": "literal", "value": 40},
            }
        )
        self.assertEqual(observation.left.field, "observation.spacing.horizontal.leadingBearing")

    def test_operation_registry_is_closed_and_physical(self) -> None:
        operations = {
            "set": {"field": "width", "value": 500},
            "translate": {"delta": {"x": 1, "y": 2}},
            "transform": {"matrix": [1, 0, 0.2, 1, 0, 0]},
            "insert": {"field": "features", "value": {"id": "liga"}},
            "remove": {},
            "move": {"index": 0},
            "duplicate": {"newId": "copy"},
            "materialize": {
                "destinationEntity": "master",
                "newId": "materialized",
            },
        }
        for operation, values in operations.items():
            parsed = ChangeOperation.model_validate(
                {
                    "op": operation,
                    "target": {"entity": "document"},
                    **values,
                }
            )
            self.assertEqual(parsed.op, operation)
        with self.assertRaisesRegex(ValueError, "Extra inputs are not permitted"):
            ChangeOperation.model_validate(
                {
                    "op": "remove",
                    "target": {"entity": "glyph", "ids": ["A"]},
                    "field": "width",
                }
            )
        with self.assertRaisesRegex(ValueError, "Input should be 'exact'"):
            ChangeOperation.model_validate(
                {
                    "op": "translate",
                    "target": {"entity": "layer", "ids": ["L1"]},
                    "delta": {"x": 0.25, "y": 0},
                    "quantizer": "grid",
                }
            )

    def test_mechanics_registry_matches_transport_schemas(self) -> None:
        selector_schema = EntitySelector.model_json_schema()["$defs"][
            "EntitySelector"
        ]
        operation_schema = ChangeOperation.model_json_schema()
        self.assertEqual(
            set(selector_schema["properties"]["entity"]["enum"]),
            set(ENTITY_KINDS),
        )
        self.assertEqual(
            set(operation_schema["discriminator"]["mapping"]),
            set(OPERATION_DEFINITIONS),
        )
        registry = public_mechanics_registry()
        self.assertEqual(set(registry["entityCapabilities"]), set(ENTITY_KINDS))
        self.assertEqual(
            set(registry["translationTargets"]),
            {"layer", "shape", "node", "anchor"},
        )
        self.assertEqual(
            set(registry["transformTargets"]),
            {"layer", "shape", "node", "anchor"},
        )
        self.assertEqual(registry["geometryExecution"]["quantizers"], ["exact"])
        self.assertEqual(
            registry["geometryExecution"]["nativeLayerRounding"],
            "temporarily_disabled",
        )
        self.assertTrue(registry["geometryExecution"]["restoresGrid"])
        self.assertTrue(
            registry["geometryExecution"]["preservesGlobalAutomaticAlignment"]
        )

    def test_python_modes_are_permanent_and_staged_apply_is_not_execute_confirmation(self) -> None:
        parameters = inspect.signature(ToolHandlers.execute_python).parameters
        mode = parameters["mode"].annotation
        self.assertIn("read_only", str(mode))
        self.assertIn("staged_document", str(mode))
        self.assertIn("live_open_world", str(mode))
        self.assertIn("approvalId", parameters)
        apply_parameters = inspect.signature(ToolHandlers.apply_change).parameters
        self.assertIn("previewId", apply_parameters)
        self.assertNotIn("operations", apply_parameters)
        self.assertIn("confirmRecovery", apply_parameters)
        preview_parameters = inspect.signature(ToolHandlers.preview_change).parameters
        self.assertIn("verificationMode", preview_parameters)
        self.assertIn("transactionMode", preview_parameters)

    def test_success_and_failure_share_versioned_envelopes(self) -> None:
        definition = TOOL_CATALOG["get_server_info"]
        success = ToolResponse.success(
            tool="get_server_info",
            effect="read",
            summary="ready",
            data={"serverVersion": "2.0.0"},
        ).to_dict()
        failure = ToolResponse.failure(
            tool="get_server_info",
            effect="read",
            summary="unavailable",
            code="host_unavailable",
            message="Glyphs is unavailable",
        ).to_dict()
        validate(success, definition.output_schema)
        validate(failure, definition.output_schema)
        self.assertEqual(success["apiVersion"], failure["apiVersion"])

    def test_catalog_output_schemas_are_deterministic(self) -> None:
        first = json.dumps(
            {name: definition.output_schema for name, definition in TOOL_CATALOG.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
        second = json.dumps(
            {name: definition.output_schema for name, definition in TOOL_CATALOG.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
