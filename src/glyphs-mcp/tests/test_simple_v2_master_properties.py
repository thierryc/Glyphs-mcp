"""M7 requested native master properties; doubles do not establish host support."""
import math
from types import SimpleNamespace as NS
import pytest
from test_simple_v2_master_reads import setup
from glyphs_mcp_bridge import master_properties as props
from glyphs_mcp_bridge.core import BridgeError
from glyphs_mcp_protocol.reads import READ_CAPABILITIES


def fixture(masters=3, axes=2):
    core, doc, collection = setup(masters)
    font = core.adapter.glyphs.fonts[0]
    rows = [NS(axisId=f'axis-{i}', axisTag=('CSTM' if i == 0 else 'wght'),
               name='Custom' if i == 0 else 'Weight') for i in range(axes)]
    visits = []
    def indexed(i):
        visits.append(('axis', i)); return rows[i]
    font.countOfAxes = lambda: len(rows)
    font.objectInAxesAtIndex_ = indexed
    for mi, m in enumerate(collection.rows):
        m.font = font
        for i, (key, method) in enumerate(props.METRICS.items()):
            setattr(m, key, 999)  # Deliberately wrong/truncating wrapper alias.
            setattr(m, method, lambda mi=mi, i=i: (-1 if i in (3, 4) else 1) * (700 + mi + i + .375))
        def position(key, mi=mi, external=False):
            visits.append(('value', mi, key, external))
            return mi * 100 + int(key.split('-')[-1]) + (.625 if external else .125)
        m.axisInternalValueValueForId_ = position
        m.axisExternalValueValueForId_ = lambda key, fn=position: fn(key, external=True)
    return core, doc, collection, rows, visits


def read(core, doc, fields, *ids):
    return core.read_entities(doc, [{'kind': 'master', 'id': i} for i in ids or ('opaque-0',)], fields)


def test_exact_fractional_native_defaults_and_requested_fields():
    c, d, ms, _, visits = fixture()
    got = read(c, d, ['id', *props.METRICS], 'opaque-2', 'opaque-0')
    for row, mi in zip(got, (2, 0)):
        assert row['values'] == {'id': f'opaque-{mi}', **{key: getattr(ms.rows[mi], method)() for key, method in props.METRICS.items()}}
    assert not visits


def test_compact_fields_never_touch_axis_collection_or_default_getters():
    c, d, ms, _, visits = fixture()
    def fail(): raise AssertionError('unsolicited native read')
    c.adapter.glyphs.fonts[0].countOfAxes = fail
    for m in ms.rows:
        for method in props.METRICS.values(): setattr(m, method, fail)
    assert read(c, d, ['id'])[0]['values'] == {'id': 'opaque-0'}
    page = c.read_entities(d, [{'kind': 'masters'}], ['id', 'name'])[0]['values']
    assert page['total'] == 3 and page['complete'] and not visits


def test_axis_order_identity_and_two_native_coordinate_representations():
    c, d, _, rows, visits = fixture()
    rows.reverse()
    got = read(c, d, ['axes', 'axes'])[0]['values']['axes']
    assert got == dict(items=[dict(axisId='axis-1', tag='wght', name='Weight', index=0, internalValue=1.125, externalValue=1.625),
                             dict(axisId='axis-0', tag='CSTM', name='Custom', index=1, internalValue=.125, externalValue=.625)],
                       total=2, returned=2, complete=True)
    assert len([r for r in visits if r[0] == 'value']) == 4


def test_fresh_values_and_foreground_do_not_change_the_target():
    c, d, ms, _, _ = fixture()
    f = c.adapter.glyphs.fonts[0]
    f.filepath = None; f.parent.hasUnautosavedChanges = lambda: True
    c.adapter.glyphs.font = NS(masters=[])
    before = read(c, d, ['ascender'])
    ms.rows[0].defaultAscender = lambda: 0.0
    assert read(c, d, ['ascender'])[0]['values'] == {'ascender': 0.0}
    assert before[0]['values']['ascender'] == 700.375
    c.adapter.glyphs.fonts.clear()
    with pytest.raises(BridgeError, match='no longer open') as error: read(c, d, ['ascender'])
    assert error.value.code == 'document_not_found'


@pytest.mark.parametrize('masters,axes', [(8,32), (100,0), (4,32), (1,32)])
def test_budget_boundaries_and_native_indexed_only_access(masters, axes):
    c, d, ms, _, visits = fixture(masters, axes)
    result = c.read_entities(d, [{'kind': 'masters', 'limit': masters}], ['id', 'axes'])[0]['values']
    assert result['total'] == masters and result['complete']
    assert all(r['axes']['complete'] and r['axes']['returned'] == axes for r in result['items'])
    assert len([v for v in visits if v[0] == 'axis']) == masters * axes
    assert set(ms.visited) == set(range(masters))


@pytest.mark.parametrize('masters,axes', [(9,32), (1,33), (86,3)])
@pytest.mark.parametrize('paged', [False, True])
def test_over_budget_rejects_before_projection(masters, axes, paged):
    c, d, ms, _, visits = fixture(masters, axes)
    selectors = ([{'kind': 'masters'}] if paged else [{'kind':'master','id': m.id} for m in ms.rows])
    with pytest.raises(BridgeError) as e: c.read_entities(d, selectors, ['axes'])
    assert e.value.code == 'invalid_request' and '256' in str(e.value)
    assert not visits and not ms.visited


def test_small_page_axis_budget_and_cursor_remain_live():
    c, d, ms, _, _ = fixture(9,32)
    p = c.read_entities(d, [{'kind':'masters','limit':8}], ['id','axes'])[0]['values']
    assert not p['complete'] and len(p['items']) == 8
    ms.visited.clear()
    last = c.read_entities(d, [{'kind':'masters','cursor':p['nextCursor']}], ['id','axes'])[0]['values']
    assert last['complete'] and last['items'][0]['id'] == 'opaque-8' and ms.visited == [7,8]
    ms.rows[7].id = 'changed'
    with pytest.raises(BridgeError) as e:
        c.read_entities(d, [{'kind':'masters','cursor':p['nextCursor']}], ['axes'])
    assert e.value.code == 'stale_master_cursor'


def test_mixed_invalid_selector_cannot_bypass_axis_work_budget():
    c,d,ms,_,visits = fixture(9,32)
    selectors = [{'kind':'master','id':m.id} for m in ms.rows] + [{'kind':'glyph','id':'A'}]
    with pytest.raises(BridgeError) as e: c.read_entities(d,selectors,['axes'])
    assert e.value.code == 'invalid_request' and not visits and not ms.visited


def test_empty_page_needs_no_axis_getter():
    c,d,_ = setup(0)
    assert c.read_entities(d,[{'kind':'masters'}],['axes'])[0]['values'] == dict(items=[],total=0,complete=True,nextCursor=None)


@pytest.mark.parametrize('field', list(props.METRICS))
@pytest.mark.parametrize('invalid', [None, True, '700', math.nan, math.inf, -math.inf])
def test_invalid_metric_never_fabricates_value(field, invalid):
    c,d,ms,_,_ = fixture()
    setattr(ms.rows[0],props.METRICS[field],lambda:invalid)
    with pytest.raises(BridgeError) as e: read(c,d,[field])
    assert e.value.code == 'unsupported_read' and field in str(e.value)


@pytest.mark.parametrize('count', [None, True, '2', 1.5, -1])
def test_invalid_native_count_is_not_a_zero_axis_result(count):
    c,d,_,_,_ = fixture();c.adapter.glyphs.fonts[0].countOfAxes=lambda:count
    with pytest.raises(BridgeError) as e: read(c,d,['axes'])
    assert e.value.code == 'unsupported_read'


@pytest.mark.parametrize('value', [True, '1', math.nan, math.inf])
def test_invalid_axis_number_rejected(value):
    c,d,ms,_,_ = fixture();ms.rows[0].axisInternalValueValueForId_=lambda key:value
    with pytest.raises(BridgeError) as e: read(c,d,['axes'])
    assert e.value.code == 'unsupported_read'


def test_native_null_position_is_explicit_incomplete_evidence():
    c,d,ms,_,_ = fixture(1,1);ms.rows[0].axisExternalValueValueForId_=lambda key:None
    got=read(c,d,['axes'])[0]['values']['axes']
    assert got['items'][0]['externalValue'] is None and not got['complete']
    assert got['total'] == got['returned'] == 1
    assert got['unavailable'] == [{'axisId':'axis-0','field':'externalValue'}]


@pytest.mark.parametrize('field', ['axisId','axisTag','name'])
def test_missing_axis_metadata_rejected(field):
    c,d,_,rows,_ = fixture();delattr(rows[0],field)
    with pytest.raises(BridgeError) as e: read(c,d,['axes'])
    assert e.value.code == 'unsupported_read'


@pytest.mark.parametrize('mode', ['missing','raises','noncallable'])
def test_unreadable_native_access_has_no_wrapper_fallback(mode):
    c,d,ms,_,_ = fixture()
    if mode == 'missing': del ms.rows[0].axisInternalValueValueForId_
    elif mode == 'noncallable': ms.rows[0].axisInternalValueValueForId_ = 700
    else:
        def fail(key): raise RuntimeError('unavailable')
        ms.rows[0].axisInternalValueValueForId_ = fail
    with pytest.raises(BridgeError) as e: read(c,d,['axes'])
    assert e.value.code == 'unsupported_read'


def test_pyobjc_numeric_subclass_is_not_rejected():
    class NativeFloat(float): pass
    c,d,ms,_,_ = fixture(1,1)
    ms.rows[0].defaultAscender = lambda:NativeFloat(0)
    ms.rows[0].axisInternalValueValueForId_ = lambda key:NativeFloat(-.375)
    got=read(c,d,['ascender','axes'])[0]['values']
    assert got['ascender']==0 and got['axes']['items'][0]['internalValue']==-.375


def test_new_fields_reject_missing_id_and_unknown_field_without_retargeting():
    c,d,_,_,_ = fixture()
    for fields,ids,code in [(['ascender'],('Regular',),'target_not_found'),
                            (['ascender'],('opaque-0','missing'),'target_not_found'),
                            (['axisMappings'],('opaque-0',),'unsupported_read')]:
        with pytest.raises(BridgeError) as e: read(c,d,fields,*ids)
        assert e.value.code == code


def test_capability_is_advertised_by_existing_protocol_only():
    assert 'master.properties.v1' in READ_CAPABILITIES
