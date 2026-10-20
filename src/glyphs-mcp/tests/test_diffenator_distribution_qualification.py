"""Qualification failures retain evidence and never change a working installation."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import qualify_diffenator_distribution as qualification


def test_changed_candidate_is_rejected_before_extraction_and_retains_evidence(tmp_path, monkeypatch):
    archive = tmp_path / 'candidate.zip'; archive.write_bytes(b'changed')
    release = tmp_path / 'release.json'
    release.write_text(json.dumps(dict(sourceRevision='pinned', archiveSHA256='a' * 64, archiveSize=7)))
    monkeypatch.setattr(qualification.installer, 'extract', lambda *args: pytest.fail('Unverified bytes reached extraction'))
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='identity differs'):
        qualification.qualify(archive, release, output, 'all')
    record = json.loads((output / 'qualification.json').read_text())
    assert not record['passed']
    assert record['archiveSHA256'] == hashlib.sha256(b'changed').hexdigest()
    assert record['workingInstallationChanged'] is False
    assert record['error']['type'] == 'ValueError'


def test_invalid_inventory_blocks_execution_and_records_failure(tmp_path, monkeypatch):
    archive = tmp_path / 'candidate.zip'; archive.write_bytes(b'archive')
    release = tmp_path / 'release.json'
    release.write_text(json.dumps(dict(sourceRevision='pinned', archiveSHA256=hashlib.sha256(b'archive').hexdigest(),
                                      archiveSize=7, files={})))
    def invalid(*args): raise ValueError('Archive contains an unlisted file')
    monkeypatch.setattr(qualification.installer, 'extract', invalid)
    monkeypatch.setattr(qualification.subprocess, 'run', lambda *args, **kwargs: pytest.fail('Invalid inventory reached execution'))
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='unlisted'):
        qualification.qualify(archive, release, output, 'all')
    assert not json.loads((output / 'qualification.json').read_text())['passed']


def test_existing_evidence_is_never_overwritten(tmp_path):
    output = tmp_path / 'result'; output.mkdir()
    evidence = output / 'qualification.json'; evidence.write_text('retained')
    with pytest.raises(FileExistsError):
        qualification.qualify(tmp_path / 'missing', tmp_path / 'missing', output, 'all')
    assert evidence.read_text() == 'retained'
