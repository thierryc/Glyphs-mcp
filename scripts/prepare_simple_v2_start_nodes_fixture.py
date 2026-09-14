"""Prepare controlled cyclic offsets externally, without saving a font."""

import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
for part in ('sidecar','protocol'):sys.path.insert(0,str(ROOT/'src'/part))
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_sidecar.spacing import exact_copy
from glyphs_mcp_sidecar.spacing_job import layer_hash
from glyphs_mcp_sidecar.source import source_hash

config=json.loads((ROOT/'build/lean-benefits-current.json').read_text())
source=Path(config['source']);assert source.is_relative_to('/private/tmp')
assert source_hash(Path(config['original']))==config['originalHash']
font=_load_font(source);glyph=font.glyphs['o'];changes=[]
for master in list(font.masters)[1:]:
    layer=glyph.layers[master.id];candidate=exact_copy(layer);path=candidate.paths[0]
    index=next(i for i,n in enumerate(path.nodes) if str(n.type)!='offcurve')
    shift=index+1;assert shift<len(path.nodes)
    path.makeNodeFirst_(path.nodes[index])
    changes.append(dict(kind='start_node',glyph='o',layer=str(master.id),path=0,shift=shift,nodeCount=len(path.nodes),
        beforeHash=layer_hash(layer),afterHash=layer_hash(candidate)))
result=dict(sourceHash=source_hash(source),changes=changes)
(ROOT/'build/start-node-fixture-plan.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'targets':len(changes),'sourceUnchanged':source_hash(source)==result['sourceHash']}))
