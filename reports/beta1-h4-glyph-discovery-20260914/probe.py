from GlyphsApp import Glyphs,GSGlyph
from pathlib import Path
from PyObjCTools import AppHelper
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
import json,re,traceback
OUT=Path('/private/tmp/glyphs-h4-20260914')
BASE=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop/reports/beta1-h3-context-20260914/ContextTest.glyphs')
p=OUT/'probe.glyphs';p.write_text(re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',BASE.read_text(),count=1))
f=Glyphs.open(str(p),True);rows=[]
def safe(fn):
 try:return fn()
 except Exception as e:return {'error':str(e)}
def state(label):
 rows.append(dict(label=label,count=len(f.glyphs),type=type(f.glyphs).__name__,first=[f.glyphs[i].name for i in range(3)],nativeCount=f.count(),nativeChangeCount=safe(lambda:f.parent.changeCount()),generation=life.adapter._generation(f),dirty=bool(f.parent.isDocumentEdited())))
 (OUT/'native-probe.json').write_text(json.dumps(rows,indent=2))
def step(i=0):
 try:
  if i==0:state('initial')
  elif i==1:f.glyphs[0].name='h4renamed';state('rename-immediate')
  elif i==2:state('rename-after-yield');f.selection=[f.glyphs[1]]
  elif i==3:state('selection-after-yield');f.parent.updateChangeCount_(0)
  elif i==4:state('explicit-dirty');f.masterIndex=1
  elif i==5:state('master-after-yield');f.glyphs.append(GSGlyph('h4added'))
  elif i==6:state('add-after-yield');del f.glyphs['h4added']
  elif i==7:state('delete-after-yield');f.close(ignoreChanges=True);print('H4 PROBE COMPLETE');return
  AppHelper.callLater(.25,step,i+1)
 except Exception:
  (OUT/'native-probe-error.txt').write_text(traceback.format_exc());traceback.print_exc()
step()
