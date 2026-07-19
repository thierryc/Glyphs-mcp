"""Release-gate coverage and undo-risk checks for public MCP tools."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


RESOURCES_DIR = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


READ_ONLY = "read_only"
EXECUTES_CODE = "executes_code"
WRITES_FILES = "writes_files"
OPENS_UI = "opens_ui"
EDITS_FONT = "edits_font"
SAVES_FONT = "saves_font"
SERVER_DOCS = "server_docs"

UNIT_BEHAVIOR = "unit_behavior"
UNIT_INTERNAL = "unit_internal"
LIVE_SMOKE_REQUIRED = "live_smoke_required"
REGISTRATION_ONLY_GAP = "registration_only_gap"

ALLOWED_COVERAGE = {
    UNIT_BEHAVIOR,
    UNIT_INTERNAL,
    LIVE_SMOKE_REQUIRED,
    REGISTRATION_ONLY_GAP,
}
ALLOWED_MUTATION = {
    READ_ONLY,
    EXECUTES_CODE,
    WRITES_FILES,
    OPENS_UI,
    EDITS_FONT,
    SAVES_FONT,
    SERVER_DOCS,
}
ALLOWED_UNDO_RISK = {"none", "low", "medium", "high"}


TOOL_RELEASE_GATE = {
    "execute_code": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_code_execution.py",),
        "mutation": EXECUTES_CODE,
        "undoRisk": "high",
        "undoNote": "Runs user-supplied code; release smoke must keep snippets tiny and avoid undo APIs.",
        "smoke": "execute_code with a one-line print, capture_output=true.",
    },
    "execute_code_with_context": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_code_execution.py",),
        "mutation": EXECUTES_CODE,
        "undoRisk": "high",
        "undoNote": "Runs user-supplied code with live font context; context setup must resolve fonts before execution.",
        "smoke": "execute_code_with_context on M with sys.version and len(font.glyphs).",
    },
    "docs_search": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_docs_tools.py",),
        "mutation": SERVER_DOCS,
        "undoRisk": "none",
        "undoNote": "Docs lookup only.",
        "smoke": "docs_search(query='GSFont').",
    },
    "docs_get": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_docs_tools.py",),
        "mutation": SERVER_DOCS,
        "undoRisk": "none",
        "undoNote": "Docs lookup only.",
        "smoke": "docs_get for a known section id.",
    },
    "docs_enable_page_resources": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_docs_tools.py",),
        "mutation": SERVER_DOCS,
        "undoRisk": "none",
        "undoNote": "Registers MCP resources only; no Glyphs state touched.",
        "smoke": "docs_enable_page_resources and verify ok=true.",
    },
    "get_glyph_annotations": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads annotation and metadata state only.",
        "smoke": "get_glyph_annotations on M with include_user_annotations=false.",
    },
    "add_glyph_annotation": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Writes layer annotations; must use layer.beginChanges/endChanges, not glyph beginUndo/endUndo.",
        "smoke": "Add one tiny text annotation, read it back, delete it immediately.",
    },
    "add_glyph_annotation_group": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Can add multiple annotations; release smoke should use at most two and clean up.",
        "smoke": "Add a two-item annotation group on a temp/test glyph, then clear managed annotations.",
    },
    "update_glyph_annotation": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Mutates existing annotation fields; use only after adding one temporary managed annotation.",
        "smoke": "Update one temporary annotation by id, then delete it.",
    },
    "delete_glyph_annotation": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Deletes layer annotations; explicit index cleanup must stay small.",
        "smoke": "Delete the one annotation created by the smoke test.",
    },
    "clear_glyph_annotations": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Can delete multiple annotations; live smoke must target MCP-managed temporary notes only.",
        "smoke": "Clear scope='mcp' after creating one temporary managed note.",
    },
    "get_glyph_annotation_groups": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_annotations.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads annotation metadata only.",
        "smoke": "get_glyph_annotation_groups on M.",
    },
    "measure_stem_ratio": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_compensated_tuning_engine.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only geometry measurement.",
        "smoke": "measure_stem_ratio on one glyph and two masters.",
    },
    "review_compensated_tuning": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_compensated_tuning_engine.py", "test_compensated_tuning_tools.py"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Preview only.",
        "smoke": "review_compensated_tuning on one glyph, no apply.",
    },
    "apply_compensated_tuning": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_compensated_tuning_tools.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Can replace paths across glyphs; release smoke must use dry_run first or a disposable glyph.",
        "smoke": "apply_compensated_tuning dry_run=true on one glyph.",
    },
    "get_glyph_components": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_components.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads components only.",
        "smoke": "get_glyph_components on a known composite glyph.",
    },
    "add_component_to_glyph": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_components.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Appends one component through layer.shapes and layer change batching.",
        "smoke": "Add one component to a disposable glyph, then delete the glyph.",
    },
    "add_anchor_to_glyph": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_components.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Adds or replaces anchors; live smoke should use a disposable glyph.",
        "smoke": "Add one anchor to a disposable glyph, then delete the glyph.",
    },
    "add_corner_to_all_masters": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_components.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Adds hints/corners across masters; do not live-smoke on production glyphs.",
        "smoke": "Run only on a disposable glyph with one simple path.",
    },
    "ExportDesignspaceAndUFO": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_export_designspace_ufo.py",),
        "mutation": WRITES_FILES,
        "undoRisk": "medium",
        "undoNote": "Exports to disk and preprocesses a copied GSFont; avoid optional decompositions in routine live smoke.",
        "smoke": "Export to /private/tmp with decompose_smart_components=false and decompose_smart_corners=false, then verify output file list.",
    },
    "list_style_sets": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_features.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads OpenType feature text only.",
        "smoke": "list_style_sets(include_inactive=true).",
    },
    "list_open_fonts": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Font discovery only.",
        "smoke": "list_open_fonts.",
    },
    "get_font_glyphs": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads glyph metadata only.",
        "smoke": "get_font_glyphs with result count capped in review notes.",
    },
    "get_font_masters": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads master metadata only.",
        "smoke": "get_font_masters(font_index=0).",
    },
    "set_master_italic_angle": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "low",
        "undoNote": "Mutates one master metric; requires confirm for live writes.",
        "smoke": "dry_run=true, then optional confirm on test file only.",
    },
    "get_font_instances": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads instance metadata only.",
        "smoke": "get_font_instances(font_index=0).",
    },
    "get_glyph_details": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("live Glyphs 4 smoke batch",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads glyph/layer details only.",
        "smoke": "get_glyph_details on M.",
    },
    "get_font_kerning": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_font.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads kerning dictionary only.",
        "smoke": "get_font_kerning on current master.",
    },
    "create_glyph": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Appends glyph to font on Glyphs' main thread; live smoke must be isolated in a clean session.",
        "smoke": "Create one uniquely named disposable glyph, then pause and verify no undo dialog before any next mutation.",
    },
    "delete_glyph": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Deletes glyphs on Glyphs' main thread; live smoke must delete only a disposable glyph and then stop.",
        "smoke": "Delete one disposable glyph in its own step, then verify no undo dialog before continuing.",
    },
    "update_glyph_properties": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Mutates glyph metadata; live smoke should target disposable glyph only.",
        "smoke": "Update export=false on a disposable glyph.",
    },
    "copy_glyph": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Copies layer data and may create target glyphs; use disposable target only.",
        "smoke": "Copy A into a disposable glyph, then delete it.",
    },
    "update_glyph_metrics": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Updates layer metrics; use dry-run equivalent if added, otherwise disposable glyph only.",
        "smoke": "Update width on a disposable glyph, then delete it.",
    },
    "save_font": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_glyph_ops.py",),
        "mutation": SAVES_FONT,
        "undoRisk": "none",
        "undoNote": "Saves file; release smoke must save only a copy in /private/tmp.",
        "smoke": "save_font(path='/private/tmp/...copy.glyphs') on test file only.",
    },
    "review_italic_first_pass": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_mcp_tools_italic.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Preview only.",
        "smoke": "review_italic_first_pass on one glyph.",
    },
    "apply_italic_first_pass": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_mcp_tools_italic.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Can copy and transform layer data; must use layer changes and disposable glyphs for live confirm.",
        "smoke": "dry_run=true first; confirm only on disposable glyph.",
    },
    "set_kerning_pair": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_kerning.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Mutates kerning dictionary; should use public setKerningForPair/removeKerningForPair before release.",
        "smoke": "Set and then remove one disposable glyph-glyph kerning pair.",
    },
    "generate_kerning_tab": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_kerning.py",),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Opens an edit tab only; no font mutation.",
        "smoke": "generate_kerning_tab with small limits and open_tab=false if available.",
    },
    "review_kerning_bumper": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_kerning_collision_engine.py", "live Glyphs 4 smoke batch"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only geometry review; can open tab when requested.",
        "smoke": "review_kerning_bumper open_tab=false, pair_limit small.",
    },
    "apply_kerning_bumper": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_kerning.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Applies kerning exceptions; dry_run must be the default release smoke.",
        "smoke": "apply_kerning_bumper dry_run=true, confirm=false.",
    },
    "get_glyph_paths": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_paths.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads path data only.",
        "smoke": "get_glyph_paths on M.",
    },
    "set_glyph_paths": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_paths.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Replaces paths and metrics in one main-thread layer change block with readback verification.",
        "smoke": "Use only on an existing disposable glyph; write one simple path, read it back, then pause.",
    },
    "get_selected_glyphs": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_selection.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads selection only.",
        "smoke": "get_selected_glyphs with one selected glyph.",
    },
    "get_selected_font_and_master": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("live Glyphs 4 smoke batch",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads active font/master/selection only.",
        "smoke": "get_selected_font_and_master.",
    },
    "get_selected_nodes": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_selection.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads edit selection only.",
        "smoke": "get_selected_nodes with no selected node and with one selected node.",
    },
    "get_server_info": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_server.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Server health only.",
        "smoke": "get_server_info and verify version/runtime/python/Glyphs host fields.",
    },
    "review_collinear_handles": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_smoothness.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only smoothness review.",
        "smoke": "review_collinear_handles on one path.",
    },
    "apply_collinear_handles_smooth": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_smoothness.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Sets node smooth flags; release smoke should use dry_run or disposable glyph.",
        "smoke": "apply_collinear_handles_smooth dry_run=true.",
    },
    "set_spacing_guides": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_spacing.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Adds/removes many layer guides; likely undo-popup candidate if run on many glyphs.",
        "smoke": "dry_run=true first; confirm add/clear on one disposable glyph only.",
    },
    "review_spacing": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_spacing_engine.py", "live Glyphs 4 smoke batch"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only spacing review.",
        "smoke": "review_spacing on H/O/n/o.",
    },
    "apply_spacing": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_spacing.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Updates sidebearings/width; release smoke should use dry_run or disposable glyph.",
        "smoke": "apply_spacing dry_run=true.",
    },
    "set_spacing_params": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_spacing.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "low",
        "undoNote": "Writes custom parameters, not layer geometry; still needs explicit confirm smoke.",
        "smoke": "set_spacing_params dry_run-like audit if added; otherwise skip live mutation.",
    },
    "review_master_stem_metrics": {
        "coverage": UNIT_INTERNAL,
        "tests": ("test_mcp_tools_stems.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only stem review.",
        "smoke": "review_master_stem_metrics include_measurements=false.",
    },
    "set_master_stem_metrics": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_stems.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "low",
        "undoNote": "Writes master stem metrics; release smoke should use dry_run first.",
        "smoke": "set_master_stem_metrics dry_run=true.",
    },
    "render_glyph_review_image": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_visual_review.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only render.",
        "smoke": "render_glyph_review_image on H/O/n/o.",
    },
    "show_glyphs_status": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py", "test_mcp_app_ui.py"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads runtime and open-font status only.",
        "smoke": "show_glyphs_status and verify the embedded status card.",
    },
    "show_font_feedback": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads bounded font metadata only and never exposes an editor.",
        "smoke": "show_font_feedback on one open disposable font.",
    },
    "show_glyph_feedback": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads glyph/layer metadata without transmitting outline paths.",
        "smoke": "show_glyph_feedback for the current selection.",
    },
    "show_opentype_features": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads feature metadata and optionally returns read-only code.",
        "smoke": "show_opentype_features with include_code=false.",
    },
    "preview_spacing_feedback": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Calls apply_spacing with dry_run=true and confirm=false only.",
        "smoke": "preview_spacing_feedback on one disposable glyph.",
    },
    "preview_kerning_feedback": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Calls the kerning bumper with dry_run=true and confirm=false only.",
        "smoke": "preview_kerning_feedback for one explicit pair.",
    },
    "preview_handle_smoothing_feedback": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Calls handle smoothing with dry_run=true and confirm=false only.",
        "smoke": "preview_handle_smoothing_feedback on one reviewed path.",
    },
    "apply_feedback_plan": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Applies one consumed, revalidated spacing, kerning, or smoothing plan; never saves.",
        "smoke": "Use a disposable font: preview, confirm, verify, undo, and close without saving.",
    },
    "open_feedback_target": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_feedback.py",),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Opens resolved layers from an already open font; cannot open paths or URLs.",
        "smoke": "Open one resolved glyph in a new Glyphs Edit tab.",
    },
}


class ReleaseGateToolCoverageTests(unittest.TestCase):
    maxDiff = None

    def _registered_tools(self):
        tools = {}
        for path in sorted(RESOURCES_DIR.glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any(ast.unparse(decorator).startswith("mcp.tool") for decorator in node.decorator_list):
                    tools[node.name] = path.name
        return tools

    def test_every_registered_tool_has_release_gate_entry(self) -> None:
        registered = set(self._registered_tools())
        covered = set(TOOL_RELEASE_GATE)
        self.assertEqual(covered, registered)

    def test_each_tool_entry_has_test_owner_smoke_prompt_and_undo_risk(self) -> None:
        for tool_name, entry in sorted(TOOL_RELEASE_GATE.items()):
            with self.subTest(tool=tool_name):
                self.assertIn(entry.get("coverage"), ALLOWED_COVERAGE)
                self.assertIn(entry.get("mutation"), ALLOWED_MUTATION)
                self.assertIn(entry.get("undoRisk"), ALLOWED_UNDO_RISK)
                self.assertTrue(entry.get("tests"), "Every tool needs a test owner or explicit release-gap owner.")
                self.assertTrue(entry.get("smoke"), "Every tool needs a reusable release smoke prompt.")
                self.assertTrue(entry.get("undoNote"), "Every tool needs an undo-risk note.")

    def test_mutating_tools_are_classified_for_undo_release_risk(self) -> None:
        mutating = {EDITS_FONT, EXECUTES_CODE}
        for tool_name, entry in sorted(TOOL_RELEASE_GATE.items()):
            if entry["mutation"] not in mutating:
                continue
            with self.subTest(tool=tool_name):
                self.assertNotEqual(entry["undoRisk"], "none")
                self.assertNotEqual(entry["coverage"], "")

    def test_registration_only_behavior_gaps_are_visible(self) -> None:
        gaps = sorted(
            tool_name
            for tool_name, entry in TOOL_RELEASE_GATE.items()
            if entry["coverage"] == REGISTRATION_ONLY_GAP
        )
        self.assertEqual(
            gaps,
            [],
        )

    def test_no_executable_glyph_beginundo_or_endundo_calls(self) -> None:
        violations = []
        for path in sorted(RESOURCES_DIR.glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in {"beginUndo", "endUndo"}:
                    violations.append(f"{path.name}:{node.lineno}:{func.attr}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
