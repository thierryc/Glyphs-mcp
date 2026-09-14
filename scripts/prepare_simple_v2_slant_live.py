"""Select existing outline glyphs for a disposable-font slant acceptance gate."""

import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for part in ('sidecar','protocol'):sys.path.insert(0,str(root/'src'/part))
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_sidecar.slant_job import prepare
config=json.loads((root/'build/lean-benefits-current.json').read_text())
font=_load_font(Path(config['source']))
names=[g.name for g in font.glyphs if any(l.paths for l in g.layers) and all(not l.components for l in g.layers if l.layerId==l.associatedMasterId)]
changes,report=prepare(font,{'glyphs':names,'options':{'angle':12,'preserveStraightStems':True}})
result={'glyphs':names,'layers':len(report['layers']),'changes':len(changes),
 'correctedPairs':sum(r.get('correction',{}).get('compensatedPairCount',0) for r in report['layers']),
 'skipped':sum(r['status']=='skipped' for r in report['layers']),
 'byGlyph':{name:sum(r.get('correction',{}).get('compensatedPairCount',0) for r in report['layers'] if r['glyph']==name) for name in names}}
(root/'build/slant-dactylotype-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
