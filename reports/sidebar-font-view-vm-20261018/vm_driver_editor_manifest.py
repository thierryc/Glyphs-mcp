"""Bounded VirtualBuddy-only full-editor qualification; no installed runtime changes."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import threading
import time
import traceback
import urllib.request
import zipfile

HOST = '192.168.64.1'
APP_SHA = '4f1c05873d7aa3b4ada9f84cfdc06f204f51eb6ff56fe953cd0af6eadf101a5d'
SOURCE_SHA = '01f3397de9427608a1ae6136a139afd9088c5eaefb5ff710370193dd8cca3b7f'
MODEL = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.model'], text=True).strip()
if not MODEL.startswith('VirtualMac'):
    raise SystemExit('This driver is restricted to a disposable macOS VM')
ROOT = Path.home() / ('sidebar-qualification-' + time.strftime('%Y%m%dT%H%M%S'))
ROOT.mkdir()
REPORT = ROOT / 'report'; REPORT.mkdir()
def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')
status = dict(model=MODEL, root=str(ROOT), state='preparing', nativeRuns=0,
              transport='in-process SidecarService/BridgeCore; HTTP and installed-client transport excluded')
write(REPORT/'status.json', status)
# Read-only, bounded evidence endpoint. It accepts only the host and has no commands.
class Evidence(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] != HOST:
            self.send_error(403); return
        if self.path == '/status.json':
            data = (REPORT/'status.json').read_bytes(); content = 'application/json'
        elif self.path == '/report.zip':
            import io
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                for item in REPORT.rglob('*'):
                    if item.is_file() and not item.is_symlink():
                        archive.write(item, str(item.relative_to(REPORT)))
            data = stream.getvalue(); content = 'application/zip'
        else:
            self.send_error(404); return
        self.send_response(200); self.send_header('Content-Type',content)
        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
server = http.server.ThreadingHTTPServer(('192.168.64.5',8775), Evidence)
threading.Thread(target=server.serve_forever, daemon=True).start()
print('Evidence endpoint ready on guest port 8775', flush=True)
def download(name, expected):
    request = urllib.request.Request('http://' + HOST + ':1080/' + name)
    target = ROOT/name
    with urllib.request.urlopen(request, timeout=60) as response, target.open('wb') as stream:
        shutil.copyfileobj(response,stream)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected: raise RuntimeError('Transfer hash mismatch: '+name)
    return target

def terminate(child):
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)

def run_case(variant, preflight=False, repetition=0):
    case = REPORT / ('preflight' if preflight else variant+'-'+str(repetition)); case.mkdir()
    home = ROOT / ('home-'+case.name)
    plugin_dir = home/'Library/Application Support/Glyphs 4/Plugins'
    plugin_dir.mkdir(parents=True)
    shutil.copytree(ROOT/'source/diagnostic.glyphsPlugin', plugin_dir/'Sidebar Isolation Probe.glyphsPlugin')
    (home/'Library/Preferences').mkdir(parents=True)
    (home/'Library/Caches').mkdir(parents=True)
    tmp = ROOT/('tmp-'+case.name); tmp.mkdir()
    meta = dict(root=str(ROOT),app=str(app),identifier='com.GeorgSeifert.Glyphs4',
                home=str(home),probe=str(case),repo=str(ROOT/'source'),variant=variant,preflight=preflight)
    setup = ROOT/('setup-'+case.name+'.json');write(setup,meta)
    # The VM owns its normal trial preferences. Never read host-user preferences.
    # Deny fallback loading of pre-existing guest third-party plugins as well.
    denied = [Path.home()/('Library/Application Support/'+version+'/'+folder)
              for version in ('Glyphs 3','Glyphs 4') for folder in ('Plugins','Plugins (Disabled)')]
    sandbox = ROOT/('sandbox-'+case.name+'.sb')
    sandbox.write_text('(version 1)\n(allow default)\n(deny appleevent-send)\n'+

        '\n'.join('(deny file-read* (subpath '+json.dumps(str(p))+'))' for p in denied)+'\n')
    env = dict(os.environ, CFFIXED_USER_HOME=str(home),TMPDIR=str(tmp),
        MCP_ISOLATED_GUI_SETUP=str(setup),GLYPHS_MCP_SIDEBAR_REPORT_DIR=str(case),
        GLYPHS_MCP_SIDEBAR_PARENT_PGID=str(os.getpgrp()),PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONNOUSERSITE',None)
    command = ['/usr/bin/sandbox-exec','-f',str(sandbox),str(app/'Contents/MacOS/Glyphs 4'),
        '-ApplePersistenceIgnoreState','YES','-NSQuitAlwaysKeepsWindows','NO',
        '-GSPythonFrameworkPath',str(framework),'-SUEnableAutomaticChecks','NO',
        '-SUAutomaticallyUpdate','NO','-GSShowScriptingWindow','NO']
    for label, prefix in [('plain', []),('sandbox', ['/usr/bin/sandbox-exec','-f',str(sandbox)])]:
        check=subprocess.run(prefix+['/usr/bin/codesign','--verify','--deep','--strict','--verbose=2',str(app)],capture_output=True,text=True,timeout=20,env=env)
        write(case/('signature-'+label+'.json'),dict(returncode=check.returncode,stdout=check.stdout,stderr=check.stderr))
    status['sandboxBoundary']='VM filesystem boundary; child denies Apple Events and original guest plugin reads'
    write(REPORT/'status.json',status)
    start=time.monotonic();reason='exited'; child=None
    with (case/'gui.stdout.log').open('w') as out, (case/'gui.stderr.log').open('w') as err:
        try:
            child=subprocess.Popen(command,env=env,stdout=out,stderr=err,start_new_session=True)
            write(case/'started.json',dict(pid=child.pid,command=command))
            while child.poll() is None:
                result=case/'result.json'
                if result.exists():
                    data=json.loads(result.read_text())
                    if data.get('outcome')=='passed' or data.get('error'):
                        reason='completed';break
                if (case/'loader-error.txt').exists():reason='loader-error';break
                if (case/'events.jsonl').exists() and '"event": "alert"' in (case/'events.jsonl').read_text():
                    reason='alert';break
                if time.monotonic()-start > (900 if preflight else 180):reason='timeout';break
                time.sleep(.1)
        finally:
            if child:terminate(child)
    write(case/'launch.json',dict(reason=reason,pid=child.pid if child else None,
        seconds=time.monotonic()-start,exitCode=child.returncode if child else None))
    status['nativeRuns']+=1
    data=json.loads((case/'result.json').read_text()) if (case/'result.json').exists() else {}
    ok=reason=='completed' and data.get('outcome')=='passed' and data.get('uiQualified') is True
    status.update(state='running' if ok else 'blocked',lastCase=case.name,lastReason=reason)
    write(REPORT/'status.json',status)
    return ok
try:
    app_zip=download('glyphs4202.zip',APP_SHA)
    source_zip=download('source9.zip',SOURCE_SHA)
    subprocess.run(['/usr/bin/ditto','-x','-k',str(app_zip),str(ROOT)],check=True)
    with zipfile.ZipFile(source_zip) as archive:archive.extractall(ROOT/'source')
    app=ROOT/'Glyphs 4.app'
    info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if str(info['CFBundleVersion'])!='4202':raise RuntimeError('Wrong app build')
    framework=Path.home()/'Library/Application Support/Glyphs 4/Repositories/Python/Python.framework/Versions/3.14'
    if not (framework/'Python').is_file():raise RuntimeError('Native Python framework missing')
    write(REPORT/'identity.json',dict(model=MODEL,version=info.get('CFBundleShortVersionString'),
        build=info['CFBundleVersion'],framework=str(framework),archiveSha256=APP_SHA,
        sourceArchiveSha256=SOURCE_SHA,executableSha256=hashlib.sha256((app/'Contents/MacOS/Glyphs 4').read_bytes()).hexdigest()))
    if run_case('baseline',True):
        status['state']='ui-qualified';write(REPORT/'status.json',status)
        for variant in ('baseline','batching-only','suppression-only','combined'):
            for repetition in range(1,6):
                if not run_case(variant,False,repetition):raise RuntimeError('Native case failed: '+variant+'-'+str(repetition))
        status['state']='completed';write(REPORT/'status.json',status)
except BaseException:
    (REPORT/'driver-error.txt').write_text(traceback.format_exc())
    status['state']='blocked';write(REPORT/'status.json',status)
finally:
    print(json.dumps(status,indent=2),flush=True)
    # Leave reports available for collection, then close the endpoint automatically.
    time.sleep(1200)
    server.shutdown();server.server_close()
