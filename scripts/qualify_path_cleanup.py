"""Run candidate cleanup on an explicitly authorized disposable font.

Executed through the recoverable native-script workflow. Never installs code.
All captures and reports belong in an ignored private output directory.
"""
from pathlib import Path
import importlib.util
import json


def run(font, params):
    if str(font.familyName) != params['expectedFamily']:
        raise ValueError('candidate qualification requires the exact disposable family')
    repository=Path(params['repository']);output=Path(params['output']);output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('cleanup_candidate_loader',repository/'scripts/qualify_path_doctor.py')
    loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
    doctor,edit=loader.candidate(repository,output)
    from pd_candidate_protocol.preparation import consume, stored_layers
    from pd_candidate_protocol.preparation.path_cleanup import prepare_iter
    from pd_candidate_protocol.preparation.outline import _shape_state
    from pd_candidate_protocol.outline import outline_state_hash, path_hash
    from GlyphsApp import GSLayer,GSPath,GSNode
    # Independent generic node removal, identity retention and exact restoration.
    layer=GSLayer();path=GSPath();path.closed=True
    for xy in [(0,0),(100,0),(100,0),(100,0),(50,100)]:
        node=GSNode();node.type='line';node.position=xy;path.nodes.append(node)
    layer.shapes.append(path)
    snapshot=edit.capture(layer);before=doctor.path_state(path);objects=list(path.nodes)
    doctor.remove_duplicates(layer,path,path_hash(before))
    assert list(path.nodes)==[objects[0],objects[1],objects[4]]
    edit.restore(layer,snapshot);assert doctor.path_state(path)==before
    from Foundation import NSUndoManager
    from pd_candidate_bridge.native_undo import write_value
    from pd_candidate_bridge.glyphs_adapter import GlyphsAdapter
    manager=NSUndoManager.alloc().init();manager.setGroupsByEvent_(False)
    manager.beginUndoGrouping()
    key={'kind':'outline','operations':[{'op':'remove_consecutive_duplicate_nodes','path':0,'stateHash':path_hash(before)}]}
    write_value(manager,layer,key,lambda owner:edit.apply(owner,key),edit.capture,GlyphsAdapter._write_exact)
    manager.endUndoGrouping();after=doctor.path_state(path)
    manager.undo();assert doctor.path_state(path)==before
    manager.redo();assert doctor.path_state(path)==after
    if params.get('genericOnly'):
        print(json.dumps({'genericDuplicateRecovery':True,'liveFontEdited':False}));return
    capture=lambda:{(str(g.name),str(l.layerId)):outline_state_hash(_shape_state(l)) for g in font.glyphs for l in stored_layers(g)}
    baseline=capture()
    _,before_report=consume(doctor.prepare_iter(font,{'options':{'glyphs':'all','layers':'all_interpolation_layers'}}))
    (output/'before.json').write_text(json.dumps(before_report,indent=2))
    changes,report=consume(prepare_iter(font,{'options':params['settings']}))
    (output/'prepared.json').write_text(json.dumps(report,indent=2))
    (output/'patch.json').write_text(json.dumps(changes,indent=2))
    # Preflight every target before the first native edit.
    for change in changes:
        layer=font.glyphs[change['glyph']].layers[change['layer']]
        assert outline_state_hash(_shape_state(layer))==change['beforeHash']
    applied=[]
    try:
        for change in changes:
            layer=font.glyphs[change['glyph']].layers[change['layer']]
            edit.apply(layer,change)
            assert outline_state_hash(_shape_state(layer))==change['afterHash']
            applied.append((change['glyph'],change['layer']))
    finally:
        (output/'applied.json').write_text(json.dumps(applied))
    after=capture();expected={(c['glyph'],c['layer']):c['afterHash'] for c in changes}
    assert after=={key:expected.get(key,value) for key,value in baseline.items()}
    _,after_report=consume(doctor.prepare_iter(font,{'options':{'glyphs':'all','layers':'all_interpolation_layers'}}))
    (output/'after.json').write_text(json.dumps(after_report,indent=2))
    repeated,repeat_report=consume(prepare_iter(font,{'options':params['settings']}))
    result={'genericDuplicateRecovery':True,'preparedLayers':len(changes),'appliedLayers':len(applied),
            'untargetedLayersExact':True,'beforeCounts':before_report['issueCounts'],
            'afterCounts':after_report['issueCounts'],'coverage':after_report['coverage'],
            'heldCount':len(report['held']),'repeatChanges':len(repeated),
            'removedNodes':sum(row['removedNodes'] for row in report['layers'])}
    (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
