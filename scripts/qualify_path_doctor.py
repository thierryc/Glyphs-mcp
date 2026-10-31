"""Native qualification entry, executed as an authorized script on a disposable.

params: repository, output (private local directory), optional ownerPaths for
READ-ONLY live audits. This file contains no private geometry or font paths.
Does not install/reload the bridge. Imports candidate modules under isolated names.
"""
from pathlib import Path
import importlib
import json
import shutil
import sys
import traceback
import hashlib


def candidate(repository, output):
    root=output/'candidate';root.mkdir(exist_ok=True)
    for part,package in [('protocol','glyphs_mcp_protocol'),('bridge','glyphs_mcp_bridge')]:
        target=root/('pd_candidate_'+part)
        if target.exists(): shutil.rmtree(target)
        shutil.copytree(repository/'src'/part/package,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for file in target.rglob('*.py'):
            source=file.read_text().replace('glyphs_mcp_protocol','pd_candidate_protocol').replace('glyphs_mcp_bridge','pd_candidate_bridge')
            file.write_text(source)
    sys.path.insert(0,str(root))
    for name in list(sys.modules):
        if name.startswith(('pd_candidate_protocol','pd_candidate_bridge')):del sys.modules[name]
    return importlib.import_module('pd_candidate_protocol.preparation.path_doctor'),importlib.import_module('pd_candidate_bridge.outline_edit')


def qualify(font,params,Glyphs):
    output=Path(params['output']);output.mkdir(parents=True,exist_ok=True)
    doctor,edit=candidate(Path(params['repository']),output)
    from pd_candidate_protocol.preparation import consume, path_attributes
    from pd_candidate_protocol.outline import path_hash
    from GlyphsApp import GSLayer,GSPath,GSNode
    import objc
    Pen=objc.lookUpClass('GSPenPoint')
    result={'checks':{},'audits':[],'host':{'version':str(Glyphs.versionString),'build':str(Glyphs.buildNumber)}}
    def check(name,fn):
        try:result['checks'][name]={'passed':True,'evidence':fn()}
        except Exception:result['checks'][name]={'passed':False,'error':traceback.format_exc()}
        (output/'qualification.json').write_text(json.dumps(result,indent=2))
    # Owner access is strictly read-only. Do not copy, save, dirty or switch them.
    for path in params.get('ownerPaths',[]):
        owners=[f for f in Glyphs.fonts if str(f.filepath)==path]
        if len(owners)!=1:raise RuntimeError('read-only owner binding is ambiguous')
        owner=owners[0]
        request={'options':{'glyphs':'all','layers':'all_masters'}}
        _,report=consume(doctor.prepare_iter(owner,request))
        (output/('audit-'+str(len(result['audits']))+'.json')).write_text(json.dumps(report,indent=2))
        result['audits'].append({'source':path,'coverage':report['coverage'],'issueCounts':report['issueCounts'],'scanHash':report['scanHash']})
        (output/'qualification.json').write_text(json.dumps(result,indent=2))
    def make(cubic=False):
        layer=GSLayer();layer.setTemporarilyDisableRounding_(True)
        path=GSPath();path.closed=True
        coords=[(.125,.25,'line'),(90.375,5.625,'line'),(45.875,80.125,'line')]
        if cubic:coords += [(20.25,60.125,'offcurve'),(-5.125,10.25,'offcurve')]
        coords += [(.125,.25,'curve' if cubic else 'line')]
        for x,y,kind in coords:
            n=GSNode();n.position=(x,y);n.type=kind;path.nodes.append(n)
        layer.shapes.append(path)
        path.pyobjc_instanceMethods.setAttribute_forKey_(24.123456789,'strokeWidth')
        path.pyobjc_instanceMethods.setAttribute_forKey_(0,'fill')
        def point(t,w=24.125):
            p=Pen.alloc().init();p.setT_(t);p.setWidth_(w);p.setHeight_(20.25)
            p.setStrokePosition_(.03123456789);p.setProgressionIn_(.2345678901);p.setProgressionOut_(.3456789012)
            return p
        path.nodes[-1].pyobjc_instanceMethods.setAttribute_forKey_([point(.375,32.123456789),point(1.0)],'penPoints')
        path.nodes[0].pyobjc_instanceMethods.setAttribute_forKey_([point(1.0)],'penPoints')
        return layer,path
    def generic(cubic):
        layer,path=make(cubic);before=doctor.path_state(path);snapshot=edit.capture(layer)
        (output/('generic-before-'+str(cubic)+'.json')).write_text(json.dumps(before,indent=2))
        mapping=doctor.normalize(layer,path,path_hash(before));after=doctor.path_state(path)
        assert after['nodes'][1:]==before['nodes'][1:-1]
        assert after['nodes'][0]['attributeState']==before['nodes'][-1]['attributeState']
        assert after['attributeState']==before['attributeState']
        assert not doctor.seam_pattern(after)
        edit.restore(layer,snapshot);assert doctor.path_state(path)==before
        return mapping
    check('generic_line',lambda:generic(False));check('generic_cubic',lambda:generic(True))
    def wrapper_precision():
        layer,path=make();native=float(path.pyobjc_instanceMethods.attributes()['strokeWidth'])
        assert native==24.123456789
        saved=path_attributes.snapshot(path);path_attributes.restore(path,saved)
        assert float(path.pyobjc_instanceMethods.attributes()['strokeWidth'])==native
        return native
    check('native_attribute_precision',wrapper_precision)
    def metadata_recovery():
        layer,path=make(True)
        path.userData['note']='original generic path metadata'
        path.nodes[1].userData['logicalNode']=1
        before=doctor.path_state(path);saved=edit.capture(layer)
        path.pyobjc_instanceMethods.setAttribute_forKey_(32.123456789,'strokeWidth')
        edit.restore(layer,saved)
        assert dict(path.userData)=={'note':'original generic path metadata'}
        assert dict(path.nodes[1].userData)=={'logicalNode':1}
        assert doctor.path_state(path)==before
        return {'nativeMetadataReadable':True,'geometryProfilesAttributesExact':True}
    check('native_metadata_recovery',metadata_recovery)
    def real_roundtrip():
        glyph=font.glyphs[params.get('testGlyph','a.alt2')]
        rows=[]
        for master in font.masters:
            layer=glyph.layers[master.id];path=layer.paths[1]
            before=doctor.path_state(path);snapshot=edit.capture(layer)
            # New native code is tested on a detached clone, then on the disposable.
            from pd_candidate_protocol.preparation.outline import _copy
            clone=_copy(layer)
            doctor.normalize(clone,clone.paths[1],path_hash(before))
            old=bool(layer.temporarilyDisableRounding());layer.setTemporarilyDisableRounding_(True)
            try:
                mapping=doctor.normalize(layer,path,path_hash(before));after=doctor.path_state(path)
                assert after==doctor.path_state(clone.paths[1])
                edit.restore(layer,snapshot);assert doctor.path_state(path)==before
                doctor.normalize(layer,path,path_hash(before));assert doctor.path_state(path)==after
            finally:layer.setTemporarilyDisableRounding_(old)
            rows.append({'master':str(master.id),'before':before,'after':after,'mapping':mapping})
        (output/'private-seam-roundtrip.json').write_text(json.dumps(rows,indent=2))
        return {'layers':len(rows),'exactRecovery':True,'idempotent':all(not doctor.seam_pattern(r['after']) for r in rows)}
    if not params.get('skipPrivate'):check('private_disposable_roundtrip',real_roundtrip)
    def native_undo():
        from Foundation import NSUndoManager
        from pd_candidate_bridge.native_undo import write_value
        from pd_candidate_bridge.glyphs_adapter import GlyphsAdapter
        layer,path=make(True);before=doctor.path_state(path)
        manager=NSUndoManager.alloc().init();manager.setGroupsByEvent_(False)
        manager.beginUndoGrouping()
        key={'kind':'outline','operations':[{'op':'normalize_closed_seam','path':0,'stateHash':path_hash(before)}]}
        write_value(manager,layer,key,lambda owner:edit.apply(owner,key),edit.capture,GlyphsAdapter._write_exact)
        manager.endUndoGrouping();after=doctor.path_state(path)
        manager.undo();assert doctor.path_state(path)==before
        manager.redo();assert doctor.path_state(path)==after
        return {'exactUndo':True,'exactRedo':True,'manager':'native NSUndoManager'}
    check('native_undo_redo',native_undo)
    def variants():
        evidence=[]
        for mode in ['conflict','inherited','inactive_open','path_lock','hint','fractional_stale']:
            layer,path=make(True)
            if mode=='conflict':path.nodes[0].attributeForKey_('penPoints')[0].setAngle_(0.0)
            if mode=='inherited':
                for n in [path.nodes[0],path.nodes[-1]]:
                    n.attributeForKey_('penPoints')[-1].setAngle_(float.fromhex('0x1.fffffffffffffp+1023'))
            if mode=='inactive_open':path.closed=False
            if mode=='path_lock':path.pyobjc_instanceMethods.setAttribute_forKey_(True,'locked')
            if mode=='hint':
                from GlyphsApp import GSHint
                hint=GSHint();hint.originNode=path.nodes[1];layer.hints.append(hint)
            before=doctor.path_state(path);guard=path_hash(before)
            (output/('variant-'+mode+'.json')).write_text(json.dumps(before,indent=2))
            if mode=='fractional_stale':
                n=path.nodes[1];n.position=(n.position.x+.0001,n.position.y)
            try:
                doctor.normalize(layer,path,guard)
                assert mode=='inherited',mode
                evidence.append({'case':mode,'normalized':True})
            except ValueError as exc:
                assert mode!='inherited'
                if mode!='fractional_stale':assert doctor.path_state(path)==before
                evidence.append({'case':mode,'held':str(exc)})
        return evidence
    check('native_variants',variants)
    def reopened():
        from GlyphsApp import GSFont
        source=Path(params['reopenPath'])
        if not source.is_file():raise RuntimeError('disposable saved file missing')
        # Detached native load only; no open/reload/close of either owner.
        reopened=GSFont(str(source))
        glyph=params.get('testGlyph','a.alt2')
        rows=[]
        for m in font.masters:
            live=doctor.path_state(font.glyphs[glyph].layers[m.id].paths[1])
            saved=doctor.path_state(reopened.glyphs[glyph].layers[m.id].paths[1])
            (output/('reopened-'+str(m.id)+'.json')).write_text(json.dumps({'live':live,'saved':saved},indent=2))
            assert live==saved,'native save/reopen changed authored geometry or profiles'
            rows.append(str(m.id))
        return {'exact':True,'masters':rows}
    if params.get('reopenPath'):check('disposable_save_reopen',reopened)
    def host_gate():
        from pd_candidate_bridge.path_doctor_qualification import repair_available
        assert repair_available(), 'candidate host gate did not qualify this host'
        return True
    check('qualified_host_gate',host_gate)
    def profile_ownership():
        layer,path=make(True)
        def ownership(node):
            rows=[]
            for point in path_attributes.attributes(node).get('penPoints',[]):
                parent=path_attributes.native(point,'parent')
                rows.append({'parentType':type(parent).__name__,'parentIsNode':parent is node,
                             'parentIsPath':parent is path,'parentIsNone':parent is None})
            return rows
        before=ownership(path.nodes[-1]);doctor.normalize(layer,path,path_hash(doctor.path_state(path)))
        after=ownership(path.nodes[0])
        assert len(before)==len(after)
        # On this native host points without explicit parents are owned through
        # endpoint attribute storage. Never retain a removed node as parent.
        assert all(r['parentIsNone'] or r['parentIsNode'] or r['parentIsPath'] for r in after)
        return {'before':before,'after':after}
    check('profile_ownership',profile_ownership)
    return result


if 'font' in globals() and 'params' in globals():
    try:
        evidence=qualify(font,params,Glyphs)
        print(json.dumps({'checks':{k:v['passed'] for k,v in evidence['checks'].items()},'audits':evidence['audits']}))
    except Exception:
        Path(params['output']).mkdir(parents=True,exist_ok=True)
        Path(params['output'],'failure.txt').write_text(traceback.format_exc())
        raise

# Optional existing-disposable preparation check. No owner document is targeted.
if 'font' in globals() and 'params' in globals() and params.get('prepareGlyph'):
    from pd_candidate_protocol.preparation import consume
    from pd_candidate_protocol.preparation.outline import prepare_iter
    from pd_candidate_protocol.preparation.path_doctor import path_state
    from pd_candidate_protocol.outline import path_hash
    glyph=font.glyphs[params['prepareGlyph']]
    targets=[]
    for master in font.masters:
        identity=str(master.id);p=glyph.layers[identity].paths[1];h=path_hash(path_state(p))
        targets.append({'glyph':str(glyph.name),'referenceLayer':identity,'layers':{'scope':'ids','ids':[identity]},
            'guards':[{'path':1,'hash':h}],'operations':[{'op':'normalize_closed_seam','path':1,'stateHash':h}]})
    before={'lastChange':str(glyph.lastChange),'paths':[path_state(glyph.layers[m.id].paths[1]) for m in font.masters]}
    changes,report=consume(prepare_iter(font,{'options':{'targets':targets}}))
    after={'lastChange':str(glyph.lastChange),'paths':[path_state(glyph.layers[m.id].paths[1]) for m in font.masters]}
    assert before==after,'preparation emitted owner changes'
    Path(params['output'],'preparation-isolation.json').write_text(json.dumps({'unchanged':True,'layers':len(changes)},indent=2))
