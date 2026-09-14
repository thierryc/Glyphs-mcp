#!/usr/bin/env python3
"""Disposable native qualification; never installs or attaches to live documents.

Use the same Python/glyphs-cli runtime for both roots. Timing wrappers exist only
in this harness; raw samples remain separate from any agent assessment.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time


def now(): return datetime.now(timezone.utc).isoformat()
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, default=str) + '\n')
def stats(values):
    ordered = sorted(values)
    return {'n':len(values), 'medianMs':statistics.median(values), 'minMs':min(values),
            'maxMs':max(values), 'p95Ms':ordered[math.ceil(.95*len(ordered))-1]}
def config(): return json.loads(Path(os.environ['GMCP_QUALIFICATION_CONFIG']).read_text())


def bridge_process():
    cfg = config(); sys.path.insert(0, cfg['bridgeResources'])
    from GlyphsApp import Glyphs, GSFont
    from Foundation import NSRunLoop, NSDate, NSBundle
    from glyphs_mcp_bridge.core import BridgeCore
    from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
    from glyphs_mcp_bridge.main_thread import CocoaMainThread
    from glyphs_mcp_bridge.http_server import BridgeHTTPServer
    rows = []; reads = []; main = CocoaMainThread(); schedule = main.schedule
    if cfg['instrument']:
        def measured_schedule(callback):
            queued = time.perf_counter_ns()
            def measured():
                start = time.perf_counter_ns()
                try: callback()
                finally:
                    rows.append({'queuedAtNs':queued, 'startedAtNs':start, 'finishedAtNs':time.perf_counter_ns(),
                                 'dispatchWaitMs':(start-queued)/1e6,
                                 'callbackMs':(time.perf_counter_ns()-start)/1e6})
            schedule(measured)
        main.schedule = measured_schedule
    adapter = GlyphsAdapter(Glyphs); core = BridgeCore(adapter, main.schedule)
    before = core.list_documents()
    assert not before, 'Isolated worker unexpectedly contains documents'
    if cfg.get('fixture'):
        # Native source-only qualification. Headless fonts are not registered
        # in Glyphs.fonts; inject only the target list, never metadata results.
        font = GSFont(cfg['fixture'])
        assert font is not None, 'Native fixture open failed'
        adapter._fonts = lambda: [font]
        assert len(core.list_documents()) == 1, 'Expected one native source target'
    if cfg['instrument']:
        original_read = core.read_entities
        def timed_read(document_id, entities, fields):
            start = time.perf_counter_ns()
            try: return original_read(document_id, entities, fields)
            finally:
                reads.append({'startedAtNs':start, 'finishedAtNs':time.perf_counter_ns(),
                              'targets':len(entities), 'nativeReadMs':(time.perf_counter_ns()-start)/1e6})
        core.read_entities = timed_read
    server = BridgeHTTPServer(core, main, token=cfg['token'], port=0)
    server.start()
    bundle = NSBundle.mainBundle()
    host = {key:bundle.objectForInfoDictionaryKey_(key) for key in
            ('CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion')}
    write(cfg['bridgeReady'], {'port':server.address[1], 'host':host})
    try:
        deadline = time.monotonic() + 120
        while not Path(cfg['stop']).exists() and time.monotonic() < deadline:
            NSRunLoop.currentRunLoop().runMode_beforeDate_('NSDefaultRunLoopMode', NSDate.dateWithTimeIntervalSinceNow_(.01))
    finally:
        server.stop()
        write(cfg['bridgeTimings'], {'samples':rows, 'documentsBefore':before,
              'documentsAfter':core.list_documents(), 'nativeReads':reads,
              'host':host, 'stoppedAt':now()})


def sidecar_process():
    cfg = config(); sys.path.insert(0, cfg['sidecar'])
    from glyphs_mcp_sidecar.bridge_client import BridgeClient
    from glyphs_mcp_sidecar.jobs import JobStore
    from glyphs_mcp_sidecar.service import SidecarService
    from glyphs_mcp_sidecar.server import create_server
    from glyphs_mcp_sidecar.worker import GlyphsCliWorker
    bridge = BridgeClient('http://127.0.0.1:' + str(cfg['bridgePort']), cfg['token'])
    service = SidecarService(bridge, jobs=JobStore(Path(cfg['jobs'])),
                            worker=GlyphsCliWorker(executable=cfg['glyphsCLI'], app=cfg['application']))
    rows = []; read_rows = []
    if cfg['instrument']:
        original_bridge = bridge.status; original_status = service.get_status
        bridge_elapsed = 0
        def timed_bridge():
            nonlocal bridge_elapsed
            start = time.perf_counter_ns()
            try: return original_bridge()
            finally: bridge_elapsed = (time.perf_counter_ns()-start)/1e6
        def timed_status():
            start = time.perf_counter_ns()
            result = original_status()
            elapsed = (time.perf_counter_ns()-start)/1e6
            rows.append({'at':now(), 'statusTotalMs':elapsed, 'bridgeHttpMs':bridge_elapsed,
                         'sidecarAssemblyMs':elapsed-bridge_elapsed})
            return result
        bridge.status = timed_bridge; service.get_status = timed_status
        original_bridge_read = bridge.read_entities; original_service_read = service.read_entities
        read_bridge_elapsed = 0
        def timed_bridge_read(*args, **kwargs):
            nonlocal read_bridge_elapsed
            start = time.perf_counter_ns()
            try: return original_bridge_read(*args, **kwargs)
            finally: read_bridge_elapsed = (time.perf_counter_ns()-start)/1e6
        def timed_service_read(*args, **kwargs):
            start = time.perf_counter_ns()
            try: return original_service_read(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter_ns()-start)/1e6
                read_rows.append({'at':now(), 'readTotalMs':elapsed, 'bridgeHttpMs':read_bridge_elapsed,
                                  'sidecarAssemblyMs':elapsed-read_bridge_elapsed})
        bridge.read_entities = timed_bridge_read; service.read_entities = timed_service_read
    signal.signal(signal.SIGTERM, lambda *_: None)  # Uvicorn replays SIGTERM after graceful shutdown.
    try:
        create_server(service).run(transport='streamable-http', host='127.0.0.1',
                                  port=cfg['port'], stateless_http=True, show_banner=False)
    finally:
        service.close(); write(cfg['sidecarTimings'], rows)
        write(cfg['sidecarReadTimings'], read_rows)


def unused_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); return listener.getsockname()[1]


def wait_ready(path, process):
    deadline = time.monotonic()+25
    while not Path(path).exists():
        if process.poll() is not None or time.monotonic()>deadline:
            raise RuntimeError('Isolated native worker did not become ready')
        time.sleep(.05)
    return json.loads(Path(path).read_text())


async def measure(endpoint, expected, metadata=None):
    from fastmcp import Client
    calls = []; trials = []; status = None; catalog = None; init = None
    async def call(client, name, phase, arguments=None, expected_error=None):
        start = time.perf_counter_ns(); at=now()
        value = await client.call_tool_mcp(name, arguments or {})
        elapsed = (time.perf_counter_ns()-start)/1e6
        data = json.loads(value.content[0].text)
        calls.append({'at':at, 'phase':phase, 'method':name, 'latencyMs':elapsed,
                      'arguments':arguments or {}, 'response':data, 'ok':data['ok']})
        if expected_error:
            assert not data['ok'] and data['error']['code'] == expected_error, data
            return data, elapsed
        assert data['ok'], data
        if name == 'get_status':
            info = data['data']
            assert info['protocol'] == info['bridge']['protocol'] == 1
            for component, fields in expected.items():
                observed = info if component == 'sidecar' else info['bridge']
                assert all(observed.get(key) == value for key, value in fields.items()), (component, observed)
        return data['data'], elapsed
    for phase in ('first','warmup','trial-1','trial-2','trial-3','trial-4','trial-5'):
        start=time.perf_counter_ns(); at=now()
        async with Client(endpoint, timeout=10, init_timeout=10) as client:
            init_ms=(time.perf_counter_ns()-start)/1e6
            init=client.initialize_result.model_dump(mode='json')
            calls.append({'at':at,'phase':phase,'method':'initialize','latencyMs':init_ms,'ok':True})
            assert init['serverInfo']['version'] == expected['sidecar'].get('release', {}).get('releaseVersion', '0.1.0')
            list_start=time.perf_counter_ns(); at=now(); tools=await client.list_tools()
            list_ms=(time.perf_counter_ns()-list_start)/1e6
            calls.append({'at':at,'phase':phase,'method':'tools/list','latencyMs':list_ms,'ok':True})
            catalog=[t.model_dump(mode='json') for t in tools]
            assert {t.name for t in tools} == {'get_status','list_documents','read_entities','start_job','get_job','apply_job','discard_job'}
            status, status_ms=await call(client,'get_status',phase)
            assert status['bridge']['reachable'] and status['worker']['available']
            trials.append({'phase':phase,'initializeMs':init_ms,'catalogMs':list_ms,'statusMs':status_ms,
                           'connectionMs':(time.perf_counter_ns()-start)/1e6})
    samples=[]
    start=time.perf_counter_ns(); at=now()
    async with Client(endpoint, timeout=10) as client:
        calls.append({'at':at,'phase':'idle-probe','method':'initialize','latencyMs':(time.perf_counter_ns()-start)/1e6,'ok':True})
        start=time.perf_counter_ns(); at=now(); probe_tools=await client.list_tools()
        calls.append({'at':at,'phase':'probe-preflight','method':'tools/list','latencyMs':(time.perf_counter_ns()-start)/1e6,'ok':True})
        assert {t.name for t in probe_tools} == {t['name'] for t in catalog}
        await call(client,'get_status','probe-preflight')
        docs_before,_=await call(client,'list_documents','preservation-before')
        for _ in range(20):
            _,elapsed=await call(client,'get_status','idle-probe'); samples.append(elapsed)
            await asyncio.sleep(.05)
        docs_after,_=await call(client,'list_documents','preservation-after')
        metadata_results = None
        if metadata:
            assert len(docs_after) == 1 and docs_after[0]['path'] == metadata['fixture'], docs_after
            document_id = docs_after[0]['id']; checks = 0; measurements = []
            async def read(names, phase, fields=None, error=None):
                nonlocal checks
                fields = fields or metadata['fields']
                args = {'document_id':document_id, 'entities':[{'kind':'glyph','id':n} for n in names], 'fields':fields}
                result, elapsed = await call(client, 'read_entities', phase, args, error)
                if not error:
                    assert len(result) == len(names), result
                    for name, row in zip(names, result):
                        assert row['entity'] == {'kind':'glyph','id':name}, row
                        expected_row = {f:metadata['expected'][name][f] for f in fields}
                        assert row['values'] == expected_row, (name, row, expected_row)
                        checks += len(fields)
                measurements.append({'phase':phase, 'targets':len(names), 'latencyMs':elapsed})
                return elapsed
            for phase in ('first','warmup','trial-1','trial-2','trial-3','trial-4','trial-5'):
                await read(metadata['core'], phase+'-core')
                await read(metadata['batch'][:100], phase+'-bounded-batch')
            for _ in range(20): await read(metadata['core'], 'metadata-probe')
            await read(['A','a','missing.name'], 'mixed-missing', error='target_not_found')
            await read(['A','a'], 'known-subset-retry')
            await read(['meta.multi'], 'primary-unicode', ['unicode'])
            await read(['meta.multi'], 'complete-unicodes', ['unicodes'], 'unsupported_read')
            await read([], 'empty', error='invalid_request')
            await read(metadata['batch'], 'over-bound', error='invalid_request')
            metadata_results = {'correctFields':checks, 'measurements':measurements,
                'coreHttp':stats([r['latencyMs'] for r in measurements if r['phase'].startswith('trial-') and r['phase'].endswith('-core')]),
                'batch100Http':stats([r['latencyMs'] for r in measurements if r['phase'].startswith('trial-') and r['phase'].endswith('-bounded-batch')]),
                'probeHttp':stats([r['latencyMs'] for r in measurements if r['phase']=='metadata-probe'])}
    return {'trials':trials, 'calls':calls, 'initialize':init, 'catalog':catalog,'status':status,
            'connection':stats([t['connectionMs'] for t in trials if t['phase'].startswith('trial-')]),
            'statusHttpRoundTrip':stats(samples), 'documentsBefore':docs_before,'documentsAfter':docs_after,
            'metadata':metadata_results}


def run(args):
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    expected={}
    for component, root in (('sidecar', args.sidecar), ('bridge', args.bridge)):
        if (root/'glyphs-mcp-release.json').exists():
            helper_path=args.sidecar/'glyphs_mcp_protocol/identity.py'
            spec=importlib.util.spec_from_file_location('qualification_identity', helper_path)
            helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
            evidence=helper.component_identity(root)
            assert evidence['codeHash'], evidence
            expected[component]={key:evidence[key] for key in ('release','codeHash','runtimeId')}
        else:
            expected[component]={component+'Version':'0.1.0'}

    facts={'startedAt':now(),'hostLoadBefore':os.getloadavg(),'logicalCPUs':os.cpu_count(),
           'instrumented':not args.no_instrument,'errors':[], 'application':str(args.application),
           'targetMode':'native-source-with-explicit-font-list' if args.fixture else 'empty-native-host',
           'sidecarRoot':str(args.sidecar.resolve()),'bridgeRoot':str(args.bridge.resolve())}
    with tempfile.TemporaryDirectory(prefix='gmcp-identity-') as temporary:
        tmp=Path(temporary)
        metadata = None
        if args.fixture:
            metadata = json.loads(args.expected.read_text())
            baseline_hash = hashlib.sha256(args.fixture.read_bytes()).hexdigest()
            assert baseline_hash == metadata['baselineSHA256']
            fixture = tmp/'MetadataDisposable.glyphs'; shutil.copy2(args.fixture, fixture)
            metadata['fixture'] = str(fixture)
        cfg={'sidecar':str(args.sidecar.resolve()),'bridgeResources':str(args.bridge.resolve()/'Contents/Resources'),
             'token':secrets.token_urlsafe(32), 'port':unused_port(), 'jobs':str(tmp/'jobs'),
             'glyphsCLI':str(args.glyphs_cli),'application':str(args.application),
             'instrument':not args.no_instrument,'stop':str(tmp/'stop'), 'bridgeReady':str(tmp/'ready'),
             'fixture':metadata['fixture'] if metadata else None,
             'bridgeTimings':str(output/'bridge-timings.json'),'sidecarTimings':str(output/'sidecar-timings.json'),
             'sidecarReadTimings':str(output/'sidecar-read-timings.json')}
        path=tmp/'config.json'; write(path,cfg); path.chmod(0o600)
        env={**os.environ,'GMCP_QUALIFICATION_CONFIG':str(path),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
        script=str(Path(__file__).resolve()); bridge=None; sidecar=None
        with (output/'native-process.log').open('w') as native_log, (output/'sidecar-process.log').open('w') as sidecar_log:
            try:
                bridge=subprocess.Popen([str(args.glyphs_cli),'run','--quiet','--app',str(args.application),'--plugins','',script], env={**env,'GMCP_QUALIFICATION_ROLE':'bridge'},stdout=native_log,stderr=subprocess.STDOUT)
                ready=wait_ready(cfg['bridgeReady'],bridge); cfg['bridgePort']=ready['port']; facts['host']=ready['host']; write(path,cfg)
                sidecar=subprocess.Popen([sys.executable,'-B',script,'--role','sidecar'],env=env,stdout=sidecar_log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+20
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1',cfg['port']),timeout=.1): break
                    except OSError:
                        if sidecar.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Sidecar did not start')
                        time.sleep(.05)
                facts['endpoint']='http://127.0.0.1:'+str(cfg['port'])+'/mcp/'
                facts.update(asyncio.run(measure(facts['endpoint'], expected, metadata)))
            except Exception as exc:
                facts['errors'].append(type(exc).__name__+': '+str(exc))
            finally:
                if sidecar is not None:
                    sidecar.terminate()
                    try: sidecar.wait(timeout=10)
                    except subprocess.TimeoutExpired: sidecar.kill(); sidecar.wait(); facts['errors'].append('Sidecar cleanup required kill')
                Path(cfg['stop']).touch()
                if bridge is not None:
                    try: bridge.wait(timeout=10)
                    except subprocess.TimeoutExpired: bridge.kill(); bridge.wait(); facts['errors'].append('Native cleanup required kill')
        if metadata:
            facts['preservation'] = {'baselineBefore':baseline_hash,
                'baselineAfter':hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
                'disposableAfter':hashlib.sha256(fixture.read_bytes()).hexdigest()}
            assert len(set(facts['preservation'].values())) == 1
    for name,key,fields in (('bridge-timings.json','bridgeTiming',('dispatchWaitMs','callbackMs')),
                            ('sidecar-timings.json','sidecarTiming',('bridgeHttpMs','sidecarAssemblyMs','statusTotalMs'))):
        if (output/name).exists():
            data=json.loads((output/name).read_text()); samples=data['samples'] if isinstance(data,dict) else data
            if samples: facts[key]={f:stats([row[f] for row in samples]) for f in fields}
        else: facts['errors'].append('Missing '+name)
    if (output/'bridge-timings.json').exists():
        bridge_data = json.loads((output/'bridge-timings.json').read_text())
        reads = bridge_data.get('nativeReads', [])
        if reads:
            facts['nativeReadTiming'] = {str(n):stats([r['nativeReadMs'] for r in reads if r['targets']==n])
                                        for n in sorted({r['targets'] for r in reads})}
            metadata_callbacks = [row for row in bridge_data['samples'] if any(
                row['startedAtNs'] <= r['startedAtNs'] <= r['finishedAtNs'] <= row['finishedAtNs'] for r in reads)]
            assert len(metadata_callbacks) == len(reads)
            facts['metadataCallbackTiming'] = {f:stats([r[f] for r in metadata_callbacks]) for f in ('dispatchWaitMs','callbackMs')}
    if (output/'sidecar-read-timings.json').exists():
        reads = json.loads((output/'sidecar-read-timings.json').read_text())
        if reads: facts['metadataSidecarTiming'] = {f:stats([r[f] for r in reads]) for f in ('bridgeHttpMs','sidecarAssemblyMs','readTotalMs')}
    facts.update(finishedAt=now(),hostLoadAfter=os.getloadavg())
    write(output/'facts.json',facts)
    print(json.dumps({k:v for k,v in facts.items() if k not in ('calls','trials','catalog','status','initialize')},indent=2))
    if facts['errors']: raise SystemExit(1)


if __name__=='__main__':
    if os.environ.get('GMCP_QUALIFICATION_ROLE')=='bridge': bridge_process()
    elif '--role' in sys.argv: sidecar_process()
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--sidecar',type=Path,required=True); parser.add_argument('--bridge',type=Path,required=True)
        parser.add_argument('--glyphs-cli',type=Path,required=True); parser.add_argument('--application',type=Path,default=Path('/Applications/Glyphs 4.app'))
        parser.add_argument('--output',type=Path,required=True); parser.add_argument('--no-instrument',action='store_true')
        parser.add_argument('--fixture', type=Path); parser.add_argument('--expected', type=Path)
        args = parser.parse_args()
        if bool(args.fixture) != bool(args.expected): parser.error('--fixture and --expected must be supplied together')
        run(args)
