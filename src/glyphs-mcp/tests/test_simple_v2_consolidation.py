"""Current catalog routing, shared hashing and architecture contracts."""
import ast
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from jsonschema import validate

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'sidecar'):
    sys.path.insert(0, str(ROOT/'src'/part))


@pytest.fixture(scope='module')
def catalog():
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server
    async def read():
        async with Client(create_server(None)) as client:
            return {tool.name: tool for tool in await client.list_tools()}
    return asyncio.run(read())


def test_current_catalog_examples_remain_valid_and_discoverable(catalog):
    from glyphs_mcp_protocol import TOOL_NAMES
    from glyphs_mcp_sidecar.service import SidecarService
    assert set(catalog) == set(TOOL_NAMES) and len(catalog) == 18
    cases = json.loads((Path(__file__).parent/'fixtures/current_tool_routing.json').read_text())
    for case in cases:
        tool = catalog[case['tool']]
        validate(case['arguments'], tool.inputSchema)
        for term in case['routingTerms']:
            assert term in tool.description, (case['task'], term)
        args = case['arguments']
        if args.get('kind') == 'checkpoint_restore':
            from glyphs_mcp_sidecar.checkpoint_restore import validate as validate_restore
            from glyphs_mcp_sidecar.service import ServiceError
            service = SimpleNamespace(bridge=SimpleNamespace(status=lambda: {'writeCapabilities': ['font.checkpoint-restore.v1']}))
            validate_restore(service, args['kind'], None, None, args['options'], ServiceError)
        elif 'kind' in args:
            SidecarService._job_request(args['kind'], args.get('delta'), args.get('glyphs'), args.get('options'))


def test_script_negotiation_keeps_one_execution_capability(tmp_path):
    from glyphs_mcp_sidecar.service import SidecarService
    from glyphs_mcp_sidecar.jobs import JobStore
    advertised = ['script.scoped.v1', 'script.unrestricted.v1', 'script.native.v1']
    service = SidecarService(SimpleNamespace(status=lambda: {'protocol': 1, 'jobCapabilities': advertised}),
                             jobs=JobStore(tmp_path), worker=SimpleNamespace(status=lambda: {'available': False}))
    try:
        status = service.get_status()
        assert [x for x in status['jobCapabilities'] if x.startswith('script.')] == ['script.native.v1']
        assert 'python_script' in status['jobKinds']
        advertised.remove('script.native.v1')
        assert 'python_script' not in service.get_status()['jobKinds']
    finally:
        service.close()


@pytest.mark.parametrize('data', [b'', b'fractional export\x00\xff', b'x'*(2*1024*1024+17)], ids=['empty', 'binary', 'multi-chunk'])
def test_shared_artifact_hash_streams_exact_bytes(data):
    from glyphs_mcp_sidecar.source import file_hash
    sizes = []
    class Stream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 1024*1024
            sizes.append(size)
            return super().read(size)
    class File:
        def open(self, mode):
            assert mode == 'rb'
            return Stream(data)
    assert file_hash(File()) == 'sha256:' + hashlib.sha256(data).hexdigest()
    assert len(sizes) >= 1 + len(data)//(1024*1024)


def test_shared_artifact_hash_propagates_io_errors_and_is_used_by_both_routes(tmp_path):
    from glyphs_mcp_sidecar.source import file_hash
    from glyphs_mcp_sidecar import artifact_publication, font_export_job
    with pytest.raises(FileNotFoundError):
        file_hash(tmp_path/'missing')
    with pytest.raises(IsADirectoryError):
        file_hash(tmp_path)
    assert artifact_publication._sha256 is file_hash
    assert font_export_job._sha256 is file_hash


def test_current_guidance_identifies_history_and_shared_contract():
    for name in ('ROADMAP.md', 'LEAN-V2-BENEFITS.md', 'V2-SIMPLE-RESET.md', 'V2-CONVERSATION-WORKFLOW-PLAN.md'):
        intro = (ROOT/name).read_text().splitlines()[:12]
        assert 'historical' in '\n'.join(intro).lower(), name
        assert 'V2-RELEASE.md' in '\n'.join(intro), name
    for name in ('README.md', 'CODEX.md', 'src/bridge/README.md', 'src/sidecar/README.md', 'skills/ROADMAP.md'):
        assert 'command-set.mdx' in (ROOT/name).read_text(), name
    bridge = (ROOT/'src/bridge/README.md').read_text()
    assert 'it never saves' not in bridge
    assert 'script.native.v1' in bridge and 'verified Save' in bridge
    contributor = (ROOT/'CODEX.md').read_text()
    assert 'Core budgets:' not in contributor and 'seven MCP tools' not in contributor
    assert 'script.native.v1' in contributor and 'eighteen' in contributor


def test_protocol_and_bridge_import_boundaries_replace_line_limits():
    for component, forbidden in (
        ('protocol', {'fastmcp', 'mcp', 'glyphs_mcp_bridge', 'glyphs_mcp_sidecar'}),
        ('bridge', {'fastmcp', 'mcp', 'glyphs_mcp_sidecar'}),
    ):
        for path in (ROOT/'src'/component/f'glyphs_mcp_{component}').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                    [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                assert not {name.split('.')[0] for name in names} & forbidden, path


def test_managed_package_parity_excludes_local_routing():
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    names = {item['name'] for item in manifest['managedSkills']}
    assert 'glyphs-mcp-server-maintenance' not in names
    mirror = ROOT/'plugins/glyphs-mcp/skills'
    for name in names:
        def files(base):
            return {str(p.relative_to(base)): p.read_bytes() for p in base.rglob('*')
                    if p.is_file() and not any(part in {'__pycache__', '.DS_Store'} for part in p.parts)
                    and p.suffix not in {'.pyc', '.pyo'}}
        assert files(ROOT/'skills'/name) == files(mirror/name)
    assert not any(p.name in {'AGENTS.md', 'AGENTS.override.md', '.codex-local'} for p in mirror.rglob('*'))
