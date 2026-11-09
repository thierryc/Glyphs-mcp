"""Analytic curve fixtures and conservative, non-mutating quality reports."""
from copy import deepcopy
from types import SimpleNamespace as NS
import math
import pytest
from test_simple_v2_path_fitting import polygon,circle,font_fixture
from glyphs_mcp_protocol.path_quality import path_findings,layer_findings,signed_area
from glyphs_mcp_protocol.preparation.path_doctor import inspect_path,path_state,prepare_iter
from glyphs_mcp_protocol.preparation import consume


def curve(points):
    return {'closed':False,'locked':False,'attributeState':{'attributes':{},'userData':{}},
            'nodes':[{'x':x,'y':y,'type':kind,'smooth':False,'name':None,
                      'attributeState':{'attributes':{},'userData':{}}}
                     for (x,y),kind in zip(points,['line','offcurve','offcurve','curve'])]}


def codes(state):return {row[0]:row for row in path_findings(state)}


def test_zero_handles_are_distinct_from_duplicate_lines_and_have_no_automatic_repair():
    state=curve([(0,0),(0,0),(100,100),(100,0)]);before=deepcopy(state)
    findings=inspect_path(state,glyph='test',layer='M',path=0)
    assert any(f['code']=='zero_handle' and f['confidence']=='definite' for f in findings)
    assert not any(f['repair'] for f in findings)
    assert not any(f['code']=='consecutive_duplicate_nodes' for f in findings)
    assert state==before


def test_forward_triangle_overshoot_and_parallel_exception():
    assert 'handle_triangle_violation' in codes(curve([(0,0),(200,0),(100,-100),(100,100)]))
    assert 'handle_triangle_violation' not in codes(curve([(0,0),(100,0),(200,0),(300,0)]))


def test_inflection_extrema_and_stationary_events_are_not_conflated():
    findings=codes(curve([(0,0),(100,100),(200,-100),(300,0)]))
    assert findings['inflection_review'][3]['pathTimes']==[.5]
    events=findings['interior_extrema'][3]['events']
    assert len(events)==2 and all(e['axis']=='y' for e in events)
    assert 'stationary_curve_review' not in findings
    cusp=codes(curve([(0,0),(100,100),(-100,-100),(0,0)]))
    assert len(cusp['stationary_curve_review'][3]['pathTimes'])==2


def test_stroke_conventions_are_excluded_and_large_or_quadratic_paths_report_coverage():
    state=curve([(0,0),(0,0),(100,100),(100,0)])
    state['attributeState']['attributes']['strokeWidth']=20
    assert not codes(state)
    state['attributeState']['attributes']={};state['nodes'][-1]['type']='qcurve'
    assert 'quality_analysis_held' in codes(state)
    assert 'quality_analysis_held' in codes(path_state(circle(513)))


def test_winding_alternates_for_nested_counters_without_mutation():
    states=[(0,path_state(circle(32))),(1,path_state(circle(16,rx=20,ry=20)))]
    before=deepcopy(states);findings=list(layer_findings(states))
    winding=[(i,row) for i,row in findings if row[0]=='path_direction_review']
    assert len(winding)==1 and winding[0][0]==1
    assert winding[0][1][3]['expectedDirection']=='clockwise'
    assert winding[0][1][3]['nestingDepth']==1
    states[1]=(1,path_state(circle(16,rx=20,ry=20,clockwise=True)))
    assert not any(row[0]=='path_direction_review' for _,row in layer_findings(states))
    assert before[0]==states[0]


def test_exact_cubic_area_and_small_distant_debris_candidates():
    # A cubic arch closed by a straight line has analytic area magnitude 60.
    state=curve([(0,0),(0,10),(10,10),(10,0)])
    state['closed']=True
    assert math.isclose(abs(signed_area(state)),60)
    tiny=path_state(polygon([(5000,0),(5000.1,0),(5000.1,.1),(5000,.1)]))
    findings={row[0] for _,row in layer_findings([(0,tiny)],width=500)}
    assert {'tiny_contour_review','distant_contour_review'}<=findings


def test_overlaps_are_review_findings_and_never_direction_repairs():
    states=[(0,path_state(circle(16))),(1,path_state(circle(16,cx=150)))]
    findings=list(layer_findings(states))
    assert any(row[0]=='topology_review' for _,row in findings)
    assert not any(row[0]=='path_direction_review' for _,row in findings)


def test_live_scan_stable_addresses_and_incomplete_quality_coverage():
    font,glyph=font_fixture(lambda i:[circle(513)])
    req={'options':{'glyphs':'all','layers':'all_masters'}}
    _,report=consume(prepare_iter(font,req,document_id='doc'))
    assert report['coverage']['complete'] is False
    assert report['issueCounts']['quality_analysis_held']==2
    assert consume(prepare_iter(font,req,document_id='doc'))[1]==report
    assert all(f['repair'] is None and f['stateHash'].startswith('sha256:') and
               f['target']['document']=='doc' for f in report['issues'])


def test_malformed_path_does_not_abort_layer_quality_scan():
    font,glyph=font_fixture()
    glyph.layers[0].paths[0].nodes[0].type='curve'
    _,report=consume(prepare_iter(font,{'options':{'glyphs':'all'}}))
    assert report['issueCounts']['malformed_segments']==1


def test_topology_subdivision_has_a_bounded_work_budget(monkeypatch):
    from glyphs_mcp_protocol import path_measurements
    monkeypatch.setattr(path_measurements,'MAX_TOPOLOGY_CELLS',2)
    state=curve([(0,0),(0,100),(100,100),(100,0)])
    with pytest.raises(ValueError,match='work limit'):path_measurements.topology_cells(state,.002)
