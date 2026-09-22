"""Dimensions reference metadata: bounded reads, approvals and exact recovery."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / part))
from glyphs_mcp_protocol import dimensions as d, ProtocolError, validate_patch
from glyphs_mcp_bridge import dimensions as native
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_sidecar import dimensions_job
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.source import source_hash
from test_simple_v2_native_actions import UndoManager


class UserData(dict):
    def __getitem__(self, key): return self.get(key)


class Masters(list):
    def __getitem__(self, key):
        if isinstance(key, str): return next((v for v in self if v.id == key), None)
        return super().__getitem__(key)


@pytest.fixture
def font(monkeypatch, tmp_path):
    manager = UndoManager()
    path = tmp_path / 'font.glyphs'; path.write_text('source')
    value = NS(userData=UserData(), masters=Masters(), glyphs=[], familyName='Dimensions Test',
               filepath=str(path), parent=NS(undoManager=manager, changeCount=0, isDocumentEdited=False))
    value.masters.extend(NS(id=f'm{i}', name=f'Master {i}', font=value) for i in range(2))
    monkeypatch.setattr(native, 'available', lambda: True)
    monkeypatch.setattr(native, 'refresh', lambda font: None)
    return value


def prepared(font, entries):
    return dimensions_job.prepare(font, {'options': {'changes': entries}})


def entry(value=46, key='HV', master='m0'):
    return {'master': master, 'key': key, 'value': value}


def patch(font, changes, adapter, job='dimensions'):
    doc = adapter.list_documents()[0]
    return validate_patch(dict(version=1, jobId=job, documentId=doc['id'], sourcePath=doc['path'],
        sourceHash=source_hash(Path(doc['path'])), generation=doc['generation'], changes=changes, summary='Dimensions'))


@pytest.mark.parametrize('root', [None, {}, {'m0': {}}, {'m1': {'HV': 88}}])
def test_read_does_not_create_metadata_and_reports_absence(root):
    original = copy.deepcopy(root)
    rows = d.read_rows(root, 'm0', editable=True)['items']
    assert root == original
    assert all(not row['present'] and row['value'] is None for row in rows)
    assert {'VThin', 'VThick', 'vThin', 'vThick', 'kanada8', 'khmer7', 'han8'} <= {r['key'] for r in rows}


@pytest.mark.parametrize('value', [0, 46.125, '0', '46.125', '-5.5'])
def test_existing_values_are_not_blank(value):
    row = next(r for r in d.read_rows({'m0': {'HV': value}}, 'm0', editable=True)['items'] if r['key'] == 'HV')
    assert row['present'] and row['value'] == float(value) and row['storedValue'] == value


@pytest.mark.parametrize('value', [True, False, float('nan'), float('inf'), 'nonsense', '', [], {}])
def test_malformed_stored_values_cannot_be_filled(value):
    root = {'m0': {'HV': value}}
    row = next(r for r in d.read_rows(root, 'm0', editable=True)['items'] if r['key'] == 'HV')
    assert row['present'] and not row['valid'] and not row['editable']
    with pytest.raises(ProtocolError, match='malformed'): d.read_state(root, 'm0', 'HV')


@pytest.mark.parametrize('root', [[], False, {'m0': None}, {'m0': []}, {'m0': {'x'*256: 1}}])
def test_malformed_containers_are_not_missing(root):
    with pytest.raises(ProtocolError): d.read_rows(root, 'm0', editable=True)


@pytest.mark.parametrize('value', [True, '46', float('nan'), float('inf'), 10**400])
def test_requests_reject_non_numeric_values(value):
    with pytest.raises(ProtocolError): d.validate_options({'changes': [entry(value)]})


def test_request_bounds_and_exact_targets(font):
    for changes in ([], [entry()]*2, [entry(master=str(i)) for i in range(101)], [entry(key='other')]):
        with pytest.raises(ProtocolError): d.validate_options({'changes': changes})
    with pytest.raises(ProtocolError): prepared(font, [entry(master='missing')])
    with pytest.raises(ProtocolError): d.validate_options({'changes': [{**entry(), 'extra': True}]})


def test_preview_classification_exact_storage_and_complete_approval(font):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': '46', 'HH': 0, 'OV': '50.25'}}
    changes, report = prepared(font, [entry(46), entry(2, 'HH'), entry(None, 'OV'), entry(9, 'OH'), entry(None, 'nV')])
    assert [r['status'] for r in report['targets']] == ['no-op', 'overwrite', 'clear', 'fill', 'no-op']
    assert len(changes) == 3 and len(report['requiredOverwrites']) == 2
    assert changes[1]['before'] == {'present': True, 'value': '50.25'}
    for approved in (None, [], report['requiredOverwrites'][:1], report['requiredOverwrites']*2):
        with pytest.raises(ProtocolError) as exc: d.validate_approval(changes, approved)
        assert exc.value.code == 'overwrite_approval_required'
    assert d.validate_approval(changes, list(reversed(report['requiredOverwrites'])))
    wrong = copy.deepcopy(report['requiredOverwrites']); wrong[0]['after']['value'] = 5
    with pytest.raises(ProtocolError): d.validate_approval(changes, wrong)
    wrong = copy.deepcopy(report['requiredOverwrites']); wrong[1]['before']['value'] = 50.25
    with pytest.raises(ProtocolError): d.validate_approval(changes, wrong)


@pytest.mark.parametrize('initial', [None, {}, {'m0': {}}, {'m0': {'unknown': {'preserve': [1, 2]}}, 'm1': {'HV': '77'}}])
def test_native_undo_redo_and_discard_preserve_exact_absence(font, initial):
    if initial is not None: font.userData[d.STORAGE_KEY] = copy.deepcopy(initial)
    baseline = copy.deepcopy(font.userData)
    font.userData['unrelated'] = 'keep'
    baseline['unrelated'] = 'keep'
    changes, _ = prepared(font, [entry(46.25), entry(5, 'HH'), entry(10, master='m1')])
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    result = core.begin_apply(patch(font, changes, adapter), approved_overwrites=d.approval_entries(changes))
    assert result['status'] == 'applied' and result['error'] is None
    after = copy.deepcopy(font.userData)
    assert after[d.STORAGE_KEY]['m0']['HV'] == 46.25
    manager = font.parent.undoManager
    manager.undo(); assert font.userData == baseline
    manager.redo(); assert font.userData == after
    assert core.discard('dimensions')['status'] == 'discarded'
    assert font.userData == baseline


def test_overwrite_approval_enforced_at_native_boundary(font):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': '46'}}
    changes, report = prepared(font, [entry(55)])
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    p = patch(font, changes, adapter)
    with pytest.raises(BridgeError) as exc: core.begin_apply(p)
    assert exc.value.code == 'overwrite_approval_required'
    assert font.userData[d.STORAGE_KEY]['m0']['HV'] == '46'
    assert core.begin_apply(p, approved_overwrites=report['requiredOverwrites'])['status'] == 'applied'
    assert core.discard('dimensions')['status'] == 'discarded'
    assert font.userData[d.STORAGE_KEY]['m0']['HV'] == '46'


def test_newly_populated_field_is_never_overwritten(font):
    changes, _ = prepared(font, [entry()])
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    p = patch(font, changes, adapter)
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': 999}}
    result = core.begin_apply(p)
    assert result['status'] == 'failed' and result['error']['code'] == 'target_conflict'
    assert font.userData[d.STORAGE_KEY]['m0']['HV'] == 999


def test_mid_batch_failure_rolls_back_all_changes(font, monkeypatch):
    changes, _ = prepared(font, [entry(), entry(50, 'HH')])
    original = native.write_exact
    def fail_once(owner, target, wanted):
        original(owner, target, wanted)
        if target['key'] == 'HH' and wanted['present']: raise ValueError('after setter failure')
    monkeypatch.setattr(native, 'write_exact', fail_once)
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    result = core.begin_apply(patch(font, changes, adapter))
    assert result['status'] == 'failed' and not font.userData
    assert result['error']['details']['recovery']['complete']


def test_read_requires_bounded_exact_masters(font):
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    doc = core.list_documents()[0]['id']
    font.parent.isDocumentEdited = True
    assert core.read_entities(doc, [{'kind':'master', 'id':'m0'}], ['dimensions'])[0]['values']['dimensions']['complete']
    assert not font.userData
    for selectors in ([{'kind':'masters'}], [{'kind':'master', 'id':'m0'}]*5):
        with pytest.raises(BridgeError): core.read_entities(doc, selectors, ['dimensions'])


def test_negotiation_and_old_bridge_refusal(font):
    bridge = NS(status=lambda: {'writeCapabilities': []}, documents=lambda: [{'id': 'd', 'path': font.filepath, 'dirty': False, 'generation': 0}])
    service = SidecarService(bridge, worker=NS(status=lambda: {'available': True}))
    assert 'dimensions_edit' not in service.get_status()['jobKinds']
    with pytest.raises(ServiceError) as exc: service.start_job('d', kind='dimensions_edit', options={'changes': [entry()]})
    assert exc.value.code == 'unsupported_job'
    bridge.status = lambda: {'writeCapabilities': [d.WRITE_CAPABILITY], 'readCapabilities': [d.READ_CAPABILITY]}
    assert 'dimensions_edit' in service.get_status()['jobKinds']
    assert d.READ_CAPABILITY in service.get_status()['readCapabilities']


def test_service_approval_blocks_before_bridge_and_retains_for_retry(font, tmp_path):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': 0}}
    changes, report = prepared(font, [entry()])
    adapter = GlyphsAdapter(NS(fonts=[font])); doc = adapter.list_documents()[0]
    calls = []
    def apply(p, **kwargs):
        calls.append((p, kwargs)); return {'jobId': p['jobId'], 'documentId': doc['id'], 'status': 'applying'}
    bridge = NS(documents=lambda: [doc], apply=apply, operation=lambda job: {'status': 'applied'})
    jobs = JobStore(tmp_path / 'jobs'); service = SidecarService(bridge, jobs=jobs)
    job = jobs.create(doc, {'kind': 'dimensions_edit'})
    p = patch(font, changes, adapter, job['id'])
    jobs.write_json(job['id'], 'patch.json', p)
    jobs.update(job['id'], status='ready', sourceHash=p['sourceHash'])
    with pytest.raises(ServiceError) as exc: service.apply_job(job['id'])
    assert exc.value.code == 'overwrite_approval_required' and not calls
    service.apply_job(job['id'], approved_overwrites=report['requiredOverwrites'])
    assert jobs.get(job['id'])['overwriteApproval'] == report['requiredOverwrites']
    assert service.apply_job(job['id'])['status'] == 'applied' and len(calls) == 1


def test_unknown_fields_are_read_only_and_not_clobbered():
    root = {'m0': {'future': 12}}
    row = next(v for v in d.read_rows(root, 'm0', editable=True)['items'] if v['key'] == 'future')
    assert row['present'] and not row['editable'] and row['label'] is None
    assert d.replace(root, 'm0', 'HV', {'present': True, 'value': 46}, {'root': True, 'master': True})['m0']['future'] == 12


def test_rounding_does_not_hide_a_required_overwrite(font):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': '46.00000000000000001'}}
    changes, report = prepared(font, [entry(46)])
    assert report['targets'][0]['status'] == 'overwrite'
    assert report['requiredOverwrites'][0]['before']['value'] == '46.00000000000000001'
    with pytest.raises(ProtocolError): d.validate_approval(changes, None)


def test_declining_an_overwrite_allows_a_reduced_fill_job(font):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': 0}}
    mixed, report = prepared(font, [entry(46), entry(22, 'HH')])
    with pytest.raises(ProtocolError): d.validate_approval(mixed, None)
    reduced, _ = prepared(font, [entry(22, 'HH')])
    assert d.validate_approval(reduced, None) == []
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    assert core.begin_apply(patch(font, reduced, adapter))['status'] == 'applied'
    assert font.userData[d.STORAGE_KEY]['m0'] == {'HV': 0, 'HH': 22}


def test_cancelling_partial_application_restores_absent_metadata(font):
    changes, _ = prepared(font, [entry(), entry(50, 'HH')])
    pending = []
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, pending.append, chunk_limit=1)
    assert core.begin_apply(patch(font, changes, adapter))['status'] == 'applying'
    pending.pop(0)()
    assert font.userData[d.STORAGE_KEY]['m0']['HV'] == 46
    core.discard('dimensions')
    while pending: pending.pop(0)()
    result = core.operation('dimensions')
    assert result['status'] == 'cancelled' and result['error']['details']['recovery']['complete']
    assert not font.userData


@pytest.mark.parametrize('changed', ['source', 'generation', 'dirty', 'master'])
def test_stale_preparations_cannot_apply_even_with_approval(font, tmp_path, changed):
    font.userData[d.STORAGE_KEY] = {'m0': {'HV': '46'}}
    changes, report = prepared(font, [entry(55)])
    adapter = GlyphsAdapter(NS(fonts=[font])); core = BridgeCore(adapter, lambda cb: cb())
    doc = adapter.list_documents()[0]
    bridge = NS(documents=lambda: [doc], apply=core.begin_apply)
    jobs = JobStore(tmp_path / 'jobs'); service = SidecarService(bridge, jobs=jobs)
    job = jobs.create(doc, {'kind': 'dimensions_edit'})
    p = patch(font, changes, adapter, job['id'])
    jobs.write_json(job['id'], 'patch.json', p)
    jobs.update(job['id'], status='ready', sourceHash=p['sourceHash'])
    if changed == 'source': Path(font.filepath).write_text('changed source')
    elif changed == 'generation': doc = {**doc, 'generation': doc['generation'] + 1}
    elif changed == 'dirty': doc = {**doc, 'dirty': True}
    else: font.masters.pop(0)
    if changed == 'master':
        service.apply_job(job['id'], approved_overwrites=report['requiredOverwrites'])
        assert core.operation(job['id'])['status'] == 'failed'
    else:
        with pytest.raises(ServiceError) as exc:
            service.apply_job(job['id'], approved_overwrites=report['requiredOverwrites'])
        assert exc.value.code == {'source': 'stale_source', 'generation': 'stale_document', 'dirty': 'document_not_clean'}[changed]
    assert font.userData[d.STORAGE_KEY]['m0']['HV'] == '46'


def test_interrupted_dimensions_job_is_not_replayed(font, tmp_path):
    from glyphs_mcp_sidecar.bridge_client import BridgeClientError
    doc = GlyphsAdapter(NS(fonts=[font])).list_documents()[0]
    jobs = JobStore(tmp_path / 'jobs')
    job = jobs.create(doc, {'kind': 'dimensions_edit'})
    jobs.update(job['id'], status='applying', overwriteApproval=[],
                bridgeOperation={'jobId': job['id'], 'documentId': doc['id']})
    def missing(job_id): raise BridgeClientError('job_not_found', 'native history lost')
    service = SidecarService(NS(operation=missing), jobs=jobs)
    assert service.get_job(job['id'])['status'] == 'interrupted'
    with pytest.raises(ServiceError) as exc: service.apply_job(job['id'])
    assert exc.value.code == 'bridge_operation_lost' and not font.userData
