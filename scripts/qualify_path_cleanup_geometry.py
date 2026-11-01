"""Detached native fixtures for interpolation, special layers and bounded edits."""
def run(repository,output):
    import importlib.util,json
    from pathlib import Path
    from GlyphsApp import GSFont,GSFontMaster,GSGlyph,GSLayer,GSPath,GSNode,GSAxis
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('cleanup_loader',Path(repository)/'scripts/qualify_path_doctor.py')
    loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
    doctor,edit=loader.candidate(Path(repository),output)
    from pd_candidate_protocol.preparation.path_cleanup import prepare_iter
    from pd_candidate_protocol.preparation import consume
    results={}
    def make():
        font=GSFont();axis=GSAxis();axis.name='Weight';axis.axisTag='wght';font.axes=[axis]
        masters=[]
        for index,value in enumerate([100,400,900]):
            master=GSFontMaster();master.name=str(value);master.id='cleanup-'+str(index);masters.append(master)
        font.masters=masters
        for master,value in zip(font.masters,[100,400,900]):master.axes=[value]
        glyph=GSGlyph('cleanupTest');font.glyphs.append(glyph)
        for master in font.masters:
            layer=glyph.layers[master.id];path=GSPath();path.closed=True
            for x,y in [(0,0),(50,0),(50,0),(100,0),(100,100),(0,100)]:
                n=GSNode();n.type='line';n.position=(x,y);path.nodes.append(n)
            layer.shapes.append(path)
        return font,glyph
    def check(name,fn):
        import traceback
        try:results[name]={'passed':True,'evidence':fn()}
        except Exception:results[name]={'passed':False,'error':traceback.format_exc()}
        (output/'result.json').write_text(json.dumps(results,indent=2))
    def exact(special=None):
        font,glyph=make()
        if special=='brace':
            layer=glyph.layers[font.masters[1].id].copy();layer.layerId='cleanup-brace';layer.associatedMasterId=font.masters[1].id
            layer.attributes['coordinates']={'0':500};glyph.layers.append(layer)
        if special=='bracket':
            for i,master in enumerate(font.masters):
                layer=glyph.layers[master.id].copy();layer.layerId='cleanup-bracket-'+str(i);layer.associatedMasterId=master.id
                layer.attributes['axisRules']=[{'min':500}];glyph.layers.append(layer)
        changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all','operations':['duplicates','collinear']}}))
        assert not report['held'],report['held']
        assert len(changes)==(4 if special=='brace' else 6 if special=='bracket' else 3),len(changes)
        for change in changes:edit.apply(glyph.layers[change['layer']],change)
        repeated,_=consume(prepare_iter(font,{'options':{'glyphs':'all','operations':['duplicates','collinear']}}))
        assert not repeated
        return {'changedLayers':len(changes),'idempotent':True}
    def bounded(operation='near_nodes',special=None):
        font,glyph=make()
        # A near-collinear, smooth node with small deviation and real nonzero edges.
        for master in font.masters:
            layer=glyph.layers[master.id];layer.setTemporarilyDisableRounding_(True)
            path=layer.paths[0]
            del path.nodes[2]
            path.nodes[1].position=(.1,.01);path.nodes[1].smooth=True
            if operation!='near_nodes':
                path.nodes=[]
                for x,y,kind,smooth in [(0,0,'line',False),(100,0,'line',False),(100,100,'line',False),
                        (80,100,'offcurve',False),(60,100.2,'offcurve',False),(50,100,'curve',True),
                        (40,100,'offcurve',False),(20,100,'offcurve',False),(0,100,'curve',False)]:
                    node=GSNode();node.type=kind;node.position=(x,y);node.smooth=smooth;path.nodes.append(node)
        if special=='brace':
            layer=glyph.layers[font.masters[1].id].copy();layer.layerId='bounded-brace';layer.associatedMasterId=font.masters[1].id
            layer.attributes['coordinates']={'0':500};glyph.layers.append(layer)
        if special=='bracket':
            for i,master in enumerate(font.masters):
                layer=glyph.layers[master.id].copy();layer.layerId='bounded-bracket-'+str(i);layer.associatedMasterId=master.id
                layer.attributes['axisRules']=[{'min':500}];glyph.layers.append(layer)
        changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all','policy':'bounded','operations':[operation],'maxDeviation':.5}}))
        if not changes:
            from pd_candidate_protocol.preparation.outline import _copy,_apply
            from pd_candidate_protocol.preparation.path_doctor import path_state
            original=glyph.layers[font.masters[0].id];trial=_copy(original)
            _apply(trial,{'op':'remove_node','path':0,'node':1})
            (output/'bounded-debug.json').write_text(json.dumps({'before':path_state(original.paths[0]),'after':path_state(trial.paths[0]),'report':report},indent=2))
        assert len(changes)==(4 if special=='brace' else 6 if special=='bracket' else 3),report
        assert all(row['measurements'] and row['measurements'][0]['intermediateSamples'] for row in report['layers'])
        from pd_candidate_protocol.preparation.outline import _shape_state
        from pd_candidate_protocol.outline import outline_state_hash
        for change in changes:
            layer=glyph.layers[change['layer']];snapshot=edit.capture(layer)
            edit.apply(layer,change);assert outline_state_hash(_shape_state(layer))==change['afterHash']
            edit.restore(layer,snapshot);assert outline_state_hash(_shape_state(layer))==change['beforeHash']
        return {'changedLayers':len(changes),'measurements':report['layers']}
    check('ordinary',lambda:exact());check('brace',lambda:exact('brace'));check('bracket',lambda:exact('bracket'));check('bounded',bounded)
    check('handle_alignment',lambda:bounded('align_handles'))
    check('curve_simplification',lambda:bounded('simplify_curves'))
    check('bounded_brace',lambda:bounded(special='brace'))
    check('bounded_bracket',lambda:bounded(special='bracket'))
    print(json.dumps(results))
