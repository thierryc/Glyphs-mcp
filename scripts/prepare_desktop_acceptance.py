"""Create isolated native-save controls for the desktop's visible font gate."""
import json
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/sidecar'), str(ROOT/'src/protocol')]
from glyphs_mcp_sidecar.source import source_hash
from GlyphsApp import GSFont, GSPackageBundle
from Foundation import NSURL

OUT = ROOT/'build/desktop-acceptance'
if (OUT/'config.json').exists():
    raise RuntimeError('Existing acceptance evidence must be preserved.')
original = Path.home()/'Documents/fonts/Dactylotype/Dactylotype.glyphspackage'
fingerprint = source_hash(original)
assert fingerprint == 'sha256:7f87019f3fe677999f7c45f498ef5d68e2ba1a2d21ded2cd2387c56f1354e5b2', fingerprint
folder = Path(tempfile.mkdtemp(prefix='glyphs-m7-live-')).resolve()
source, control = [folder/name for name in ('Dactylotype-M7-Acceptance.glyphspackage', 'Dactylotype-M7-Native-Control.glyphspackage')]
for destination in (source, control):
    shutil.copytree(original, destination)
    loaded = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(destination)), None)
    font = loaded[0] if isinstance(loaded, tuple) else loaded
    assert font is not None
    result = font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(destination)), GSPackageBundle, None)
    assert result[0], result
assert source_hash(original) == fingerprint
settings = plistlib.loads((Path.home()/'Library/LaunchAgents/com.ap.cx.glyphs-mcp-sidecar.plist').read_bytes())
arguments = settings['ProgramArguments']; port = arguments[arguments.index('--port')+1]
OUT.mkdir(parents=True, exist_ok=True)
config = {'folder':str(folder), 'source':str(source), 'control':str(control), 'original':str(original),
          'originalHash':fingerprint, 'endpoint':f'http://127.0.0.1:{port}/mcp/'}
(OUT/'config.json').write_text(json.dumps(config,indent=2)+'\n')
print(json.dumps(config), flush=True)
