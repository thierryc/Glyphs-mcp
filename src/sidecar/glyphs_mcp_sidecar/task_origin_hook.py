"""Opt-in PostToolUse adapter. Enabling it is a separate agent setup action.

Only successful starts establish origin; reading a task never adopts ownership.
Hook failures are non-blocking and never print tool contents or credentials.
"""
import argparse
import json
from pathlib import Path
import plistlib
import re
import sys
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from .task_inventory import IDENTIFIER, WORKFLOW_ID


def association(event, agent):
    if event.get('hook_event_name') != 'PostToolUse':
        return None
    name = event.get('tool_name', '')
    # This callback is specific to the Glyphs MCP server, not arbitrary tools
    # that happen to return an id or text containing a workflow reference.
    if not re.fullmatch(r'mcp__glyphs[-_]mcp(?:[-_]sidecar)?__start_edit_workflow', name, re.I):
        return None
    identity = event.get('session_id', '')
    if not IDENTIFIER.fullmatch(identity):
        return None
    response = event.get('tool_response')
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict) or response.get('isError'):
        return None
    payload = response.get('structuredContent') or response.get('structured_content')
    if payload is None and 'ok' in response:
        payload = response
    if payload is None:
        for block in response.get('content', []):
            if block.get('type') == 'text':
                try:
                    candidate = json.loads(block.get('text', ''))
                except ValueError:
                    continue
                if isinstance(candidate, dict) and 'ok' in candidate:
                    payload = candidate
                    break
    if not isinstance(payload, dict) or payload.get('ok') is not True:
        return None
    workflow = (payload.get('data') or {}).get('id', '')
    if not isinstance(workflow, str) or not WORKFLOW_ID.fullmatch(workflow):
        return None
    return dict(workflowId=workflow, agent=agent, conversationId=identity)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', required=True, choices=('codex', 'claude_code'))
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(262145)
        if len(raw) > 262144:
            return 0
        value = association(json.loads(raw), args.agent)
        if value is None:
            return 0
        base = Path.home() / 'Library/Application Support/Glyphs MCP'
        launch = Path.home() / 'Library/LaunchAgents/com.ap.cx.glyphs-mcp-sidecar.plist'
        settings = plistlib.loads(launch.read_bytes())
        arguments = settings.get('ProgramArguments', [])
        port = int(arguments[arguments.index('--port') + 1]) if '--port' in arguments else 9680
        if not 1024 <= port <= 65535:
            return 0
        token_path = (settings.get('EnvironmentVariables') or {}).get('GLYPHS_MCP_BRIDGE_TOKEN_FILE')
        token = (Path(token_path).expanduser() if token_path else base / 'bridge-token').read_text().strip()
        request = Request(f'http://127.0.0.1:{port}/internal/task-origins',
                          data=json.dumps(value).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST')
        # Never route a local authentication token through an environment proxy.
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *_args, **_kwargs):
                return None
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=1) as response:
            response.read(2048)
    except Exception:
        # A missing/older sidecar leaves Copy Request available. Do not affect
        # the tool outcome, create tasks, or silently submit another agent turn.
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
