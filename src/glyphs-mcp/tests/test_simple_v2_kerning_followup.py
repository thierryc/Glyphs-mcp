"""P10 boundaries: existing native history, exact errors, optional projections."""
from copy import deepcopy
import json
from threading import Event
from unittest.mock import Mock
import pytest
from test_simple_v2_kerning import Font, GlyphsAdapter, NS, kerning_job, native_worker
from test_simple_v2_exact_history import History
from test_simple_v2_sidecar import service, wait_for
from glyphs_mcp_sidecar.worker import GlyphsCliWorker, WorkerError, WORKER_ERROR_PREFIX
from glyphs_mcp_sidecar.service import SidecarService

@pytest.mark.parametrize('before',[None,0.0,-90.125])
def test_kerning_uses_left_glyph_history_with_exact_presence_and_existing_group(before):
    f=Font(before);history=History();f.glyphs['A'].layers['M1'].undoManager=lambda:history
    a=GlyphsAdapter(NS(fonts=[f]));doc=a.list_documents()[0]['id'];baseline=dict(f.store)
    change=dict(kind='kerning',master='M1',left='A',right='V',direction='LTR',before=before,after=-74.625)
    a.begin_undo(doc);a.apply_change(doc,change);a.end_undo(doc,'Kerning')
    assert history.events==['begin','Kerning','end']
    history.undo();assert f.store==baseline
    history.undo();assert f.kerningForPair('M1','A','V')==-74.625
    assert all(f.store[k]==v for k,v in baseline.items() if k!=('M1',0,'A','V'))
    history.undo();assert f.store==baseline

@pytest.mark.parametrize('options,missing',[
    ({'pairs':[['A','missing.two'],['missing.one','V']]},['missing.one','missing.two']),
    ({'pairs':[['A','V']],'masters':['M1','missing-master']},['missing-master']),
])
def test_missing_targets_named_before_any_detached_setter(options,missing):
    f=Font();f.setKerningForPair=Mock(side_effect=AssertionError('must not prepare any edit'))
    with pytest.raises(WorkerError) as error:kerning_job.prepare(f,{'options':options})
    assert json.dumps(missing) in str(error.value)
    assert 'Keep the document ID' in str(error.value)
    f.setKerningForPair.assert_not_called()

def test_expected_native_failure_emits_only_structured_message(tmp_path,monkeypatch,capsys):
    p=tmp_path/'request.json';p.write_text(json.dumps({'output':str(tmp_path/'patch.json')}))
    def fail(payload):raise WorkerError('Missing exact glyph "A.missing"')
    monkeypatch.setattr(native_worker,'build_patch',fail)
    assert native_worker.main([str(p)])==1
    output=capsys.readouterr();assert 'Traceback' not in output.err
    assert json.loads(output.err.removeprefix(WORKER_ERROR_PREFIX))=='Missing exact glyph "A.missing"'
    assert not (tmp_path/'patch.json').exists()

def test_parent_worker_preserves_exact_error_over_process_noise(tmp_path,monkeypatch):
    import glyphs_mcp_sidecar.worker as module
    worker=GlyphsCliWorker(executable='/bin/true',app='/Applications/Glyphs 4.app')
    monkeypatch.setattr(worker,'executable',lambda:'/test/glyphs')
    process=Mock(returncode=1,pid=123)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    message='Kerning glyphs missing: ["A.missing"]'
    monkeypatch.setattr(worker,'_communicate',lambda *a:('native startup noise',WORKER_ERROR_PREFIX+json.dumps(message)+'\nwrapper noise'))
    with pytest.raises(WorkerError,match='A.missing') as e:worker.prepare(tmp_path,{}, {},tmp_path/'font.glyphs','hash',Event())
    assert str(e.value)==message

def test_optional_projection_preserves_metadata_errors_and_stored_preview(tmp_path):
    value,bridge,_=service(tmp_path)
    try:
        job=value.start_job('doc_1',kind='width_delta',delta=8);wait_for(value,job['id'],'ready')
        report=dict(path='/tmp/report.json',sample=[{'evidence':'full row'}],claim='bounded',pairCount=3,unavailableCount=1)
        value.jobs.update(job['id'],report=report)
        original=value.get_job(job['id']);compact=value.get_job(job['id'],include_preview=False)
        expected=deepcopy(original);expected.pop('sample');expected['report'].pop('sample');expected['previewIncluded']=False
        assert compact==expected
        assert value.get_job(job['id'])==original
        for result in (value.apply_job(job['id'],include_preview=False),value.apply_job(job['id'],include_preview=False),value.discard_job(job['id'],include_preview=False),value.get_job(job['id'],include_preview=False),value.discard_job(job['id'],include_preview=False)):
            assert result['previewIncluded'] is False and 'sample' not in result and 'sample' not in result['report']
            assert all(k in result for k in ('error','activity','bridgeOperation','changeCount'))
        assert value.get_job(job['id'])['report']['sample']==report['sample']
    finally:value.close()

def test_projection_of_failed_job_does_not_hide_error():
    job=dict(id='job',createdAt=0,status='failed',error=dict(code='job_failed',message='missing glyph'),sample=[],report=None,document={'id':'doc','path':'/tmp/font.glyphs'},request={'kind':'kerning_collision'})
    assert SidecarService._public(job,include_preview=False)['error']==job['error']
