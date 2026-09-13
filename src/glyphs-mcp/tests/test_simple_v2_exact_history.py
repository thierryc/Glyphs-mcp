"""Grouped native values share exact history and partial-write recovery."""
from types import SimpleNamespace as NS

import pytest

from test_simple_v2_glyphs_adapter import adapter, UndoManager
from test_simple_v2_slant import Layer, Node, Point
from glyphs_mcp_bridge import coordinates


class History(UndoManager):
    def __init__(self):
        super().__init__()
        self.actions = []
        self.enabled = True
    def disableUndoRegistration(self): self.enabled = False
    def enableUndoRegistration(self): self.enabled = True
    def registerUndoWithTarget_handler_(self, target, handler):
        assert self.enabled
        self.actions.append((target, handler))
    def undo(self):
        actions, self.actions = self.actions, []
        for target, handler in reversed(actions): handler(target)


def coordinate_change(layer):
    change = {'kind': 'coordinates', 'glyph': 'A', 'layer': layer.layerId,
              'topologyHash': coordinates.signature(layer),
              'nodes': [[0, i] for i in range(4)], 'anchors': ['top'], 'components': []}
    change['before'] = coordinates.read(layer, change)
    change['after'] = [[x + .375, y + .125] for x, y in change['before']]
    return change


class RoundingNode(Node):
    def __init__(self, layer, point):
        self.layer = layer
        self._position = Point(*point)
        self.userData = {'keep': 'metadata'}
        self.fail = False
    @Node.position.setter
    def position(self, value):
        self._position = Point(*(value if self.layer.temporarilyDisableRounding else map(round, value)))
        if self.fail:
            self.fail = False
            raise RuntimeError('partial native setter')


def native_layer(mid='M1'):
    layer = Layer()
    layer.layerId = mid
    layer.paths[0].nodes = [RoundingNode(layer, n.position) for n in layer.paths[0].nodes]
    layer.hints = [NS(originNode=layer.paths[0].nodes[0], targetNode=layer.paths[0].nodes[1])]
    return layer


def test_fractional_coordinates_undo_redo_multiple_masters_preserve_other_state():
    layers = [native_layer(mid) for mid in ('M1', 'M2', 'M3')]
    value, _ = adapter(layers[0])
    document = value.list_documents()[0]['id']
    value._font(document).glyphs['A'].layers.extend(layers[1:])
    manager = History()
    for layer in layers: layer.undoManager = lambda: manager
    changes = [coordinate_change(layer) for layer in layers]
    metadata = [(l.width, coordinates.signature(l), l.hints[0].originNode,
                 [id(n) for n in l.paths[0].nodes]) for l in layers]
    value.begin_undo(document)
    for change in changes: value.apply_change(document, change)
    value.end_undo(document, 'Coordinates')
    for direction in ('after', 'before', 'after', 'before'):
        assert [coordinates.read(l, c) for l, c in zip(layers, changes)] == [c[direction] for c in changes]
        assert all(not l.temporarilyDisableRounding for l in layers)
        assert [(l.width, coordinates.signature(l), l.hints[0].originNode,
                 [id(n) for n in l.paths[0].nodes]) for l in layers] == metadata
        assert manager.enabled
        manager.undo()
    assert manager.events == ['begin', 'Coordinates', 'end']


def test_failed_native_history_write_restores_flags_and_registration():
    layer = native_layer()
    value, _ = adapter(layer)
    document = value.list_documents()[0]['id']
    manager = History()
    layer.undoManager = lambda: manager
    value.begin_undo(document)
    value.apply_change(document, coordinate_change(layer))
    value.end_undo(document, 'Coordinates')
    layer.paths[0].nodes[1].fail = True
    with pytest.raises(RuntimeError, match='partial native setter'):
        manager.undo()
    assert not layer.temporarilyDisableRounding
    assert manager.enabled


def test_partial_coordinate_setter_restores_exact_values_before_yield():
    from test_simple_v2_bridge import BridgeCore, QueueScheduler, patch
    layer = native_layer()
    value, _ = adapter(layer)
    document = value.list_documents()[0]
    change = coordinate_change(layer)
    request = patch(1)
    request.update(documentId=document['id'], sourcePath=document['path'],
                   generation=document['generation'], changes=[change])
    layer.paths[0].nodes[1].fail = True
    queue = QueueScheduler()
    core = BridgeCore(value, queue)
    core.begin_apply(request)
    queue.run_one()
    assert coordinates.read(layer, change) == change['before']
    queue.drain()
    assert core.operation('job_1')['error']['details']['recovery']['complete']
    assert not layer.temporarilyDisableRounding


def test_translation_history_preserves_images_guides_and_component_linear_transform():
    layer = native_layer()
    class Component(RoundingNode):
        linear = (.75, .125, -.25, 1.5)
        @property
        def transform(self): return self.linear + tuple(self.position)
        @transform.setter
        def transform(self, matrix):
            self.linear = tuple(matrix[:4])
            self.position = matrix[4:]
    component = Component(layer, (50.125, 70.25))
    component.componentName = 'base'
    component.automaticAlignment = False
    component.transform = (.75, .125, -.25, 1.5, 50.125, 70.25)
    layer.components = [component]
    layer.backgroundImage = NS(position=(10.125, -20.25))
    layer.guides = [NS(position=(30.125, 40.25), angle=12.5)]
    def native_transform(matrix):
        # Whole-layer native transforms also move non-foreground decorations.
        for owner in [n for p in layer.paths for n in p.nodes] + list(layer.anchors) + layer.components:
            owner.position = (owner.position.x + matrix[4], owner.position.y + matrix[5])
        image = layer.backgroundImage
        image.position = (image.position[0] + matrix[4], image.position[1] + matrix[5])
        layer.guides[0].position = image.position
    layer.applyTransform = native_transform
    value, _ = adapter(layer)
    document = value.list_documents()[0]['id']
    manager = History()
    layer.undoManager = lambda: manager
    change = dict(kind='translate', glyph='A', layer='M1', dx=.375, dy=-.125)
    owners = [n for p in layer.paths for n in p.nodes] + list(layer.anchors) + layer.components
    before = [tuple(owner.position) for owner in owners]
    after = [(x + .375, y - .125) for x, y in before]
    value.begin_undo(document)
    value.apply_change(document, change)
    value.end_undo(document, 'Translate foreground')
    for expected in (after, before, after, before):
        assert [tuple(owner.position) for owner in owners] == expected
        assert layer.backgroundImage.position == (10.125, -20.25)
        assert layer.guides[0].position == (30.125, 40.25)
        assert component.transform[:4] == (.75, .125, -.25, 1.5)
        assert layer.width == 600.125 and not layer.temporarilyDisableRounding
        assert manager.enabled
        manager.undo()


@pytest.mark.parametrize('kind', ['translate', 'start_node'])
def test_partial_native_geometry_operation_restores_starting_target(kind):
    from test_simple_v2_bridge import BridgeCore, QueueScheduler, patch
    layer = native_layer()
    value, _ = adapter(layer)
    document = value.list_documents()[0]
    original = coordinate_change(layer)
    nodes = tuple(layer.paths[0].nodes)
    if kind == 'translate':
        layer.paths[0].nodes[1].fail = True
        change = dict(kind=kind, dx=.375, dy=.125)
    else:
        calls = []
        def reorder(node):
            path = layer.paths[0]
            index = path.nodes.index(node) + 1
            path.nodes = path.nodes[index:] + path.nodes[:index]
            calls.append(node)
            if len(calls) == 1:
                raise RuntimeError('partial reorder')
        layer.paths[0].makeNodeFirst_ = reorder
        change = dict(kind=kind, path=0, shift=2, nodeCount=4)
    change.update(glyph='A', layer='M1', beforeHash=value._outline_hash(layer), afterHash='sha256:' + 'a' * 64)
    request = patch(1)
    request.update(documentId=document['id'], sourcePath=document['path'], generation=document['generation'], changes=[change])
    queue = QueueScheduler()
    core = BridgeCore(value, queue)
    core.begin_apply(request)
    queue.run_one()
    assert tuple(layer.paths[0].nodes) == nodes
    assert coordinates.read(layer, original) == original['before']
    queue.drain()
    assert core.operation('job_1')['error']['details']['recovery']['complete']
    assert layer.width == 600.125 and not layer.temporarilyDisableRounding


def test_rounding_guard_failure_retains_original_flag_for_cleanup(monkeypatch):
    layer = native_layer()
    value, _ = adapter(layer)
    document = value.list_documents()[0]['id']
    value.begin_undo(document)
    def rejected(owner, flag):
        owner.temporarilyDisableRounding = flag
        return not flag  # The enable write happened but readback failed.
    monkeypatch.setattr(value, '_set_rounding', rejected)
    with pytest.raises(Exception, match='rounding suppression'):
        value.apply_change(document, coordinate_change(layer))
    value.end_undo(document, 'Failed start')
    assert not layer.temporarilyDisableRounding
    assert not value._operation_layers and not value._operation_fonts


def test_native_undo_begin_that_opens_then_raises_closes_only_its_group():
    from glyphs_mcp_bridge.native_undo import NativeUndoScope
    class PartialManager:
        level = 2
        def groupingLevel(self): return self.level
        def beginUndoGrouping(self):
            self.level += 1
            raise RuntimeError('partial begin')
        def endUndoGrouping(self): self.level -= 1
    manager = PartialManager()
    with pytest.raises(RuntimeError, match='partial begin'):
        NativeUndoScope(manager)
    assert manager.level == 2
