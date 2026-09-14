#!/usr/bin/env python3
"""Local-only signed Sparkle acceptance fixture; never changes release artifacts."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
from urllib.parse import urlparse

from prepare_desktop_update import feed
from release_payload import IDENTITY, verify_code

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/update-trial'


def prepare(port):
    app = ROOT / 'dist/installer-app/Glyphs MCP.app'
    verify_code(app)
    subprocess.run(['/usr/bin/xcrun', 'stapler', 'validate', str(app)], check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    older = OUT / 'Glyphs MCP.app'
    if older.exists():
        raise ValueError('The older trial fixture already exists; preserve its evidence.')
    shutil.copytree(app, older, symlinks=True)
    info_path = older / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    version, build = info['CFBundleShortVersionString'], int(info['CFBundleVersion'])
    channel, beta_number = info.get('GMCPReleaseChannel', 'stable'), info.get('GMCPBetaNumber', 0)
    if build < 2: raise ValueError('Update trial requires a previous positive build number')
    info.update(CFBundleVersion=str(build - 1),
                SUFeedURL=f'http://localhost:{port}/appcast.xml')
    # Only this disposable older fixture permits an HTTP localhost feed.
    # The release app continues to use its signed HTTPS GitHub feed.
    info['NSAppTransportSecurity'] = {'NSAllowsLocalNetworking': True}
    info_path.write_bytes(plistlib.dumps(info))
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', IDENTITY,
                    '--timestamp', '--options', 'runtime', str(older)], check=True)
    verify_code(older)
    archive = OUT / 'new.zip'
    shutil.copy2(ROOT / 'dist/installer-app/Glyphs MCP.zip', archive)
    signer = str(ROOT / 'build/desktop-dependencies/bin/sign_update')
    signature = subprocess.check_output([signer, '--account', 'cx.ap.glyphsMcp', '-p', str(archive)], text=True).strip()
    subprocess.run([signer, '--account', 'cx.ap.glyphsMcp', '--verify', str(archive), signature], check=True)
    for mode in ('valid', 'bad-archive', 'interrupted'):
        signed = signature if mode != 'bad-archive' else ('A' if signature[0] != 'A' else 'B') + signature[1:]
        path = OUT / (mode + '.xml')
        path.write_bytes(feed(version, build, f'http://localhost:{port}/{mode}.zip', signed, archive.stat().st_size, channel=channel, beta_number=beta_number))
        subprocess.run([signer, '--account', 'cx.ap.glyphsMcp', str(path)], check=True)
    invalid = (OUT / 'valid.xml').read_bytes().replace(b'Glyphs MCP Desktop', b'Untrusted Desktop')
    (OUT / 'bad-feed.xml').write_bytes(invalid)
    (OUT / 'mode.txt').write_text('bad-feed')
    (OUT / 'fixture.json').write_text(json.dumps({'port': port, 'older': str(older),
        'olderVersion': version, 'olderBuild': build - 1, 'newerVersion': version, 'newerBuild': build,
        'scope': 'Notarized desktop copy with lowered version for full-archive Sparkle acceptance; never published'}, indent=2)+'\n')
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--keepParent', str(older), str(OUT/'older.zip')], check=True)
    print(json.dumps({'older': str(older), 'needsNotarization': str(OUT/'older.zip')}), flush=True)


def serve(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            mode = (OUT/'mode.txt').read_text().strip()
            if path == '/appcast.xml':
                payload = OUT/(mode+'.xml')
            elif path in ('/valid.zip', '/bad-archive.zip', '/interrupted.zip'):
                payload = OUT/'new.zip'
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', 'application/xml' if path.endswith('.xml') else 'application/zip')
            self.send_header('Content-Length', str(payload.stat().st_size))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            with payload.open('rb') as stream:
                if path == '/interrupted.zip':
                    self.wfile.write(stream.read(65536)); self.wfile.flush()
                    self.close_connection = True
                else:
                    try: shutil.copyfileobj(stream, self.wfile)
                    except (BrokenPipeError, ConnectionResetError): pass
        def log_message(self, fmt, *args):
            print(fmt % args, flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(json.dumps({'localTestFeed': f'http://localhost:{port}/appcast.xml'}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'serve'))
    parser.add_argument('--port', type=int, default=18473)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else serve)(args.port)
