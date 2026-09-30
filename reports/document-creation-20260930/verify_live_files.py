import json,sys
from pathlib import Path
from Foundation import NSURL
from GlyphsApp import GSFont
root=Path(__file__).resolve().parent
repo=root.parents[1]
sys.path.insert(0,str(repo/'src/bridge'))
sys.path.insert(0,str(repo/'src/protocol'))
from glyphs_mcp_bridge.context import value
inputs=json.loads((root/'live-inputs.json').read_text())
report=json.loads((root/'live-verification.json').read_text())
checks=[]
for item,check in zip(inputs,report['checks']):
    f,error=GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(item['destination']),None)
    assert f is not None and error is None
    assert f.familyName==item['family_name'] and f.upm==1000
    assert len(f.masters)==len(f.instances)==1 and len(f.glyphs)==0
    assert f.masters[0].name==f.instances[0].name=='Regular'
    created=next(call['result']['data'] for call in report['calls'] if call['name']=='create_document' and call['arguments']['family_name']==item['family_name'])
    assert [value(f.masters[0],'id')]==created['masterIds']
    assert [value(f.instances[0],'id')]==created['instanceIds']
    checks.append({'destination':item['destination'],'nativeReopenVerified':True,'nativeIdsPersisted':True})
(root/'live-files-reopened.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks))
