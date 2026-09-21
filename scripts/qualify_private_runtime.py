#!/usr/bin/env python3
"""Launch the bundled sidecar and stdio proxy without package downloads."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def check(lean, architecture):
    python=lean/'runtimes'/architecture/'bin/python3'
    prefix=['/usr/bin/arch','-x86_64'] if architecture=='x86_64' else []
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='glyphs-runtime-qualification-') as tmp:
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','PATH':'/usr/bin:/bin',
             'GLYPHS_MCP_BRIDGE_TOKEN_FILE':str(Path(tmp)/'token')}
        # Exercise the actual packaged entry point outside the checkout. Source
        # tests can otherwise conceal missing imports in the shipped installer.
        env.pop('PYTHONPATH', None)
        installer = lean.parent/'Installer/install_simple_v2.py'
        subprocess.run(prefix+[str(python), '-B', '-s', str(installer), '--help'],
                       cwd=tmp, env=env, check=True, capture_output=True, text=True, timeout=30)
        # No native document or package index is needed for catalog discovery.
        log=(Path(tmp)/"server.log").open("w+")
        started=time.monotonic()
        process=subprocess.Popen(prefix+[str(python),'-B',str(lean/'sidecar/run.py'),'--transport','http','--port',str(port),'--jobs',str(Path(tmp)/'jobs')],env=env,stdout=log,stderr=log)
        try:
            url=f'http://127.0.0.1:{port}/mcp/'
            for _ in range(600):
                try:
                    async with Client(url) as client:
                        catalog=await client.list_tools()
                    break
                except Exception:
                    if process.poll() is not None: log.seek(0); raise RuntimeError(log.read()[-2000:])
                    await asyncio.sleep(.1)
            else:
                log.seek(0); raise TimeoutError('Private runtime did not start: '+log.read()[-2000:])
            expected=['get_status','list_documents','read_entities','start_job','get_job','apply_job','accept_job','discard_job','save_document']
            assert [t.name for t in catalog]==expected
            command=prefix+[str(python),'-B',str(lean/'sidecar/proxy.py'),url]
            async with Client(StdioTransport(command=command[0],args=command[1:],env=env)) as proxy:
                assert [t.name for t in await proxy.list_tools()]==expected
            return {'architecture':architecture,'privatePython':True,'httpCatalog':expected,'stdioProxy':True,'packageDownloads':0,'packagedInstallerCLI':True,'startupSeconds':round(time.monotonic()-started,3)}
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    lean=Path(sys.argv[1]).resolve()
    result=[asyncio.run(check(lean,architecture)) for architecture in ('arm64','x86_64')]
    print(json.dumps(result,indent=2))
