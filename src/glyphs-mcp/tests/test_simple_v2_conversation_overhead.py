"""Conversation reuse must reduce calls without lending stale evidence authority."""
from pathlib import Path
import shutil
import subprocess

import pytest
from test_simple_v2_edit_workflow import env, start, wait
from glyphs_mcp_sidecar.edit_workflow_state import public_workflow

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT/'src/sidecar/glyphs_mcp_sidecar/edit_workflow_v1.html'


@pytest.mark.parametrize('scenario', ['duplicate','reopen','document','late_read','late_write','visibility','typed_summary'])
def test_card_reuses_matching_evidence_and_reconciles_changes(scenario):
    node=shutil.which('node')
    if not node: pytest.skip('Node is needed to exercise the actual card script')
    subprocess.run([node,str(Path(__file__).parent/'fixtures/conversation_overhead_host.js'),
                    str(HTML),scenario],check=True,timeout=15)


def test_typed_text_leads_with_intended_effect_without_an_extra_job_read(env, monkeypatch):
    service, bridge, _, _=env
    value=wait(service,start(env,auto_keep=False),'applied')
    assert value['summary']=='Add 8 units'
    assert 'Intended change: Add 8 units' in value['text']
    assert value['text'].index('Intended change:') < value['text'].index('Operation:')
    # Once scoped context is known, reads use the same workflow and never launch again.
    def forbidden(): raise AssertionError('workflow polling must not rediscover capabilities')
    monkeypatch.setattr(bridge,'status',forbidden)
    for _ in range(3):
        assert service.edit_workflows.get(value['id'])['jobId']==value['jobId']
    assert bridge.applies==1 and bridge.adapter.save_calls==[]


def test_script_details_remain_opt_in_for_text_only_reads():
    value=dict(id='edit_a',jobId='job_a',nonce='nonce',revision=1,state='waiting_run',
        document=dict(id='doc_a'),request=dict(kind='python_script',options=dict(
            source='print("<tag>")',params=dict(x=.25),targets=[],entrypoint='script')))
    compact=public_workflow(value)
    assert 'scriptReview' not in compact and 'print(' not in compact['text']
    detailed=public_workflow(value,include_review=True)
    assert detailed['scriptReview']==value['request']['options']
    assert detailed['requestFingerprint']==compact['requestFingerprint']
    assert detailed['actions']==compact['actions']


def test_waiting_typed_request_does_not_use_earlier_jobs_summary():
    value=dict(id='edit_b',nonce='nonce',revision=1,state='blocked',blockerId='job_a',
        document=dict(id='doc_a'),request=dict(kind='width_delta',glyphs=['H'],delta=8),
        job=dict(summary='Earlier unrelated adjustment',status='applied'))
    result=public_workflow(value)
    assert 'summary' not in result
