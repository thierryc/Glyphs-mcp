"""Summarize only the final, passing five-run M2 comparison matrix."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
report=ROOT/'reports/beta8-milestone2/matrix'
metrics=['preparationSeconds','applicationPollingSeconds','totalSeconds','verificationSeconds',
    'selectiveRecoverySeconds','saveSeconds','peakRSSBytes','longestPreparationCallSeconds',
    'longestApplicationCallSeconds','longestRecoveryCallSeconds','longestScheduledChunkSeconds']
rows=[]
for kind,counts in [('color',[1,10,100]),('width',[1,100,1000,4096])]:
    for suffix in ['glyphs','glyphspackage']:
        for count in counts:
            groups={}
            for route in ['baseline','candidate']:
                files=[report/f'{route}-{kind}-{count}-{suffix}-{i}.json' for i in range(1,6)]
                runs=[json.loads(p.read_text()) for p in files]
                assert all(r.get('passed') and r['methodologyVersion']==3 for r in runs)
                data=[r['data'] for r in runs]
                assert all(d['targets']==count and d['kind']==kind and d['format']==suffix and
                    d['workerLaunches']==0 and d['sourceCopyCount']==0 and d['nativeUndoRedo'] and d['selectiveRecovery'] for d in data)
                def stats(values):return dict(median=statistics.median(values),minimum=min(values),maximum=max(values))
                groups[route]={key:stats([d[key] for d in data]) for key in metrics}
                groups[route]['longestScheduledPreparationChunkSeconds']=stats([d['preparationMetrics']['longestChunkSeconds'] for d in data])
            rows.append(dict(kind=kind,format=suffix,targets=count,**groups,
                preparationSpeedRatio=groups['baseline']['preparationSeconds']['median']/groups['candidate']['preparationSeconds']['median'],
                totalSpeedRatio=groups['baseline']['totalSeconds']['median']/groups['candidate']['totalSeconds']['median']))
(report/'summary.json').write_text(json.dumps(dict(runs=140,repetitions=5,cases=rows),indent=2)+'\n')
lines=['# Milestone 2 native-route benchmark','',
    'Five fresh processes per route, case and format. Times below are median [minimum–maximum] seconds. Both routes use identical prebuilt fixtures. Baseline is the frozen milestone 1 runtime; this is not a v1 or external-worker comparison.','',
    'Colors select 1/10/100 glyphs from 501, with two masters and four triangular contours on each foreground plus a four-contour Regular background. Widths select 1/100/1,000/4,096 named glyphs from 5,000, each with one master and four contours in foreground and background. Requests name dispersed glyphs in reverse order. All unselected persisted contents, backgrounds, native Undo/Redo and selective recovery are checked.','',
    '| Task | Format | Targets | Before prep | After prep | Before prepare + apply | After prepare + apply |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
def fmt(d,key):
    v=d[key];return f"{v['median']:.3f} [{v['minimum']:.3f}–{v['maximum']:.3f}]"
for r in rows:lines.append(f"| {r['kind']} | {r['format']} | {r['targets']:,} | {fmt(r['baseline'],'preparationSeconds')} | {fmt(r['candidate'],'preparationSeconds')} | {fmt(r['baseline'],'totalSeconds')} | {fmt(r['candidate'],'totalSeconds')} |")
lines+=['','All stage timings, longest measured calls/chunks and per-process peak RSS are in [summary.json](summary.json). Peak RSS includes native runtime, fixture loading and verification. It is not an incremental allocation measurement. These are local workflow timings, excluding process startup and fixture generation, with polling included in application. Clean baselines need no Save; Save time is zero. Actual editor saving and installed-client latency are separate checks.','',
    'Main-thread measurements cover instrumented bridge calls and scheduled callbacks; they do not cover all native event-loop work and are not a UI-stall guarantee. Verification uses persisted native property lists as well as scalar widths/colors and runs outside edit timings. Recovery timing includes guarded selective restoration; Undo/Redo verification is separate. The benchmark remains a small synthetic contour workload, not a capacity promise for arbitrary complex fonts.']
(report/'README.md').write_text('\n'.join(lines)+'\n')
