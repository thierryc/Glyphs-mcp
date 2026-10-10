"""Selection semantics and direct native actions, with explicit API doubles."""
import copy
from types import SimpleNamespace
import pytest
from test_curve_repair import Font, Node, Layer, PathDouble
from curve_repair.actions import resolve_scope, Scope, Result, selected_joins, apply_steps, prepare_path, commit_paths, trial_fonts, validate_limit
from curve_repair.native import path_state, position
from curve_repair.geometry import diagnose_join
from curve_repair.joins import source_join

APP=SimpleNamespace(CURVE='curve',OFFCURVE='offcurve',LINE='line',GSSHARP=100,GSSMOOTH=101,GSSUPERSMOOTH=102)
PathDouble.copy=lambda self:copy.deepcopy(self)

class Glyphs(dict):
    def __iter__(self): return iter(self.values())

def fixture():
    f=Font();f.glyphs=Glyphs(f.glyphs);f.selection=[];f.currentTab=object();f.selectedFontMaster=f.masters[0]
    g=f.glyphs['test'];g.undoManager=lambda:SimpleNamespace(isUndoRegistrationEnabled=lambda:True)
    l=g.layers[0]
    return f,g,l

def run(scope,**kw):
    task=apply_steps(scope,APP,**kw)
    while True:
        try:next(task)
        except StopIteration as done:return done.value

def scope(f,l,selection=None): return Scope(f,(l.parent,),l,False,tuple(l.selection if selection is None else selection))


@pytest.mark.parametrize('result,message', [
    (Result(already_smooth=3), 'No change · already smooth'),
    (Result(threshold_rejected=2, max_change_units=1), 'No change · over 1-unit limit'),
    (Result(unsupported=1, reasons=['o / path 0: Locked outline']), 'No change · selection is locked'),
    (Result(unsupported=1, reasons=['o: Select an on-curve, curve handle or path']), 'No change · select a node, handle or path'),
    (Result(), 'No change · no eligible joins'),
])
def test_no_change_message_explains_reason_and_retains_detailed_counts(result,message):
    assert result.message() == message
    assert 'Repaired:' in result.details() and 'Limit blocked:' in result.details()
    assert all(reason in result.details() for reason in result.reasons)

def test_font_tab_selected_or_whole_font_ignores_edit_layer():
    f,g,l=fixture();f.currentTab=None
    host=SimpleNamespace(font=f)
    s=resolve_scope(host,lambda _:l)
    assert s.glyphs==(g,) and s.layer is None and 'Whole font' in s.description
    f.selection=[g];assert 'Selected glyphs' in resolve_scope(host,lambda _:None).description
    f.selection=None
    with pytest.raises(Exception,match='unavailable'): resolve_scope(host,lambda _:l)

def test_edit_scope_selection_and_empty_whole_glyph_background_identity():
    f,g,l=fixture();host=SimpleNamespace(font=f)
    assert resolve_scope(host,lambda _:l).selection==tuple(l.selection)
    l.selection=[];assert 'whole glyph' in resolve_scope(host,lambda _:l).description
    l.hasBackground=True;l.background=Layer(l.layerId);l.background.parent=l
    assert resolve_scope(host,lambda _:l.background).background

def test_selected_curve_handle_includes_smooth_join_without_expanding_corners():
    f,g,l=fixture();p=l.paths[0]
    assert selected_joins(p,[p.nodes[4]],APP)[0]==(3,)
    assert selected_joins(p,[p],APP)[0]==(3,)
    assert selected_joins(p,[object()],APP)[0]==()

def test_font_scope_status_does_not_traverse_unselected_font():
    class Inventory:
        def __len__(self):return 1234
        def __iter__(self):raise AssertionError('UI must not traverse whole font')
    f,g,l=fixture();f.currentTab=None;f.glyphs=Inventory()
    s=resolve_scope(SimpleNamespace(font=f),lambda _:None,capture=False)
    assert '1234' in s.description




def test_healthy_ordinary_nodes_and_existing_stars_are_star_noops_with_hints():
    f,g,l=fixture();p=l.paths[0];p.nodes[4].position=(40,0)
    l.hints=[object()];g.layers[1].hints=[object()]
    old=path_state(p);r=run(scope(f,l))
    assert r.changed==0 and r.already_smooth==1 and path_state(p)==old
    p.nodes[3].connection=102;r=run(scope(f,l))
    assert r.changed==0 and r.already_smooth==1

def test_star_repairs_only_bad_join_and_preserves_stored_coordinates():
    f,g,l=fixture();before=[position(n) for n in l.paths[0].nodes]
    r=run(scope(f,l))
    assert r.repaired==1 and not r.skipped and l.paths[0].nodes[3].connection==102
    assert [position(n) for n in l.paths[0].nodes]==before and f.undo_depth==0
    assert run(scope(f,l)).changed==0

def test_default_node_moves_join_using_native_repair_and_tunni_stays_within_limit():
    f,g,l=fixture();r=run(scope(f,l),method='default-node')
    p=l.paths[0]
    assert r.repaired==1 and position(p.nodes[3])==(-.5,0) and p.nodes[3].connection==101
    assert position(p.nodes[1])==(-100,40) # Tunni would exceed one unit.
    assert any('Tunni omitted' in n for n in r.notes)
    assert r.max_outline_change_units<=1
    a,b=source_join(p,3,APP);assert diagnose_join(a.curve,b.curve)['g2']
    assert run(scope(f,l),method='default-node').changed==0

def test_tunni_can_be_accepted_with_a_larger_budget():
    f,g,l=fixture();r=run(scope(f,l),method='default-node',max_change_units=100)
    assert r.repaired==1 and not r.notes and position(l.paths[0].nodes[1])!=(-100,40)

def test_existing_star_conversion_measures_outline_not_stored_point_movement():
    f,g,l=fixture();p=l.paths[0];p.nodes[3].connection=102
    r=run(scope(f,l),method='default-node',max_change_units=.0001)
    assert r.converted==1 and position(p.nodes[3])==(-.5,0) and p.nodes[3].connection==101
    assert r.max_outline_change_units==0 and not r.skipped

def test_all_master_rejection_is_atomic_and_healthy_masters_can_noop():
    f,g,l=fixture();g.layers[1].paths[0].nodes[4].position=(30,0)
    before=[path_state(x.paths[0]) for x in g.layers]
    r=run(scope(f,l),all_masters=True,max_change_units=1)
    assert r.changed==0 and r.threshold_rejected==1
    assert [path_state(x.paths[0]) for x in g.layers]==before
    g.layers[1].paths[0].nodes[4].position=(40,0)
    r=run(scope(f,l),all_masters=True)
    assert r.repaired==1 and r.already_smooth==1
    assert g.layers[1].paths[0].nodes[3].connection==101

def test_incompatible_masters_refuse_without_partial_edits():
    f,g,l=fixture();g.layers[1].paths[0].nodes.pop()
    r=run(scope(f,l),all_masters=True)
    assert r.changed==0 and r.unsupported==1 and l.paths[0].nodes[3].connection==101

def test_threshold_below_at_and_above_certified_bound():
    f,g,l=fixture()
    bound=prepare_path(g,l,l,l.paths[0],(3,),APP,'star',1).maximum
    for limit,accepted in ((bound-1e-5,False),(bound,True),(bound+1e-5,True)):
        f,g,l=fixture();r=run(scope(f,l),max_change_units=limit)
        assert bool(r.repaired)==accepted
        assert (l.paths[0].nodes[3].connection==102)==accepted
        assert r.max_outline_change_units<=limit

@pytest.mark.parametrize('limit',[0,-1,float('nan'),float('inf'),'','abc'])
def test_invalid_limits_are_refused_before_mutation(limit):
    f,g,l=fixture()
    with pytest.raises(Exception,match='Max change'):run(scope(f,l),max_change_units=limit)
    assert l.paths[0].nodes[3].connection==101

def test_unresolved_bound_never_falls_back_to_unbounded_application(monkeypatch):
    from curve_repair import actions
    from curve_repair.geometry import RepairError
    f,g,l=fixture()
    def refuse(*a):raise RepairError('unresolved_deviation','Bound could not be certified')
    monkeypatch.setattr(actions,'outline_bound',refuse)
    r=run(scope(f,l),method='default-node')
    assert r.changed==0 and r.threshold_rejected==1 and l.paths[0].nodes[3].connection==101

def test_stale_connection_or_attribute_guard_rejects_prepared_result():
    f,g,l=fixture();p=l.paths[0]
    plan=prepare_path(g,l,l,p,(3,),APP,'star')
    p.nodes[3].attributes['hoi']=2
    with pytest.raises(Exception,match='Source changed'):commit_paths([plan],APP,1)
    assert p.nodes[3].connection==101

def test_second_master_write_failure_compensates_first_master(monkeypatch):
    f,g,l=fixture();trials=trial_fonts(f)
    plans=[prepare_path(g,x,x,x.paths[0],(3,),APP,'star',trials=trials) for x in g.layers]
    victim=g.layers[1].paths[0].nodes[3]
    original=Node.setConnection_
    def failing(self,c):
        original(self,c)
        if self is victim and c==102:raise RuntimeError('injected')
    monkeypatch.setattr(Node,'setConnection_',failing)
    with pytest.raises(RuntimeError):commit_paths(plans,APP,1)
    assert all(x.paths[0].nodes[3].connection==101 for x in g.layers)
    assert all(not x.temporarilyDisableRounding for x in g.layers) and f.undo_depth==0

def test_no_native_undo_stops_before_edit():
    f,g,l=fixture();g.undoManager=lambda:None
    with pytest.raises(Exception,match='Undo'):run(scope(f,l))
    assert l.paths[0].nodes[3].connection==101

def test_locked_node_and_backup_preservation():
    f,g,l=fixture();p=l.paths[0];p.nodes[3].locked=True
    assert run(scope(f,l)).changed==0 and p.nodes[3].connection==101
    p.nodes[3].locked=False;backup=Layer('backup');backup.parent=g;g.layers.append(backup)
    assert run(scope(f,l,[]),all_masters=True).repaired==2
    assert backup.paths[0].nodes[3].connection==101

@pytest.mark.parametrize('reverse',[False,True])
def test_line_curve_star_and_regular_alignment(reverse):
    from test_curve_repair_line_curve import fixture as make
    adapter,f,l=make(reverse=reverse);g=l.parent
    g.undoManager=lambda:SimpleNamespace(isUndoRegistrationEnabled=lambda:True)
    f.selectedFontMaster=f.masters[0];p=l.paths[0];join=p.join
    r=run(scope(f,l),method='default-node',max_change_units=10)
    assert r.repaired==1 and not r.skipped and p.nodes[join].connection==101
    a,b=source_join(p,join,APP);assert diagnose_join(a.curve,b.curve)['g2']
    adapter,f,l=make(reverse=reverse);g=l.parent
    g.undoManager=lambda:SimpleNamespace(isUndoRegistrationEnabled=lambda:True);f.selectedFontMaster=f.masters[0]
    r=run(scope(f,l),method='star',max_change_units=1)
    assert r.repaired==1 and not r.skipped
    assert run(scope(f,l),method='default-node',max_change_units=100).unsupported==1


def test_multiple_contours_share_one_glyph_undo_and_independent_limit_failures():
    f,g,l=fixture();l.paths.append(PathDouble(30));l.selection=[]
    starts=[]
    g.beginUndo=lambda:starts.append('begin')
    g.endUndo=lambda:starts.append('end')
    r=run(scope(f,l))
    assert r.repaired==1 and r.threshold_rejected==1
    assert l.paths[0].nodes[3].connection==102 and l.paths[1].nodes[3].connection==101
    assert starts==['begin','end']
    l.paths[1].nodes[4].position=(39,0);l.paths[0].nodes[3].connection=101;starts.clear()
    r=run(scope(f,l));assert r.repaired==2 and starts==['begin','end']


def test_corresponding_master_corner_is_preserved_unless_join_explicitly_selected():
    f,g,l=fixture();l.selection=[];g.layers[1].paths[0].nodes[3].connection=APP.GSSHARP
    r=run(scope(f,l),all_masters=True)
    assert r.changed==0 and r.unsupported==1 and g.layers[1].paths[0].nodes[3].connection==APP.GSSHARP
    r=run(scope(f,l,[l.paths[0].nodes[3]]),all_masters=True)
    assert r.repaired==2


def test_expanded_hints_and_strokes_on_edited_contours_are_unqualified():
    f,g,l=fixture();p=l.paths[0]
    l.hints=[SimpleNamespace(isCorner=True,originNode=p.nodes[3])]
    r=run(scope(f,l));assert r.changed==0 and r.unsupported==1
    l.hints=[];p.attributes['strokeWidth']=10
    r=run(scope(f,l));assert r.changed==0 and r.unsupported==1


def test_all_masters_from_backup_does_not_edit_backup():
    f,g,l=fixture();backup=Layer('backup');backup.parent=g;g.layers.append(backup)
    before=path_state(backup.paths[0])
    r=run(scope(f,backup,[]),all_masters=True)
    assert r.repaired==2 and path_state(backup.paths[0])==before
