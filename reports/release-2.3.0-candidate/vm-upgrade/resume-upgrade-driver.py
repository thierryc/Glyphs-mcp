import hashlib,http.server,json,os,plistlib,shutil,subprocess,threading,time,urllib.request
from pathlib import Path
model=subprocess.check_output(['/usr/sbin/sysctl','-n','hw.model'],text=True).strip()
assert model.startswith('VirtualMac')
assert subprocess.check_output(['/usr/bin/sw_vers','-productVersion'],text=True).strip()=='14.6.1'
root=Path.home()/'gmcp-release-230-final-r1';assert root.is_dir()
receipt=Path.home()/'Library/Application Support/Glyphs MCP/lean-v2/installation.json'
record=dict(state='waiting-for-signed-candidate',macOS='14.6.1',model=model,startedAt=time.time(),componentReceiptBeforeSHA256=hashlib.sha256(receipt.read_bytes()).hexdigest())
stop=threading.Event();app=None;reference=None
class Report(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.client_address[0]!='192.168.64.1' or self.path!='/report.json':self.send_error(404);return
  value=dict(record)
  value['componentReceiptUnchanged']=hashlib.sha256(receipt.read_bytes()).hexdigest()==record['componentReceiptBeforeSHA256']
  if app and (app/'Contents/Info.plist').exists():
   info=plistlib.loads((app/'Contents/Info.plist').read_bytes());value.update(currentVersion=info.get('CFBundleShortVersionString'),currentBuild=info.get('CFBundleVersion'))
  for name in ['stderr.log','stdout.log','requests.log']:
   p=root/name
   if p.exists():value[name]=p.read_text(errors='replace')[-14000:]
  (root/'resume-report.json').write_text(json.dumps(value,indent=2)+'\n')
  data=json.dumps(value,indent=2).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  if self.client_address[0]!='192.168.64.1' or self.path!='/complete':self.send_error(404);return
  stop.set();self.send_response(204);self.end_headers()
server=http.server.ThreadingHTTPServer(('0.0.0.0',8790),Report);threading.Thread(target=server.serve_forever,daemon=True).start()
def tree(path):
 h=hashlib.sha256()
 for p in sorted(path.rglob('*')):
  n=p.relative_to(path).as_posix().encode()
  if p.is_symlink():v=('link:'+os.readlink(p)).encode()
  elif p.is_file():v=hashlib.sha256(p.read_bytes()).digest()
  else:continue
  h.update(n+b'\0'+v+b'\0')
 return h.hexdigest()
try:
 deadline=time.monotonic()+6600
 while time.monotonic()<deadline and not stop.is_set():
  try:
   with urllib.request.urlopen('http://192.168.64.1:1080/manifest.json',timeout=5) as response:meta=json.load(response)
   break
  except Exception:stop.wait(5)
 else:raise TimeoutError('Signed candidate was not staged')
 assert meta['version']=='2.3.0' and meta['build']==68
 assert shutil.disk_usage(root).free>2_000_000_000
 record['archiveSHA256']=meta['archiveSHA256']
 assert hashlib.sha256((root/'candidate.zip').read_bytes()).hexdigest()==meta['archiveSHA256']
 assert hashlib.sha256((root/'update.xml').read_bytes()).hexdigest()==meta['feedSHA256']
 reference=root/'reference/Glyphs MCP.app'
 app=root/'upgrade/Glyphs MCP.app'
 assert hashlib.sha256((app/'Contents/MacOS/Glyphs MCP').read_bytes()).hexdigest()==meta['baselineExecutableSHA256']
 assert not any('/Glyphs MCP.app/Contents/MacOS/' in x for x in subprocess.check_output(['/bin/ps','-axo','comm='],text=True).splitlines()),'Quit the VM desktop companion before testing'
 for candidate in (reference,app):subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(candidate)],check=True,timeout=90)
 record['resumedAfterVMRestart']=True
 class Feed(http.server.SimpleHTTPRequestHandler):
  def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
  def do_GET(self):
   if self.path not in ('/update.xml','/candidate.zip'):self.send_error(404);return
   with (root/'requests.log').open('a') as log:log.write(json.dumps(dict(path=self.path,time=time.time()))+'\n')
   super().do_GET()
  def list_directory(self,path):self.send_error(403)
 feed=http.server.ThreadingHTTPServer(('127.0.0.1',8788),Feed);threading.Thread(target=feed.serve_forever,daemon=True).start()
 args=[str(app/'Contents/MacOS/Glyphs MCP'),'-SUFeedURL','http://127.0.0.1:8788/update.xml','-SUEnableAutomaticChecks','YES','-SUScheduledCheckInterval','3600']
 child=subprocess.Popen(args,stdout=(root/'stdout.log').open('w'),stderr=(root/'stderr.log').open('w'),start_new_session=True)
 record.update(state='signed-2.2.0-launched',oldPID=child.pid,beforeVersion='2.2.0',beforeBuild='67',arguments=args,baselineExecutableSHA256=meta['baselineExecutableSHA256'])
 print('Exact signed 2.2.0 launched; awaiting standard update acceptance.',flush=True)
 while time.monotonic()<deadline and not stop.is_set():
  info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
  if info.get('CFBundleVersion')=='68':
   subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True,timeout=90)
   actual=tree(app);expected=tree(reference);assert actual==expected
   record.update(state='signed-2.3.0-upgrade-verified',version='2.3.0',build='68',exactApplicationTreeSHA256=actual,referenceApplicationTreeSHA256=expected,signatureVerified=True,componentReceiptUnchanged=hashlib.sha256(receipt.read_bytes()).hexdigest()==record['componentReceiptBeforeSHA256'])
   break
  stop.wait(1)
 while time.monotonic()<deadline and not stop.is_set():stop.wait(1)
except BaseException as error:
 record.update(state='failed',errorType=type(error).__name__,error=str(error));print(json.dumps(record,indent=2),flush=True)
 while not stop.wait(1) and time.monotonic()<deadline:pass
finally:
 (root/'resume-final-record.json').write_text(json.dumps(record,indent=2)+'\n')
 server.shutdown();server.server_close()
 if 'feed' in locals():feed.shutdown();feed.server_close()
