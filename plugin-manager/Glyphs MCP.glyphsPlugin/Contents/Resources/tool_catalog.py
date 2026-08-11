# encoding: utf-8

"""Authoritative, host-independent metadata for the Glyphs MCP tool surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


MODEL_AND_APP = "model+app"
APP_ONLY = "app-only"
ACTIVE = "active"
REMOVED = "removed"


@dataclass(frozen=True)
class ToolCatalogEntry:
    name: str
    title: str
    description: str
    category: str
    tags: Tuple[str, ...]
    visibility: str
    effect: str
    state: str
    replacement: Optional[str]
    output_schema: Optional[str]
    annotations: Dict[str, object]
    resource_uri: Optional[str] = None


def _title(name: str) -> str:
    if name == "ExportDesignspaceAndUFO":
        return "Export Designspace and UFO"
    value = name.replace("_", " ").title()
    for source, target in (
        ("Mcp", "MCP"),
        ("Ufo", "UFO"),
        ("Opentype", "OpenType"),
        ("Tunni", "Tunni"),
    ):
        value = value.replace(source, target)
    return value


def _annotations(title: str, effect: str) -> Dict[str, object]:
    read_only = effect in {"read", "docs"}
    destructive = effect in {"edit", "save", "files", "code"}
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": read_only,
        "openWorldHint": effect in {"save", "files", "code"},
    }


def _entry(
    name: str,
    description: str,
    category: str,
    effect: str = "read",
    *,
    visibility: str = MODEL_AND_APP,
    output_schema: Optional[str] = None,
    resource_uri: Optional[str] = None,
) -> ToolCatalogEntry:
    title = _title(name)
    return ToolCatalogEntry(
        name=name,
        title=title,
        description=description,
        category=category,
        tags=(category, effect),
        visibility=visibility,
        effect=effect,
        state=ACTIVE,
        replacement=None,
        output_schema=output_schema,
        annotations=_annotations(title, effect),
        resource_uri=resource_uri,
    )


def _removed(name: str, description: str, replacement: str) -> ToolCatalogEntry:
    title = _title(name)
    return ToolCatalogEntry(
        name=name,
        title=title,
        description=description,
        category="compatibility",
        tags=("compatibility", "removed"),
        visibility=APP_ONLY,
        effect="read",
        state=REMOVED,
        replacement=replacement,
        output_schema=None,
        annotations=_annotations(title, "read"),
    )


_FEEDBACK_URI = "ui://glyphs-mcp/feedback-v1.html"


_ENTRIES = [
    _entry("get_server_info", "Read local server identity, runtime health, and open-font count without changing Glyphs.", "server"),
    _entry("get_document_change_overview", "Read the bounded MCP mutation overview for one tracked open Glyphs document.", "document-audit", output_schema="document-audit"),
    _entry("execute_code", "Run bounded Python in Glyphs when no dedicated tool fits; this can change fonts or external state.", "automation", "code"),
    _entry("execute_code_with_context", "Run bounded Python with an explicit font and glyph context when dedicated tools are insufficient.", "automation", "code"),
    _entry("docs_search", "Search the bundled official Glyphs API, plug-in, and file-format documentation without changing state.", "documentation", "docs"),
    _entry("docs_get", "Fetch one bundled Glyphs documentation page by its exact result ID or path.", "documentation", "docs"),
    _entry("list_open_fonts", "List every font currently open in Glyphs and return stable font indices for later calls.", "font"),
    _entry("get_font_glyphs", "List bounded glyph metadata for one explicit open font without changing it.", "font"),
    _entry("get_font_masters", "Read masters, IDs, design metrics, and italic angles for one explicit open font.", "font"),
    _entry("set_master_italic_angle", "Dry-run or set one master's Glyphs italicAngle after explicit confirmation; never saves.", "font", "edit"),
    _entry("get_font_instances", "Read instance metadata for one explicit open font without changing it.", "font"),
    _entry("get_glyph_details", "Inspect one glyph's layers, metrics, shapes, anchors, components, and compatibility metadata.", "outlines"),
    _entry("get_font_kerning", "Read bounded kerning data for one explicit font and master without changing it.", "kerning", output_schema="kerning"),
    _entry("get_selected_glyphs", "Read the current Glyphs font-view selection and return exact glyph targets and links.", "selection"),
    _entry("get_selected_font_and_master", "Read the active font, master, and selection context from Glyphs without changing it.", "selection"),
    _entry("get_selected_nodes", "Read selected Edit View nodes with glyph, layer, path, node, and master mapping.", "selection"),
    _entry("get_glyph_paths", "Read editable path data for one glyph and master in a bounded round-trip-safe format.", "outlines"),
    _entry("update_glyph_node_positions", "Dry-run or atomically update explicit node coordinates on one glyph layer using the font grid by default.", "outlines", "edit", output_schema="outline"),
    _entry("set_glyph_paths", "Replace paths on one explicit glyph layer after validation; preserves surrounding shapes and never saves.", "outlines", "edit"),
    _entry("get_glyph_components", "Inspect component identities, transforms, smart values, and target layers for one glyph.", "components"),
    _entry("add_component_to_glyph", "Add one component to an explicit glyph layer after validating its target.", "components", "edit"),
    _entry("add_anchor_to_glyph", "Add one anchor at explicit coordinates on one targeted glyph layer.", "components", "edit"),
    _entry("add_corner_to_all_masters", "Add one corner hint at selected compatible nodes across explicit masters.", "components", "edit"),
    _entry("create_glyph", "Create one named glyph in an explicit open font; does not save the document.", "glyph-editing", "edit"),
    _entry("delete_glyph", "Delete one named glyph from an explicit open font; use only after confirming references.", "glyph-editing", "edit"),
    _entry("update_glyph_properties", "Update explicit glyph metadata fields without changing unrelated properties or saving.", "glyph-editing", "edit"),
    _entry("copy_glyph", "Copy outline data from one explicit glyph to another after validating the destination.", "glyph-editing", "edit"),
    _entry("update_glyph_metrics", "Update width or sidebearings on one explicit glyph and master without saving.", "glyph-editing", "edit"),
    _entry("save_font", "Save one explicit open font to its current path or an explicit new path.", "persistence", "save"),
    _entry("get_custom_parameters", "Read generic font or master custom parameters without changing the document.", "parameters"),
    _entry("set_custom_parameters", "Dry-run or atomically set explicit custom parameters after confirmation; never saves.", "parameters", "edit"),
    _entry("list_style_sets", "List OpenType stylistic sets, substitutions, and direct Glyphs review links without mutation.", "features"),
    _entry("set_kerning_pair", "Set or remove one explicit kerning pair in one master; does not save the font.", "kerning", "edit", output_schema="kerning"),
    _entry("generate_kerning_tab", "Open a bounded kerning proof tab in Glyphs for interactive review.", "kerning", "ui", visibility=APP_ONLY),
    _entry("review_kerning_bumper", "Measure bounded kerning collisions and propose conservative exceptions without mutation.", "kerning", output_schema="kerning"),
    _entry("apply_kerning_bumper", "Dry-run or apply explicit reviewed kerning exceptions after confirmation; never saves.", "kerning", "edit", output_schema="kerning"),
    _entry("set_spacing_guides", "Add or clear only Glyphs MCP spacing guides on explicit glyph layers.", "spacing", "edit", output_schema="spacing"),
    _entry("review_spacing", "Measure and propose class-aware spacing for explicit glyphs without changing the font.", "spacing", output_schema="spacing"),
    _entry("apply_spacing", "Dry-run or apply reviewed spacing to explicit glyphs after confirmation; never saves.", "spacing", "edit", output_schema="spacing"),
    _entry("set_spacing_params", "Dry-run or set spacing custom parameters for one font or master without saving.", "spacing", "edit", output_schema="spacing"),
    _entry("review_master_stem_metrics", "Review master stem metrics required by italic construction without changing the font.", "italic"),
    _entry("set_master_stem_metrics", "Dry-run or set explicit master stem metrics after confirmation; never saves.", "italic", "edit"),
    _entry("review_unicode_assignments", "Review Unicode mappings and deterministic allocation proposals without changing glyphs.", "unicode"),
    _entry("apply_unicode_assignments", "Dry-run or atomically apply explicit Unicode mappings after collision checks.", "unicode", "edit"),
    _entry("review_tunni_geometry", "Measure grid-safe Tunni balance for explicit cubic path segments without changing the font.", "curve-geometry", output_schema="curve"),
    _entry("apply_tunni_balance", "Dry-run or balance explicit cubic handles after confirmation and exact read-back verification.", "curve-geometry", "edit", output_schema="curve"),
    _entry("review_curve_quality", "Measure adaptive cubic events, curvature, continuity, and warnings on one explicit raw path.", "curve-geometry", output_schema="curve"),
    _entry("review_curve_quality_across_masters", "Compare compatible cubic geometry and quality measurements across explicit masters.", "curve-geometry", output_schema="curve"),
    _entry("set_curve_review_overlay", "Show or hide native curvature and curve-event overlays in Glyphs Edit View.", "curve-geometry", "ui", output_schema="curve"),
    _entry("get_curve_review_overlay_state", "Read bounded native curve Reporter state for the embedded Glyphs app.", "curve-geometry", visibility=APP_ONLY, output_schema="curve"),
    _entry("apply_collinear_handles_smooth", "Dry-run or mark explicit collinear curve nodes smooth after confirmation.", "curve-geometry", "edit"),
    _entry("preview_tunni_balance_candidate", "Create a detached multi-target Tunni candidate and show only its visual difference.", "candidates", "ui", output_schema="candidate"),
    _entry("preview_collinear_handles_candidate", "Create a detached smooth-node candidate for explicit path and node targets.", "candidates", "ui", output_schema="candidate"),
    _entry("preview_compensated_tuning_candidate", "Create detached compensated-tuning candidates for explicit glyphs and masters.", "candidates", "ui", output_schema="candidate"),
    _entry("preview_italic_first_pass_candidate", "Create a detached Roman-to-italic construction draft for guarded visual review.", "candidates", "ui", output_schema="candidate"),
    _entry("set_outline_candidate_overlay", "Show, hide, switch, or clear ephemeral candidate Reporter state without editing fonts.", "candidates", "ui", output_schema="candidate"),
    _entry("get_outline_candidate_state", "Read bounded ephemeral and materialized candidate-session state without mutation.", "candidates", output_schema="candidate"),
    _entry("materialize_outline_candidate_session", "Dry-run or create editable candidate layers for one reviewed session.", "candidates", "edit", output_schema="candidate"),
    _entry("review_outline_candidate_session", "Revalidate a candidate against its live source and issue a fingerprint-bound token.", "candidates", output_schema="candidate"),
    _entry("accept_outline_candidate_session", "Dry-run or promote only the exact reviewed candidate fields after confirmation.", "candidates", "edit", output_schema="candidate"),
    _entry("discard_outline_candidate_session", "Dry-run or delete only materialized layers owned by one candidate session.", "candidates", "edit", output_schema="candidate"),
    _entry("get_glyph_annotations", "Read native annotations and Glyphs MCP ownership metadata for one explicit glyph layer.", "annotations"),
    _entry("add_glyph_annotation", "Add one native annotation to an explicit layer and record Glyphs MCP ownership.", "annotations", "edit"),
    _entry("add_glyph_annotation_group", "Add a linked group of native annotations to one explicit glyph layer.", "annotations", "edit"),
    _entry("update_glyph_annotation", "Update one explicitly identified native annotation without touching unrelated items.", "annotations", "edit"),
    _entry("delete_glyph_annotation", "Delete one explicitly identified native annotation from one glyph layer.", "annotations", "edit"),
    _entry("clear_glyph_annotations", "Clear managed annotations by default, or all annotations only with explicit scope.", "annotations", "edit"),
    _entry("get_glyph_annotation_groups", "Read Glyphs MCP-managed annotation groups for one explicit glyph layer.", "annotations"),
    _entry("ExportDesignspaceAndUFO", "Export designspace and UFO packages for one selected font to an explicit directory.", "export", "files"),
    _entry("show_glyphs_status", "Show local server, Glyphs, and open-font status in the embedded feedback panel.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("show_font_feedback", "Show read-only information for one open font in the embedded feedback panel.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("show_glyph_feedback", "Show read-only glyph metadata in the embedded feedback panel.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("show_opentype_features", "Show a read-only OpenType feature report in the embedded feedback panel.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("preview_spacing_feedback", "Preview an exact spacing plan in the embedded feedback panel without mutation.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("preview_kerning_feedback", "Preview an exact kerning plan in the embedded feedback panel without mutation.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("preview_handle_smoothing_feedback", "Preview an exact handle-smoothing plan in the embedded feedback panel.", "app-feedback", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("apply_feedback_plan", "Apply one unexpired embedded feedback plan after explicit app confirmation.", "app-feedback", "edit", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _entry("open_feedback_target", "Open resolved glyph targets from an embedded feedback result in a new Glyphs tab.", "app-feedback", "ui", visibility=APP_ONLY, output_schema="feedback", resource_uri=_FEEDBACK_URI),
    _removed("render_glyph_review_image", "Removed legacy PNG renderer.", "set_curve_review_overlay"),
    _removed("docs_enable_page_resources", "Removed noisy per-page resource registration.", "docs_search"),
    _removed("measure_stem_ratio", "Removed public stem-ratio helper; candidate generation measures internally.", "preview_compensated_tuning_candidate"),
    _removed("review_collinear_handles", "Removed overlapping direct review wrapper.", "preview_collinear_handles_candidate"),
    _removed("review_italic_first_pass", "Removed overlapping direct italic review wrapper.", "preview_italic_first_pass_candidate"),
    _removed("apply_italic_first_pass", "Removed direct italic mutation wrapper.", "accept_outline_candidate_session"),
    _removed("review_compensated_tuning", "Removed overlapping compensated-tuning review wrapper.", "preview_compensated_tuning_candidate"),
    _removed("apply_compensated_tuning", "Removed direct compensated-tuning mutation wrapper.", "accept_outline_candidate_session"),
]


TOOL_CATALOG: Dict[str, ToolCatalogEntry] = {entry.name: entry for entry in _ENTRIES}
if len(TOOL_CATALOG) != len(_ENTRIES):
    raise RuntimeError("Duplicate Glyphs MCP tool catalog name")


def active_entries() -> Tuple[ToolCatalogEntry, ...]:
    return tuple(entry for entry in _ENTRIES if entry.state == ACTIVE)


def model_entries() -> Tuple[ToolCatalogEntry, ...]:
    return tuple(entry for entry in active_entries() if entry.visibility == MODEL_AND_APP)


def app_only_entries() -> Tuple[ToolCatalogEntry, ...]:
    return tuple(entry for entry in active_entries() if entry.visibility == APP_ONLY)


__all__ = [
    "ACTIVE",
    "APP_ONLY",
    "MODEL_AND_APP",
    "REMOVED",
    "TOOL_CATALOG",
    "ToolCatalogEntry",
    "active_entries",
    "app_only_entries",
    "model_entries",
]
