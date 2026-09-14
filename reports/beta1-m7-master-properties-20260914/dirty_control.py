"""Fresh-copy host-only controls: no MCP reads and no runtime instrumentation."""
from GlyphsApp import Glyphs
from pathlib import Path
from threading import Thread
import json,time,sys,traceback,hashlib
from glyphs_mcp_bridge.main_thread import CocoaMainThread
S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop')
OUT=S/'reports/beta1-m7-master-properties-20260914';T=Path('/private/tmp/glyphs-m7-20260914')
sys.path.insert(0,str(OUT));import m7_oracle as oracle
main=CocoaMainThread(timeout=60);result=[];box={}
def state():
    f=box['font'];return dict(dirty=bool(f.parent.isDocumentEdited()),data=oracle.digest(oracle.snapshot(f)))
def run():
    try:
        for trial in range(2):
            p=T/('dirty-host-control-'+str(trial)+'.glyphs');p.write_bytes((OUT/'MasterPropertiesBound.glyphs').read_bytes())
            main.call(lambda:box.update(font=Glyphs.open(str(p),True)))
            samples=[];start=time.perf_counter()
            for i in range(12):
                samples.append(dict(ms=(time.perf_counter()-start)*1000,**main.call(state)));time.sleep(.2)
            result.append(dict(trial=trial,publicMCPCalls=0,samples=samples));main.call(lambda:box.pop('font').close(ignoreChanges=True))
    except Exception:result.append(dict(error=traceback.format_exc()))
    finally:
        if box:main.call(lambda:box.pop('font').close(ignoreChanges=True))
        (OUT/'dirty-host-control.json').write_text(json.dumps(result,indent=2));print('M7 HOST DIRTY CONTROL COMPLETE')
Thread(target=run,daemon=True).start()
