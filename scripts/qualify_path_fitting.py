"""Plugin-free native fixtures; no live font, installation, save or restart.

Run with the established glyphs-cli and exact app/Python arguments:
glyphs run --plugins '' ... scripts/qualify_path_fitting.py -- REPOSITORY OUTPUT
Candidate modules are isolated using the existing Path Doctor loader. Output
must be a disposable local directory; tests create only detached GSFont objects.
"""
import importlib.util
import json
import math
from pathlib import Path
import sys
import traceback


def run(repository, output):
    from GlyphsApp import GSFont,GSFontMaster,GSGlyph,GSPath,GSNode,GSAxis,Glyphs
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    repository=Path(repository)
    spec=importlib.util.spec_from_file_location('fitting_loader',repository/'scripts/qualify_path_doctor.py')
    loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
    doctor,edit=loader.candidate(repository,output)
    from pd_candidate_protocol.preparation import consume
    from pd_candidate_protocol.preparation.path_fitting import prepare_iter
    from pd_candidate_protocol.preparation.outline import _shape_state
    from pd_candidate_protocol.outline import outline_state_hash
    results={'host':{'version':str(Glyphs.versionString),'build':str(Glyphs.buildNumber)},'checks':{}}
    def shape(cx=0,rx=100,ry=100,clockwise=False,count=64):
        path=GSPath();path.closed=True
        for i in range(count):
            t=(-1 if clockwise else 1)*i*math.tau/count
            n=GSNode();n.type='line';n.position=(cx+rx*math.cos(t),ry*math.sin(t));path.nodes.append(n)
        return path
    def make(special=None,counters=False):
        font=GSFont();axis=GSAxis();axis.name='Weight';axis.axisTag='wght';font.axes=[axis]
        masters=[]
        for i in range(2):
            master=GSFontMaster();master.id='fitting-'+str(i);master.name=str(i);masters.append(master)
        font.masters=masters
        for i,master in enumerate(font.masters):master.axes=[100+800*i]
        glyph=GSGlyph('fittingTest');font.glyphs.append(glyph)
        for i,master in enumerate(font.masters):
            layer=glyph.layers[master.id];layer.setTemporarilyDisableRounding_(True)
            layer.width=500
            layer.shapes.append(shape(ry=100+i*8,rx=180 if counters else 100))
            if counters:
                layer.shapes.append(shape(-95,25,22,True));layer.shapes.append(shape(95,25,22,True))
        if special=='brace':
            layer=glyph.layers[font.masters[0].id].copy();layer.layerId='fitting-brace';layer.associatedMasterId=font.masters[0].id
            layer.attributes['coordinates']={'0':500};glyph.layers.append(layer)
        if special=='bracket':
            for i,master in enumerate(font.masters):
                layer=glyph.layers[master.id].copy();layer.layerId='fitting-bracket-'+str(i);layer.associatedMasterId=master.id
                layer.attributes['axisRules']=[{'min':500}];glyph.layers.append(layer)
        return font,glyph
    def check(name,callback):
        try:results['checks'][name]={'passed':True,'evidence':callback()}
        except Exception:results['checks'][name]={'passed':False,'error':traceback.format_exc()}
        (output/'result.json').write_text(json.dumps(results,indent=2))
    def qualify(special=None,counters=False,undo=False):
        font,glyph=make(special,counters)
        request={'options':{'targets':[{'glyph':'fittingTest','paths':[{'path':i} for i in range(3 if counters else 1)]}],'maxDeviation':2.}}
        before=[outline_state_hash(_shape_state(l)) for l in glyph.layers]
        changes,report=consume(prepare_iter(font,request))
        assert changes and not report['held'],report
        assert [outline_state_hash(_shape_state(l)) for l in glyph.layers]==before
        for change in changes:
            layer=glyph.layers[change['layer']];snapshot=edit.capture(layer)
            path=layer.paths[0];start=path.nodes[0]
            edit.apply(layer,change)
            assert outline_state_hash(_shape_state(layer))==change['afterHash']
            assert layer.paths[0] is path and path.nodes[0] is start
            assert all(n.smooth for n in path.nodes if n.type!='offcurve')
            edit.restore(layer,snapshot)
            assert outline_state_hash(_shape_state(layer))==change['beforeHash']
            if undo:
                from Foundation import NSUndoManager
                from pd_candidate_bridge.native_undo import write_value
                from pd_candidate_bridge.glyphs_adapter import GlyphsAdapter
                manager=NSUndoManager.alloc().init();manager.setGroupsByEvent_(False)
                manager.beginUndoGrouping()
                write_value(manager,layer,change,lambda owner:edit.apply(owner,change),edit.capture,GlyphsAdapter._write_exact)
                manager.endUndoGrouping()
                assert outline_state_hash(_shape_state(layer))==change['afterHash']
                manager.undo();assert outline_state_hash(_shape_state(layer))==change['beforeHash']
                manager.redo();assert outline_state_hash(_shape_state(layer))==change['afterHash']
                edit.restore(layer,snapshot)
        return {'changedLayers':len(changes),'beforeNodes':report['beforeNodes'],'afterNodes':report['afterNodes'],
                'measurements':report['layers'],'detachedPreparation':True,'exactRecovery':True,'nativeUndoRedo':undo}
    check('ordinary',qualify)
    check('brace',lambda:qualify('brace'))
    check('bracket',lambda:qualify('bracket'))
    check('counters',lambda:qualify(counters=True))
    check('native_undo_redo',lambda:qualify(undo=True))
    def tight_budget():
        font,glyph=make()
        changes,report=consume(prepare_iter(font,{'options':{'targets':[{'glyph':'fittingTest','paths':[{'path':0}]}]}}))
        assert not changes and report['held'],report
        return {'defaultHalfUnitBudgetRefused':True,'reason':report['held'][0]['reason']}
    check('native_grid_budget_refusal',tight_budget)
    print(json.dumps(results))
    return results


if __name__=='__main__':
    args=[a for a in sys.argv[1:] if a!='--']
    if len(args)!=2:raise ValueError('expected repository and disposable output directory')
    result=run(*args)
    if not all(c['passed'] for c in result['checks'].values()):raise RuntimeError('native fitting qualification failed; inspect result.json')
