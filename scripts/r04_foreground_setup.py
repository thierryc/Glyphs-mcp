# MenuTitle: R04 Master Qualification
"""Temporary native setup/timing driver. Public MCP performs all measured reads.

Run via Glyphs' Script menu. Fixed workspace config, disposable-path guards,
bounded in-memory timing, explicit collection/removal; no watcher or live tool.
"""
import json
from pathlib import Path
import time
from datetime import datetime, timezone
from GlyphsApp import Glyphs, GSFont, GSFontMaster
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle

ROOT = Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2')
OUT = ROOT/'reports/v1-v2/04-master-identification/v2-improvements-20260910'
cfg = json.loads((OUT/'foreground-config.json').read_text())
folder = Path(cfg['copies'])
assert folder.is_relative_to('/private/tmp/r04-improvements-20260910')
action = cfg['action']


def allowed(font):
    return (font.filepath and Path(str(font.filepath)).parent == folder) or (
        not font.filepath and font.familyName == 'R04 Unsaved Qualification')


def attach():
    life = bridge_lifecycle
    assert life.ready and not hasattr(life, '_r04_qualification')
    main = life.server.main_thread
    original_call = main.call
    methods = {name: getattr(life.core, name) for name in ('status', 'read_entities', 'list_documents')}
    state = {'samples': [], 'tag': None, 'methodOriginals': methods, 'callOriginal': original_call}
    def method_wrapper(name, original):
        def measured(*args, **kwargs):
            state['tag'] = name
            return original(*args, **kwargs)
        return measured
    for name, original in methods.items():
        setattr(life.core, name, method_wrapper(name, original))
    def measured_call(callback):
        queued = time.perf_counter_ns()
        def measured():
            begin = time.perf_counter_ns(); state['tag'] = 'other'
            try:
                return callback()
            finally:
                end = time.perf_counter_ns()
                if len(state['samples']) < 1000:
                    state['samples'].append({'at': datetime.now(timezone.utc).isoformat(), 'method': state['tag'],
                        'dispatchWaitMs': (begin-queued)/1e6, 'callbackMs': (end-begin)/1e6})
        return original_call(measured)
    main.call = measured_call
    life._r04_qualification = state


if action == 'open':
    assert not list(Glyphs.fonts), 'Only start setup with empty native documents'
    files = sorted(folder.glob('*.glyphs'))
    assert len(files) == 15
    for path in files:
        Glyphs.open(str(path), showInterface=True)
elif action == 'attach':
    assert len(list(Glyphs.fonts)) == 15 and all(allowed(f) for f in Glyphs.fonts)
    attach()
elif action == 'collect':
    state = bridge_lifecycle._r04_qualification
    bridge_lifecycle.server.main_thread.call = state['callOriginal']
    for name, original in state['methodOriginals'].items():
        setattr(bridge_lifecycle.core, name, original)
    (OUT/cfg['timingFile']).write_text(json.dumps(state['samples'], indent=2)+'\n')
    del bridge_lifecycle._r04_qualification
elif action == 'rename':
    assert all(allowed(f) for f in Glyphs.fonts)
    dirty = next(f for f in Glyphs.fonts if f.filepath and Path(str(f.filepath)).name == 'core-07-dirty.glyphs')
    dirty.masters[0].name = 'Regular'
elif action == 'unsaved':
    assert all(allowed(f) for f in Glyphs.fonts)
    font = GSFont(); font.familyName = 'R04 Unsaved Qualification'; font.masters = []
    for index in range(3):
        master = GSFontMaster(); master.id = f'opaque-native-{index}'; master.name = 'Regular'
        font.masters.append(master)
    font.show()
elif action == 'close':
    assert not hasattr(bridge_lifecycle, '_r04_qualification'), 'Collect timing before cleanup'
    assert all(allowed(f) for f in Glyphs.fonts)
    for font in list(Glyphs.fonts):
        font.close(ignoreChanges=True)
else:
    raise ValueError('Unknown qualification action')
with (OUT/'native-setup.jsonl').open('a') as stream:
    stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'action': action,
        'copies': str(folder), 'documents': bridge_lifecycle.adapter.list_documents()})+'\n')
print('R04 qualification:', action, 'complete')
