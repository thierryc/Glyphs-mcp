"""Qualify Dimensions against Glyphs 4's real palette on disposable documents.

Run with glyphs run --app '/Applications/Glyphs 4.app' --plugins '' <script>.
No installed bridge, user's open documents or original font files are changed.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for part in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / part))
from AppKit import NSApplication
from Foundation import NSBundle, NSObject, NSURL
import objc
from GlyphsApp import GSFont, GSFontMaster, GSGlyph, GSLayer, Glyphs
from glyphs_mcp_protocol import dimensions as d
from glyphs_mcp_bridge import dimensions as native
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_sidecar.dimensions_job import prepare
from glyphs_mcp_sidecar.source import source_hash
from glyphs_mcp_sidecar.native_worker import _load_font, build_patch

OUT = ROOT / 'build/dimensions-beta6'
OUT.mkdir(parents=True, exist_ok=True)
checks = []
completed = False


def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    assert condition, name


NSApplication.sharedApplication()
bundle = NSBundle.bundleWithPath_(str(Path(Glyphs.appPath) / 'Contents/PlugIns/Dimensions.glyphsPalette')) if hasattr(Glyphs, 'appPath') else NSBundle.bundleWithPath_('/Applications/Glyphs 4.app/Contents/PlugIns/Dimensions.glyphsPalette')
check('native palette loads', bundle.load())
palette = objc.lookUpClass('GlyphsPaletteDimensions').alloc().init()
font = GSFont(); font.familyName = 'MCP Dimensions disposable qualification'
font.masters.append(GSFontMaster()); font.masters[0].name = 'Regular'
font.masters.append(GSFontMaster()); font.masters[1].name = 'Bold'
font.glyphs.append(GSGlyph('H'))
layer = GSLayer(); layer.layerId = font.masters[0].id; layer.associatedMasterId = layer.layerId
font.glyphs['H'].layers.append(layer)
document = objc.lookUpClass('GSDocument').alloc().init()
document.setFont_(font)


class DimensionsQualificationController(NSObject):
    def font(self): return font
    def document(self): return document
    @objc.typedSelector(b'q@:')
    def masterIndex(self): return 0
    def masterId(self): return font.masters[0].id
    def activeLayer(self): return layer


controller = DimensionsQualificationController.alloc().init()
palette.setWindowController_(controller)
fields = {}
for name in dir(palette):
    if name.endswith('TextField') and not name.startswith('_'):
        field = getattr(palette, name)()
        fields[str(field.identifier())] = field

try:
    check('catalog exactly matches all palette identifiers', set(fields) == set(d.CATALOG))
    check('qualified write capability', native.available())
    master = str(font.masters[0].id)
    other = str(font.masters[1].id)
    # Exercise the real palette setter, including its string storage and clearing.
    for index, (key, field) in enumerate(sorted(fields.items())):
        value = str(30.125 + index)
        field.setStringValue_(value); palette.setDimension_(field)
        check(key + ' palette setter stores exact text', d.read_state(native.root(font), master, key) == {'present': True, 'value': value})
        field.setStringValue_(''); palette.setDimension_(field)
        check(key + ' palette clear removes key', not d.read_state(native.root(font), master, key)['present'])
    del font.userData[d.STORAGE_KEY]
    font.userData['dimensionsQualificationUnrelated'] = {'keep': [1, 2]}
    # Actual source save/reopen for both formats; explicit disposable destinations.
    for suffix in ('.glyphs', '.glyphspackage'):
        path = OUT / ('fixture' + suffix)
        font.userData[d.STORAGE_KEY] = {master: {'HV': '46.25', 'VThin': 0}, other: {'kanada1': '55.5'}}
        font.save(str(path), makeCopy=True)
        reopened = _load_font(path)
        check(suffix + ' exact metadata survives reopening', str(reopened.userData[d.STORAGE_KEY]) == str(font.userData[d.STORAGE_KEY]))
        check(suffix + ' unrelated data persists', reopened.userData['dimensionsQualificationUnrelated'] == font.userData['dimensionsQualificationUnrelated'])
    # Make a saved baseline without the namespace and use the real native document.
    del font.userData[d.STORAGE_KEY]
    source = OUT / 'baseline.glyphs'; font.save(str(source), makeCopy=True)
    document.setFileURL_(NSURL.fileURLWithPath_(str(source)))
    # Finish only fixture-construction history in this isolated process.
    manager = document.undoManager()
    while manager.groupingLevel(): manager.endUndoGrouping()
    manager.removeAllActions()
    document.updateChangeCount_(2)
    baseline_hash = source_hash(source)
    adapter = GlyphsAdapter(Glyphs); adapter._fonts = lambda: [font]
    core = BridgeCore(adapter, lambda cb: cb())
    doc = core.list_documents()[0]
    check('native document clean before job', doc['dirty'] is False)
    rows = core.read_entities(doc['id'], [{'kind': 'master', 'id': master}], ['dimensions'])[0]['values']['dimensions']
    check('blank reads do not create metadata', native.root(font) is None and all(not r['present'] for r in rows['items']))
    requests = [{'master': master, 'key': key, 'value': 10.25 + i} for i, key in enumerate(sorted(fields))]
    requests.append({'master': other, 'key': 'HV', 'value': 0})
    changes, report = prepare(font, {'options': {'changes': requests}})
    patch = {'version': 1, 'jobId': 'native-dimensions', 'documentId': doc['id'], 'sourcePath': doc['path'],
             'sourceHash': baseline_hash, 'generation': doc['generation'], 'changes': changes, 'summary': 'Dimensions qualification'}
    external = build_patch({'request': {'kind': 'dimensions_edit', 'options': {'changes': requests}},
        'source': str(source), 'sourceHash': baseline_hash, 'document': doc,
        'jobId': patch['jobId'], 'output': str(OUT / 'worker-result.json')})
    check('saved-source worker agrees with live metadata', external['changes'] == changes)
    result = core.begin_apply(external)
    check('all fields applied through actual bridge core', result['status'] == 'applied')
    check('native document marked dirty', bool(document.isDocumentEdited()))
    after = json.dumps(dict(native.root(font)), default=dict, sort_keys=True)
    # No manual palette.update_: bridge notification must refresh the controls.
    for request in requests[:-1]:
        check(request['key'] + ' palette reads bridge value', float(fields[request['key']].stringValue()) == request['value'])
    manager = document.undoManager()
    manager.undo()
    check('native Undo restores absent namespace', native.root(font) is None)
    manager.redo()
    check('native Redo restores all values', json.dumps(dict(native.root(font)), default=dict, sort_keys=True) == after)
    result = core.discard('native-dimensions')
    check('discard restores exact absent namespace', result['status'] == 'discarded' and native.root(font) is None)
    check('application and discard never save', source_hash(source) == baseline_hash)
    check('unrelated metadata preserved', font.userData['dimensionsQualificationUnrelated'] == {'keep': [1, 2]})
    # Exercise existing string values, explicit approval, clearing and restoration.
    font.userData[d.STORAGE_KEY] = {master: {'HV': '0', 'HH': '46.25'}, other: {'future': 99}}
    font.save(str(source), makeCopy=True)
    while manager.groupingLevel(): manager.endUndoGrouping()
    manager.removeAllActions(); document.updateChangeCount_(2)
    doc = core.list_documents()[0]
    before = json.dumps(dict(native.root(font)), default=dict, sort_keys=True)
    changes, report = prepare(font, {'options': {'changes': [
        {'master': master, 'key': 'HV', 'value': 12.5},
        {'master': master, 'key': 'HH', 'value': None}]}})
    patch.update(jobId='native-overwrite', changes=changes, generation=doc['generation'], sourceHash=source_hash(source))
    try:
        core.begin_apply(patch)
    except BridgeError as exc:
        check('native boundary rejects unapproved overwrite', exc.code == 'overwrite_approval_required')
    else:
        check('native boundary must require overwrite approval', False)
    result = core.begin_apply(patch, approved_overwrites=report['requiredOverwrites'])
    check('approved overwrite and clear apply', result['status'] == 'applied')
    check('native palette refreshes overwrite and clear', fields['HV'].stringValue() == '12.5' and fields['HH'].stringValue() == '')
    manager.undo()
    check('native overwrite Undo restores exact strings', json.dumps(dict(native.root(font)), default=dict, sort_keys=True) == before)
    manager.redo()
    check('native overwrite Redo preserves clear', not d.read_state(native.root(font), master, 'HH')['present'])
    result = core.discard('native-overwrite')
    check('native overwrite discard preserves unknown other master', result['status'] == 'discarded' and json.dumps(dict(native.root(font)), default=dict, sort_keys=True) == before)
    check('overwrite and clear never save', source_hash(source) == patch['sourceHash'])
    completed = True

finally:
    (OUT / 'native.json').write_text(json.dumps({'host': {'version': str(Glyphs.versionString), 'build': str(Glyphs.buildNumber)},
        'scope': 'Actual native palette, document, metadata and Undo in isolated glyphs-cli process; installed MCP not changed',
        'fields': sorted(fields), 'checks': checks, 'passed': completed and bool(checks) and all(row['passed'] for row in checks)}, indent=2) + '\n')
print(json.dumps({'passed': True, 'checks': len(checks), 'fields': len(fields)}))
