"""Qualify local Codex attribution against a disposable, font-free MCP service."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def fixture(log):
    for component in ('sidecar', 'protocol', 'bridge'):
        sys.path.insert(0, str(ROOT/'src'/component))
    from fastmcp.server.dependencies import get_context
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_sidecar.edit_workflow_state import public_workflow
    class Workflows:
        def get(self, workflow_id, include_review=False):
            context = get_context()
            meta = context.request_context.meta
            with Path(log).open('a') as out:
                out.write(json.dumps({'progressToken': meta.progressToken if meta else None})+'\n')
            time.sleep(1.1)  # Exercise the slow-request notification threshold.
            return public_workflow(dict(id=workflow_id, nonce='fixture', revision=1, state='applying',
                updatedAt=time.time(), jobId='job_fixture', document=dict(id='doc_fixture',familyName='Fixture'),
                request=dict(kind='python_script', options=dict(entrypoint='script',targets=[])),
                job=dict(id='job_fixture',status='applying',bridgeOperation=dict(scriptResult=dict(executed=True)))))
    class Service:
        edit_workflows = Workflows()
    create_server(Service()).run(transport='stdio', show_banner=False)


class RPC:
    def __init__(self, env, cwd, log):
        self.log = Path(log).open('w')
        self.process = subprocess.Popen(['codex', 'app-server', '--stdio'], env=env, cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        self.messages = queue.Queue()
        self.events = []
        self.counter = 0
        def read():
            for line in self.process.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: pass
        threading.Thread(target=read, daemon=True).start()

    def send(self, value):
        self.process.stdin.write(json.dumps(value)+'\n')
        self.process.stdin.flush()

    def call(self, method, params):
        self.counter += 1
        identity = self.counter
        self.send({'jsonrpc': '2.0', 'id': identity, 'method': method, 'params': params})
        deadline = time.monotonic()+35
        while time.monotonic() < deadline:
            try: value = self.messages.get(timeout=max(.1, deadline-time.monotonic()))
            except queue.Empty: break
            if value.get('id') == identity:
                if 'error' in value: raise RuntimeError(value['error'])
                return value['result']
            self.events.append(value)
        raise TimeoutError(method)

    def close(self):
        self.process.terminate()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait()
        self.log.close()


def run(python, output):
    repo = ROOT
    output.mkdir(parents=True, exist_ok=True)
    (output/'host-probe.json').unlink(missing_ok=True)
    results = []
    for mode in ('standalone', 'plugin', 'overlap'):
        with tempfile.TemporaryDirectory(prefix='glyphs-codex-probe-') as temporary:
            work = Path(temporary)
            home = work/'home'; home.mkdir()
            market = work/'market'; package = market/'plugins/glyphs-mcp'
            (package/'.codex-plugin').mkdir(parents=True)
            (market/'.agents/plugins').mkdir(parents=True)
            manifest = json.loads((repo/'plugins/glyphs-mcp/.codex-plugin/plugin.json').read_text())
            manifest.pop('skills', None)
            (package/'.codex-plugin/plugin.json').write_text(json.dumps(manifest))
            shutil.copytree(repo/'plugins/glyphs-mcp/assets', package/'assets')
            shutil.copy2(repo/'.agents/plugins/marketplace.json', market/'.agents/plugins/marketplace.json')
            trace = output/(mode+'-requests.jsonl')
            trace.write_text('')
            server = {'command': python, 'args': ['-B', str(Path(__file__).resolve()), '--fixture', str(trace)]}
            (package/'.mcp.json').write_text(json.dumps({'mcpServers': {'glyphs-mcp-server': server}}))
            env = dict(os.environ, CODEX_HOME=str(home))
            config = ''
            if mode in ('standalone', 'overlap'):
                config = '[mcp_servers.glyphs-mcp-server]\ncommand = '+json.dumps(server['command'])+'\nargs = '+json.dumps(server['args'])+'\n'
            (home/'config.toml').write_text(config)
            if mode in ('plugin', 'overlap'):
                for args in (['plugin','marketplace','add',str(market),'--json'], ['plugin','add','glyphs-mcp@glyphs-mcp','--json']):
                    command = subprocess.run(['codex',*args],env=env,cwd=work,text=True,capture_output=True,timeout=25)
                    if command.returncode: raise RuntimeError(command.stdout+command.stderr)
            rpc = RPC(env, work, output/(mode+'-appserver.log'))
            try:
                rpc.call('initialize', {'clientInfo': {'name': 'glyphs-qualification', 'version': '1.0'},
                                       'capabilities': {'experimentalApi': True}})
                rpc.send({'jsonrpc':'2.0','method':'initialized'})
                inventory = rpc.call('mcpServerStatus/list', {'serverName': 'glyphs-mcp-server'})
                thread = rpc.call('thread/start', {'cwd': str(work), 'ephemeral': True})
                identity = thread['thread']['id']
                call = rpc.call('mcpServer/tool/call', {'threadId':identity,'server':'glyphs-mcp-server',
                    'tool':'get_edit_workflow','arguments':{'workflow_id':'edit_fixture'}})
                row, = inventory['data']
                expected = 'glyphs-mcp@glyphs-mcp' if mode == 'plugin' else None
                assert row.get('pluginId') == expected, row.get('pluginId')
                icon, = row['serverInfo']['icons'] or []
                image = base64.b64decode(icon['src'].split(',',1)[1])
                assert image == (repo/'plugins/glyphs-mcp/assets/icon.png').read_bytes()
                assert len(row['tools']) == 22
                progress = call['structuredContent']['data']['progress']
                assert progress['indeterminate'] and progress['total'] is None
                assert all('ctx' not in t['inputSchema'].get('properties',{}) for t in row['tools'].values())
                requests = [json.loads(line) for line in trace.read_text().splitlines()]
                assert requests and requests[-1]['progressToken'] is not None
                result = {'mode':mode,'pluginId':row.get('pluginId'),'serverName':row['serverInfo']['name'],
                    'iconSHA256':hashlib.sha256(image).hexdigest(),'tools':len(row['tools']),
                    'progress':progress,'requests':requests,
                    'progressEvents':[e for e in rpc.events if 'progress' in e.get('method','').lower()]}
                results.append(result)
                print(json.dumps(result),flush=True)
            finally:
                rpc.close()
    version = subprocess.check_output(['codex','--version'],text=True).strip()
    (output/'host-probe.json').write_text(json.dumps({'codexVersion':version,'cases':results},indent=2)+'\n')


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1] == '--fixture': fixture(sys.argv[2])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--python', default=sys.executable, help='Locked private-runtime Python for the fixture server')
        parser.add_argument('--output', type=Path, default=ROOT/'build/codex-feedback-qualification')
        args = parser.parse_args()
        run(str(Path(args.python).resolve()),args.output.resolve())
