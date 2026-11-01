"""Cleanup contract and detached coordinated preparation on generic fixtures."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_simple_v2_path_doctor import duplicate_fixture, fixture, Collection, Node, PathShape
from glyphs_mcp_protocol import path_cleanup
from glyphs_mcp_protocol.preparation import consume
from glyphs_mcp_protocol.preparation.path_cleanup import prepare_iter as native_prepare_iter, groups, candidates, validate_bounded


def prepare_iter(font, request, **kwargs):
    # Generic fixtures have no native interpolation engine; native coverage is
    # qualified separately on disposables. Explicit failure tests override this.
    kwargs.setdefault("sample_validator", lambda *args: [{"genericFixture": True}])
    return native_prepare_iter(font, request, **kwargs)
from glyphs_mcp_protocol.preparation.path_doctor import path_state


def font_fixture(factory=duplicate_fixture):
    layers=Collection()
    for identity in ['M0','M1','M2']:
        layer,path=factory();layer.layerId=layer.id=identity;layer.width=500;layers.append(layer)
    glyph=NS(name='generic',layers=layers)
    return NS(glyphs=Collection([glyph]),masters=[NS(id=l.layerId) for l in layers]),glyph


def test_default_and_invalid_settings():
    from glyphs_mcp_protocol import recognized_job_capabilities
    assert recognized_job_capabilities(['path.cleanup.v1'])==['path.cleanup.v1']
    assert path_cleanup.validate_options({'glyphs':['a']})['operations']==['duplicates']
    for options in ({'glyphs':['a'],'maxDeviation':float('nan')}, {'glyphs':['a'],'operations':['align_handles']}, {'glyphs':['a'],'layers':'all_masters'}, {'glyphs':['a'],'operations':[]}):
        with pytest.raises(Exception):path_cleanup.validate_options(options)


def test_coordinated_duplicates_prepare_without_touching_source():
    font,glyph=font_fixture();before=[path_state(l.paths[0]) for l in glyph.layers]
    changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all'}}))
    assert len(changes)==3
    assert [r['removedNodes'] for r in report['layers']]==[2,2,2]
    assert not report['held']
    assert [path_state(l.paths[0]) for l in glyph.layers]==before
    assert consume(prepare_iter(font,{'options':{'glyphs':'all'}}))==(changes,report)


def test_one_layer_conflict_holds_whole_group():
    font,glyph=font_fixture();glyph.layers[1].paths[0].nodes[2].name='authored'
    changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all'}}))
    assert not changes and report['held']


def test_brace_participates_and_unknown_special_holds():
    font,glyph=font_fixture();brace=deepcopy(glyph.layers[0]);brace.layerId='brace';brace.isBraceLayer=True
    glyph.layers.append(brace)
    changes,_=consume(prepare_iter(font,{'options':{'glyphs':'all'}}));assert len(changes)==4
    brace.isBraceLayer=False;brace.isSpecialLayer=True
    changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all'}}));assert not changes and report['held']


def test_partial_bracket_branch_is_held():
    font,glyph=font_fixture();bracket=deepcopy(glyph.layers[0]);bracket.layerId='bracket';bracket.isBracketLayer=True
    bracket.associatedMasterId='M0';bracket.attributes={'axisRules':[{'min':500}]};glyph.layers.append(bracket)
    with pytest.raises(ValueError,match='every master'):groups(font,glyph)


def test_stroke_profiles_are_not_bounded_candidates():
    _,path=fixture(True)
    opts=path_cleanup.validate_options({'glyphs':'all','policy':'bounded','operations':list(path_cleanup.BOUNDED)})
    assert not list(candidates(path_state(path),opts))


def test_boundary_budget_and_intersections():
    _,path=duplicate_fixture();path.nodes=[path.nodes[0],path.nodes[1],path.nodes[-1]]
    state=path_state(path);changed=deepcopy(state);changed['nodes'][1]['x']+=1
    with pytest.raises(ValueError,match='budget'):validate_bounded([state],[changed],.1)
    evidence=validate_bounded([state],[changed],2)
    assert evidence['boundaryErrorUpperBound']<=2


def test_settings_update_is_revision_bound_and_analysis_never_saves(tmp_path):
    from glyphs_mcp_sidecar.edit_workflow import EditWorkflows
    from glyphs_mcp_sidecar.edit_workflow_state import action_token, public_workflow
    from glyphs_mcp_sidecar.service import ServiceError
    from contextlib import nullcontext
    calls=[]
    service=NS(jobs=NS(root=tmp_path),lifecycle=NS(mutation=lambda:nullcontext()))
    def start_job(document_id,**kwargs):
        calls.append((document_id,kwargs));return {'id':'analysis1','status':'preparing','resultKind':'diagnostic'}
    service.start_job=start_job
    workflows=EditWorkflows(service,ServiceError);workflows._start_runner=lambda:None
    options=path_cleanup.validate_options({'glyphs':['a']})
    request=dict(kind='path_cleanup',glyphs=[],options=options)
    value=workflows.store.create({'id':'doc1','path':None,'dirty':True},dict(kind='path_cleanup',options=options),request,'preview','key')
    workflows.store.update(value,state='waiting_save')
    revision=value['revision'];token=action_token(value,'configure_cleanup')
    settings={'policy':'exact','operations':['duplicates','seams']}
    result=workflows.configure_cleanup(value['id'],revision,token,settings)
    assert result['state']=='diagnosing'
    assert calls==[('doc1',{'kind':'path_diagnostics','options':{'glyphs':['a'],'layers':'all_interpolation_layers'}})]
    assert workflows.configure_cleanup(value['id'],revision,token,settings)['state']=='diagnosing'
    assert len(calls)==1
    with pytest.raises(ServiceError,match='different settings'):
        workflows.configure_cleanup(value['id'],revision,token,{'operations':['seams']})
    with pytest.raises(ServiceError,match='Refresh'):
        workflows.configure_cleanup(value['id'],revision,token+'stale',settings)
    assert public_workflow(value)['pathDoctor']['settings']['glyphs']==['a']


def near_fixture():
    layer,path=duplicate_fixture()
    path.nodes=[Node(x,y) for x,y in [(0,0),(.1,.01),(100,0),(100,100),(0,100)]]
    for node in path.nodes:node.userData={};node.attributes={}
    path.nodes[1].smooth=True
    return layer,path


def test_intermediate_failure_holds_every_master_without_writes():
    font,glyph=font_fixture(near_fixture)
    before=[path_state(l.paths[0]) for l in glyph.layers]
    def reject(*args):raise ValueError('sample at Weight 500 exceeds budget')
    changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all','policy':'bounded','operations':['near_nodes']}},sample_validator=reject))
    assert not changes and any('Weight 500' in row['reason'] for row in report['held'])
    assert [path_state(l.paths[0]) for l in glyph.layers]==before


def test_native_side_effect_holds_candidate(monkeypatch):
    import glyphs_mcp_protocol.preparation.path_cleanup as cleanup
    font,glyph=font_fixture(near_fixture);original=cleanup._apply
    def changed_metrics(layer,operation):
        result=original(layer,operation);layer.width+=1;return result
    monkeypatch.setattr(cleanup,'_apply',changed_metrics)
    changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all','policy':'bounded','operations':['near_nodes']}},sample_validator=lambda *args:[]))
    assert not changes and any('unrelated layer data' in row['reason'] for row in report['held'])
    assert all(layer.width==500 for layer in glyph.layers)


def test_cleanup_report_survives_job_projection(tmp_path):
    from glyphs_mcp_sidecar.job_preparation import _mutation_report
    font,_=font_fixture();changes,report=consume(prepare_iter(font,{'options':{'glyphs':'all'}}))
    public=_mutation_report(report,tmp_path/'report.json')
    assert public['changedLayers']==3 and public['removedNodes']==6
    assert public['heldCount']==0 and public['unchangedLayers']==0


def test_samples_include_brace_exports_midpoints_and_boundary_sides():
    from glyphs_mcp_protocol.preparation.path_cleanup_samples import locations
    masters=[NS(id='M0',axes=[100]),NS(id='M1',axes=[900])]
    font=NS(masters=masters,axes=[NS()],instances=[NS(exports=True,axes=[725])])
    brace=NS(isBraceLayer=True,attributes={'coordinates':{'0':400}},associatedMasterId='M0')
    bracket=NS(isBracketLayer=True,attributes={'axisRules':[{'min':500}]})
    points=locations(font,[brace],[bracket]);values=[p[0] for p in points]
    assert {100,250,400,500,650,725,900}<=set(values)
    assert any(499.99<x<500 for x in values) and any(500<x<500.01 for x in values)
    bracket.attributes['axisRules']=[{'min':{'float':float(500.5).hex()}}]
    fractional=[p[0] for p in locations(font,[brace],[bracket])]
    assert 500.5 in fractional and any(500.49<x<500.5 for x in fractional)


def test_native_rounding_zero_measurement_edges_are_not_intersections():
    layer,path=near_fixture();before=path_state(path);before['nodes'][1].update(x=0,y=0)
    after=deepcopy(before);del after['nodes'][1]
    assert validate_bounded([before],[after],.5)['boundaryErrorUpperBound']<.5


def test_exact_sample_geometry_retains_real_curves_and_profiles():
    from glyphs_mcp_protocol.preparation.path_cleanup_samples import exact_geometry
    from glyphs_mcp_protocol.preparation.path_doctor import normalize
    from glyphs_mcp_protocol.outline import path_hash
    layer,path=fixture(True);before=path_state(path)
    normalize(layer,path,path_hash(before));after=path_state(path)
    assert exact_geometry([before])==exact_geometry([after])
    after['nodes'][1]['x']+=.001
    assert exact_geometry([before])!=exact_geometry([after])


def test_cumulative_budget_is_against_original_not_previous_step():
    _,path=near_fixture();original=path_state(path);del original['nodes'][1]
    first=deepcopy(original);first['nodes'][1]['x']+=.3
    last=deepcopy(first);last['nodes'][1]['x']+=.3
    assert validate_bounded([original],[first],.5)
    assert validate_bounded([first],[last],.5)
    with pytest.raises(ValueError,match='budget'):validate_bounded([original],[last],.5)


def test_self_crossing_outline_is_held():
    from glyphs_mcp_protocol.preparation.path_cleanup import topology
    _,path=near_fixture();state=path_state(path)
    state['nodes']=[dict(state['nodes'][0],x=x,y=y) for x,y in [(0,0),(100,100),(0,100),(100,0)]]
    with pytest.raises(ValueError,match='intersection'):topology([state],.002)


def test_diagnosed_card_survives_refresh_and_closes_without_discard(tmp_path):
    from glyphs_mcp_sidecar.edit_workflow import EditWorkflows
    from glyphs_mcp_sidecar.edit_workflow_state import offered_actions
    from glyphs_mcp_sidecar.service import ServiceError
    service=NS(jobs=NS(root=tmp_path))
    workflows=EditWorkflows(service,ServiceError)
    value=workflows.store.create({'id':'doc1'},dict(kind='path_cleanup'),dict(kind='path_cleanup',options={}), 'preview','key')
    workflows.store.update(value,state='diagnosed',job={'id':'analysis1','status':'completed','resultKind':'diagnostic'},jobId='analysis1')
    workflows._advance(value)
    assert value['state']=='diagnosed' and ('cancel','Close Path Doctor') in offered_actions(value)
    workflows._respond(value,'cancel',None,None)
    assert value['state']=='cancelled'
