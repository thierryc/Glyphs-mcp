"""Milestone 2: scope-proportional reads with unchanged guards and exact recovery."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_simple_v2_native_actions import NativeGlyph as Glyph, Collection
from test_simple_v2_outline_edit import Node, PathShape
from glyphs_mcp_protocol.preparation import consume, simple, native_action
from glyphs_mcp_bridge import native_actions, outline_edit


class MetadataGlyph(Glyph):
    """Full-copy and live serialization fail; detached metadata preserves the guard."""
    def copy(self):
        raise AssertionError('must not copy outlines')

    def propertyListValueFormat_(self, _format):
        raise AssertionError('must not serialize live outlines')

    def copyWithOptions_(self, options):
        assert options == 0
        value = Glyph(self.name, [])
        for key, item in vars(self).items():
            if key not in ('layers', 'undoManager'): setattr(value, key, deepcopy(item))
        return value


@pytest.mark.parametrize('initial,wanted', [(None, 'orange'), (1, 'none'), (1, 'orange')])
def test_color_preparation_uses_metadata_only_and_keeps_patch_report(initial, wanted):
    live = MetadataGlyph('h', [object()]); live.color = initial
    detached = live.copyWithOptions_(0)
    request = dict(options=dict(action='set_glyph_color', arguments=dict(color=wanted), targets=[dict(glyph='h')]))
    expected = native_action.prepare(NS(glyphs=Collection([detached])), request)
    actual = consume(native_action.prepare_iter(NS(glyphs=Collection([live])), request, detached=True))
    assert actual == expected
    assert live.color == initial and len(live.layers) == 1


def test_custom_color_is_still_rejected_without_reading_outlines():
    live = MetadataGlyph('h', [object()]); live.info['color'] = [.2, .3, .4, 1.]
    request = dict(options=dict(action='set_glyph_color', arguments=dict(color='orange'), targets=[dict(glyph='h')]))
    with pytest.raises(native_action.WorkerError, match='custom glyph color'):
        consume(native_action.prepare_iter(NS(glyphs=Collection([live])), request, detached=True))
    assert live.color is None


class IndexedGlyphs:
    def __init__(self, glyphs): self.lookup = {g.name: g for g in glyphs}; self.reads=[]
    def __iter__(self): raise AssertionError('must not enumerate unrelated glyphs')
    def __getitem__(self, name): self.reads.append(name); return self.lookup.get(name)


def width_font():
    a=NS(name='A', layers=[NS(layerId='M1',width=500.25), NS(layerId='M2',width=600.5), NS(layerId='special',width=300.75)])
    b=NS(name='B', layers=[NS(layerId='M1',width=700)])
    return NS(glyphs=IndexedGlyphs([a,b]), indexOfGlyph_=lambda g: {'A':0,'B':1}[g.name])


def test_named_widths_lookup_only_requested_glyphs_and_preserve_font_order_scope():
    font=width_font()
    changes, report=consume(simple.width_iter(font, dict(glyphs=['B','A'],delta=.25)))
    assert [(c['glyph'],c['layer'],c['after']) for c in changes]==[
        ('A','M1',500.5),('A','M2',600.75),('A','special',301),('B','M1',700.25)]
    assert report is None
    assert sorted(font.glyphs.reads)==['A','B']
    assert font.glyphs.lookup['A'].layers[0].width==500.25


def test_missing_named_widths_fail_without_scanning_other_glyphs():
    font=width_font()
    with pytest.raises(ValueError, match='missing.*absent'):
        consume(simple.width_iter(font, dict(glyphs=['A','absent'],delta=.25)))
    assert sorted(font.glyphs.reads)==['A','absent']


@pytest.mark.parametrize('name',[None,'','named'])
def test_outline_restore_preserves_exact_node_name_identity_and_fractional_position(name):
    node=Node(10.25,700.5);node.name=name
    path=PathShape([node,Node(20.75,0)])
    layer=NS(paths=[path],shapes=[path],selection=[node])
    before=outline_edit.hash_layer(layer);snapshot=outline_edit.capture(layer)
    node.name='changed';node.position=(30.125,50.875)
    outline_edit.restore(layer,snapshot)
    assert node.name==name and path.nodes[0] is node
    assert outline_edit.hash_layer(layer)==before
    assert layer.selection==[node]


def test_native_name_setter_receives_nil_instead_of_wrapper_string_conversion():
    class NativeNode(Node):
        def setName_(self,value):self.name=value
    node=NativeNode(1.25,2.5);path=PathShape([node,Node(5,6)])
    layer=NS(paths=[path],shapes=[path],selection=[])
    snapshot=outline_edit.capture(layer);node.name='later'
    outline_edit.restore(layer,snapshot)
    assert node.name is None


def test_preparation_and_application_agree_on_clearing_node_name():
    from glyphs_mcp_protocol.preparation import outline
    node=Node(1.25,2.5);node.name='named'
    path=PathShape([node,Node(5,6)]);layer=NS(paths=[path],shapes=[path],selection=[])
    outline._apply(layer,dict(op='update_nodes',path=0,updates=[dict(index=0,name=None)]))
    assert node.name is None


def test_custom_native_color_rejected_before_metadata_copy_loses_it():
    live=MetadataGlyph('h',[]);live.colorObject=object()
    live.copyWithOptions_=lambda _:pytest.fail('custom label must be checked before copying')
    with pytest.raises(native_action.WorkerError,match='custom glyph color'):
        native_action._detached_color_metadata(live)


def test_absent_metadata_copy_api_fails_explicitly_without_full_copy_fallback():
    live=Glyph('h',[]);live.copy=lambda:pytest.fail('no hidden full-copy fallback')
    with pytest.raises(native_action.WorkerError,match='metadata preparation'):
        native_action._detached_color_metadata(live)


def test_detached_color_patch_retains_full_metadata_conflict_guard():
    live=MetadataGlyph('h',[])
    request=dict(options=dict(action='set_glyph_color',arguments=dict(color='orange'),targets=[dict(glyph='h')]))
    changes,_=consume(native_action.prepare_iter(NS(glyphs=Collection([live])),request,detached=True))
    owner=live.copyWithOptions_(0)
    assert native_actions.current_hash(owner,'glyph',changes[0])==changes[0]['beforeHash']
    owner.note='intervening edit'
    assert native_actions.current_hash(owner,'glyph',changes[0])!=changes[0]['beforeHash']


def test_unreadable_native_color_does_not_silently_become_absent():
    class Unreadable(MetadataGlyph):
        @property
        def colorObject(self):raise RuntimeError('color read failed')
    with pytest.raises(RuntimeError,match='color read failed'):
        native_action._detached_color_metadata(Unreadable('h',[]))


def test_keyed_missing_width_lookup_does_not_fallback_to_font_enumeration():
    font=width_font()
    class KeyErrorGlyphs(IndexedGlyphs):
        def __getitem__(self,name):return self.lookup[name]
    font.glyphs=KeyErrorGlyphs(font.glyphs.lookup.values())
    with pytest.raises(ValueError,match='missing.*absent'):
        consume(simple.width_iter(font,dict(glyphs=['absent'],delta=.25)))
