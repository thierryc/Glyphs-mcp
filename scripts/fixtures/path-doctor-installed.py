"""Original generic fixture for installed Path Doctor acceptance.

Run via the existing python_script workflow on an explicitly created disposable.
params: family, mode=setup|capture|verify, snapshot (capture/verify only).
Use advertised path_diagnostics and outline_edit for the actual repair, not this
script. Capture after saving the generic baseline; verify after typed repair.
No private font data, owner lookup, bridge imports, Save or Close calls.
"""
if params["mode"] == "setup":
    from GlyphsApp import GSGlyph, GSPath, GSNode, GSFontMaster
    import objc, json
    assert str(font.familyName)==params['family']
    assert len(font.glyphs)==0
    extra=GSFontMaster();extra.name='Bold';font.masters.append(extra)
    Pen=objc.lookUpClass('GSPenPoint')
    def point(t,w=24.125):
     p=Pen.alloc().init();p.setT_(t);p.setWidth_(w);p.setHeight_(20.25);p.setStrokePosition_(.03123456789);p.setProgressionIn_(.2345678901);p.setProgressionOut_(.3456789012);return p
    for case in ['line','cubic','valid','open','conflict','locked']:
     glyph=GSGlyph('doctor.'+case);font.glyphs.append(glyph)
     for master in font.masters:
      layer=glyph.layers[master.id];layer.width=500
      old=bool(layer.temporarilyDisableRounding());layer.setTemporarilyDisableRounding_(True)
      try:
       path=GSPath();path.closed=case!='open'
       coords=[(.125,.25,'line'),(90.375,5.625,'line'),(45.875,80.125,'line')]
       if case=='cubic':coords += [(20.25,60.125,'offcurve'),(-5.125,10.25,'offcurve')]
       if case not in ['valid']:coords += [(.125,.25,'curve' if case=='cubic' else 'line')]
       if case=='open':coords += [(.125,-100.375,'line')]
       for x,y,kind in coords:
        n=GSNode();n.position=(x,y);n.type=kind;path.nodes.append(n)
       layer.shapes.append(path)
       path.pyobjc_instanceMethods.setAttribute_forKey_(24.123456789,'strokeWidth')
       path.pyobjc_instanceMethods.setAttribute_forKey_(0,'fill')
       if case in ['line','cubic','conflict','locked']:
        path.nodes[-1].pyobjc_instanceMethods.setAttribute_forKey_([point(.375,32.123456789),point(1)],'penPoints')
        path.nodes[0].pyobjc_instanceMethods.setAttribute_forKey_([point(1,42.125 if case=='conflict' else 24.125)],'penPoints')
       if case=='open':path.nodes[0].pyobjc_instanceMethods.setAttribute_forKey_([point(1)],'penPoints')
       if case=='locked':path.pyobjc_instanceMethods.setAttribute_forKey_(True,'locked')
      finally:layer.setTemporarilyDisableRounding_(old)
    print(json.dumps({'glyphs':len(font.glyphs),'masters':[str(m.id) for m in font.masters]}))

else:
    from pathlib import Path
    import json, copy
    assert str(font.familyName)==params['family']
    FIELDS=('t','width','height','angle','strokePosition','progressionIn','progressionOut','isLocked')
    def plain(v):
     if v is None or isinstance(v,(str,bool,int)):return v
     if isinstance(v,float):return {'float':v.hex()}
     if type(v).__name__=='GSPenPoint':
      p={k:plain(getattr(v.pyobjc_instanceMethods,k)()) for k in FIELDS}
      stored,error=v.pyobjc_instanceMethods.propertyListValueFormat_error_(4,None)
      assert error is None
      return {'penPoint':p,'stored':plain(stored)}
     if hasattr(v,'allKeys') or isinstance(v,dict):return {str(k):plain(v[k]) for k in v}
     if isinstance(v,(list,tuple)) or 'Array' in type(v).__name__:return [plain(x) for x in v]
     raise ValueError('Unsupported verification value '+type(v).__name__)
    def attrs(o):return plain(o.pyobjc_instanceMethods.attributes() or {})
    actual={}
    for glyph in font.glyphs:
     for master in font.masters:
      layer=glyph.layers[master.id]
      actual[str(glyph.name)+'/'+str(master.id)]={'width':float(layer.width).hex(),'anchors':len(layer.anchors),'components':len(layer.components),'hints':len(layer.hints),'paths':[
        {'closed':bool(p.closed),'attributes':attrs(p),'nodes':[{'x':float(n.position.x).hex(),'y':float(n.position.y).hex(),'type':str(n.type),'smooth':bool(n.smooth),'name':n.name,'attributes':attrs(n)} for n in p.nodes]} for p in layer.paths]}
    path=Path(params['snapshot'])
    if params['mode']=='capture':
     assert not path.exists()
     path.write_text(json.dumps(actual,indent=2))
     print(json.dumps({'capturedLayers':len(actual)}))
    else:
     expected=json.loads(path.read_text())
     for key,layer in expected.items():
      if key.split('/')[0] not in ('doctor.line','doctor.cubic'):continue
      nodes=layer['paths'][0]['nodes'];incoming=nodes[-1]
      nodes[0]['type']=incoming['type'];nodes[0]['attributes']['penPoints']=incoming['attributes']['penPoints'];nodes.pop()
     assert actual==expected,'Independent native geometry/profile/default comparison failed'
     print(json.dumps({'verifiedLayers':len(actual),'allNumericGeometryProfilesAndDefaultsExact':True,'allNonTargetsUnchanged':True}))
