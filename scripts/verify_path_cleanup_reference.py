"""Read-only comparison of an authorized disposable against its live original.

Only detached path copies are expanded. Private font bindings and output paths
are supplied by the caller; this helper neither saves nor edits either font.
"""
def run(params, Glyphs):
    import importlib.util,json
    from pathlib import Path
    repository=Path(params['repository']);output=Path(params['output']);output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('reference_cleanup_loader',repository/'scripts/qualify_path_doctor.py')
    loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
    doctor,_=loader.candidate(repository,output)
    from pd_candidate_protocol.preparation.path_cleanup_samples import exact_geometry
    from pd_candidate_protocol.preparation.outline import _copy,_shape_state
    from pd_candidate_protocol.outline import outline_state_hash
    from pd_candidate_protocol.path_measurements import boundary_error
    def owner(path):
        matches=[font for font in Glyphs.fonts if str(font.filepath)==path]
        if len(matches)!=1:raise ValueError('live reference binding is ambiguous')
        return matches[0]
    before=owner(params['originalPath']);after=owner(params['disposablePath'])
    patch=json.loads(Path(params['patch']).read_text())
    for change in patch:
        for font,key in ((before,'beforeHash'),(after,'afterHash')):
            assert outline_state_hash(_shape_state(font.glyphs[change['glyph']].layers[change['layer']]))==change[key], 'live target changed since qualification'
    result={'layers':0,'paths':0,'differentRealGeometry':[],'nativeExpansion':[]}
    for glyph in before.glyphs:
        other=after.glyphs[glyph.name]
        for master in before.masters:
            a,b=glyph.layers[master.id],other.layers[master.id]
            pa=[doctor.path_state(p) for p in a.paths];pb=[doctor.path_state(p) for p in b.paths]
            result['layers']+=1;result['paths']+=len(pa)
            if exact_geometry(pa)!=exact_geometry(pb):result['differentRealGeometry'].append([str(glyph.name),str(master.id)])
    for name in params.get('sampleGlyphs',[]):
        for master in before.masters:
            a=_copy(before.glyphs[name].layers[master.id]);b=_copy(after.glyphs[name].layers[master.id])
            for index,(pa,pb) in enumerate(zip(a.paths,b.paths)):
                entry={'glyph':name,'master':str(master.id),'path':index}
                try:
                    variants=[]
                    for path in (pa,pb):
                        expanded=path.expandedStroke()
                        variants.append([doctor.path_state(p) for p in expanded])
                    if exact_geometry(variants[0])==exact_geometry(variants[1]):entry['exact']=True
                    else:entry.update(exact=False,**boundary_error(*variants))
                except Exception as exc:entry['unavailable']=str(exc)
                result['nativeExpansion'].append(entry)
    for change in patch:
        for font,key in ((before,'beforeHash'),(after,'afterHash')):
            assert outline_state_hash(_shape_state(font.glyphs[change['glyph']].layers[change['layer']]))==change[key]
    (output/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
