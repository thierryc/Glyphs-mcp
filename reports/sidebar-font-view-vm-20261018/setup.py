import json,os,sys,subprocess,plistlib
from pathlib import Path
p=Path('/tmp/sidebar-vm-probe')
p.mkdir(exist_ok=True)
data={}
for base in [Path('/Applications/Glyphs 4.app/Contents/Frameworks'),Path('/Users/ziggy/Library/Application Support/Glyphs MCP/lean-v2/runtime'),Path('/Applications/Glyphs MCP.app/Contents/Resources'),Path('/Users/ziggy/Library/Application Support/Glyphs 4/Repositories')]:
 if base.exists():
  data[str(base)]=[str(f.relative_to(base)) for f in base.rglob('*') if f.name in ['Python','Python.framework','python3','site-packages','pyvenv.cfg']][:60]
pref=Path('/Users/ziggy/Library/Preferences/com.GeorgSeifert.Glyphs4.plist')
if pref.exists():
 values=plistlib.loads(pref.read_bytes())
 data['pythonSettings']={k:v for k,v in values.items() if 'python' in k.lower()}
q=Path('/Users/ziggy/Library/Application Support/Glyphs MCP/lean-v2/runtime/bin/python3')
if q.exists():
 r=subprocess.run([str(q),'-c','import sys; print(sys.version); import objc; print(objc.__file__); import fastmcp; print(fastmcp.__file__)'],capture_output=True,text=True,timeout=10)
 data['runtimeInspection']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
(p/'runtime.json').write_text(json.dumps(data,indent=2));print(json.dumps(data,indent=2))

import http.server,functools,threading
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(p))
server=http.server.ThreadingHTTPServer(('192.168.64.5',8766),handler)
timer=threading.Timer(1800,server.shutdown);timer.daemon=True;timer.start()
print('Evidence available for 30 minutes',flush=True)
try:server.serve_forever()
finally:timer.cancel();server.server_close()
