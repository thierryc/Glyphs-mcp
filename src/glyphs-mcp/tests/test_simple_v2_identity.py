"""Packaged release identity, cache semantics, and unavailable evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
for path in ('scripts', 'src/protocol', 'src/sidecar', 'src/bridge'):
    sys.path.insert(0, str(ROOT / path))
from build_simple_v2 import build, _identity
from desktop_release_identity import load
from glyphs_mcp_protocol.identity import component_identity, payload_hash
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.service import SidecarService, JOB_KINDS


def test_packaged_runtime_matches_manifest_then_keeps_initialization_fingerprint(tmp_path):
    target = tmp_path / 'candidate'
    manifest = build(target)
    release = {key: load(ROOT)[key] for key in ('version', 'releaseVersion', 'channel', 'betaNumber', 'installerBuild')}
    assert manifest['release'] == release
    assert manifest['version'] == release['version']
    assert manifest['protocol'] == 1
    for component, root, package, import_root in (
        ('sidecar', target/'sidecar', 'glyphs_mcp_sidecar', target/'sidecar'),
        ('bridge', target/manifest['bridge']['bundle'], 'glyphs_mcp_bridge', target/manifest['bridge']['bundle']/'Contents/Resources'),
    ):
        assert manifest[component]['codeHash'] == payload_hash(root) == _identity(root)
        metadata = component_identity(root)
        assert metadata['release'] == release
        assert metadata['runtimeId'] == release['releaseVersion'] + '+' + metadata['codeHash'][7:19]
        script = '''import json, pathlib
from PACKAGE.identity import IDENTITY
before = dict(IDENTITY)
pathlib.Path(ROOT, 'changed-code.py').write_text('# changed after module initialization\\n')
from PACKAGE.identity import IDENTITY as after
from glyphs_mcp_protocol.identity import component_identity
print(json.dumps([before, after, component_identity(ROOT)]))
'''.replace('PACKAGE', package).replace('ROOT', repr(str(root)))
        output = subprocess.check_output([sys.executable, '-B', '-c', script], env={**os.environ, 'PYTHONPATH':str(import_root)}, text=True)
        before, after, reloaded = json.loads(output)
        assert before == after == metadata
        assert reloaded['codeHash'] != before['codeHash']
        release_file = (
            root/'Contents/Resources/glyphs-mcp-release.json'
            if component == 'bridge'
            else root/'glyphs-mcp-release.json'
        )
        assert 'codeHash' not in json.loads(release_file.read_text())
        if component == 'bridge':
            assert not (root/'glyphs-mcp-release.json').exists()


def test_fingerprint_ignores_location_timestamps_and_generated_caches(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    for root in (a,b):
        root.mkdir(); (root/'file.py').write_text('hello')
    os.utime(a/'file.py', (0, 0))
    assert payload_hash(a) == payload_hash(b)
    (a/'__pycache__').mkdir(); (a/'__pycache__/file.pyc').write_bytes(b'cache')
    (a/'file.pyo').write_bytes(b'cache'); (a/'.DS_Store').write_bytes(b'cache')
    assert payload_hash(a) == payload_hash(b)
    (a/'renamed.py').write_text('hello')
    assert payload_hash(a) != payload_hash(b)
    (b/'link').symlink_to(a/'file.py')
    with pytest.raises(OSError): payload_hash(b)


@pytest.mark.parametrize('metadata', [None, '{}', 'null', 'broken', '{"version": 7}'])
def test_missing_or_invalid_metadata_never_claims_identity(tmp_path, metadata):
    if metadata is not None: (tmp_path/'glyphs-mcp-release.json').write_text(metadata)
    identity = component_identity(tmp_path)
    assert identity['codeHash'] is None and identity['runtimeId'] is None
    assert identity['identityEvidence'] == 'unavailable'


def test_unreadable_payload_retains_only_release_evidence(tmp_path, monkeypatch):
    build(tmp_path/'payload')
    root = tmp_path/'payload/sidecar'
    from glyphs_mcp_protocol import identity
    def unavailable(root): raise PermissionError('unreadable test file')
    monkeypatch.setattr(identity, 'payload_hash', unavailable)
    result = identity.component_identity(root)
    assert result['release']['version'] == load(ROOT)['version']
    assert result['codeHash'] is None and result['runtimeId'] is None
    assert result['identityEvidence'] == 'unavailable'


def test_status_does_not_rehash_or_read_receipt_or_fonts(tmp_path, monkeypatch):
    service = SidecarService(SimpleNamespace(status=lambda: {'protocol':1}), jobs=JobStore(tmp_path),
                             worker=SimpleNamespace(status=lambda: {'available':True}))
    def forbidden(*args, **kwargs): raise AssertionError('unexpected identity IO')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr('glyphs_mcp_protocol.identity.payload_hash', forbidden)
    status = service.get_status()
    assert status['interface'] == 'glyphs-mcp-sidecar' and status['interfaceVersion'] == 1
    assert status['jobKinds'] == list(JOB_KINDS)
    assert len(status['tools']) == 12 and status['protocol'] == 1
    assert status['workflowCapabilities'] == ['edit.workflow.v1']
    assert status['codeHash'] is None  # unpackaged source cannot claim a release


def test_outline_job_is_advertised_only_with_matching_bridge_capability(tmp_path):
    bridge = SimpleNamespace(status=lambda: {'protocol': 1, 'writeCapabilities': ['outline.edit.v1']})
    service = SidecarService(bridge, jobs=JobStore(tmp_path),
                             worker=SimpleNamespace(status=lambda: {'available': True}))
    status = service.get_status()
    assert status['writeCapabilities'] == ['outline.edit.v1']
    assert status['jobKinds'] == [*JOB_KINDS, 'outline_edit']
    bridge.status = lambda: {'protocol': 1, 'writeCapabilities': [
        'outline.edit.v1', 'outline.remove-node.v1']}
    status = service.get_status()
    assert status['writeCapabilities'] == ['outline.edit.v1', 'outline.remove-node.v1']
    assert status['jobKinds'] == [*JOB_KINDS, 'outline_edit']
    bridge.status = lambda: {'protocol': 1}
    status = service.get_status()
    assert status['writeCapabilities'] == [] and status['jobKinds'] == list(JOB_KINDS)


def test_packaged_mcp_initialize_release_and_catalog(tmp_path):
    build(tmp_path/'payload')
    script = '''import asyncio, json
from fastmcp import Client
from glyphs_mcp_sidecar.server import create_server
from glyphs_mcp_protocol import TOOL_NAMES
async def main():
    async with Client(create_server(None)) as client:
        assert client.initialize_result.serverInfo.version == EXPECTED
        catalog = await client.list_tools()
        assert set(t.name for t in catalog) == set(TOOL_NAMES) and len(catalog) == 12
        read = next(t for t in catalog if t.name == "read_entities")
        assert set(read.inputSchema["properties"]) == {"document_id", "entities", "fields"}
        assert set(read.inputSchema["required"]) == {"document_id", "entities", "fields"}
        assert read.inputSchema["properties"]["document_id"]["type"] == "string"
        assert read.inputSchema["properties"]["entities"]["type"] == "array"
        assert read.inputSchema["properties"]["fields"]["items"]["type"] == "string"
        accept = next(t for t in catalog if t.name == "accept_job")
        assert set(accept.inputSchema["properties"]) == {"job_id", "destination", "include_preview"}
        assert set(accept.inputSchema["required"]) == {"job_id"}
        save = next(t for t in catalog if t.name == "save_document")
        assert set(save.inputSchema["properties"]) == {"document_id", "destination"}
        assert set(save.inputSchema["required"]) == {"document_id"}
        assert "confirm" not in accept.inputSchema["properties"] | save.inputSchema["properties"]
        assert "reason" not in accept.inputSchema["properties"] | save.inputSchema["properties"]
        for text in ("Kerning uses", "exact native master ID", "LTR, RTL or vertical", "fields [value] only", "null means no entry", "Dirty and unsaved", "paths.list.v1", "path.geometry.v1", "fields [items]", "fields [nodes]", "invalid_request"):
            assert text in read.description
asyncio.run(main())
'''.replace('EXPECTED',repr(load(ROOT)['releaseVersion']))
    subprocess.run([sys.executable, '-B', '-c', script], env={**os.environ, 'PYTHONPATH':str(tmp_path/'payload/sidecar')}, check=True)
