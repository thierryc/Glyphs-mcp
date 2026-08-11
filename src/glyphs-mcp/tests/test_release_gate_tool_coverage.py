"""Release-gate coverage and undo-risk checks for public MCP tools."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest


RESOURCES_DIR = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
if str(RESOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(RESOURCES_DIR))

from tool_catalog import TOOL_CATALOG, active_entries, app_only_entries


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
    "get_custom_parameters": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_custom_parameters.py",),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads font/master custom-parameter records and resolves effective values only.",
        "smoke": "Read a small prefixed parameter set at font and effective-master scopes.",
    },
    "set_custom_parameters": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_custom_parameters.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "low",
        "undoNote": "Writes explicit font/master custom parameters only after dry-run and confirmation; never saves.",
        "smoke": "On a disposable font, preview one set and one delete, confirm, verify read-back, then close without saving.",
    },
    "review_unicode_assignments": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_unicode_assignment_engine.py", "test_mcp_tools_unicode_assignments.py"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads glyph Unicode/export state and computes plain-data findings only.",
        "smoke": "Review selected glyphs with allocate_unencoded=false, then a small disposable PUA allocation preview.",
    },
    "apply_unicode_assignments": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_unicode_assignment_engine.py", "test_mcp_tools_unicode_assignments.py"),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Can change multiple glyph Unicode values; require dry-run, a disposable copy, and a small confirmed batch.",
        "smoke": "Dry-run one reviewed assignment; confirm only on a disposable glyph and verify no auto-save.",
    },
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
    "update_glyph_node_positions": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_outline_node_patch.py",
            "test_mcp_tools_node_positions.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Changes only explicit node coordinates in one guarded layer transaction and rolls back on any verification failure.",
        "smoke": "On a disposable glyph, dry-run and confirm two explicit node positions using grid_policy='font', verify read-back, then close without saving.",
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
    "apply_collinear_handles_smooth": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_smoothness.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Sets node smooth flags; release smoke should use dry_run or disposable glyph.",
        "smoke": "apply_collinear_handles_smooth dry_run=true.",
    },
    "review_tunni_geometry": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_outline_geometry_engine.py",
            "test_mcp_tools_curve_geometry.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads one explicit path and computes plain-data Tunni geometry only.",
        "smoke": "review_tunni_geometry on one curved disposable glyph path.",
    },
    "apply_tunni_balance": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_outline_geometry_engine.py",
            "test_mcp_tools_curve_geometry.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Moves two handles per explicit eligible segment in one verified layer change batch; dry-run is the default smoke.",
        "smoke": "apply_tunni_balance dry_run=true for one explicit reviewed segment.",
    },
    "review_curve_quality": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_outline_geometry_engine.py",
            "test_mcp_tools_curve_geometry.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Computes bounded cubic curvature metrics from a plain node snapshot only.",
        "smoke": "review_curve_quality on one curved glyph path with include_samples=false.",
    },
    "get_curve_review_overlay_state": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_curve_overlay_model.py",
            "test_glyphs_curve_reporter.py",
            "test_mcp_tools_curve_overlay.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads Reporter availability, activation, and a bounded last-draw snapshot only.",
        "smoke": "Enable the native overlay, inspect its last-draw counts, and verify the font remains clean.",
    },
    "set_curve_review_overlay": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": (
            "test_curve_overlay_model.py",
            "test_glyphs_curve_reporter.py",
            "test_mcp_tools_curve_overlay.py",
            "live Glyphs 3.5 and Glyphs 4 smoke batch",
        ),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Changes only global Reporter display state, requests a redraw, and never edits or saves a font.",
        "smoke": "Toggle on/off, confirm View menu state and live comb drawing, and verify no dirty font state.",
    },
    "preview_tunni_balance_candidate": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Builds bounded detached state and enables a drawing-only Reporter; no font mutation.",
        "smoke": "Preview one grid-safe Tunni target in two masters and switch active masters.",
    },
    "preview_collinear_handles_candidate": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Builds a detached smooth-flag candidate and enables the Reporter only.",
        "smoke": "Preview one explicit collinear smooth target without dirtying the font.",
    },
    "preview_italic_first_pass_candidate": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Runs the established italic generator on detached copies and enables the Reporter only.",
        "smoke": "Preview one existing compatible target glyph from a serialized disposable copy.",
    },
    "preview_compensated_tuning_candidate": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Runs compensated tuning into detached plain geometry and enables the Reporter only.",
        "smoke": "Preview one compatible decomposed glyph without font mutation.",
    },
    "set_outline_candidate_overlay": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_glyphs_candidate_reporter.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": OPENS_UI,
        "undoRisk": "none",
        "undoNote": "Changes Reporter/process-local UI state only; clearing never deletes layers.",
        "smoke": "Toggle the candidate Reporter and clear one ephemeral session.",
    },
    "get_outline_candidate_state": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads bounded process-local state and namespaced manifests only.",
        "smoke": "Inspect one ephemeral and one materialized session.",
    },
    "review_outline_candidate_session": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_outline_candidate_state.py", "test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Reads fingerprints/diffs and issues a process-local token; no font mutation.",
        "smoke": "Review generated and manually edited materialized candidates and exercise stale rejection.",
    },
    "materialize_outline_candidate_session": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Creates owned non-background GSLayer copies and a namespaced manifest after dry-run.",
        "smoke": "Materialize a two-master session on a serialized disposable font and verify new layer IDs.",
    },
    "accept_outline_candidate_session": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": EDITS_FONT,
        "undoRisk": "high",
        "undoNote": "Atomically promotes only operation-approved fields, preserves required backups, cleans candidates, and rolls back failures.",
        "smoke": "Dry-run then accept one reviewed disposable candidate; verify exact fields, cleanup, backup policy, and no save.",
    },
    "discard_outline_candidate_session": {
        "coverage": LIVE_SMOKE_REQUIRED,
        "tests": ("test_mcp_tools_outline_candidates.py", "live Glyphs 3.5 and Glyphs 4 smoke batch"),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Deletes only layers with matching candidate ownership metadata and rolls back partial cleanup.",
        "smoke": "Dry-run then discard a materialized disposable session and verify sources/backgrounds remain.",
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
        "tests": ("test_spacing_engine.py", "test_mcp_tools_spacing.py", "live Glyphs 4 smoke batch"),
        "mutation": READ_ONLY,
        "undoRisk": "none",
        "undoNote": "Read-only spacing review.",
        "smoke": "review_spacing on H/O/J/V/W/Y/n/o/one/seven; verify class-aware references and guards.",
    },
    "apply_spacing": {
        "coverage": UNIT_BEHAVIOR,
        "tests": ("test_mcp_tools_spacing.py",),
        "mutation": EDITS_FONT,
        "undoRisk": "medium",
        "undoNote": "Updates sidebearings/width; release smoke should use dry_run or disposable glyph.",
        "smoke": "apply_spacing dry_run=true; verify blocked/manual results are ineligible without named overrides.",
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


TOOL_RELEASE_GATE["review_curve_quality_across_masters"] = {
    "coverage": LIVE_SMOKE_REQUIRED,
    "tests": (
        "test_outline_geometry_engine.py",
        "test_mcp_tools_curve_geometry.py",
        "live Glyphs 3.5 and Glyphs 4 smoke batch",
    ),
    "mutation": READ_ONLY,
    "undoRisk": "none",
    "undoNote": "Compares detached compatible raw-path snapshots across explicit masters only.",
    "smoke": "Compare one compatible curved path across at least two masters without per-master samples.",
}

TOOL_RELEASE_GATE["get_document_change_overview"] = {
    "coverage": LIVE_SMOKE_REQUIRED,
    "tests": (
        "test_document_change_audit.py",
        "test_mcp_tools_document_changes.py",
        "test_document_changes_panel_model.py",
        "live Glyphs 3.5 and Glyphs 4 smoke batch",
    ),
    "mutation": READ_ONLY,
    "undoRisk": "none",
    "undoNote": "Reads only the process-local bounded MCP activity ledger; it never changes or saves a font.",
    "smoke": "Exercise DA1–DA10 in the release QA protocol with saved and unsaved disposable fonts.",
}


class ReleaseGateToolCoverageTests(unittest.TestCase):
    maxDiff = None

    def _registered_tool_records(self):
        modules = {}
        for path in sorted(RESOURCES_DIR.glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any(
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "glyphs_tool"
                    for decorator in node.decorator_list
                ):
                    modules[node.name] = path.name
        return [
            {
                "name": entry.name,
                "module": modules.get(entry.name),
                "appOnly": entry.visibility == "app-only",
                "description": entry.description,
            }
            for entry in active_entries()
            if entry.name in modules
        ]

    def _registered_tools(self):
        return {record["name"]: record["module"] for record in self._registered_tool_records()}

    def test_tool_surface_is_bounded_named_and_discoverable(self) -> None:
        records = self._registered_tool_records()
        names = [record["name"] for record in records]
        app_only = {record["name"] for record in records if record["appOnly"]}

        self.assertEqual(len(records), 78, "Tool-surface growth requires an explicit budget review.")
        self.assertEqual(len(set(names)), len(names), "MCP tool names must be unique.")
        self.assertEqual(app_only, {entry.name for entry in app_only_entries()})
        self.assertEqual(len(records) - len(app_only), 67)

        for record in records:
            with self.subTest(tool=record["name"]):
                if record["name"] != "ExportDesignspaceAndUFO":
                    self.assertRegex(record["name"], r"^[a-z][a-z0-9_]*$")
                description = record["description"].strip()
                self.assertTrue(description, "Every discoverable tool needs a useful description.")
                self.assertLessEqual(len(description), 220, "Catalog descriptions must stay bounded.")

    def test_every_registered_tool_has_release_gate_entry(self) -> None:
        registered = set(self._registered_tools())
        covered = set(TOOL_RELEASE_GATE)
        self.assertEqual(covered, registered)

    def test_catalog_safety_annotations_match_release_mutation_classes(self) -> None:
        for entry in active_entries():
            with self.subTest(tool=entry.name):
                mutation = TOOL_RELEASE_GATE[entry.name]["mutation"]
                should_be_read_only = mutation in {READ_ONLY, SERVER_DOCS}
                self.assertIs(entry.annotations["readOnlyHint"], should_be_read_only)
                should_be_destructive = mutation in {EDITS_FONT, SAVES_FONT, WRITES_FILES, EXECUTES_CODE}
                self.assertIs(entry.annotations["destructiveHint"], should_be_destructive)

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

    def test_curve_geometry_tools_require_both_host_live_smoke(self) -> None:
        for tool_name in (
            "review_tunni_geometry",
            "apply_tunni_balance",
            "review_curve_quality",
            "review_curve_quality_across_masters",
            "get_curve_review_overlay_state",
            "set_curve_review_overlay",
        ):
            with self.subTest(tool=tool_name):
                entry = TOOL_RELEASE_GATE[tool_name]
                self.assertEqual(entry["coverage"], LIVE_SMOKE_REQUIRED)
                self.assertIn("live Glyphs 3.5 and Glyphs 4 smoke batch", entry["tests"])

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
