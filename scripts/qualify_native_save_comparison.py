"""Diagnose native-save differences without changing either input font."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'/p) for p in ('protocol','bridge','sidecar')]
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from GlyphsApp import GSPackageBundle
from Foundation import NSURL
config=json.loads((ROOT/'build/desktop-acceptance/config.json').read_text())
work=Path(tempfile.mkdtemp(prefix='glyphs-native-save-comparison-')).resolve()
fonts=[];snapshots=[]
for name in ('source','control'):
    path=work/(name+'.glyphspackage');shutil.copytree(config[name],path)
    font=_load_font(path);fonts.append(font)
    snapshots.append({(str(g.name),str(l.layerId)):{'width':float(l.width),'outlineHash':GlyphsAdapter._outline_hash(l)} for g in font.glyphs for l in g.layers})
    result=font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(path)),GSPackageBundle,None)
    assert result[0],result
keys=set(snapshots[0])|set(snapshots[1])
differences=[{'glyph':k[0],'layer':k[1],'source':snapshots[0].get(k),'control':snapshots[1].get(k)} for k in sorted(keys) if snapshots[0].get(k)!=snapshots[1].get(k)]
def files(path):return {str(p.relative_to(path)):p.read_bytes() for p in path.rglob('*') if p.is_file() and p.name not in {'UIState.plist','.DS_Store'}}
a,b=[files(work/(name+'.glyphspackage')) for name in ('source','control')]
result={'work':str(work),'layers':len(keys),'effectiveDifferences':differences,'nativeResavedDifferences':[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]}
(ROOT/'build/desktop-acceptance/native-save-diagnosis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
