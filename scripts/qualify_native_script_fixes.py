"""Native content eligibility and consecutive workflow qualification."""
import base64
import importlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/simple-native-scripting'
sys.path[:0]=[str(BUILD/'sidecar'),str(BUILD/'Glyphs MCP Bridge.glyphsPlugin/Contents/Resources'),str(ROOT/'scripts')]
for name in ('glyphs_mcp_protocol.script_targets','glyphs_mcp_bridge.core','glyphs_mcp_sidecar.service'):
    assert Path(importlib.import_module(name).__file__).is_relative_to(BUILD)
from native_script_harness import Harness
from glyphs_mcp_protocol.script_targets import resolve


def exercise(h):
    checks=[]
    def check(name, passed):
        assert passed,name
        checks.append(name)
    def contents():
        from GlyphsApp import GSBackgroundImage
        image=Path(h.temp.name)/'pixel.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ9sAAAAASUVORK5CYII='))
        managers=[g.undoManager() for g in h.doc.font.glyphs]
        for m in managers:m.disableUndoRegistration()
        try:
            for g in h.doc.font.glyphs:g.layers[h.mid].background.shapes=[]
            h.doc.font.glyphs[0].layers[h.mid].background.backgroundImage=GSBackgroundImage(str(image))
            h.doc.font.glyphs[1].layers[h.mid].background.userData['note']='metadata only'
            h.doc.font.glyphs[2].layers[h.mid].background.attributes['qualification']='attributes only'
            h.doc.font.glyphs[3].layers[h.mid].background.widthMetricsKey='=probe0'
        finally:
            for m in managers:m.enableUndoRegistration()
        rows,skipped=resolve(h.doc.font,dict(master=h.mid,glyphs='all',surface='background'))
        return [r[0]['glyph'] for r in rows],skipped
    selected,skipped=h.main(contents)
    check('image metadata attributes metrics-only backgrounds eligible',selected==['probe0','probe1','probe2','probe3'])
    check('genuinely empty background skipped',skipped['count']==1)
    h.main(lambda:h.doc.font.save(str(h.source),makeCopy=True));h.main(h.clean)
    options=dict(source='def run(layer, params, context):\n    layer.width += 1.25',targets=[dict(glyph='probe0',layer=h.mid)])
    a=h.wait(h.start(options,'first'),'waiting_run');a=h.wait(h.choose(a,'run_script'),'applied')
    b=h.wait(h.start(options,'second'),'blocked_review')
    check('original workflow linked',b['blockingWorkflowId']==a['id'])
    check('script blocker has no typed Undo',all(x['action']!='discard_previous' for x in b['actions']))
    h.choose(a,'finish_script');b=h.wait(b,'waiting_run')
    check('Keep resumes next request needing Save',b['document']['dirty'] and any(a['action']=='save_run_script' for a in b['actions']))
    b=h.wait(h.choose(b,'save_run_script'),'applied')
    c=h.wait(h.start(options,'third'),'blocked_review')
    old=c['document']['id'];h.choose(b,'restore_saved_script');c=h.wait(c,'waiting_run')
    check('Restore resumes with fresh binding',c['document']['id']!=old and not c['document']['dirty'])
    c=h.wait(h.choose(c,'run_script'),'applied');h.choose(c,'restore_saved_script')
    bad=dict(options,source='def run(layer, params, context):\n    layer.width += 1\n    raise ValueError("partial")')
    a=h.wait(h.start(bad,'bad'),'waiting_run');a=h.wait(h.choose(a,'run_script'),'failed')
    b=h.wait(h.start(options,'after-failure'),'blocked_review')
    check('partial error still owns next task',b['blockingWorkflowId']==a['id'])
    h.choose(a,'restore_saved_script');b=h.wait(b,'waiting_run');h.choose(b,'cancel')
    return checks


out=Harness(count=5).run(exercise)
path=ROOT/'build/native-scripting-fixes.json';path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out),flush=True)
if not out.get('passed'):raise RuntimeError(out.get('error'))
