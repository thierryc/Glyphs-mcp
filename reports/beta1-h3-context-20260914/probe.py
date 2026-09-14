from GlyphsApp import Glyphs
from pathlib import Path
import json, shutil, traceback, hashlib
OUT=Path('/private/tmp/glyphs-h3-20260914'); OUT.mkdir(exist_ok=True)
BASE=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/reports/v1-v2/06-selection-inspection/SelectionInspectionTest.glyphs')
def safe(fn):
    try: return fn()
    except Exception as e: return {'error':str(e)}
def collection(c, attr):
    if c is None: return None
    return dict(type=type(c).__name__, count=safe(lambda:len(c)), first=safe(lambda:[str(getattr(c[i],attr)) for i in range(min(6,len(c)))]))
def state(f):
    wc=f.parent.windowController(); bar=wc.tabBarControl()
    return dict(path=str(f.filepath), current=str(Glyphs.font.filepath), dirty=bool(f.parent.isDocumentEdited()),
       tabType=type(f.currentTab).__name__, tab=str(f.currentTab),
       fontViewType=type(f.fontView).__name__,selectedTab=safe(lambda:str(bar.selectedTabItem())),
       selectedTabType=safe(lambda:type(bar.selectedTabItem()).__name__),
       selectedMaster=safe(lambda:{'id':str(f.selectedFontMaster.id),'name':str(f.selectedFontMaster.name)}),
       glyphSelection=collection(f.selection,'name'),selectedLayers=collection(f.selectedLayers,'layerId'),
       layerGlyphs=safe(lambda:[str(f.selectedLayers[i].parent.name) for i in range(min(6,len(f.selectedLayers)))]))
try:
    protected=[state(f) for f in Glyphs.fonts]
    out={'protectedBefore':protected,'states':[]}
    source=OUT/'H3-A.glyphs';shutil.copyfile(BASE,source)
    f=Glyphs.open(str(source),True)
    out['states'].append({'case':'opened',**state(f)})
    f.selection=[f.glyphs['control'],f.glyphs['mixed']]
    out['states'].append({'case':'font-multiple',**state(f)})
    for i in range(3):
        f.masterIndex=i;out['states'].append({'case':'master-'+str(i),**state(f)})
    f.selection=[];out['states'].append({'case':'font-empty',**state(f)})
    tab=f.newTab('/control/mixed/control')
    out['states'].append({'case':'edit-repeated',**state(f)})
    f.currentTab=f.fontView
    out['states'].append({'case':'font-after-tab',**state(f)})
    out['protectedAfter']=[state(x) for x in Glyphs.fonts if x is not f]
    (OUT/'native-probe.json').write_text(json.dumps(out,indent=2))
    print('H3 PROBE COMPLETE',OUT/'native-probe.json')
except Exception:
    (OUT/'native-probe-error.txt').write_text(traceback.format_exc());traceback.print_exc()
