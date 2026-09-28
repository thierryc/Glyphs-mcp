"""M8 exact-entry integration in a disposable native process (not editor UI)."""
import json
from pathlib import Path
import sys
from native_script_harness import Harness, GSFontMaster
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_protocol import kerning_edits as contract

suffix, output = [a for a in sys.argv[1:] if a != '--']
h = Harness(count=3, suffix=suffix, single_master=True)


def exercise(h):
    def setup():
        font = h.doc.font
        h.doc.undoManager().beginUndoGrouping()
        other = GSFontMaster(); other.name = 'Control'; font.masters.append(other)
        for g in font.glyphs:
            g.beginUndo()
            for side in ('left', 'right', 'top', 'bottom'): setattr(g, side+'KerningGroup', side+'_'+g.name)
            g.endUndo()
        font.setKerningForPair(other.id, 'probe0', 'probe1', -31.125)
        h.doc.undoManager().endUndoGrouping()
        font.save(str(h.source), makeCopy=True)
        h.doc.setFont_(_load_font(h.source, preserve_grid=True)); h.clean()
        return str(other.id)
    other = h.main(setup)
    document = h.service.list_documents()[0]['id']
    h.service.worker.prepare = lambda *a, **k: (_ for _ in ()).throw(AssertionError('exact assignments must not launch the worker'))
    results = []
    for direction in contract.DIRECTIONS:
        for group_left, group_right in ((False, False), (True, False), (False, True), (True, True)):
            prefix_left, prefix_right = contract.SIDES[direction]
            left = prefix_left + contract.GROUPS[prefix_left]+'_probe0' if group_left else 'probe0'
            right = prefix_right + contract.GROUPS[prefix_right]+'_probe1' if group_right else 'probe1'
            target = dict(master=h.mid, direction=direction, left=left, right=right)
            def read():
                return contract.read_stored(h.doc.font, h.mid, left, right, direction)
            for desired in (-72.5, 0, None, 2000000.5):
                def baseline():
                    h.doc.undoManager().beginUndoGrouping()
                    font = h.doc.font
                    # Each case starts from the same known explicit entry.
                    font.setKerningForPair(h.mid, left, right, -10.125, direction=contract.DIRECTIONS[direction])
                    h.doc.undoManager().endUndoGrouping()
                    font.save(str(h.source), makeCopy=True); h.clean()
                h.main(baseline)
                row = dict(op='remove' if desired is None else 'set', master=h.mid, direction=direction,
                           left=dict(kind='group', key=left) if group_left else dict(kind='glyph', name=left),
                           right=dict(kind='group', key=right) if group_right else dict(kind='glyph', name=right),
                           **({} if desired is None else dict(value=desired)))
                key = f'{direction}-{group_left}-{group_right}-{desired}'
                value = h.service.edit_workflows.start(document, kind='kerning_edit', options=dict(edits=[row]),
                    mode='preview', auto_keep=False, idempotency_key=key)
                value = h.wait(value, 'ready')
                assert h.main(read) == -10.125
                job_id = value['jobId']
                assert h.service.jobs.get(job_id)['preparationRoute'] == 'native'
                assert not list(h.service.jobs.path(job_id).glob('source*'))
                value = h.wait(h.choose(value, 'apply'), 'applied')
                assert h.main(read) == desired
                def native_history():
                    font = h.doc.font
                    manager = h.doc.undoManager() if group_left else font.glyphs[left].undoManager()
                    assert manager.canUndo()
                    manager.undo(); assert read() == -10.125
                    manager.redo(); assert read() == desired
                    assert font.kerningForPair(other, 'probe0', 'probe1') == -31.125
                h.main(native_history)
                value = h.wait(h.choose(value, 'discard'), 'discarded')
                assert h.main(read) == -10.125
                assert h.main(lambda: h.doc.font.glyphs['probe2'].layers[h.mid].width) == 500
                h.main(lambda: (h.doc.font.save(str(h.source), makeCopy=True), h.clean()))
                results.append(dict(**target, desired=desired, nativeUndoRedo=True, selectiveRecovery=True, workerLaunches=0, sourceCopies=0))
    return dict(cases=results, longestMainThreadChunk=h.max_chunk)


result=h.run(exercise)
Path(output).write_text(json.dumps(result, indent=2))
print(json.dumps(result))
if not result.get('passed'): raise SystemExit(1)
