"""One disposable native capacity case in a fresh glyphs-cli process."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import time

from native_script_harness import Harness, ROOT
from glyphs_mcp_protocol import scripts, script_targets
from glyphs_mcp_protocol.script_runtime import ScriptRuntime
from glyphs_mcp_bridge import script_execution

parser = argparse.ArgumentParser()
parser.add_argument('--count', type=int, required=True)
parser.add_argument('--contours', type=int, default=1)
parser.add_argument('--format', choices=['glyphs', 'glyphspackage'], required=True)
parser.add_argument('--mode', choices=['native', 'direct'], default='native')
parser.add_argument('--dirty', action='store_true')
parser.add_argument('--fixtures', type=Path)
parser.add_argument('--prepare-fixture', action='store_true')
parser.add_argument('--output', type=Path, required=True)
import sys
args = parser.parse_args([a for a in sys.argv[1:] if a != '--'])
assert not args.output.exists(), 'never overwrite benchmark evidence'
source = (ROOT/'skills/glyphs-mcp-scripting/examples/vertical_flip.py').read_text()


def exercise(h):
    # The simulated Save must not change the document URL through a /var alias.
    assert h.source == h.source.resolve(), 'benchmark baseline path must be canonical before review'
    main_calls = []
    original_main = h.main
    def main(callback):
        def measured_call():
            started = time.perf_counter()
            try: return callback()
            finally: main_calls.append(time.perf_counter()-started)
        return original_main(measured_call)
    h.main = main
    options = scripts.validate_options(dict(source=source,
        targets=dict(master=h.mid, glyphs='all', surface='background')))
    stage_seconds = {}
    original = script_execution.advance
    def measured(core, op):
        stage = op['scriptStage']; started = time.perf_counter()
        try: return original(core, op)
        finally: stage_seconds[stage] = stage_seconds.get(stage, 0) + time.perf_counter()-started
    script_execution.advance = measured
    save_seconds = []
    original_save = h.service.save_document
    def save(*a, **kw):
        started = time.perf_counter()
        try: return original_save(*a, **kw)
        finally: save_seconds.append(time.perf_counter()-started)
    h.service.save_document = save
    if args.dirty: h.main(lambda: h.doc.updateChangeCount_(0))
    if args.mode == 'native':
        started = time.perf_counter()
        value = h.wait(h.start(options, 'capacity-benchmark'), 'waiting_run')
        preparation = time.perf_counter()-started
        review = h.service.jobs.read_json(value['jobId'], 'report.json')
        assert review['targetCount'] == args.count and not review['skippedCount']
        started = time.perf_counter()
        value = h.wait(h.choose(value, 'save_run_script' if args.dirty else 'run_script'), 'applied')
        dispatch = time.perf_counter()-started
        operation = h.core._operations[value['jobId']]
        request_bytes = len(json.dumps({'script': operation['scriptRequest']}, ensure_ascii=False,
                                      separators=(',', ':')).encode('utf-8'))
        assert operation['scriptResult']['executedTargets'] == args.count
        row = dict(preparationSeconds=preparation, dispatchToResultSeconds=dispatch,
            saveSeconds=sum(save_seconds), saveCalls=len(save_seconds),
            totalSeconds=preparation+dispatch, requestBytes=request_bytes,
            longestPreparationChunkSeconds=operation.get('longestPreparationChunk'),
            longestMainThreadCallSeconds=max(main_calls, default=0),
            stagesSeconds=stage_seconds, longestScheduledChunkSeconds=h.max_chunk,
            scheduledNativeSeconds=h.native_seconds, scheduledChunks=h.chunks)
        assert len(save_seconds) == int(args.dirty)
    else:
        def direct():
            selected, _ = script_targets.resolve(h.doc.font, options['targets'])
            runtime = ScriptRuntime(options, font=h.doc.font, targets=[l for _, l in selected])
            runtime.initialize()
            managers = [g.undoManager() for g in h.doc.font.glyphs]
            previous = [h.adapter._rounding_value(l) for _, l in selected]
            for manager in managers: manager.disableUndoRegistration()
            for _, layer in selected: layer.setTemporarilyDisableRounding_(True)
            try:
                started = time.perf_counter()
                for i, (target, layer) in enumerate(selected): runtime.run_target(layer, target, i, len(selected))
                return time.perf_counter()-started
            finally:
                for (_, layer), before in zip(selected, previous): layer.setTemporarilyDisableRounding_(before)
                for manager in managers: manager.enableUndoRegistration()
        row = dict(callbackSeconds=h.main(direct))
    def verify(restored=False):
        for glyph in h.doc.font.glyphs:
            layer = glyph.layers[h.mid]
            assert not len(layer.shapes) and layer.width == 500
            assert len(layer.background.paths) == args.contours
            for path in layer.background.paths:
                assert path.nodes[0].position.y == (0 if restored else 700.25)
                assert path.nodes[1].position.y == (700.25 if restored else 0)
                assert path.nodes[2].position.y == (100.5 if restored else 599.75)
    started = time.perf_counter(); h.main(verify)
    row['verificationSeconds'] = time.perf_counter()-started
    row['peakRSSBeforeRestoreBytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if args.mode == 'native':
        main_calls.clear()
        started = time.perf_counter(); value = h.choose(value, 'restore_saved_script')
        row['restoreSeconds'] = time.perf_counter()-started
        row['longestRestoreCallSeconds'] = max(main_calls, default=0)
        assert value['state'] == 'discarded'
        h.main(lambda: verify(restored=True))
    row['peakRSSBytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(targets=args.count, contours=args.contours, format=args.format,
                mode=args.mode, dirty=args.dirty, **row)


fixture = args.fixtures/f'{args.count}-{args.contours}.{args.format}' if args.fixtures else None
if args.prepare_fixture:
    assert fixture is not None and not fixture.exists(), 'fixture must be a new path'
    # Build once, then load the identical serialized fixture in EVERY measured process.
    creator = Harness(count=args.count, contours=args.contours, suffix=args.format, batch_fixture=True)
    fixture.parent.mkdir(parents=True, exist_ok=True)
    if creator.source.is_dir(): shutil.copytree(creator.source, fixture)
    else: shutil.copy2(creator.source, fixture)
    creator.service.close(); creator.temp.cleanup(); del creator
    args.output.write_text(json.dumps(dict(passed=True,fixture=str(fixture)))+'\n')
    sys.exit(0)
if fixture is not None: assert fixture.exists(), 'generate fixtures in a separate unmeasured process first'
out = Harness(count=args.count, contours=args.contours, suffix=args.format, batch_fixture=True,fixture=fixture).run(exercise)
out['sourceHashes'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for part in ('protocol', 'bridge', 'sidecar') for p in sorted((ROOT/'src'/part/('glyphs_mcp_'+part)).rglob('*.py'))}
out['methodology'] = ('One fresh native process per case. Native includes workflow preparation, callbacks, '
    'cleanup and polling. Direct is callback-only after setup. RSS is process high-water including fixture '
    'and runtime. Saving uses the standalone fixture GSFont writer, not editor NSDocument Save. '
    'CLI startup, fixture setup and installed-client latency excluded. Cached fixtures are generated once '
    'outside the timed workflow and loaded fresh in each process, identically for baseline and candidate. '
    'Every path is verified before and '
    'after restoration; scheduling durations do not promise preemption of a Python callback.')
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k != 'sourceHashes'}), flush=True)
if not out.get('passed'): raise RuntimeError(out.get('error'))
