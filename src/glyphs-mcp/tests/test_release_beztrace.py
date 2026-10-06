"""The bundled engine must retain a verified inventory after release signing."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
import sign_embedded_beztrace as signer
import verify_desktop_app as verifier


@pytest.fixture
def engine_bundle(tmp_path, monkeypatch):
    app = tmp_path / 'Glyphs MCP.app'
    root = app / 'Contents/Resources' / verifier.BEZTRACE_DIRECTORY
    engine = root / 'bin/beztrace'
    engine.parent.mkdir(parents=True)
    engine.write_bytes(b'unsigned fixture')
    engine.chmod(0o755)
    upstream = {'version': '0.1.1', 'sourceRevision': 'fixture-source',
                'architectures': ['arm64', 'x86_64'], 'minimumMacOS': '13.0',
                'artifacts': [{'path': 'beztrace-0.1.1-macos-universal.zip', 'sha256': 'fixture-archive'}]}
    upstream_path = root / 'upstream-release-manifest.json'
    upstream_path.write_text(json.dumps(upstream))
    original_hash = hashlib.sha256(engine.read_bytes()).hexdigest()
    upstream_hash = hashlib.sha256(upstream_path.read_bytes()).hexdigest()
    manifest = {'version': '0.1.1', 'architectures': ['arm64', 'x86_64'],
                'minimumMacOS': '13.0', 'schemaVersion': 1, 'pathDataVersion': 2,
                'sourceRevision': 'fixture-source',
                'upstreamRelease': {'manifestSHA256': upstream_hash,
                                    'archiveSHA256': 'fixture-archive',
                                    'executableSHA256': original_hash},
                'files': {'bin/beztrace': original_hash,
                          'upstream-release-manifest.json': upstream_hash}}
    (root / verifier.BEZTRACE_MANIFEST).write_text(json.dumps(manifest))
    (root / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in [root / verifier.BEZTRACE_MANIFEST, upstream_path])
        + hashlib.sha256(engine.read_bytes()).hexdigest() + '  bin/beztrace\n')
    monkeypatch.setattr(verifier.subprocess, 'check_output', lambda *args, **kwargs: 'arm64 x86_64')
    return app, root, engine


def test_signed_copy_refreshes_checksums_without_touching_source_provenance(engine_bundle, monkeypatch):
    app, root, engine = engine_bundle
    monkeypatch.setattr(signer, 'run', lambda *args: engine.write_bytes(b'signed fixture'))
    verified = []
    monkeypatch.setattr(signer, 'verify_code', lambda path, identity: verified.append(path))
    result = signer.sign(app)
    assert verified == [engine]
    manifest = json.loads((root / verifier.BEZTRACE_MANIFEST).read_text())
    assert manifest['sourceRevision'] == 'fixture-source'
    assert manifest['files']['bin/beztrace'] == result['engineSHA256']
    assert manifest['developerIDSigning'] == 'signed-in-glyphs-mcp-release'
    assert manifest['upstreamRelease']['executableSHA256'] == hashlib.sha256(b'unsigned fixture').hexdigest()
    assert manifest['upstreamRelease']['manifestSHA256'] == hashlib.sha256((root / 'upstream-release-manifest.json').read_bytes()).hexdigest()
    assert signer.verify(app) == result
    assert verified == [engine, engine]


@pytest.mark.parametrize('failure', ['modified', 'extra', 'not_executable', 'wrong_architecture',
                                   'duplicate_checksum', 'symlink', 'contract', 'provenance'])
def test_distribution_validation_rejects_invalid_engine(engine_bundle, monkeypatch, failure):
    app, root, engine = engine_bundle
    if failure == 'modified':
        engine.write_bytes(b'changed')
    elif failure == 'extra':
        (root / 'unexpected').write_bytes(b'extra')
    elif failure == 'not_executable':
        engine.chmod(0o644)
    elif failure == 'wrong_architecture':
        monkeypatch.setattr(verifier.subprocess, 'check_output', lambda *args, **kwargs: 'arm64')
    elif failure == 'duplicate_checksum':
        checksums = root / 'SHA256SUMS'
        checksums.write_text(checksums.read_text() + checksums.read_text().splitlines()[0] + '\n')
    elif failure == 'symlink':
        (root / 'link').symlink_to(engine)
    else:
        path = root / verifier.BEZTRACE_MANIFEST
        manifest = json.loads(path.read_text())
        if failure == 'contract':
            manifest['pathDataVersion'] = 3
        else:
            manifest['upstreamRelease']['archiveSHA256'] = 'wrong-archive'
        path.write_text(json.dumps(manifest))
        checksums = root / 'SHA256SUMS'
        lines = [line for line in checksums.read_text().splitlines()
                 if not line.endswith('  ' + verifier.BEZTRACE_MANIFEST)]
        checksums.write_text('\n'.join(lines) + '\n' + hashlib.sha256(path.read_bytes()).hexdigest()
                             + '  ' + verifier.BEZTRACE_MANIFEST + '\n')
    with pytest.raises(ValueError, match='Embedded beztrace'):
        verifier.validate_embedded_beztrace(app)


def test_unsigned_release_engine_is_rejected(engine_bundle, monkeypatch):
    app, _, _ = engine_bundle
    def reject(path, identity):
        raise ValueError('Missing Developer ID signature')
    monkeypatch.setattr(signer, 'verify_code', reject)
    with pytest.raises(ValueError, match='Developer ID'):
        signer.verify(app)
