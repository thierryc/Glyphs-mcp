#!/usr/bin/env python3
"""Validate the shipped lean skill contract and locked runtime provenance offline."""
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check_skill(root, name):
    entry = root/name/'SKILL.md'
    text = entry.read_text()
    assert text.startswith('---\nname: '+name+'\n') and '\ndescription: ' in text, entry
    assert 'surface: glyphs-mcp-v2' in text, entry
    assert 'execute_code_with_context' not in text and '../../' not in text, entry
    # Instructions may live in focused references; do not require repeated prose
    # in every entry or impose job/Undo rules on native coding and release skills.
    for target in re.findall(r'\]\(([^\s)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        path = (entry.parent/target.split('#', 1)[0]).resolve()
        assert root.resolve() in path.parents and path.is_file(), f'{entry}: missing or outside skill tree: {target}'


def check():
    assert not (ROOT/'src/glyphs-mcp-v2').exists(), 'Obsolete experimental runtime in candidate'
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    names = {entry['name'] for entry in manifest['managedSkills']}
    assert len(names) == len(manifest['managedSkills']), 'Duplicate managed skill'
    for parent in ('skills', 'plugins/glyphs-mcp/skills'):
        root = ROOT/parent
        assert {p.parent.name for p in root.glob('*/SKILL.md')} == names
        for name in names:
            check_skill(root, name)
    for architecture in ('arm64', 'x86_64'):
        hashes = json.loads((ROOT/f'third_party/lean-runtime-wheels-{architecture}.json').read_text())
        lock = (ROOT/f'third_party/lean-runtime-{architecture}.lock').read_text()
        assert set(re.findall(r'--hash=sha256:([a-f0-9]{64})',lock)) == set(hashes.values())
        assert 'glyphs-cli==0.6.1' in lock and 'fastmcp==2.12.0' in lock
    for path in (ROOT/'src').glob('*/glyphs_mcp_*/*.py'): ast.parse(path.read_text())
    server_trees = [ast.parse((ROOT/'src/sidecar/glyphs_mcp_sidecar'/name).read_text())
                    for name in ('server.py', 'edit_workflow_ui.py')]
    tools = {
        keyword.value.value
        for tree in server_trees for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == 'tool'
        for keyword in decorator.keywords
        if keyword.arg == 'name' and isinstance(keyword.value, ast.Constant)
    }
    assert len(tools) == 12, f'Expected nine existing and three conversation tools, found {sorted(tools)}'
    return {'skills':len(names), 'runtimeArchitectures':['arm64','x86_64'], 'publicTools':len(tools)}


if __name__ == '__main__':
    print(json.dumps(check(),sort_keys=True))
