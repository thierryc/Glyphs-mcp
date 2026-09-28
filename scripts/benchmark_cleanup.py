"""Instrument existing native benchmarks without changing their timing boundaries."""
import json
from pathlib import Path
import runpy
import sys
import time

from native_script_harness import Harness, ROOT
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter

arguments = [v for v in sys.argv[1:] if v != '--']
index = arguments.index('--workload')
workload = arguments[index+1]; del arguments[index:index+2]
assert workload in ('width', 'script')
output = Path(arguments[arguments.index('--output')+1])
cleanup = dict(totalNativeSeconds=0, longestStepSeconds=0, steps=0,
               longestScheduledCleanupSeconds=0, scheduledCleanupChunks=0)


def measured(callback):
    started = time.perf_counter()
    try: return callback()
    finally:
        duration = time.perf_counter()-started
        cleanup['totalNativeSeconds'] += duration
        cleanup['longestStepSeconds'] = max(cleanup['longestStepSeconds'], duration)
        cleanup['steps'] += 1


steps = getattr(GlyphsAdapter, 'end_undo_steps', None)
if steps:
    def end_steps(self, document, name):
        iterator = steps(self, document, name)
        while True:
            try: measured(lambda: next(iterator))
            except StopIteration: return
            yield
    GlyphsAdapter.end_undo_steps = end_steps
else:
    finish = GlyphsAdapter.end_undo
    def end(self, document, name):
        return measured(lambda: finish(self, document, name))
    GlyphsAdapter.end_undo = end

schedule = Harness.schedule


def scheduled(self, callback):
    def run():
        before = cleanup['steps']; started = time.perf_counter()
        script_cleanup = any(o.get('scriptStage') == 'cleanup' for o in self.core._operations.values())
        try: callback()
        finally:
            if cleanup['steps'] != before or script_cleanup:
                duration = time.perf_counter()-started
                cleanup['scheduledCleanupChunks'] += 1
                cleanup['longestScheduledCleanupSeconds'] = max(cleanup['longestScheduledCleanupSeconds'], duration)
    schedule(self, run)


Harness.schedule = scheduled
script = ROOT/'scripts'/('benchmark_scoped_preparation.py' if workload == 'width' else 'benchmark_script_capacity.py')
sys.argv = [str(script), *arguments, *(['--kind', 'width'] if workload == 'width' else [])]
runpy.run_path(str(script), run_name='__main__')
result = json.loads(output.read_text()); result['cleanup'] = cleanup
result['cleanupMethodology'] = ('Native adapter cleanup, including application and selective recovery where present. '
    'Baseline step is synchronous cleanup; candidate step is one generator advance. '
    'Scheduled cleanup maxima include other work sharing that callback. Native calls remain indivisible.')
output.write_text(json.dumps(result, indent=2)+'\n')
