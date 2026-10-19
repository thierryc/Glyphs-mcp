import sys,os,json,plistlib,subprocess
from pathlib import Path
p=Path('/tmp/sidebar-vm-probe');p.mkdir(exist_ok=True)
data={'python':sys.executable,'home':str(Path.home()),'mounts':subprocess.getoutput('mount'),'apps':[],'runtimes':[],'plugins':[],'glyphsProcesses':subprocess.getoutput("pgrep -lf Glyphs")}
for app in Path('/Applications').glob('*Glyphs*.app'):
 q=app/'Contents/Info.plist'
 info=plistlib.loads(q.read_bytes()) if q.exists() else {}
 data['apps'].append({'path':str(app),'id':info.get('CFBundleIdentifier'),'version':info.get('CFBundleShortVersionString'),'build':info.get('CFBundleVersion')})
for folder in [Path('/Library/Frameworks'),Path.home()/'Library/Application Support/GlyphsMCP',Path.home()/'Library/Application Support/Glyphs 4']:
 if folder.exists():
  data['runtimes'].append({'path':str(folder),'children':[x.name for x in folder.iterdir()]})
for folder in [Path('/Library/Application Support/GlyphsMCP'),Path.home()/'Library/Application Support/Glyphs 4/Plugins']:
 if folder.exists():data['plugins'].append({'path':str(folder),'children':[x.name for x in folder.iterdir()]})
(p/'inventory.json').write_text(json.dumps(data,indent=2))
print(json.dumps(data,indent=2))

import http.server,functools,threading
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(p))
server=http.server.ThreadingHTTPServer(('192.168.64.5',8766),handler)
threading.Timer(900,server.shutdown).start()
print('Sidebar evidence server active for 15 minutes on VM interface only',flush=True)
server.serve_forever()
server.server_close()
