"""Temporary file-only transfer, restricted to this VirtualBuddy guest."""
import http.server,functools,threading
from pathlib import Path
root=Path('/private/tmp/beztrace-milestone-7-v0.2.0-20261012/sidebar')
class Files(http.server.SimpleHTTPRequestHandler):
 def do_GET(self):
  if self.client_address[0] != '192.168.64.5':self.send_error(403);return
  return super().do_GET()
 def list_directory(self,path):self.send_error(403);return None
server=http.server.ThreadingHTTPServer(('192.168.64.1',1080),functools.partial(Files,directory=str(root)))
timer=threading.Timer(3600,server.shutdown);timer.daemon=True;timer.start()
try:server.serve_forever()
finally:timer.cancel();server.server_close()
