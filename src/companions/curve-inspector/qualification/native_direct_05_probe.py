"""V2 whole-script qualification on an owned saved fixture; live geometry untouched.
Import only detached helper code under a unique namespace, never the Reporter.
"""
import importlib.util
import json
import sys
import uuid
import GlyphsApp as app

if font.familyName != 'Curve Inspector Repair Fixture':
    raise RuntimeError('Owned disposable fixture required')
root = params['sourceRoot']
sys.path.insert(0, root)
name = 'curve_inspector_candidate_05_'+uuid.uuid4().hex
spec = importlib.util.spec_from_file_location(name, root+'/curve_repair/__init__.py', submodule_search_locations=[root+'/curve_repair'])
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
a = __import__(name+'.actions', fromlist=['prepare_path'])
n = __import__(name+'.native', fromlist=['path_state'])
p = __import__(name+'.provenance', fromlist=['record'])
before = tuple(n.path_state(l.paths[0]) for l in font.glyphs['test'].layers)
results = {'engine':p.record(root), 'host':{'version':str(Glyphs.versionString),'build':str(Glyphs.buildNumber)}, 'cases':{}}

def fixture():
    f=font.copy();g=f.glyphs['test'];l=g.layers[font.masters[0].id]
    return f,g,l,l.paths[0]

def trial(method, limit=1, outgoing=39, star=False, grid=None):
    f,g,l,path=fixture()
    with n.precision(l,True):
        path.nodes[4].position=(outgoing,0)
        if star:path.nodes[3].setConnection_(app.GSSUPERSMOOTH)
    if grid is not None:f.grid=grid
    old=n.path_state(path)
    candidate=a.prepare_path(g,l,l,path,(3,),app,method,limit)
    assert old==n.path_state(path)
    return candidate

s=trial('star')
assert s.repaired==1 and s.after_nodes[3][1]==app.GSSUPERSMOOTH and s.maximum<=1
assert all(x[0]==y[0] for x,y in zip(s.before_nodes,s.after_nodes))
results['cases']['nativeStar']={'bound':s.maximum,'storedCoordinatesPreserved':True}
d=trial('default-node')
assert d.after_nodes[3]==((-0.5,0.0),app.GSSMOOTH) and d.maximum<=1
results['cases']['nativeMaterialization']={'bound':d.maximum,'position':d.after_nodes[3][0],'tunniFallback':d.notes}
for method in ('star','default-node'):
    h=trial(method,outgoing=40)
    assert h.already_smooth==1 and h.before_nodes==h.after_nodes
results['cases']['healthyOrdinaryNoops']=True
h=trial('star',star=True)
assert h.before_nodes==h.after_nodes
r=trial('default-node',limit=.0001,star=True,grid=0)
assert r.converted==1 and r.maximum==0 and r.after_nodes[3][1]==app.GSSMOOTH
results['cases']['existingStarResolved']={'grid':0,'bound':r.maximum,'position':r.after_nodes[3][0]}
r=trial('default-node',limit=1,star=True)
results['cases']['existingStarGridRounding']={'grid':float(font.gridLength),'bound':r.maximum,'position':r.after_nodes[3][0]}
results['cases']['thresholds']=[]
for limit,ok in ((s.maximum-1e-5,False),(s.maximum,True),(s.maximum+1e-5,True)):
    try:c=trial('star',limit)
    except a.RepairError as e:
        assert not ok and e.code in ('excess_deviation','unresolved_deviation')
        results['cases']['thresholds'].append({'limit':limit,'accepted':False,'reason':str(e)})
    else:
        assert ok
        results['cases']['thresholds'].append({'limit':limit,'accepted':True,'bound':c.maximum})
for reverse in (False,True):
    f,g,l,path=fixture()
    path.nodes=[]
    coords=[(-20,0),(0,0),(4,0),(10,4),(20,10)]
    kinds=[app.LINE,app.LINE,app.OFFCURVE,app.OFFCURVE,app.CURVE]
    if reverse:coords.reverse();kinds=[app.LINE,app.OFFCURVE,app.OFFCURVE,app.CURVE,app.LINE]
    for xy,kind in zip(coords,kinds):path.nodes.append(app.GSNode(xy,type=kind))
    j=3 if reverse else 1
    path.nodes[j].setConnection_(app.GSSMOOTH)
    star=a.prepare_path(g,l,l,path,(j,),app,'star',1)
    regular=a.prepare_path(g,l,l,path,(j,),app,'default-node',10)
    assert star.repaired==regular.repaired==1 and star.maximum<=1 and regular.maximum<=10
    with n.precision(l,True):a.write_nodes(path,star.after_nodes)
    try:a.prepare_path(g,l,l,path,(j,),app,'default-node',100)
    except a.RepairError as e:assert e.code=='expanded_star'
    else:raise AssertionError('Raindrop must refuse materialization')
    results['cases']['curveLine' if reverse else 'lineCurve']={'starBound':star.maximum,'regularBound':regular.maximum,'raindropMaterializationRefused':True}
results['liveGeometryUnchanged']=before==tuple(n.path_state(l.paths[0]) for l in font.glyphs['test'].layers)
assert results['liveGeometryUnchanged']
print(json.dumps(results,sort_keys=True))
