"""Entry instruction contracts, not an alternative runtime routing engine."""
from pathlib import Path
import json
import re
import sys
import yaml

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT/'skills/glyphs'


def test_slant_request_default_review_and_precision_recovery():
    sys.path.insert(0,str(ROOT/'src/sidecar'));sys.path.insert(0,str(ROOT/'src/protocol'))
    from glyphs_mcp_sidecar.slant_job import validate_options
    folder=ROOT/'skills/glyphs-mcp-italic-first-pass'
    text=(folder/'references/lean-v2.md').read_text()
    request=json.loads(re.search(r'```json\n(.*?)\n```',text,re.S).group(1))
    assert set(request)=={'document_id','kind','glyphs','options'} and request['kind']=='slant'
    options=validate_options(request['options'])
    assert options['preserveStraightStems'] is False and len(options['masters'])==3
    for phrase in ('Reuse the verified connection','do not rediscover', 'include_preview:false',
                   'partial excerpt','layer.components','Automatic','saved/live',
                   'Keep the exact target guard','Do not silently round','fresh public document ID',
                   'additive','Dirty-indicator restoration is not promised','installation needs updating'):
        assert phrase in text
    metadata=yaml.safe_load((folder/'agents/openai.yaml').read_text())
    assert '$glyphs-mcp-italic-first-pass' in metadata['interface']['default_prompt']
    assert 25<=len(metadata['interface']['short_description'])<=64
    assert 'policy' not in metadata # Preserve the existing implicit-invocation policy.
    for path in folder.rglob('*'):
        if path.is_file():assert path.read_bytes()==(ROOT/'plugins/glyphs-mcp/skills/glyphs-mcp-italic-first-pass'/path.relative_to(folder)).read_bytes()


def test_spacing_focused_request_is_valid_and_documents_scope_and_limits():
    sys.path.insert(0, str(ROOT/'src/sidecar'))
    sys.path.insert(0, str(ROOT/'src/protocol'))
    from glyphs_mcp_sidecar.spacing import validate_options
    path = ROOT/'skills/glyphs-mcp-spacing/references/lean-v2.md'
    text = path.read_text()
    request = json.loads(re.search(r'```json\n(.*?)\n```', text, re.S).group(1))
    assert request['kind'] == 'spacing' and request['glyphs'] == ['H', 'n', 'o']
    assert set(request) == {'document_id', 'kind', 'glyphs', 'options'}
    validated = validate_options(request['options'])
    assert validated['widthMode'] == 'preserve'
    assert set(validate_options({})) <= set(re.findall(r'\| `([^`]+)` \|', text))
    for phrase in ('all masters', '0–10,000', '0–100', '0.5–100', '4,096 intervals',
                   'does not override tabular-name or fixed-pitch protection',
                   'marked edited', 'Exact patch application does not establish continuous',
                   'Reuse the known connection and document ID', 'full external',
                   'Do not save', 'Omit `delta`'):
        assert phrase in text
    assert path.read_bytes() == (ROOT/'plugins/glyphs-mcp/skills/glyphs-mcp-spacing/references/lean-v2.md').read_bytes()


def test_width_route_states_scope_preview_and_native_undo_context():
    assert 'references/width-changes.md' in (SKILL/'SKILL.md').read_text()
    text = (SKILL/'references/width-changes.md').read_text()
    for phrase in ('"kind":"width_delta"', '"glyphs":["A","B"]', '"delta":17',
                   'All stored layers', 'backup', 'no master filter', 'limited to 10',
                   'Ten of 90 is incomplete', 'Edit View', 'per glyph', 'discard_job',
                   'same document ID', 'mixed valid/missing', 'booleans are rejected',
                   'without user authorization', 'bridge, sidecar and skills together'):
        assert phrase in text


def test_entry_routes_per_connection_and_requires_current_private_build():
    entry = (SKILL/'SKILL.md').read_text()
    assert 'references/connection-session.md' in entry
    text = (SKILL/'references/connection-session.md').read_text()
    for required in ('specific MCP connection', 'never merge catalogs', 'installation needs updating',
                     'v1 server reachable; matching v1 skills unavailable', 'list_open_fonts',
                     'Neither v1 nor the lean sidecar requires `apiMajor == 2`',
                     'explicit different interface/revision', 'Unknown or conflicting catalog/identity'):
        assert required in text
    assert text.index('Inspect the tool catalog') < text.index('call that connection’s `get_status`')
    assert 'staged Python' not in entry + text and 'materialize' not in entry + text


def test_invocation_metadata_and_mirror_include_recovery_reference():
    metadata = yaml.safe_load((SKILL/'agents/openai.yaml').read_text())
    assert '$glyphs' in metadata['interface']['default_prompt']
    assert 25 <= len(metadata['interface']['short_description']) <= 64
    assert metadata['policy']['allow_implicit_invocation'] is False
    mirror = ROOT/'plugins/glyphs-mcp/skills/glyphs'
    for path in SKILL.rglob('*'):
        if path.is_file(): assert path.read_bytes() == (mirror/path.relative_to(SKILL)).read_bytes()
    recovery = (SKILL/'references/connection-troubleshooting.md').read_text()
    for required in ('http://127.0.0.1:9680/mcp/', 'Edit → Glyphs MCP Server',
                     'com.GeorgSeifert.Glyphs3', 'com.GeorgSeifert.Glyphs4',
                     'worker.available', 'bridge.reachable', 'Replace preserved skills (backup)',
                     'older process remains loaded', 'Dirty', 'Plugin caches'):
        assert required.lower() in recovery.lower()


def test_metadata_reference_documents_observed_bounds_and_recovery():
    entry = (SKILL/'SKILL.md').read_text()
    assert 'references/metadata-reads.md' in entry
    reference = (SKILL/'references/metadata-reads.md').read_text()
    for required in ('1–100 explicit entities', '1–32 supported fields',
                     'missing glyph rejects the entire request', 'target_not_found',
                     'known subset `["A","a"]`', 'primary mapping',
                     'complete `unicodes` list is unavailable', 'unsupported_read',
                     'Dirty documents remain readable without saving'):
        assert required in reference


def test_master_reference_has_exact_selectors_capability_gate_and_partial_evidence():
    assert 'references/master-reads.md' in (SKILL/'SKILL.md').read_text()
    reference = (SKILL/'references/master-reads.md').read_text()
    for required in ('masters.list.v1', 'master.read.exact.v1', 'negotiated `readCapabilities`',
                     'values.nextCursor', 'values.complete: false', 'stale_master_cursor',
                     'not an atomic multi-call snapshot', 'dirty and unsaved',
                     'not\nnecessarily UUIDs', 'source script or Save', 'installation needs updating'):
        assert required in reference


def test_layer_reference_and_focused_invocations_use_current_interface():
    assert 'references/layer-reads.md' in (SKILL/'SKILL.md').read_text()
    reference = (SKILL/'references/layer-reads.md').read_text()
    for required in ('layer.read.exact.v1', 'native `layerId`', '1–100 explicit entities',
                     '1–32 supported fields', 'target_not_found', 'invalid_request',
                     'null means unset/unavailable', 'stored overrides', 'Zero-area bounds',
                     'opaque change guard', 'Dirty and unsaved'):
        assert required in reference
    for name in ('glyphs-mcp-spacing', 'glyphs-mcp-outlines-docs'):
        skill = ROOT/'skills'/name
        text = (skill/'SKILL.md').read_text()
        assert '../glyphs/references/layer-reads.md' in text
        assert 'read_entities' in text and 'require `data.apiMajor == 2`' not in text
        metadata = yaml.safe_load((skill/'agents/openai.yaml').read_text())
        assert '$glyphs' in metadata['interface']['default_prompt']
        assert metadata['policy']['allow_implicit_invocation'] is True
        assert 25 <= len(metadata['interface']['short_description']) <= 64
        assert metadata['interface']['short_description'].strip() == metadata['interface']['short_description']
        mirror = ROOT/'plugins/glyphs-mcp/skills'/name
        for path in skill.rglob('*'):
            if path.is_file(): assert path.read_bytes() == (mirror/path.relative_to(skill)).read_bytes()


def test_private_read_skills_require_updates_instead_of_older_workflows():
    for name in ('master-reads.md', 'layer-reads.md', 'selection-reads.md'):
        text = ' '.join((SKILL/'references'/name).read_text().split())
        assert 'installation needs updating' in text
        assert 'sidecar and skills together' in text
    entry = (SKILL/'SKILL.md').read_text()
    assert 'Do not maintain fallback' in entry and 'jobKinds' in entry
    assert 'use the same workflow; label missing identity' not in entry
    assert 'explicit known-ID reads can still' not in (SKILL/'references/master-reads.md').read_text()
    roadmap = (ROOT/'skills/ROADMAP.md').read_text()
    assert 'permanent Python fallback' not in roadmap and 'seven tools' in roadmap


def test_document_targeting_reuses_ids_without_weakening_error_or_intent_guards():
    text=' '.join((SKILL/'references/document-targeting.md').read_text().split())
    for required in ('Discover the intended font once', 'same font', 'document_not_found',
                     'target_not_found', 'missing glyphs', 'not a path',
                     'Closing and reopening the same file creates a new ID',
                     'bridge/Glyphs restart', 'never silently substitute',
                     'Require exactly one true marker', 'remembering identity does not cache contents'):
        assert required.lower() in text.lower()
    assert 'document-targeting.md' in (SKILL/'SKILL.md').read_text()
    for reference in ('selection-reads.md','metadata-reads.md','master-reads.md','layer-reads.md'):
        assert 'document-targeting.md' in (SKILL/'references'/reference).read_text()
    for name in ('glyphs-mcp-outlines-docs','glyphs-mcp-spacing','glyphs-mcp-kerning','glyphs-mcp-development'):
        body=' '.join((ROOT/'skills'/name/'SKILL.md').read_text().split())
        assert 'document-targeting.md' in body
        assert 'Reuse' in body or 'reuse' in body
        assert 'Call `get_status` first' not in body


def test_stored_kerning_route_is_read_only_exact_and_recovers_without_rediscovery():
    reference = (SKILL/'references/kerning-reads.md').read_text()
    for phrase in ('1–100 explicit selectors', 'fields:["value"]', '`LTR`, `RTL` or `vertical`',
                   'not v1 native glyph IDs', 'does not enumerate group membership',
                   '[-90.125, 0, null, -70.25]', 'class/exception precedence',
                   'Dirty and unsaved', 'One bad selector rejects the entire request',
                   'document_not_found', 'same document ID', 'Do not rediscover documents',
                   'installation needs updating', 'not a read prerequisite'):
        assert phrase in reference
    assert 'references/kerning-reads.md' in (SKILL/'SKILL.md').read_text()
    focused = ROOT/'skills/glyphs-mcp-kerning'
    text = (focused/'SKILL.md').read_text()
    assert text.index('For stored-value inspection') < text.index('Prepare supported work')
    assert '../glyphs/references/kerning-reads.md' in text
    assert 'Only when collision repair is requested' in text
    workflow = (focused/'references/lean-v2.md').read_text()
    assert '../../glyphs/references/kerning-reads.md' in workflow
    assert 'For explicitly requested collision-job preparation' in workflow
    metadata = yaml.safe_load((focused/'agents/openai.yaml').read_text())
    assert metadata['interface']['short_description'] == 'Inspect stored kerning and review collision repairs'
    assert metadata['interface']['default_prompt'] == 'Use $glyphs and $glyphs-mcp-kerning to inspect stored kerning. Prepare a collision repair only when requested.'
    assert 'policy' not in metadata
    assert yaml.safe_load((SKILL/'agents/openai.yaml').read_text())['policy']['allow_implicit_invocation'] is False
    for path in focused.rglob('*'):
        if path.is_file(): assert path.read_bytes() == (ROOT/'plugins/glyphs-mcp/skills/glyphs-mcp-kerning'/path.relative_to(focused)).read_bytes()


def test_linked_command_contract_matches_current_private_selection_and_targeting():
    text = (ROOT/'content/reference/command-set.mdx').read_text()
    assert 'Older bridges' not in text and '(0.1.0)' not in text
    for phrase in ('selection.context.v1', 'selectedAnchorCount', 'selectedOtherCount',
                   'nodeLimit', '1–256', 'complete', 'document_not_found',
                   'retain its `document_id`', 'bridge, sidecar and skills together'):
        assert phrase in text


def test_collision_followup_explicit_options_sampling_and_compact_polling():
    text=(ROOT/'skills/glyphs-mcp-kerning/references/lean-v2.md').read_text()
    for phrase in ('500 ms', '100 ms', 'include_preview', 'previewIncluded:false',
                   '4,096-height', '0.1–100', '1–3,000', 'targetGap', '5.125',
                   'read the complete local JSON', 'once', "left glyph's Edit-view history",
                   'correct the pair names/master IDs', 'no implicit Save'):
        assert phrase in text
    assert 'include_preview' in (ROOT/'content/reference/command-set.mdx').read_text()


def test_start_node_skill_keeps_context_and_explains_native_indices():
    import yaml
    focused=ROOT/'skills/glyphs-mcp-master-compatibility'
    text=(focused/'references/lean-v2.md').read_text()
    for required in ('Reuse the verified connection', 'layer.paths', 'path 1 is shape 2',
                     'including off-curves', 'existing cyclic phase', 'two incoming off-curve',
                     'dirty unsaved repeat is refused', 'include_preview=false'):
        assert required in text
    for path in focused.rglob('*'):
        if path.is_file():assert path.read_bytes()==(ROOT/'plugins/glyphs-mcp/skills'/focused.name/path.relative_to(focused)).read_bytes()
    metadata=yaml.safe_load((focused/'agents/openai.yaml').read_text())
    assert '$glyphs-mcp-master-compatibility' in metadata['interface']['default_prompt']
    assert not metadata['interface']['short_description'].endswith('consistent co')


def test_specialized_scope_is_focused_and_does_not_claim_retired_audits():
    entry = (SKILL/'SKILL.md').read_text()
    scope = SKILL/'references/specialized-scope.md'
    assert 'references/specialized-scope.md' in entry
    assert 'specialized-scope.md' in (SKILL/'references/connection-session.md').read_text()
    text = ' '.join(scope.read_text().split())
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    names = {item['name'] for item in manifest['managedSkills']}
    retired = {'icon-font','litsquare-metadata','color-font','variable-font',
               'production-audit','unicode-semantics','export-validation'}
    assert not {f'glyphs-mcp-{name}' for name in retired} & names
    assert len(names) == 11
    # Unsupported audits remain scoped; a native task is never an MCP fallback.
    assert 'does not prove that a current lean runtime needs updating' in text
    assert 'never claim that a partial read completes a full audit' in text
    assert 'A native script is separate from the MCP' in text
    assert 'v1 skills after catalog and identity' in text
    assert 'document IDs or jobs' in text
    assert 'Plugin caches and source worktrees are separate' in text
    assert scope.read_bytes() == (ROOT/'plugins/glyphs-mcp/skills/glyphs/references/specialized-scope.md').read_bytes()
