"""Original generic stroke measurements and multi-master selection constraints."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('pen_strategy',ROOT/'skills/glyphs-mcp-path-doctor/scripts/pen_point_strategy.py')
strategy=importlib.util.module_from_spec(spec);spec.loader.exec_module(strategy)


def rectangle(dx=0,reverse=False):
    points=[(0,0),(20,0),(20,10),(0,10)]
    if reverse:points.reverse()
    return {'closed':True,'nodes':[{'x':x+dx,'y':y,'type':'line'} for x,y in points]}


def test_known_parallel_boundary_distance_has_a_conservative_bound():
    result=strategy.boundary_error([rectangle()],[rectangle(.125)],step=.5,flatness=.001)
    assert result['sampledBoundaryError']==pytest.approx(.125)
    assert result['boundaryErrorUpperBound']>=.125


def test_identical_curved_outlines_and_fractional_geometry():
    path={'closed':True,'nodes':[{'x':0,'y':0,'type':'line'},
        {'x':10.125,'y':0,'type':'line'},{'x':20.25,'y':20.25,'type':'offcurve'},
        {'x':-10.125,'y':20.25,'type':'offcurve'},{'x':0,'y':0,'type':'curve'}]}
    assert strategy.boundary_error([path],[path])['sampledBoundaryError']==pytest.approx(0,abs=1e-10)


def test_counter_topology_and_winding_changes_are_held():
    with pytest.raises(ValueError):strategy.boundary_error([rectangle()],[rectangle(),rectangle()])
    with pytest.raises(ValueError):strategy.boundary_error([rectangle()],[rectangle(reverse=True)])


def test_greedy_trials_use_original_error_so_small_changes_cannot_accumulate():
    def evaluate(removed):return {'regular':{'edge':.6*len(removed)}}
    plan=strategy.choose_removals(['a','b'],evaluate,{'edge':1},required_cases=['regular'])
    assert plan['removed']==['a'] and plan['held']==['b']


def test_worst_master_wins_instead_of_average_and_pins_survive():
    def evaluate(removed):return {'light':{'edge':0},'bold':{'edge':2 if 'bad' in removed else 0}}
    plan=strategy.choose_removals(['bad','good','endpoint'],evaluate,{'edge':1},
        required_cases=['light','bold'],pinned=['endpoint'])
    assert plan['removed']==['good'] and plan['held']==['bad','endpoint']


def test_missing_intermediate_case_is_not_treated_as_zero_error():
    with pytest.raises(ValueError):
        strategy.choose_removals(['a'],lambda removed:{'light':{'edge':0}},
            {'edge':1},required_cases=['light','middle'])


def test_missing_nonfinite_or_negative_measurement_refuses():
    for value in [-1,float('inf'),float('nan')]:
        with pytest.raises(ValueError):
            strategy.choose_removals(['a'],lambda removed:{'m':{'edge':value}},
                {'edge':1},required_cases=['m'])
    with pytest.raises(KeyError):
        strategy.choose_removals(['a'],lambda removed:{'m':{}},{'edge':1},required_cases=['m'])


def test_exact_mode_and_master_correspondence_are_hard_constraints():
    def evaluate(removed):return {'m':{'edge':0,'layoutMismatch':int('single' in removed)}}
    plan=strategy.choose_removals(['joint','single'],evaluate,{'edge':0,'layoutMismatch':0},required_cases=['m'])
    assert plan['removed']==['joint']
