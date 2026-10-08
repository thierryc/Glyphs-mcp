"""Compiled comparisons must remain independent of live font operations."""
from pathlib import Path
import json
import sys
import time
from threading import Event
import pytest
ROOT = Path(__file__).resolve().parents[3]
for folder in ('protocol', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / folder))
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.font_comparison import ComparisonError, ComparisonWorker, run_process
from glyphs_mcp_protocol.font_comparison import validate_manifest, CAPABILITY


def font(path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', 'A'])
    builder.setupCharacterMap({65: 'A'})
    pen = TTGlyphPen(None)
    builder.setupGlyf({'.notdef': pen.glyph(), 'A': pen.glyph()})
    builder.setupHorizontalMetrics({'.notdef': (500, 0), 'A': (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(dict(familyName='Fixture', styleName='Regular', uniqueFontIdentifier='Fixture', fullName='Fixture Regular', psName='Fixture-Regular'))
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


class DisconnectedBridge:
    def __getattr__(self, name):
        raise AssertionError('Comparison must not access the Glyphs bridge: ' + name)


class ReportWorker:
    def status(self): return dict(available=True, jobCapabilities=[CAPABILITY])
    def run(self, root, request, cancel):
        out = Path(request['output']); out.mkdir()
        (out / 'diffenator2-report.html').write_text('<p>Fixture comparison</p>')
        assert request['baseline'][0] != request['candidate'][0]
        assert Path(request['baseline'][0]).read_bytes() == Path(request['candidate'][0]).read_bytes()
        return dict(sourceRevision='fixture', architecture='fixture')


@pytest.fixture
def service(tmp_path):
    source = tmp_path / 'font.ttf'; font(source)
    return SidecarService(DisconnectedBridge(), jobs=JobStore(tmp_path / 'jobs'), worker=object(), comparison_worker=ReportWorker()), source


def wait(service, identity):
    for _ in range(300):
        job = service.get_job(identity)
        if job['status'] not in ('preparing', 'cancelling'): return job
        time.sleep(.01)
    pytest.fail('Comparison did not finish')


def test_compare_and_publish_without_live_document(service, tmp_path):
    service, source = service
    job = service.compare_fonts([str(source)], [str(source)])
    ready = wait(service, job['id'])
    assert ready['status'] == 'ready', ready
    assert ready['inputKind'] == 'compiled_fonts'
    assert Path(ready['entryPoint']).is_file()
    assert ready['manifest']['entryPoint'] == 'diffenator2-report.html'
    with pytest.raises(ServiceError, match='does not produce a live document mutation'):
        service.apply_job(job['id'])
    # Inputs are immutable snapshots: later source changes do not change the report.
    source.write_bytes(b'later edit')
    destination = tmp_path / 'review'
    accepted = service.accept_job(job['id'], destination=str(destination))
    assert accepted['status'] == 'accepted'
    assert accepted['receipt']['verification'] == 'staged_report_and_compiled_input_hashes'
    assert Path(accepted['entryPoint']).is_file()
    assert service.accept_job(job['id'], destination=str(destination))['receipt'] == accepted['receipt']
    with pytest.raises(ServiceError, match='another destination'):
        service.accept_job(job['id'], destination=str(tmp_path / 'other'))


def test_existing_destination_and_changed_report_are_rejected(service, tmp_path):
    service, source = service
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    ready = wait(service, identity)
    destination = tmp_path / 'existing'; destination.mkdir()
    with pytest.raises(ServiceError, match='already exists'):
        service.accept_job(identity, destination=str(destination))
    Path(ready['entryPoint']).write_text('tampered')
    with pytest.raises(ServiceError, match='changed'):
        service.accept_job(identity, destination=str(tmp_path / 'new'))


@pytest.mark.parametrize('options', [{'styles': 'all'}, {'extra': 1}, {'filterStyles': '['}, {'userWordlist': 'relative.txt'}])
def test_rejects_invalid_options_before_registration(service, options):
    service, source = service
    with pytest.raises(ServiceError): service.compare_fonts([str(source)], [str(source)], options)
    assert service.jobs.records() == []


def test_malformed_font_fails_and_discards_staging(service, tmp_path):
    service, _ = service
    source = tmp_path / 'invalid.ttf'; source.write_bytes(b'not a font')
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    job = wait(service, identity)
    assert job['status'] == 'failed'
    assert job['error']['code'] == 'invalid_font'
    assert [p.name for p in service.jobs.path(identity).iterdir()] == ['state.json']


def test_discard_and_reopen_job_store(service):
    service, source = service
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    assert wait(service, identity)['status'] == 'ready'
    service.discard_job(identity)
    recovered = JobStore(service.jobs.root)
    assert recovered.get(identity)['status'] == 'discarded'
    assert recovered.select({'discarded'}, document_id='a-live-document') == []


def test_missing_optional_runtime_is_actionable(tmp_path):
    worker = ComparisonWorker(tmp_path / 'missing')
    assert worker.status()['available'] is False
    assert 'Setup' in worker.status()['error']['message']


def test_cancellation_terminates_subprocess(tmp_path):
    import threading
    cancel = Event()
    threading.Timer(.1, cancel.set).start()
    start = time.monotonic()
    with pytest.raises(ComparisonError, match='cancelled'):
        run_process([sys.executable, '-c', 'import time;time.sleep(30)'], tmp_path, {}, cancel)
    assert time.monotonic() - start < 2


def test_publication_reconciles_without_bridge(service, tmp_path, monkeypatch):
    from glyphs_mcp_sidecar import comparison_publication
    service, source = service
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    wait(service, identity)
    original = service.jobs.write_json
    def interrupted(job, name, value):
        if name == 'receipt.json': raise OSError('lost receipt write')
        return original(job, name, value)
    monkeypatch.setattr(service.jobs, 'write_json', interrupted)
    with pytest.raises(ServiceError): service.accept_job(identity, destination=str(tmp_path / 'published'))
    monkeypatch.setattr(service.jobs, 'write_json', original)
    reopened = SidecarService(DisconnectedBridge(), jobs=JobStore(service.jobs.root), worker=object(), comparison_worker=ReportWorker())
    assert reopened.get_job(identity)['status'] == 'accepted'


def test_comparison_manifest_does_not_relax_export_rules(service):
    from glyphs_mcp_protocol import validate_artifact_manifest
    service, source = service
    ready = wait(service, service.compare_fonts([str(source)], [str(source)])['id'])
    assert validate_manifest(ready['manifest']) == ready['manifest']
    with pytest.raises(ValueError): validate_artifact_manifest(ready['manifest'])


def test_changed_snapshot_is_rejected_before_publication(service, tmp_path):
    service, source = service
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    wait(service, identity)
    (service.jobs.path(identity) / 'baseline-0.ttf').write_bytes(b'changed snapshot')
    with pytest.raises(ServiceError, match='snapshot changed'):
        service.accept_job(identity, destination=str(tmp_path / 'report'))
    assert not (tmp_path / 'report').exists()


def test_comparison_adapter_has_valid_python_syntax():
    import ast
    ast.parse((ROOT / 'src/sidecar/glyphs_mcp_sidecar/diffenator_adapter.py').read_text())


def test_comparison_does_not_break_close_guards_for_live_documents(service):
    from glyphs_mcp_sidecar.document_closing import guard
    service, source = service
    identity = service.compare_fonts([str(source)], [str(source)])['id']
    wait(service, identity)
    document = dict(id='live-document', path='/explicit/font.glyphs')
    guard(service, document, ServiceError)
    live = service.jobs.create(document, dict(kind='width_delta', delta=10, glyphs=['A']))
    service.jobs.update(live['id'], status='applied')
    with pytest.raises(ServiceError, match='pending MCP job'):
        guard(service, document, ServiceError)
