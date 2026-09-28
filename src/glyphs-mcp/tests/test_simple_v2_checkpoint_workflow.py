"""Checkpoint integration uses real Git and the existing native workflow test adapter."""
import json
import subprocess
import pytest
from test_simple_v2_edit_workflow import env, start, choose, wait
from test_simple_v2_checkpoints import git


@pytest.fixture
def project(env):
    service,bridge,worker,font=env
    root=font.parent
    git(root,'init','-b','main');git(root,'config','user.name','Test')
    git(root,'config','user.email','test@example.invalid')
    (root/'.glyphs-mcp.json').write_text(json.dumps({'schemaVersion':1,'gitCheckpoints':{'enabled':True}}))
    git(root,'add',font.name);git(root,'commit','-m','Initial')
    return env


def test_baseline_and_result_save_are_separate_and_idempotent(project):
    service,bridge,_,font=project
    font.write_text('601');bridge.adapter.value=601
    value=wait(service,start(project),'applied')
    assert bridge.adapter.save_calls==[]
    assert git(font.parent,'show','HEAD:'+font.name)==b'601'
    baseline=service.jobs.get(value['jobId'])['checkpointBaseline']['revision']
    original=value
    value=wait(service,choose(service,value,'save_result'),'saved')
    receipt=value['receipt'];assert receipt['checkpoint']['status']=='created'
    assert len(bridge.adapter.save_calls)==1
    choose(service,original,'save_result')
    assert len(bridge.adapter.save_calls)==1
    action=json.loads(git(font.parent,'show',receipt['checkpoint']['revision']+':'+receipt['checkpoint']['recordPath']))
    assert action['actions'][0]['baselineRevision']==baseline
    assert action['actions'][0]['request']['kind']=='width_delta'
    assert action['actions'][0]['verification']['guardedApplication'] is True
    assert action['manualChanges']=='possible'


def test_git_failure_after_save_retries_only_checkpoint(project):
    service,bridge,_,font=project
    value=wait(service,start(project),'applied')
    hook=font.parent/'.git/hooks/pre-commit';hook.write_text('#!/bin/sh\nexit 0\n');hook.chmod(0o755)
    value=wait(service,choose(service,value,'save_result'),'saved')
    assert value['receipt']['checkpoint']['status']=='failed'
    assert len(bridge.adapter.save_calls)==1
    hook.unlink()
    value=choose(service,value,'retry_checkpoint')
    assert value['receipt']['checkpoint']['status']=='created'
    assert len(bridge.adapter.save_calls)==1


def test_keep_retains_action_evidence_for_later_save(project):
    service,bridge,_,font=project
    value=wait(service,start(project),'applied');identity=value['jobId']
    choose(service,value,'finish_edit')
    assert bridge.adapter.save_calls==[]
    assert service.jobs.path(identity).joinpath('action-scope.json').exists()
    bridge.adapter.value+=.25;bridge.adapter.dirty=True
    receipt=service.save_document('doc_1')
    assert receipt['checkpoint']['status']=='created'
    record=json.loads(git(font.parent,'show',receipt['checkpoint']['revision']+':'+receipt['checkpoint']['recordPath']))
    assert record['actions'][0]['jobId']==identity and record['manualChanges']=='possible'
    assert record['actions'][0]['scope']['reference']


def test_baseline_failure_prevents_application(project):
    service,bridge,_,font=project
    hook=font.parent/'.git/hooks/pre-commit';hook.write_text('#!/bin/sh\nexit 1\n');hook.chmod(0o755)
    value=start(project)
    value=wait(service,value,'failed')
    assert bridge.applies==0 and bridge.adapter.save_calls==[]


def test_preview_does_not_checkpoint(project):
    service,bridge,_,font=project; font.write_text('602');bridge.adapter.value=602
    wait(service,start(project,mode='preview'),'ready')
    assert git(font.parent,'rev-list','--count','HEAD').strip()==b'1'
    assert bridge.applies==0 and bridge.adapter.save_calls==[]


def test_historical_restore_uses_same_keep_save_workflow(project,monkeypatch):
    from glyphs_mcp_bridge import checkpoint_restore
    service,bridge,worker,font=project
    revision=git(font.parent,'rev-parse','HEAD').decode().strip()
    original_status=bridge.status
    bridge.status=lambda: {**original_status(),'writeCapabilities':['font.checkpoint-restore.v1']}
    bridge.restore_checkpoint=lambda request: bridge.call(checkpoint_restore.restore,bridge.core,request,RuntimeError)
    monkeypatch.setattr(checkpoint_restore,'load',lambda core,request,error: float(open(request['historicalPath']).read()))
    def replace(core,request,value,error):
        bridge.adapter.value=value;bridge.adapter.dirty=True
        return dict(bridge.adapter.document_state('doc_1'),familyName='Test')
    monkeypatch.setattr(checkpoint_restore,'replace',replace)
    bridge.adapter.value=900;bridge.adapter.dirty=True
    value=service.edit_workflows.start('doc_1',kind='checkpoint_restore',options={'revision':revision},idempotency_key='restore1',mode='preview',auto_keep=False)
    value=wait(service,value,'ready')
    assert bridge.adapter.value==900 and not bridge.adapter.save_calls
    value=wait(service,choose(service,value,'apply'),'applied')
    assert bridge.adapter.value==600 and not bridge.adapter.save_calls
    assert 'discard' not in {item['action'] for item in value['actions']}
    snapshot=service.edit_workflows.get(value['id'])
    assert service.edit_workflows.get(value['id'])['revision']==snapshot['revision']
    value=snapshot
    value=wait(service,choose(service,value,'save_result'),'saved')
    assert len(bridge.adapter.save_calls)==1 and value['receipt']['checkpoint']['status']=='created'
    actions=json.loads(git(font.parent,'show',value['receipt']['checkpoint']['revision']+':'+value['receipt']['checkpoint']['recordPath']))['actions']
    assert actions[0]['request']['kind']=='checkpoint_restore'


def test_failed_save_does_not_create_checkpoint(project):
    service,bridge,_,font=project
    bridge.adapter.dirty=True
    bridge.save=lambda request: {'status':'failed','error':{'code':'save_failed','message':'No write'}}
    from glyphs_mcp_sidecar.service import ServiceError
    with pytest.raises(ServiceError):service.save_document('doc_1')
    assert git(font.parent,'rev-list','--count','HEAD').strip()==b'1'
    assert all(j['status']!='accepted' for j in service.jobs.records())


def test_plain_save_reconciles_after_sidecar_restart_without_editor_save(project):
    from glyphs_mcp_sidecar import checkpoints
    from glyphs_mcp_sidecar.saving import prepare_save,bridge_request
    service,bridge,_,font=project
    bridge.adapter.value=720;bridge.adapter.dirty=True
    request=prepare_save('save_lost',bridge.documents()[0],None,bridge.documents())
    job=checkpoints.begin_save(service,bridge.documents()[0],request)
    bridge.save(bridge_request(request))
    assert len(bridge.adapter.save_calls)==1
    value=service.get_job(job['id'])
    assert value['status']=='accepted' and value['receipt']['checkpoint']['status']=='created'
    assert service.get_job(job['id'])['receipt']==value['receipt'] and len(bridge.adapter.save_calls)==1


def test_checkpoint_reads_do_not_modify_or_reach_editor_entities(project):
    service,bridge,_,font=project
    result=service.read_entities('doc_1',[{'kind':'checkpoint_history','limit':1}],['checkpoint'])
    assert result[0]['checkpoint']['checkpoints'][0]['revision']
    assert not bridge.adapter.save_calls and git(font.parent,'rev-list','--count','HEAD').strip()==b'1'


def test_save_as_creates_checkpoint_without_changing_original(project):
    service,bridge,_,font=project
    original=font.read_bytes();target=font.parent/'Saved As.glyphs'
    bridge.adapter.value=777;bridge.adapter.dirty=True
    receipt=service.save_document('doc_1',destination=str(target))
    assert receipt['checkpoint']['status']=='created'
    assert font.read_bytes()==original and target.read_text()=='777'
    assert git(font.parent,'show','HEAD:Saved As.glyphs')==b'777'
    assert len(bridge.adapter.save_calls)==1


def test_manual_save_establishes_baseline_only_at_authorized_apply(project):
    service,bridge,_,font=project
    bridge.adapter.value=700;bridge.adapter.dirty=True
    value=start(project);assert value['state']=='waiting_save'
    value=choose(service,value,'manual_save')
    font.write_text('700');bridge.adapter.dirty=False
    value=wait(service,choose(service,value,'check_continue'),'applied')
    assert not bridge.adapter.save_calls and git(font.parent,'show','HEAD:'+font.name)==b'700'
    choose(service,value,'finish_edit')


def test_historical_artifact_cleanup_is_idempotent_when_polling_races_save(project,monkeypatch):
    import shutil
    service,bridge,_,_=project
    job=service.jobs.create(bridge.documents()[0],{'kind':'checkpoint_restore','options':{}})
    historical=service.jobs.path(job['id'])/'historical';historical.mkdir()
    (historical/'font.glyphs').write_text('600')
    original=shutil.rmtree
    def raced(path):
        original(path)
        raise FileNotFoundError(path)
    monkeypatch.setattr(shutil,'rmtree',raced)
    service.jobs.release_bulk_artifacts(job['id'])
    assert service.jobs.path(job['id']).joinpath('state.json').is_file()
    assert not historical.exists()


def test_failed_presentation_reconciles_an_already_accepted_job_without_saving_again(project):
    service,bridge,_,_=project
    value=wait(service,start(project),'applied')
    before=service.jobs.get(value['jobId'])
    value=wait(service,choose(service,value,'save_result'),'saved')
    stored=service.edit_workflows.store.records[value['id']]
    service.edit_workflows.store.update(stored,state='failed',job={**before,'status':'accepting'},receipt=None,
        error={'code':'bridge_failed','message':'Historical artifact cleanup raced another result read'})
    result=service.edit_workflows.get(value['id'])
    assert result['state']=='saved' and result['receipt']['checkpoint']['revision']==value['receipt']['checkpoint']['revision']
    assert len(bridge.adapter.save_calls)==1
