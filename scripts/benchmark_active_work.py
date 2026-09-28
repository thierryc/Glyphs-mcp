"""Fresh-process registry benchmark; synthetic histories, no Glyphs or network."""
import argparse
import copy
import json
from pathlib import Path
import resource
import statistics
import sys
import tempfile
import time
from types import SimpleNamespace

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--history', type=int, required=True)
parser.add_argument('--active', action='store_true')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
for component in ('sidecar', 'protocol'):
    sys.path.insert(0, str(args.root.resolve()/'src'/component))
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.edit_workflow import EditWorkflows
from glyphs_mcp_sidecar.lifecycle import ServiceLifecycle

assert not args.output.exists(), 'Do not replace recorded evidence'
with tempfile.TemporaryDirectory(prefix='glyphs-active-bench-') as directory:
    root = Path(directory)
    store = JobStore(root)
    owner = SimpleNamespace(jobs=store)
    flows = EditWorkflows(owner, RuntimeError)
    for index in range(args.history):
        job = store.create(dict(id='old-doc'), dict(kind='width_delta', glyphs=['A']))
        store.update(job['id'], status='completed', summary='Kept without saving',
                     sample=[dict(glyph='A', before=500, after=501)]*10)
        value = flows.store.create(dict(id='old-doc'), {}, dict(kind='width_delta'), 'apply', str(index))
        flows.store.update(value, state='executed', jobId=job['id'])
    # Reconstruct rather than inheriting creation-time indexes.
    store = owner.jobs = JobStore(root)
    flows = EditWorkflows(owner, RuntimeError)
    current = None
    if args.active:
        current = store.create(dict(id='live-doc'), dict(kind='width_delta'))
        store.update(current['id'], status='applying', bridgeOperation=dict(status='applying', completedChanges=1))
        value = flows.store.create(dict(id='live-doc'), {}, dict(kind='width_delta'), 'apply', 'active')
        flows.store.update(value, state='applying', jobId=current['id'])
    counts = dict(reads=0, writes=0, copiedRecords=0, supervised=0)
    get, write, deep = store.get, store.write_json, copy.deepcopy
    def measured_get(*a, **kw):
        counts['reads'] += 1
        return get(*a, **kw)
    def measured_write(*a, **kw):
        counts['writes'] += 1
        return write(*a, **kw)
    def measured_copy(value, *a, **kw):
        if isinstance(value, list): counts['copiedRecords'] += sum(isinstance(v, dict) and 'id' in v for v in value)
        elif isinstance(value, dict) and 'id' in value: counts['copiedRecords'] += 1
        return deep(value, *a, **kw)
    store.get, store.write_json, copy.deepcopy = measured_get, measured_write, measured_copy
    def reconcile(identity):
        job = store.get(identity)
        return store.update(identity, status=job['status'], bridgeOperation=job['bridgeOperation'])
    owner.get_job = reconcile
    def advance(value):
        counts['supervised'] += 1
    flows._advance = advance
    class Ticks:
        def __init__(self): self.count = 0
        def wait(self, _): self.count += 1; return self.count > 100
        def is_set(self): return False
    flows.stopped = Ticks()
    lifecycle = ServiceLifecycle(owner, RuntimeError)
    latencies = []
    cpu = time.process_time()
    for _ in range(20):
        start = time.perf_counter()
        result = lifecycle.snapshot()
        latencies.append(time.perf_counter()-start)
        assert result['activeCount'] == int(args.active)
    activity_cpu = time.process_time()-cpu
    activity_counts = dict(counts)
    cpu, start = time.process_time(), time.perf_counter()
    flows._run()
    supervisor_cpu, supervisor_wall = time.process_time()-cpu, time.perf_counter()-start
    report = dict(history=args.history, active=args.active, root=str(args.root.resolve()),
        activityPolls=20, activityMedianSeconds=statistics.median(latencies),
        activityRangeSeconds=[min(latencies), max(latencies)], activityCpuSeconds=activity_cpu,
        activityCounts=activity_counts, supervisorTicks=100, supervisorCpuSeconds=supervisor_cpu,
        supervisorWallSeconds=supervisor_wall, supervisorAdvances=counts['supervised'],
        peakMemoryBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        methodology='Synthetic persisted jobs/workflows, fresh process, hot polls; CPU work excludes timer sleeping. macOS ru_maxrss includes history seeding/startup.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
