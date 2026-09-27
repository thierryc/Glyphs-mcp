"""Native single-route execution and saved-version restoration on disposable fonts."""
import json
import importlib
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import time
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/simple-native-scripting'
sys.path[:0] = [str(BUILD/'sidecar'), str(BUILD/'Glyphs MCP Bridge.glyphsPlugin/Contents/Resources'), str(ROOT/'scripts')]
for name in ('glyphs_mcp_protocol.script_targets', 'glyphs_mcp_bridge.core', 'glyphs_mcp_sidecar.service'):
    assert Path(importlib.import_module(name).__file__).resolve().is_relative_to(BUILD)
from native_script_harness import Harness, ROOT
from glyphs_mcp_sidecar.source import source_hash


def exercise(h):
    checks=[]
    def check(name,condition):
        print(name,condition,flush=True);assert condition,name;checks.append(name)
    def enrich():
        from GlyphsApp import GSFontMaster, GSPath, GSNode, GSAnchor, GSComponent, OFFCURVE, CURVE
        font=h.doc.font;managers=[h.doc.undoManager()]+[g.undoManager() for g in font.glyphs]
        for m in managers:m.disableUndoRegistration()
        try:
            other=GSFontMaster();font.masters.append(other);h.other_mid=str(other.id)
            for glyph in font.glyphs:glyph.layers[h.other_mid].width=777
            owner=font.glyphs[0].layers[h.mid]
            owner.setTemporarilyDisableRounding_(True)
            path=GSPath();path.closed=True
            for point in ((0.25,0.5),(100.25,0.5),(0.25,100.5)):path.nodes.append(GSNode(point))
            owner.shapes.append(path);owner.setTemporarilyDisableRounding_(False)
            background=owner.background;background.setTemporarilyDisableRounding_(True)
            background.anchors.append(GSAnchor('top',(17.5,850.25)))
            background.shapes.append(GSComponent('probe1'))
            curve=GSPath();curve.closed=True
            for point,kind in (((20.25,0),'line'),((30.25,100),OFFCURVE),((80.5,100),OFFCURVE),((100.25,0),CURVE)):
                curve.nodes.append(GSNode(point,type=kind))
            background.shapes.append(curve);background.setTemporarilyDisableRounding_(False)
        finally:
            for m in managers:m.enableUndoRegistration()
        h.clean()
    h.main(enrich)
    code=(ROOT/'skills/glyphs-mcp-scripting/examples/vertical_flip.py').read_text()
    options=dict(source=code,targets=dict(master=h.mid,glyphs='all',surface='background'))
    def first():return h.doc.font.glyphs[0].layers[h.mid]
    def positions():return [[(float(n.position.x),float(n.position.y)) for n in p.nodes] for p in first().background.paths]
    def run(opts,key):
        value=h.wait(h.start(opts,key),'waiting_run')
        return h.wait(h.choose(value,'save_run_script' if value['document']['dirty'] else 'run_script'),'applied','failed')
    def manual(width):
        manager=first().parent.undoManager();manager.beginUndoGrouping()
        try:first().width=width
        finally:manager.endUndoGrouping()
        h.doc.updateChangeCount_(0)
    h.main(lambda:manual(510))
    before=h.main(positions)
    def preserved():
        layer=first();other=h.doc.font.glyphs[0].layers[h.other_mid]
        return dict(foreground=[[(float(n.position.x),float(n.position.y)) for n in p.nodes] for p in layer.paths],
                    anchor=(float(layer.background.anchors['top'].position.x),float(layer.background.anchors['top'].position.y)),
                    components=[str(c.componentName) for c in layer.background.components],otherWidth=float(other.width))
    untouched=h.main(preserved)
    value=h.wait(h.start(options,'dirty'),'waiting_run')
    check('dirty preparation does not execute',h.main(positions)==before)
    check('optional source omitted from polling','scriptReview' not in value)
    value=h.wait(h.choose(value,'save_run_script'),'applied')
    baseline=source_hash(h.source)
    check('native flip preserves fractional coordinates',h.main(lambda:first().background.paths[0].nodes[0].position.y)==700.25)
    check('foreground other master anchors components preserved',h.main(preserved)==untouched)
    check('control points mirrored',h.main(positions)[-1][1][1]==700.25-before[-1][1][1])
    check('foreground preserved',h.main(lambda:first().width)==510)
    check('execution unsaved',h.main(lambda:h.doc.isDocumentEdited()))
    check('no layer snapshots retained',h.main(lambda:h.core._operations[value['jobId']]['nativeStateBytes'])==0)
    check('precision flags released',not h.main(lambda:h.adapter._rounding_value(first().background)))
    h.main(lambda:manual(555));value=h.service.edit_workflows.get(value['id'])
    old_id=value['document']['id'];value=h.choose(value,'restore_saved_script')
    check('whole saved version restored',value['state']=='discarded' and h.main(positions)==before)
    check('later manual edits replaced',h.main(lambda:first().width)==510)
    check('restoration does not save',source_hash(h.source)==baseline)
    check('restored document clean',not h.main(lambda:h.doc.isDocumentEdited()))
    check('fresh document binding',value['document']['id']==h.service.list_documents()[0]['id'] and value['document']['id']!=old_id)
    check('restoration clears Undo',h.main(lambda:not h.doc.undoManager().canUndo() and not first().parent.undoManager().canUndo()))
    failed=dict(options,source='def run(layer, params, context):\n    layer.width += 20\n    raise ValueError("partial failure")',targets=[dict(glyph='probe0',layer=h.mid)])
    value=run(failed,'failure')
    check('failure retains partial effects',value['state']=='failed' and h.main(lambda:first().width)==530)
    check('failure offers Keep and Restore',{a['action'] for a in value['actions']}=={'finish_script','restore_saved_script'})
    value=h.choose(value,'restore_saved_script');check('failure restored',value['state']=='discarded' and h.main(lambda:first().width)==510)
    # Persisted collections outside layers are covered by the saved font itself.
    font_code='''from GlyphsApp import GSFeature
font.userData['probe'] = 'added'
font.features.append(GSFeature('liga', 'sub probe0 probe1 by probe2;'))
font.setKerningForPair(font.masters[0].id, 'probe0', 'probe1', -42)
'''
    whole=dict(source=font_code,entrypoint='script',targets=[])
    value=run(whole,'font-data')
    check('whole script with zero layer targets executes',value['state']=='applied' and h.main(lambda:h.doc.font.userData['probe'])=='added')
    check('whole script has no callback progress',value['entrypoint']=='script')
    value=h.choose(value,'restore_saved_script')
    check('font metadata removed by reload',h.main(lambda:h.doc.font.userData['probe']) is None)
    check('feature additions removed by reload',h.main(lambda:len(h.doc.font.features))==0)
    check('kerning additions removed by reload',h.main(lambda:not dict(h.doc.font.kerning)))
    # Clean execution must not invoke the save service.
    original=h.adapter.save_document
    h.adapter.save_document=lambda *a:(_ for _ in ()).throw(AssertionError('redundant Save'))
    value=run(options,'clean');check('clean baseline uses zero Save calls',value['state']=='applied')
    value=h.choose(value,'restore_saved_script');h.adapter.save_document=original
    # Module-level exceptions also leave effects available for explicit restoration.
    value=run(dict(whole,source="font.userData['partial']='yes'\nraise ValueError('module failure')"),'module-failure')
    check('module failure preserves partial edits',value['state']=='failed' and h.main(lambda:h.doc.font.userData['partial'])=='yes')
    h.choose(value,'restore_saved_script')
    # Test observed script Save rather than declaring every result unsaved.
    value=run(dict(whole,source="font.userData['saved']='yes'\nfont.save(params['path'], makeCopy=True)",params={"path":str(h.source)}),'script-save')
    check('script save detected',value['state']=='applied' and not value['savedVersion']['available'])
    h.choose(value,'finish_script')
    h.main(h.clean)
    prior_widths=h.main(lambda:[g.layers[h.mid].width for g in h.doc.font.glyphs])
    cancel_opts=dict(options,source='import time\ndef run(layer, params, context):\n    layer.width += 1\n    time.sleep(.02)',targets=dict(master=h.mid,glyphs='all',surface='foreground'))
    value=h.wait(h.start(cancel_opts,'cancel'),'waiting_run');value=h.choose(value,'run_script')
    for _ in range(100):
        if h.main(lambda:h.core._operations[value['jobId']]['scriptResult']['executedTargets'])>0:break
        time.sleep(.005)
    value=h.service.edit_workflows.get(value['id']);value=h.wait(h.choose(value,'cancel'),'cancelled')
    executed=value['job']['bridgeOperation']['scriptResult']['executedTargets']
    check('cancellation stops remaining callbacks',0<executed<60)
    check('partial cancellation unsaved',h.main(lambda:h.doc.isDocumentEdited()))
    value=h.choose(value,'restore_saved_script')
    check('cancelled script restored',value['state']=='discarded' and h.main(lambda:[g.layers[h.mid].width for g in h.doc.font.glyphs])==prior_widths)
    value=run(options,'keep');value=h.choose(value,'finish_script')
    check('Keep ends restoration offer',value['savedVersion'] is None and not value['actions'])
    return checks

suffix=sys.argv[-1] if sys.argv[-1] in ('glyphs','glyphspackage') else 'glyphs'
out=Harness(count=60,suffix=suffix).run(exercise)
(ROOT/f'build/simple-native-{suffix}.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out),flush=True)
if not out.get('passed'):raise RuntimeError(out.get('error'))
