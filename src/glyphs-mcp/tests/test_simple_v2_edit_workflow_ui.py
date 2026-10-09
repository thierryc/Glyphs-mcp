"""Execute the actual bundled UI script against a deterministic standard host."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]
HTML = ROOT / 'src/sidecar/glyphs_mcp_sidecar/edit_workflow_v1.html'


def test_standard_host_actions_and_fallback(tmp_path):
    from glyphs_mcp_sidecar.edit_workflow_state import MESSAGES, public_workflow

    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the MCP App contract fixture')
    states = []
    for state in MESSAGES:
        value = public_workflow(dict(
            id='edit_wording', nonce='test', revision=len(states), state=state,
            document=dict(id='doc_wording', familyName='Workflow Sample', path='/fonts/Workflow Sample.glyphs'),
            request=dict(kind='width_delta', glyphs=['A']),
            job=dict(bridgeOperation=dict(completedChanges=1, totalChanges=1)),
            error=dict(message='A later edit prevents undo.', code='conflict') if state == 'failed' else None,
        ))
        assert value['message'].splitlines()[0] == MESSAGES[state]
        assert value['text'].count(MESSAGES[state]) == 1
        states.append(dict(ok=True, data=value))
    fixture = tmp_path / 'wording.json'
    fixture.write_text(json.dumps(states))
    subprocess.run([node, str(Path(__file__).parent/'fixtures/mock_edit_workflow_host.js'), str(HTML), str(fixture)], check=True, timeout=15)


def test_card_is_self_contained_and_accessible():
    text = HTML.read_text()
    assert 'role="status"' in text and ':focus-visible' in text
    assert '<label for="folder">' in text and '<label for="filename">' in text
    for forbidden in ('fetch(', 'XMLHttpRequest', '<script src=', '<link rel=', 'window.openai', '9681', 'innerHTML'):
        assert forbidden not in text


@pytest.mark.parametrize('scenario', [
    'stale', 'refresh_failure', 'validation', 'external_completion', 'menu',
    'countdown_refresh', 'inspection_during_refresh', 'wrong_response', 'compact', 'focus',
])
def test_card_reconciles_and_simplifies_choices(scenario):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the MCP App contract fixture')
    subprocess.run([node, str(Path(__file__).parent/'fixtures/workflow_card_states_host.js'),
                    str(HTML), scenario], check=True, timeout=15)


@pytest.mark.parametrize('state,kind,main,menu', [
    ('ready', 'width_delta', ['apply', 'discard'], []),
    ('waiting_save', 'width_delta', ['save_continue', 'cancel'], ['save_as_continue', 'manual_save']),
    ('waiting_run', 'python_script', ['run_script', 'cancel'], []),
    ('applied', 'width_delta', ['finish_edit', 'discard'], ['save_result', 'save_result_as']),
    ('applied', 'python_script', ['finish_script', 'save_result'], ['restore_saved_script']),
    ('cancelled', 'python_script', ['finish_script', 'restore_saved_script'], []),
    ('outdated', 'width_delta', ['reprepare', 'cancel'], ['save_reprepare', 'manual_save']),
    ('uncertain', 'width_delta', ['check_outcome'], []),
    ('saved', 'width_delta', [], []),
])
def test_card_and_text_use_the_same_offered_actions(state, kind, main, menu):
    from glyphs_mcp_sidecar.edit_workflow_state import public_workflow, offered_actions

    value = dict(id='edit_presentation', nonce='test', revision=1, state=state,
                 document=dict(id='doc_a', path='/fonts/A.glyphs', dirty=False),
                 request=dict(kind=kind, glyphs=['A'], options={}),
                 autoKeepEnabled=True, savedVersion=dict(available=True),
                 job=dict(status='applied', bridgeOperation=dict(status='applied',
                          scriptResult=dict(executed=True, executionSucceeded=True))))
    result = public_workflow(value)
    assert [a['action'] for a in result['actions'] if a['presentation'] in {'primary', 'secondary'}] == main
    assert [a['action'] for a in result['actions'] if a['presentation'] == 'menu'] == menu
    assert {a['action'] for a in result['actions']} == {name for name, _ in offered_actions(value)}
    context = json.loads(result['modelContext'])
    assert [a['action'] for a in context['actions']] == [a['action'] for a in result['actions']]
    for a in result['actions']:
        if a['presentation'] != 'auto_keep':
            assert a['label'] in result['text']
    if main and menu:
        assert result['text'].index('Available choices:') < result['text'].index('More options:')
    if state in {'waiting_run', 'waiting_save', 'applied', 'outdated', 'cancelled'}:
        assert result['poll'] is False
        assert result['uiRefreshIntervalMs'] == 5000
    if state == 'saved':
        assert result['uiRefreshIntervalMs'] == 0
    if state == 'applied':
        assert result['autoKeep']['enabled'] is True
        assert result['autoKeep']['delaySeconds'] == 30
        assert result['actions'][-1]['presentation'] == 'auto_keep'


def test_unnamed_fonts_checkpoint_recovery_and_compact_text():
    from glyphs_mcp_sidecar.edit_workflow_state import public_workflow

    value = dict(id='edit_a', nonce='test', revision=1, state='waiting_save',
                 document=dict(id='doc_a'), request=dict(kind='width_delta', glyphs=[]))
    result = public_workflow(value)
    assert result['actions'][0]['action'] == 'save_as_continue'
    value.update(state='saved', receipt=dict(checkpoint=dict(status='failed')))
    assert public_workflow(value)['actions'][0]['presentation'] == 'primary'
    value.update(state='waiting_run', document=dict(id='doc_a', path='/fonts/A.glyphs', dirty=False),
                 request=dict(kind='python_script', options=dict(summary='An intended effect. ' * 30)),
                 job=dict(report=dict(targetCount=11, skippedCount=0)))
    result = public_workflow(value)
    summary = next(line for line in result['text'].splitlines() if line.startswith('Intended change: '))
    assert len(summary.removeprefix('Intended change: ')) == 140
    assert '/fonts/' not in result['text'] and '11 resolved targets.' in result['text']
    assert '0 skipped' not in result['text']
    detailed = public_workflow(value, include_review=True)
    assert '/fonts/A.glyphs' in detailed['text'] and value['request']['options']['summary'] in detailed['text']


def test_card_refresh_hint_is_independent_of_agent_polling():
    from glyphs_mcp_sidecar.edit_workflow_state import public_workflow

    value = dict(id='edit_a', nonce='test', revision=1, state='uncertain', jobId='job_a',
                 document=dict(id='doc_a'), request=dict(kind='width_delta', glyphs=[]))
    result = public_workflow(value)
    assert result['poll'] is True
    assert result['uiRefreshIntervalMs'] == 5000
    value.update(state='preparing')
    assert public_workflow(value)['uiRefreshIntervalMs'] == 1500
    value.update(state='blocked_review')
    assert public_workflow(value)['uiRefreshIntervalMs'] == 5000
