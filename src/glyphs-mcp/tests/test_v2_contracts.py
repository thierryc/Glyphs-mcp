"""Contract and import-boundary tests for the Glyphs MCP 2.0 spine."""

from __future__ import annotations

import ast
import inspect
import sys
import unittest
from pathlib import Path

from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.catalog import TOOL_CATALOG, TOOL_DEFINITIONS  # noqa: E402
from glyphs_mcp_v2.contracts import ToolError, ToolResponse  # noqa: E402
from glyphs_mcp_v2.identity import DocumentIdRegistry  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ToolHandlers  # noqa: E402


class V2ContractTests(unittest.TestCase):
    def test_catalog_is_the_complete_typed_milestone_surface(self) -> None:
        expected = {
            "get_server_info",
            "list_open_fonts",
            "get_document_status",
            "get_operation",
            "list_glyphs",
            "list_instances",
            "list_kerning_pairs",
            "review_kerning_coverage",
            "review_master_compatibility",
            "review_metrics_inheritance",
            "apply_metrics_updates",
            "review_anchor_consistency",
            "apply_compatibility_updates",
            "apply_anchor_updates",
            "apply_glyph_updates",
            "apply_kerning_updates",
            "apply_opentype_updates",
            "review_spacing",
            "apply_spacing",
            "review_export",
            "export_source_bundle",
            "list_audit_events",
            "list_change_commits",
            "revert_change",
            "execute_python",
            "rollback_python_execution",
        }
        self.assertEqual(set(TOOL_CATALOG), expected)
        self.assertEqual(
            tuple(definition.name for definition in TOOL_DEFINITIONS),
            tuple(TOOL_CATALOG),
        )
        for definition in TOOL_DEFINITIONS:
            self.assertEqual(
                set(definition.annotations),
                {
                    "title",
                    "readOnlyHint",
                    "destructiveHint",
                    "idempotentHint",
                    "openWorldHint",
                },
            )
            if definition.effect == "read":
                self.assertTrue(definition.annotations["readOnlyHint"])
            if definition.name in {"execute_python", "rollback_python_execution", "revert_change"}:
                self.assertTrue(definition.annotations["destructiveHint"])
            if definition.name == "execute_python":
                self.assertTrue(definition.annotations["openWorldHint"])

    def test_success_and_failure_share_one_valid_versioned_envelope(self) -> None:
        definition = TOOL_CATALOG["list_open_fonts"]
        success = ToolResponse.success(
            tool="list_open_fonts",
            effect="read",
            summary="No documents.",
            data={"count": 0, "documents": []},
        )
        failure = ToolResponse.failure(
            tool="list_open_fonts",
            effect="read",
            summary="Host unavailable.",
            error=ToolError(
                code="host_unavailable",
                message="Glyphs is unavailable.",
                recoverable=True,
            ),
        )

        validate(success.to_dict(), definition.output_schema)
        validate(failure.to_dict(), definition.output_schema)
        self.assertEqual(success.to_dict()["resultSchemaVersion"], "2.0")
        self.assertEqual(success.to_dict()["apiVersion"], "2.0")
        for field in (
            "requestId",
            "runId",
            "operationId",
            "startedAt",
            "completedAt",
            "durationMs",
            "status",
            "page",
            "auditReceipt",
        ):
            self.assertIn(field, success.to_dict())

    def test_failure_factory_builds_the_common_error_contract_from_scalars(self) -> None:
        failure = ToolResponse.failure(
            tool="get_document_status",
            effect="read",
            summary="Document unavailable.",
            code="document_unavailable",
            message="The document is closed.",
            recoverable=True,
            details={"closed": True},
        )

        self.assertEqual(failure.error.code, "document_unavailable")
        self.assertEqual(failure.error.message, "The document is closed.")
        self.assertTrue(failure.error.recoverable)
        self.assertEqual(failure.error.details, {"closed": True})
        with self.assertRaises(ValueError):
            ToolResponse.failure(
                tool="get_document_status",
                effect="read",
                summary="Invalid mixed construction.",
                error=ToolError("explicit", "Explicit error.", True),
                code="duplicate",
                message="Duplicate error.",
            )

    def test_document_ids_are_stable_distinct_and_opaque(self) -> None:
        values = iter(("doc_first", "doc_second"))
        registry = DocumentIdRegistry(id_factory=lambda: next(values))

        self.assertEqual(registry.resolve(("native", 1)), "doc_first")
        self.assertEqual(registry.resolve(("native", 1)), "doc_first")
        self.assertEqual(registry.resolve(("native", 2)), "doc_second")
        self.assertEqual(len(registry), 2)
        self.assertTrue(registry.discard(("native", 1)))
        self.assertEqual(len(registry), 1)

    def test_core_and_application_layers_have_no_host_or_transport_imports(self) -> None:
        package = V2_SOURCE / "glyphs_mcp_v2"
        files = [
            package / name
            for name in (
                "application.py",
                "catalog.py",
                "contracts.py",
                "identity.py",
                "ports.py",
                "versions.py",
            )
        ]
        forbidden = {"GlyphsApp", "AppKit", "Foundation", "fastmcp", "uvicorn"}

        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0])
            self.assertFalse(imported & forbidden, msg="forbidden import in {}".format(path))

    def test_fastmcp_registration_is_confined_to_the_catalog_registrar(self) -> None:
        package = V2_SOURCE / "glyphs_mcp_v2"
        callers = []
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if ".tool(" in text:
                callers.append(path.relative_to(package).as_posix())
        self.assertEqual(callers, ["transport/fastmcp.py"])

    def test_typed_mutations_are_direct_apply_first_contracts(self) -> None:
        mutation_tools = {
            "apply_glyph_updates": "updates",
            "apply_anchor_updates": "updates",
            "apply_kerning_updates": "updates",
            "apply_metrics_updates": "updates",
            "apply_compatibility_updates": "updates",
            "apply_opentype_updates": "updates",
            "apply_spacing": "items",
        }
        for name, items_parameter in mutation_tools.items():
            with self.subTest(tool=name):
                parameters = inspect.signature(getattr(ToolHandlers, name)).parameters
                self.assertIn("documentId", parameters)
                self.assertIn("expectedDocumentFingerprint", parameters)
                self.assertIn(items_parameter, parameters)
                self.assertIn("reason", parameters)
                self.assertNotIn("reviewId", parameters)
                self.assertNotIn("confirm", parameters)

        for removed in (
            "review_glyph_updates",
            "review_anchor_updates",
            "review_kerning_updates",
            "review_metrics_updates",
            "review_compatibility_updates",
        ):
            self.assertNotIn(removed, TOOL_CATALOG)


if __name__ == "__main__":
    unittest.main()
