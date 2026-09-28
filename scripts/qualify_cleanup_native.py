"""Disposable native cleanup, cancellation and rollback; no running editor access."""
import argparse
import json
from pathlib import Path
import sys
import time

from native_script_harness import Harness
from glyphs_mcp_protocol.source_identity import source_hash

parser = argparse.ArgumentParser()
parser.add_argument('--format', choices=['glyphs','glyphspackage'], required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args([v for v in sys.argv[1:] if v != '--'])
assert not args.output.exists(), 'preserve native evidence'
h = Harness(count=127, suffix=args.format, single_master=True, batch_fixture=True)


def exercise(h):
    def state():
        result = {}
        for glyph in h.doc.font.glyphs:
            layer = glyph.layers[h.mid]; manager = glyph.undoManager()
            result[str(glyph.name)] = (float(layer.width), bool(h.adapter._rounding_value(layer)),
                bool(h.adapter._rounding_value(layer.background)), int(manager.groupingLevel()),
                bool(manager.groupsByEvent()), float(layer.background.paths[0].nodes[0].position.x))
        return result
    before = h.main(state)
    result = []
    for outcome in ('success','cancel','conflict'):
        h.main(h.clean)
        document = h.main(h.core.list_documents)[0]
        job = 'cleanup-'+outcome
        patch = dict(version=1, jobId=job, documentId=document['id'], sourcePath=document['path'],
            sourceHash=source_hash(h.source), generation=document['generation'], summary='Fractional widths',
            changes=[dict(kind='set',glyph='probe'+str(i),layer=h.mid,field='width',before=500,after=500.375) for i in range(126)])
        if outcome == 'conflict': patch['changes'][93]['before'] = 499
        apply = h.core._apply_one; callbacks = [0]
        def count(operation, change, *, reverse):
            value = apply(operation, change, reverse=reverse)
            if not reverse:
                callbacks[0] += 1
                if outcome == 'cancel' and callbacks[0] == 31: h.core.discard(job)
            return value
        h.core._apply_one = count
        try:
            h.main(lambda: h.core.begin_apply(patch))
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                operation = h.main(lambda: h.core.operation(job))
                if operation['status'] in ('applied','failed','cancelled'): break
                time.sleep(.005)
            assert operation['status'] == dict(success='applied',cancel='cancelled',conflict='failed')[outcome], operation
            observed = h.main(state)
            assert observed.keys() == before.keys()
            assert all(row[1:] == before[name][1:] for name,row in observed.items())
            expected = {name:500.375 if outcome=='success' and name!='probe126' else 500 for name in before}
            assert {name:row[0] for name,row in observed.items()} == expected
            assert not h.adapter._rounding_states and not h.adapter._undo_managers and not h.adapter._operation_fonts
            if outcome == 'success':
                def undo_redo():
                    managers = [h.doc.font.glyphs['probe'+str(i)].undoManager() for i in range(126)]
                    for m in managers: assert m.canUndo(); m.undo()
                    assert state() == before
                    for m in managers: assert m.canRedo(); m.redo()
                    assert state() == observed
                h.main(undo_redo)
                h.main(lambda: h.core.discard(job))
                while h.main(lambda: h.core.operation(job))['status'] == 'discarding': time.sleep(.005)
                assert h.main(lambda: h.core.operation(job))['status'] == 'discarded'
                assert h.main(state) == before
            else:
                assert operation['error']['details']['recovery']['complete']
            result.append(dict(outcome=outcome,passed=True,forwardWrites=callbacks[0],settingsRestored=True,
                untouchedControl=True,nativeUndoRedo=outcome=='success',selectiveRecovery=outcome=='success'))
        finally: h.core._apply_one = apply
    return dict(format=args.format,cases=result,longestScheduledChunkSeconds=h.max_chunk)


result = h.run(exercise)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
if not result.get('passed'): raise RuntimeError(result.get('error'))
