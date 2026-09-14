"""Exercise actual FastMCP routing without sockets or a native Glyphs process."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

REPO = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(REPO / 'src' / part))
from glyphs_mcp_protocol import TOOL_NAMES
from glyphs_mcp_sidecar import server
from glyphs_mcp_sidecar.service import ServiceError

HEADERS = {'Accept': 'application/json, text/event-stream',
           'MCP-Protocol-Version': '2025-03-26'}
TOKEN = 'x' * 32


class Service:
    """Fixed outcomes isolate route changes from job/native implementation."""
    closed = False

    def get_status(self):
        return {'protocol': 1, 'tools': list(TOOL_NAMES), 'available': True}

    def list_documents(self):
        return [{'id': 'doc_1', 'dirty': True}]

    def read_entities(self, document_id, entities, fields):
        if document_id != 'doc_1':
            raise ServiceError('document_not_found', 'the Glyphs document is no longer open')
        return [{'entity': entities[0], 'values': {fields[0]: 600.125}}]

    def start_job(self, document_id, **request):
        return {'id': 'job_1', 'documentId': document_id, 'request': request, 'status': 'preparing'}

    def get_job(self, job_id, **options):
        return {'id': job_id, 'status': 'ready', **options}

    def apply_job(self, job_id, **options):
        return {'id': job_id, 'status': 'applying', **options}

    def discard_job(self, job_id, **options):
        return {'id': job_id, 'status': 'cancelled', **options}

    def reserve_idle(self):
        return {'reservationId': 'reservation_1'}

    def release_idle(self, reservation_id):
        return {'released': reservation_id}

    def close(self):
        self.closed = True


def run_options(tmp_path, transport='http'):
    service, mcp = Mock(), Mock()
    with patch.object(server, 'load_or_create_token', return_value=TOKEN), \
         patch.object(server, 'SidecarService', return_value=service), \
         patch.object(server, 'create_server', return_value=mcp):
        server.main(['--transport', transport, '--jobs', str(tmp_path / 'jobs')])
    service.close.assert_called_once_with()
    return mcp.run.call_args.kwargs


def packet(method, params=None):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}


def decoded(response):
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith('data: ')))


@pytest.mark.parametrize('transport', ['http', 'stdio'])
def test_main_configures_only_http_path(tmp_path, transport):
    options = run_options(tmp_path, transport)
    assert options == ({'transport': 'streamable-http', 'host': '127.0.0.1',
                        'port': 9680, 'path': '/mcp/', 'stateless_http': True}
                       if transport == 'http' else {})


def test_configured_route_preserves_handshake_catalog_all_tools_and_errors(tmp_path):
    options = run_options(tmp_path)
    async def exercise(path, alternate):
        service = Service()
        app = server.create_server(service).http_app(path=path, stateless_http=options['stateless_http'])
        results = []
        async with app.lifespan(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://test', headers=HEADERS,
                                         follow_redirects=False) as client:
                for method, params in [
                    ('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                    'clientInfo': {'name': 'route-test', 'version': '1'}}),
                    ('tools/list', {}),
                    *[('tools/call', {'name': name, 'arguments': arguments}) for name, arguments in [
                        ('get_status', {}), ('list_documents', {}),
                        ('read_entities', {'document_id': 'doc_1', 'entities': [{'kind': 'layer'}], 'fields': ['width']}),
                        ('start_job', {'document_id': 'doc_1', 'kind': 'width_delta', 'delta': .125}),
                        ('get_job', {'job_id': 'job_1', 'include_preview': False}),
                        ('apply_job', {'job_id': 'job_1', 'include_preview': False}),
                        ('discard_job', {'job_id': 'job_1', 'include_preview': False}),
                        ('read_entities', {'document_id': 'stale', 'entities': [{'kind': 'selection'}], 'fields': ['glyph']}),
                        ('read_entities', {}),  # Schema validation, without reaching native code.
                    ]],
                ]:
                    response = await client.post(path or '/mcp', json=packet(method, params))
                    assert not response.history and 'location' not in response.headers
                    results.append(decoded(response))
                assert results[0]['result']['protocolVersion'] == '2025-03-26'
                assert {t['name'] for t in results[1]['result']['tools']} == set(TOOL_NAMES)
                for result in results[2:-1]:
                    body = result['result']['structuredContent']
                    assert body['ok'] == (result is not results[-2])
                assert results[4]['result']['structuredContent']['data'][0]['values']['width'] == 600.125
                assert results[-2]['result']['structuredContent']['error']['code'] == 'document_not_found'
                assert results[-1]['result']['isError'] is True
                redirect = await client.post(alternate, json=packet('tools/list'))
                assert redirect.status_code == 307
                assert redirect.headers['location'] == 'http://test' + (path or '/mcp')
                for method, params in [('notifications/initialized', {}),
                                       ('notifications/cancelled', {'requestId': 'already-finished'})]:
                    response = await client.post(path or '/mcp', json={'jsonrpc': '2.0', 'method': method, 'params': params})
                    assert response.status_code == 202 and not response.history
                assert not service.closed, 'Requests/notifications must not close process-owned jobs'
        assert not service.closed
        return results

    async def compare():
        baseline = await exercise(None, '/mcp/')
        candidate = await exercise(options['path'], '/mcp')
        assert candidate == baseline  # Exact MCP JSON, including all seven schemas/errors.
    asyncio.run(compare())


def test_management_authorization_and_control_routes_unchanged(tmp_path):
    options = run_options(tmp_path)
    async def check():
        service = Service()
        app = server.create_server(service, control_token=TOKEN).http_app(
            path=options['path'], stateless_http=options['stateless_http'])
        async with app.lifespan(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://test', follow_redirects=False) as client:
                for auth, expected in [({}, 403), ({'Authorization': 'Bearer wrong'}, 403),
                                       ({'Authorization': 'Bearer ' + TOKEN}, 200)]:
                    response = await client.post('/internal/control', json={'action': 'reserve'}, headers=auth)
                    assert response.status_code == expected and not response.history
                headers = {'Authorization': 'Bearer ' + TOKEN}
                response = await client.post('/internal/control', json={'action': 'release', 'reservationId': 'reservation_1'}, headers=headers)
                assert response.json() == {'ok': True, 'data': {'released': 'reservation_1'}}
                assert response.headers['cache-control'] == 'no-store'
                response = await client.get('/internal/status', headers=headers)
                assert response.json() == {'ok': True, 'data': service.get_status()}
                response = await client.post('/internal/control', json={'action': 'unknown'}, headers=headers)
                assert response.status_code == 400
                response = await client.post('/internal/control', content='x' * 4097, headers=headers)
                assert response.status_code == 400
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.0.2.1', 1234)),
                                         base_url='http://test') as client:
                response = await client.get('/internal/status', headers={'Authorization': 'Bearer ' + TOKEN})
                assert response.status_code == 403
    asyncio.run(check())
