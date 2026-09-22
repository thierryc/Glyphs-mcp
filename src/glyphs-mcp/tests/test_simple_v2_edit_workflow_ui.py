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
