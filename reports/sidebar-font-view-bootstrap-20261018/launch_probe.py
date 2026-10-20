from pathlib import Path
import os, json, subprocess, sys, time, hashlib
sys.path.insert(0, '/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/scripts')
from run_sidebar_count_experiment import terminate_child, alert_recorded
m = json.loads(Path(__file__).with_name('setup.json').read_text())
root = Path(m['root']); probe = Path(m['probe'])
assert not (probe/'result.json').exists()
checks = {}
for relative in ('Contents/Info.plist', 'Contents/MacOS/Glyphs 4'):
    source = (Path('/Applications/Glyphs 4.app')/relative).read_bytes()
    copy = (Path(m['app'])/relative).read_bytes()
    assert source == copy
    checks[relative] = hashlib.sha256(copy).hexdigest()
env = dict(os.environ, CFFIXED_USER_HOME=m['home'],
           MCP_ISOLATED_GUI_SETUP=str(root/'setup.json'),
           GLYPHS_MCP_SIDEBAR_REPORT_DIR=str(probe),
           GLYPHS_MCP_SIDEBAR_PARENT_PGID=str(os.getpgrp()), PYTHONDONTWRITEBYTECODE='1')
env.pop('PYTHONNOUSERSITE', None)
env['TMPDIR'] = str(root/'tmp')
source = '''import json
from Foundation import NSBundle,NSHomeDirectory,NSUserDefaults
from GlyphsApp import GSGlyphsInfo
b=NSBundle.mainBundle();print(json.dumps({'id':str(b.bundleIdentifier()),'home':str(NSHomeDirectory()),'support':str(GSGlyphsInfo.applicationSupportPath()),'preferenceCount':len(NSUserDefaults.standardUserDefaults().persistentDomainForName_(b.bundleIdentifier()) or {})}),flush=True)
'''
command = ['/usr/bin/sandbox-exec', '-f', str(root/'isolation.sb')]
proof = subprocess.run(command+['/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs', 'run',
    '--app', m['app'], '--plugins', '', '--python', '/Library/Frameworks/Python.framework/Versions/3.14/Python',
    '-c', source], capture_output=True, text=True, timeout=20, start_new_session=True, env=env)
(root/'isolation-preflight.json').write_text(proof.stdout)
(root/'isolation-preflight.stderr.log').write_text(proof.stderr)
assert proof.returncode == 0, proof.stderr
pjson = json.loads(proof.stdout)
assert pjson['preferenceCount'] == 0
assert Path(pjson['home']).resolve() == Path(m['home']).resolve()
assert Path(pjson['support']).resolve().is_relative_to(Path(m['home']).resolve())
command += [str(Path(m['app'])/'Contents/MacOS/Glyphs 4'), '-ApplePersistenceIgnoreState', 'YES',
    '-NSQuitAlwaysKeepsWindows', 'NO', '-GSPythonFrameworkPath', '/Library/Frameworks/Python.framework/Versions/3.14',
    '-SUEnableAutomaticChecks', 'NO', '-SUAutomaticallyUpdate', 'NO', '-GSShowScriptingWindow', 'NO']
with (root/'gui.stdout.log').open('w') as out, (root/'gui.stderr.log').open('w') as err:
    p = subprocess.Popen(command, stdout=out, stderr=err, env=env, start_new_session=True)
    started = time.monotonic(); reason = 'exited'; sampled = False
    (root/'started.json').write_text(json.dumps({'pid':p.pid,'command':command}))
    try:
        while p.poll() is None:
            if not sampled and time.monotonic()-started > 8:
                sampled = True
                r = subprocess.run(['/usr/bin/sample',str(p.pid),'1','1','-file',str(root/'startup-sample.txt')],capture_output=True,text=True,timeout=12)
                (root/'sample-command.txt').write_text(str(r.returncode)+'\n'+r.stdout+r.stderr)
            if (probe/'result.json').exists():
                data = json.loads((probe/'result.json').read_text())
                if data.get('phase') != 'imports' and ('error' in data or data.get('outcome') == 'passed'):
                    reason = 'probe completed'; break
            if (probe/'loader-error.txt').exists(): reason = 'loader error'; break
            if alert_recorded(probe/'events.jsonl'): reason = 'alert'; break
            if time.monotonic()-started > 45: reason = 'timeout'; break
            time.sleep(.1)
    finally:
        terminate_child(p)
(root/'launch.json').write_text(json.dumps(dict(command=command, pid=p.pid, exitCode=p.returncode,
    reason=reason, seconds=time.monotonic()-started, unchangedSourceHashes=checks), indent=2)+'\n')
print('reason', reason, 'exit', p.returncode, 'root', root)
for name in ('loader.json', 'result.json', 'loader-error.txt'):
    if (probe/name).exists(): print(name, (probe/name).read_text()[:6500])
