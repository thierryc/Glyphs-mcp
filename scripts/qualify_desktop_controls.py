"""Live shared controls with no font mutations; restores the original MCP port."""
import asyncio
import hashlib
import json
from pathlib import Path
import plistlib
import socket
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANAGED = Path.home()/'Library/Application Support/Glyphs MCP/lean-v2'
sys.path.insert(0, str(MANAGED/'sidecar'))
from glyphs_mcp_sidecar.control import ServerControl
from fastmcp import Client


def private_status(port):
    token = (MANAGED.parent/'bridge-token').read_text().strip()
    request = Request(f'http://127.0.0.1:{port}/internal/status', headers={'Authorization':'Bearer '+token})
    with urlopen(request, timeout=10) as response: return json.load(response)['data']


async def check():
    controller = ServerControl()
    before = controller.status(); original = before['port']
    assert before['running'] and not private_status(original)['activity']['activeCount']
    prepared_id = None
    if '--with-prepared-job' in sys.argv:
        config = json.loads((ROOT/'build/desktop-acceptance/config.json').read_text())
        async with Client(f'http://127.0.0.1:{original}/mcp/') as client:
            async def call(name, **arguments):
                result = await client.call_tool(name, arguments)
                body = result.structured_content or json.loads(result.content[0].text)
                assert body['ok'], body
                return body['data']
            documents = await call('list_documents')
            assert len(documents) == 1 and documents[0]['path'] == config['source'] and not documents[0]['dirty']
            job = await call('start_job', document_id=documents[0]['id'], kind='width_delta', delta=8.125)
            prepared_id = job['id']; deadline = time.monotonic() + 120
            while job['status'] == 'preparing':
                assert time.monotonic() < deadline, job
                await asyncio.sleep(.1)
                job = await call('get_job', job_id=prepared_id)
            assert job['status'] == 'ready', job
    agent = plistlib.loads(controller.agent.read_bytes())
    receipt = (MANAGED/'installation.json').read_bytes()
    jobs = {p.parent.name: p.read_bytes() for p in (MANAGED/'jobs').glob('*/state.json')}
    lease = controller._management(original, 'reserve')
    try:
        async with Client(f'http://127.0.0.1:{original}/mcp/') as client:
            result = await client.call_tool('start_job', {'document_id':'no-font-is-mutated', 'kind':'width_delta', 'delta':1})
            body = result.structured_content or json.loads(result.content[0].text)
            assert body['ok'] is False and body['error']['code']=='service_reserved', body
    finally:
        controller._management(original, 'release', reservationId=lease['reservationId'])
    controller.run('stop')
    assert controller.status()['loaded'] is False
    controller.run('start')
    assert private_status(original)['controlProtocol']==1
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0)); temporary = available.getsockname()[1]
    try:
        changed = controller.run('port', str(temporary))
        assert changed['running'] and changed['port']==temporary
        assert private_status(temporary)['controlProtocol']==1
    finally:
        controller.run('port', str(original))
    current = controller.status(); assert current['running'] and current['port']==original
    assert plistlib.loads(controller.agent.read_bytes())==agent
    assert (MANAGED/'installation.json').read_bytes()==receipt
    assert {p.parent.name:p.read_bytes() for p in (MANAGED/'jobs').glob('*/state.json')}==jobs
    if prepared_id:
        async with Client(f'http://127.0.0.1:{original}/mcp/') as client:
            result = await client.call_tool('get_job', {'job_id':prepared_id})
            body = result.structured_content or json.loads(result.content[0].text)
            assert body['ok'] and body['data']['status']=='ready', body
            result = await client.call_tool('discard_job', {'job_id':prepared_id})
            body = result.structured_content or json.loads(result.content[0].text)
            assert body['ok'] and body['data']['status']=='discarded', body
    report={'reservationRefusesNewJobs':True, 'stopStart':True, 'portRoundTrip':True,
            'originalPort':original, 'jobRecordsPreserved':len(jobs), 'preferencesUnchanged':True,
            'preparedResultSurvivedRestarts':bool(prepared_id), 'preparedJobId':prepared_id,
            'receiptSHA256':hashlib.sha256(receipt).hexdigest()}
    (ROOT/'build/desktop-acceptance/live-controls.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__': asyncio.run(check())
