"""Reproduce catalog coverage and collect read-only evidence for this review.

The feature assessments below are human-readable audit judgments, not tests of
native behavior. Re-running captures the checkout/installed skills at that time.
"""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import ast
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
V1 = ROOT/'src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources'
sys.path.insert(0, str(V1))
import tool_catalog


def feature(name, tools, state, intent, outcome, decision, evidence):
    return dict(name=name, v1Tools=tools.split(), v2State=state, intent=intent,
                outcome=outcome, recommendation=decision, evidence=evidence.split())


FEATURES = [
    feature('Connection and runtime identity', 'get_server_info', 'retained', 'documented',
            'get_status advertises coordinated release, separate fingerprints, host and capabilities.',
            'Keep current route; distinguish release, interface and protocol versions.', 'contract'),
    feature('Open-document discovery and targeting', 'list_open_fonts', 'retained', 'documented',
            'list_documents returns live document IDs, paths, family names and dirty state; IDs replace font indices.',
            'Retain per-connection IDs. Frontmost selection is a separate unresolved context gap.', 'contract adapter'),
    feature('Glyph inventory and metadata', 'get_font_glyphs', 'partial', 'decision-needed',
            'Known names expose five fields. No glyph enumeration, layerCount or kerning-group fields; get_glyph_details also formerly supplied script/productionName.',
            'Keep bounded projections, but explicitly decide bounded glyph discovery and missing scalar reads. No full-font response required.', 'contract adapter metadata'),
    feature('Master metrics and axes', 'get_font_masters', 'partial', 'decision-needed',
            'Native ID/name enumeration retained. Weight/width axis values, italicAngle, ascender, capHeight, descender and xHeight are absent from reads.',
            'Decide additive requested fields in existing master reads. P04 verified identification, not all v1 master properties.', 'contract adapter masters'),
    feature('Instances', 'get_font_instances', 'omitted', 'decision-needed',
            'No instance entity or list; native coding can inspect instances, but no focused equivalent inspection route is shipped.',
            'Choose bounded instance reads or an explicit native-only Beta 1 policy; do not claim variable-font inspection parity.', 'contract adapter'),
    feature('Layer inventory, geometry and components', 'get_glyph_details get_glyph_paths get_glyph_components', 'partial', 'decision-needed',
            'Known exact layer IDs expose metrics/bounds/hash; selected nodes have details. No per-glyph layer enumeration, associatedMasterId, full paths/shape indices, anchor/path/component counts or component transforms/alignment reads.',
            'Prioritize layer discovery and bounded one-layer structural evidence. A hash and a visual overlay are not a geometry response.', 'contract adapter outlines'),
    feature('Font View selection and current context', 'get_selected_glyphs get_selected_font_and_master', 'partial', 'decision-needed',
            'Selection resolves currentTab.activeLayer only. Font View multi-selection, selectedFontMaster, explicit frontmost document, UPM and font/version counts are not returned.',
            'Prioritize a compact native context projection through read_entities; keep detailed nodes restricted to one Edit View layer.', 'contract adapter selection'),
    feature('Selected Edit View nodes', 'get_selected_nodes', 'retained', 'documented',
            'selection.context.v1 supplies exact active glyph/layer, counts and optional bounded nodes, default 64/max 256. Rich v1 repeated metadata and master correspondence are not returned.',
            'Keep the explicit counts/details contract. Additional cross-master selection mapping stays outside this capability.', 'contract selection'),
    feature('Stored kerning and group discovery', 'get_font_kerning', 'partial', 'decision-needed',
            'Exact named/group-key values, absent versus zero and LTR/RTL/vertical retained. No pair-table enumeration or glyph-group membership reads. Collision reports reveal keys for prepared pairs only.',
            'Decide a bounded discovery route; do not run an edit-preparation job merely to discover kerning groups.', 'contract kerning collision'),
    feature('Width and exact sidebearing edits', 'update_glyph_metrics', 'partial', 'documented-with-workflow-gap',
            'width_delta is additive across all stored layers, including backups/special layers. No single-master filter or arbitrary absolute width/LSB/RSB setter. Spacing suggestions are not equivalent absolute setters.',
            'Document a focused native metrics recipe or explicitly defer that workflow. Never expand a requested master scope to all stored layers.', 'contract widths'),
    feature('Spacing review and application', 'review_spacing apply_spacing', 'partial', 'documented',
            'External spacing retains reference/area policy, class-aware selection, fractions and native alignment protections. v1 rules/defaults/guards/debug parameter surface is intentionally reduced.',
            'Keep the tested lean algorithm and state narrower options; do not promise arbitrary v1 rules compatibility.', 'spacing spacingSkill benefits'),
    feature('Spacing guides and persistent spacing parameters', 'set_spacing_guides set_spacing_params', 'omitted', 'documented-with-workflow-gap',
            'No guide-writing job or dedicated persistent-parameter write; options belong to each prepared job. Native guides remain available.',
            'State that job options do not migrate persistent v1 spacing rules or reproduce managed guides. Native route needs task-specific verification.', 'contract spacingSkill'),
    feature('Collision kerning review and repair', 'review_kerning_bumper apply_kerning_bumper', 'partial', 'documented',
            'Explicit LTR pair corrections retained with native effective resolution and exact exceptions. No automatic v1 relevant-pair discovery, kerning proof-tab option or complete option parity.',
            'Keep explicit measured-pair scope and report sampling limits. Automatic discovery is not supplied by the retained collision job.', 'contract collision benefits'),
    feature('Arbitrary kerning pair/group edits', 'set_kerning_pair', 'native-route', 'documented-with-workflow-gap',
            'No public arbitrary set/remove pair operation. Collision jobs only generate measured positive corrections; raw bridge patch mechanics are not public tools.',
            'Provide a short qualified native recipe if ordinary manual pair editing is a Beta 1 promise. Do not claim collision repair covers it.', 'contract collision'),
    feature('Kerning proof tabs', 'generate_kerning_tab', 'native-route', 'documented-with-workflow-gap',
            'Native tabs can be opened via UI/scripts; the dedicated bounded proof generator is not in the seven tools.',
            'Document proof-text/tab creation as native work; no equivalent v2 generator was qualified in this audit.', 'contract reset'),
    feature('Start-node alignment', 'review_start_node_alignment apply_start_node_alignment', 'retained', 'documented',
            'start_nodes retains tested correspondence on one selected contour, preserving reference phase. Refuses malformed, ambiguous, open or mismatched contours.',
            'Keep qualified native replay and exact history. This does not implement the earlier inspect/normalize/reorder compatibility plan.', 'startNodes masterSkill benefits'),
    feature('Italic first pass', 'preview_italic_first_pass_candidate', 'partial', 'documented',
            'slant supplies native mechanical shear and optional straight-stem preservation. Full balanced/cursivy policy, curve correction, source-to-target master copying and arbitrary special-layer repair are not ported.',
            'Keep the mechanical-first-pass claim. No complete v1 optical-italic parity claim.', 'slant benefits'),
    feature('Master italic angle and stem editing', 'set_master_italic_angle review_master_stem_metrics set_master_stem_metrics', 'native-route', 'documented-with-workflow-gap',
            'No master metadata/stem setter. Slant uses a requested angle and does not set the master italicAngle property.',
            'Explicit native Font Info/script step when requested. Outline slant and master metadata are separate tasks.', 'slant contract'),
    feature('Node coordinates and path replacement', 'update_glyph_node_positions set_glyph_paths', 'native-route', 'documented',
            'General outline changes use authored native scripts/UI. RV01/RV02 qualified selected move/add/remove/extrema/split tasks, not arbitrary path replacement.',
            'Keep the native precision recipe and per-task preservation tests; do not imply scripts acquire MCP job discard.', 'nativeFeatures precision rv02'),
    feature('Components, anchors and corner hints', 'add_component_to_glyph add_anchor_to_glyph add_corner_to_all_masters', 'native-route', 'documented-with-workflow-gap',
            'No corresponding public edit job. Native APIs/UI remain available, but current realistic tests do not qualify all three v1 edit outcomes.',
            'Treat these as native-only and qualify concrete tasks; populated-hint preservation remains unverified in RV02.', 'contract precision rv02'),
    feature('Glyph creation, deletion, copying and properties', 'create_glyph delete_glyph update_glyph_properties copy_glyph', 'native-route', 'documented',
            'The seven tools do not expose general glyph CRUD; native scripting/development is the documented route.',
            'Keep explicit target and data-preservation checks. Retaining a generic script route is not proof of every former tool behavior.', 'contract scripting'),
    feature('Custom parameters', 'get_custom_parameters set_custom_parameters', 'native-route', 'documented-with-workflow-gap',
            'No custom-parameter entity or setter; font/master/instance native APIs are available through coding.',
            'Document explicit native-only status; do not conflate these with per-job options.', 'contract scripting'),
    feature('OpenType and stylistic sets', 'list_style_sets', 'partial', 'documented-with-workflow-gap',
            'RV02 supplies focused feature source review/edit/compile/export/shaping guidance. v1 one-call stylistic-set substitution listing and group deep links are not recreated.',
            'Keep corrected OpenType routing; add a concise stylistic-set inspection/proof recipe if that convenience is retained. No new feature MCP tool needed.', 'nativeFeatures rv02'),
    feature('Unicode/PUA audit and allocation', 'review_unicode_assignments apply_unicode_assignments', 'omitted', 'documented-with-workflow-gap',
            'Unicode assignment tools and v1 icon-font skill are not in the lean payload. Generic native scripting does not preserve v1 collision/range/previous-map allocation policy automatically.',
            'Explicitly defer icon/Unicode allocation for Beta 1 or port the focused native guidance and qualify it. Do not claim drawing/native Unicode UI replaces the allocator.', 'contract oldSkills metadata'),
    feature('LitSquare metadata and semantic roles', 'get_litsquare_metadata get_selected_litsquare_path_roles patch_litsquare_metadata set_litsquare_path_roles', 'omitted', 'documented',
            'Metadata Inspector and LitSquare UI/tools were explicitly removed from the lean bridge; stored native metadata is not intentionally deleted.',
            'Keep independent project tooling/native scripting separate. Release notes must say authoring/inspection integration is absent.', 'reset oldSkills'),
    feature('IconGrid fixed-centering integration', 'get_icon_grid_horizontal_center set_icon_grid_horizontal_center reset_icon_grid_horizontal_center', 'omitted', 'documented',
            'Standalone Icon Grid remains independent; the MCP read/set/reset policy is not ported or advertised.',
            'Do not describe the independent Reporter as a substitute for the removed agent controls. No second Icon Grid implementation.', 'reset oldSkills'),
    feature('Tunni analysis and balance', 'review_tunni_geometry apply_tunni_balance preview_tunni_balance_candidate', 'omitted', 'documented',
            'Custom Tunni algorithms/candidates were explicitly excluded from the lean benefit queue.',
            'Use existing native/manual methods where appropriate; no equivalent algorithm or automated outcome claim.', 'benefits'),
    feature('Adaptive curve and cross-master diagnostics', 'review_curve_quality review_curve_quality_across_masters', 'partial', 'decision-needed',
            'Curve Inspector supplies a bounded visual comb; no public adaptive event/continuity report or cross-master quality report equivalent to v1.',
            'Explicitly defer numerical diagnostic reports or specify a bounded external report recipe. A comb is not analytical parity.', 'curve benefits contract'),
    feature('Curvature display', 'set_curve_review_overlay get_curve_review_overlay_state', 'retained', 'documented',
            'Independent Curve Inspector/native UI retains qualified display behavior. No MCP overlay-toggle/state tool; capability registration alone is not control.',
            'Keep companion/UI distinction and P13 evidence; do not invent public companion calls.', 'curve curvatureSkill p13'),
    feature('Collinear smooth-node repair', 'apply_collinear_handles_smooth preview_collinear_handles_candidate', 'omitted', 'documented',
            'Custom smoothness repair and candidate flow are explicitly outside the queue; native UI/script actions remain separate.',
            'Keep native scope; no equivalent multi-target guarded smoothness repair is claimed.', 'benefits'),
    feature('Compensated scaling', 'preview_compensated_tuning_candidate', 'omitted', 'documented',
            'General compensated scaling/candidate generation explicitly excluded.',
            'Do not port the custom engine for parity alone; state absence in migration notes.', 'benefits'),
    feature('Candidate sessions and history', 'set_outline_candidate_overlay get_outline_candidate_state materialize_outline_candidate_session review_outline_candidate_session accept_outline_candidate_session discard_outline_candidate_session', 'partial', 'documented',
            'Supported edits use jobs/reports/apply/discard and native per-glyph Undo. Independent Reference Inspector compares references, not historical proposal sessions.',
            'Keep lean native history; unsupported v1 candidate families do not become supported merely because the job lifecycle exists.', 'contract reset'),
    feature('Annotations and managed annotation groups', 'get_glyph_annotations add_glyph_annotation add_glyph_annotation_group update_glyph_annotation delete_glyph_annotation clear_glyph_annotations get_glyph_annotation_groups', 'native-route', 'documented-with-workflow-gap',
            'No dedicated annotation/group reads or writes. Native annotations can be authored through UI/scripts; managed-group identity/cleanup policy is not supplied.',
            'Explicit native-only Beta 1 policy; consider focused proofing guidance, not a new annotation subsystem.', 'contract scripting'),
    feature('Designspace/UFO export', 'ExportDesignspaceAndUFO', 'omitted', 'documented-with-workflow-gap',
            'Dedicated static/variable Designspace/UFO exporter and build-script generation are absent. RV02 TTF export evidence is a different deliverable.',
            'Record explicit exporter deferral or qualify an existing external conversion route; do not claim TTF export replaces Designspace/UFO.', 'contract nativeFeatures'),
    feature('Save and persistence', 'save_font', 'native-route', 'documented',
            'Native Save is acceptance, with task authorization. No MCP save command; jobs require a saved clean source.',
            'Keep the deliberate boundary. Dirty/pathless reads are supported; dirty/pathless job edits are not.', 'contract reset'),
    feature('Live Python execution', 'execute_code execute_code_with_context', 'native-route', 'documented',
            'General Python execution is deliberately absent from MCP. Workspace scripts/native CLI or authorized in-app routes are used; saved CLI copies do not see unsaved live state.',
            'Keep current coding loop and scoped verification. No extra execution tool is justified by RV02.', 'scripting nativeFeatures rv02'),
    feature('Documentation search and retrieval', 'docs_search docs_get', 'retained', 'documented',
            'Bundled offline corpus plus local docs.py search/get replaces MCP docs tools; bounded results and provenance retained.',
            'Keep focused offline retrieval and pinned source separation.', 'docs'),
    feature('Document change overview', 'get_document_change_overview', 'partial', 'documented',
            'Per-job status/report and bounded activity replace the tracked MCP mutation overview; there is no equivalent global audit/change-history view.',
            'Keep per-job evidence and native reference comparison; do not rebuild an audit/history model.', 'contract reset'),
    feature('Embedded feedback panels and target links', 'show_glyphs_status show_font_feedback show_glyph_feedback show_opentype_features preview_spacing_feedback preview_kerning_feedback preview_handle_smoothing_feedback apply_feedback_plan open_feedback_target', 'omitted', 'documented-with-workflow-gap',
            'No legacy MCP App feedback panel or embedded-plan endpoints. Agent reports and native companions/UI replace parts of review; clickable per-glyph/style-set navigation is not equivalent.',
            'Document the UI/access change and decide whether lightweight proof navigation needs a focused recipe. No embedded feedback framework required.', 'contract reset'),
]

EVIDENCE = {
    'contract': 'content/reference/command-set.mdx',
    'adapter': 'src/bridge/glyphs_mcp_bridge/glyphs_adapter.py',
    'selection': 'src/bridge/glyphs_mcp_bridge/selection.py',
    'metadata': 'skills/glyphs/references/metadata-reads.md',
    'masters': 'skills/glyphs/references/master-reads.md',
    'kerning': 'skills/glyphs/references/kerning-reads.md',
    'widths': 'skills/glyphs/references/width-changes.md',
    'spacing': 'src/sidecar/glyphs_mcp_sidecar/spacing.py',
    'spacingSkill': 'skills/glyphs-mcp-spacing/references/lean-v2.md',
    'collision': 'src/sidecar/glyphs_mcp_sidecar/kerning_job.py',
    'startNodes': 'skills/glyphs-mcp-master-compatibility/references/lean-v2.md',
    'masterSkill': 'skills/glyphs-mcp-master-compatibility/SKILL.md',
    'slant': 'src/sidecar/glyphs_mcp_sidecar/slant_job.py',
    'outlines': 'skills/glyphs-mcp-outlines-docs/SKILL.md',
    'precision': 'skills/glyphs-mcp-development/references/native-precision.md',
    'scripting': 'skills/glyphs-mcp-scripting/SKILL.md',
    'nativeFeatures': 'skills/glyphs-mcp-opentype-features/references/native-features.md',
    'docs': 'skills/glyphs-mcp-development/references/development-docs.md',
    'reset': 'V2-SIMPLE-RESET.md',
    'benefits': 'LEAN-V2-BENEFITS.md',
    'oldSkills': 'legacy/glyphs3/skills/manifest.json',
    'curve': 'src/companions/curve-inspector/README.md',
    'curvatureSkill': 'skills/glyphs-mcp-outlines-docs/references/curvature-display.md',
    'p13': 'reports/p13-curvature-improvements-20260913/report.md',
    'rv02': 'reports/rv02-native-coding-20260914/report.md',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    catalog = list(tool_catalog.active_entries())
    mapped = [name for row in FEATURES for name in row['v1Tools']]
    assert len(mapped) == len(set(mapped)), 'Duplicate mapping'
    assert set(mapped) == {entry.name for entry in catalog}, 'Incomplete catalog coverage'
    assert len(catalog) == 87
    implementations = {}
    active_names = {entry.name for entry in catalog}
    for path in [*sorted(V1.glob('mcp_tools*.py')), V1/'docs_tools.py', V1/'code_execution.py']:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in active_names:
                assert node.name not in implementations, node.name
                implementations[node.name] = dict(path=str(path.relative_to(ROOT)),
                                                  line=node.lineno, sha256=digest(path))
    assert set(implementations) == active_names, active_names - implementations.keys()
    for i, row in enumerate(FEATURES, 1):
        row['id'] = f'F{i:02}'
        assert set(row['evidence']) <= EVIDENCE.keys()
    current = json.loads((ROOT/'skills/manifest.json').read_text())['managedSkills']
    legacy = json.loads((ROOT/'legacy/glyphs3/skills/manifest.json').read_text())['managedSkills']
    evidence = {key: dict(path=name, sha256=digest(ROOT/name)) for key, name in EVIDENCE.items()}
    stale = []
    installed = Path.home()/'.codex/skills'
    for name in ('glyphs-mcp-icon-font', 'glyphs-mcp-litsquare-metadata', 'glyphs-mcp-color-font',
                 'glyphs-mcp-variable-font', 'glyphs-mcp-production-audit',
                 'glyphs-mcp-unicode-semantics', 'glyphs-mcp-export-validation'):
        path = installed/name/'SKILL.md'
        if not path.is_file():
            stale.append(dict(name=name, present=False))
            continue
        text = path.read_text()
        metadata = installed/name/'agents/openai.yaml'
        stale.append(dict(name=name, present=True, path=str(path), sha256=digest(path),
                          managedInLeanPayload=name in {row['name'] for row in current},
                          incompatibleGate='get_server_info' in text and 'apiMajor == 2' in text,
                          claimsV2Surface='surface: glyphs-mcp-v2' in text,
                          explicitImplicitInvocation=('allow_implicit_invocation: true' in metadata.read_text())
                          if metadata.is_file() else None,
                          evidenceLines=[line for line in text.splitlines() if 'apiMajor' in line or 'get_server_info' in line]))
    facts = dict(recordedAt=datetime.now(timezone.utc).isoformat(),
                 sourceRoot=str(ROOT), sourceCommit=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip(),
                 method='Static feature/intent audit plus one read-only v2 get_status; not a native feature benchmark. V1 is historical.',
                 sourceCatalogSha256=digest(V1/'tool_catalog.py'),
                 v1Implementations=implementations,
                 activeV1Tools=len(catalog), modelVisibleV1Tools=len(tool_catalog.model_entries()),
                 appOnlyV1Tools=len(tool_catalog.app_only_entries()),
                 removedBeforeV1Baseline=[e.name for e in tool_catalog.TOOL_CATALOG.values() if e.state != tool_catalog.ACTIVE],
                 featureGroups=len(FEATURES), mappedTools=len(mapped), duplicateMappings=[], unmappedTools=[],
                 featureStateCounts=dict(Counter(row['v2State'] for row in FEATURES)),
                 intentCounts=dict(Counter(row['intent'] for row in FEATURES)),
                 v1ManagedSkills=[row['name'] for row in legacy], v2ManagedSkills=[row['name'] for row in current],
                 incompatibleInstalledSkills=stale, evidence=evidence)
    (OUT/'facts.json').write_text(json.dumps(facts, indent=2)+'\n')
    (OUT/'features.json').write_text(json.dumps(FEATURES, indent=2)+'\n')
    (OUT/'v1-catalog.json').write_text(json.dumps([asdict(e) for e in catalog], indent=2)+'\n')
    by_name = {name: row for row in FEATURES for name in row['v1Tools']}
    with (OUT/'tool-map.csv').open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['v1_tool', 'category', 'visibility', 'feature_id', 'feature', 'v2_state', 'intent', 'outcome'])
        for entry in catalog:
            row = by_name[entry.name]
            writer.writerow([entry.name, entry.category, entry.visibility, row['id'], row['name'], row['v2State'], row['intent'], row['outcome']])
    lines = ['# Complete capability mapping\n',
             'This maps all 87 active v1 tools to user-facing capabilities. Status and intent are audit judgments grounded in the linked current source; tool existence is not proof that v1 passed native tests. See [report.md](report.md) for priorities and limits.\n',
             '| ID / capability | v2 outcome | Intent / recommendation |', '|---|---|---|']
    for row in FEATURES:
        refs = ', '.join(f'[{key}](../../{EVIDENCE[key]})' for key in row['evidence'])
        lines.append(f"| {row['id']} · {row['name']} | **{row['v2State']}**. {row['outcome']} | **{row['intent']}**. {row['recommendation']} {refs} |")
    (OUT/'feature-matrix.md').write_text('\n\n'.join(lines[:2])+'\n'+'\n'.join(lines[2:])+'\n')
    print(json.dumps({key: facts[key] for key in ('activeV1Tools', 'featureGroups', 'mappedTools', 'unmappedTools', 'featureStateCounts', 'intentCounts')}, indent=2))


if __name__ == '__main__':
    main()
