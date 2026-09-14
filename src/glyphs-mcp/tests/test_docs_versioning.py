"""Protect the released guide and executable examples in the separate v2 guide."""
import ast
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_v1_snapshot_preserves_all_release_files_and_records_adaptations():
    provenance = json.loads((REPO / 'website/v1-source.json').read_text())
    snapshot = REPO / 'website/versioned_docs/version-1.11.0'
    actual = {str(path.relative_to(snapshot)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in snapshot.rglob('*') if path.is_file()}
    assert actual == provenance['snapshotSha256']
    assert actual.keys() == provenance['sha256'].keys()
    changed = {name for name in actual if actual[name] != provenance['sha256'][name]}
    assert changed == provenance['adaptations'].keys()
    assert provenance['tag'] == 'v1.11.0'
    # A v1 download or source link must not silently start serving v2 later.
    for path in snapshot.rglob('*'):
        if path.suffix in {'.md', '.mdx'}:
            text = path.read_text()
            assert 'Glyphs-mcp/releases/latest' not in text
            assert 'Glyphs-mcp/blob/main/' not in text


def test_v2_catalog_signatures_match_only_the_seven_native_server_tools():
    tree = ast.parse((REPO / 'src/sidecar/glyphs_mcp_sidecar/server.py').read_text())
    actual = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
               and d.func.attr == 'tool' for d in node.decorator_list):
            actual[node.name] = [arg.arg for arg in node.args.args]
    reference = (REPO / 'content/reference/command-set.mdx').read_text()
    reference = reference.split('## Explicit reads', 1)[0]
    documented = {}
    for name, args in re.findall(r'^\| `([a-z_]+)` \| (.*?) \|', reference, re.M):
        documented[name] = re.findall(r'`([a-z_]+)`', args)
    assert len(actual) == 7
    assert documented == actual


def test_v2_json_job_examples_are_accepted_by_the_shipped_request_validator():
    import sys
    for directory in ('protocol', 'sidecar', 'bridge'):
        sys.path.insert(0, str(REPO / 'src' / directory))
    from glyphs_mcp_sidecar.service import SidecarService
    examples = []
    for path in (REPO / 'content').rglob('*'):
        if path.suffix not in {'.md', '.mdx'}:
            continue
        for block in re.findall(r'```json\n(.*?)\n```', path.read_text(), re.S):
            value = json.loads(block)
            if 'kind' in value:
                SidecarService._job_request(value['kind'], value.get('delta'),
                                            value.get('glyphs'), value.get('options'))
                examples.append(value['kind'])
    assert set(examples) == {'width_delta', 'spacing', 'kerning_collision', 'slant', 'start_nodes'}
