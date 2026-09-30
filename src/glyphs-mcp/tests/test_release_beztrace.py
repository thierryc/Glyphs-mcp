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
    root = app / 'Contents/Resources/Beztrace/beztrace-0.1.1-dev.4'
    engine = root / 'bin/beztrace'
    engine.parent.mkdir(parents=True)
    engine.write_bytes(b'unsigned fixture')
    engine.chmod(0o755)
    manifest = {'version': '0.1.1-dev.4', 'architectures': ['arm64', 'x86_64'],
                'sourceRevision': 'fixture-source',
                'files': {'bin/beztrace': hashlib.sha256(engine.read_bytes()).hexdigest()}}
    (root / 'development-engine.json').write_text(json.dumps(manifest))
    (root / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in [root / 'development-engine.json'])
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
    manifest = json.loads((root / 'development-engine.json').read_text())
    assert manifest['sourceRevision'] == 'fixture-source'
    assert manifest['files']['bin/beztrace'] == result['engineSHA256']
    assert manifest['developerIDSigning'] == 'signed-in-glyphs-mcp-release'
    assert signer.verify(app) == result
    assert verified == [engine, engine]


@pytest.mark.parametrize('failure', ['modified', 'extra', 'not_executable', 'wrong_architecture'])
def test_distribution_validation_rejects_invalid_engine(engine_bundle, monkeypatch, failure):
    app, root, engine = engine_bundle
    if failure == 'modified':
        engine.write_bytes(b'changed')
    elif failure == 'extra':
        (root / 'unexpected').write_bytes(b'extra')
    elif failure == 'not_executable':
        engine.chmod(0o644)
    else:
        monkeypatch.setattr(verifier.subprocess, 'check_output', lambda *args, **kwargs: 'arm64')
    with pytest.raises(ValueError, match='Embedded beztrace'):
        verifier.validate_embedded_beztrace(app)


def test_unsigned_release_engine_is_rejected(engine_bundle, monkeypatch):
    app, _, _ = engine_bundle
    def reject(path, identity):
        raise ValueError('Missing Developer ID signature')
    monkeypatch.setattr(signer, 'verify_code', reject)
    with pytest.raises(ValueError, match='Developer ID'):
        signer.verify(app)
