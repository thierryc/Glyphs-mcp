"""Offline validation only; no servers, installation, or baseline rewrites."""
from pathlib import Path
import hashlib
import json
import math
import re
import statistics
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]

def read(name): return json.loads((ROOT/name).read_text())
def stats(values):
    values=sorted(values)
    return {'n':len(values),'medianMs':statistics.median(values),'minMs':min(values),
            'maxMs':max(values),'p95Ms':values[math.ceil(.95*len(values))-1]}
def check_stats(expected, values):
    actual=stats(values)
    assert all(abs(actual[key]-value)<1e-8 for key,value in expected.items()), (expected,actual)

def validate():
    results={}
    baseline=read('native-baseline-verified/facts.json');candidate=read('native-candidate-verified/facts.json')
    manifest=read('candidate-manifest.json')
    assert baseline['startedAt']<candidate['startedAt']
    for name,facts in [('baseline',baseline),('candidate',candidate)]:
        assert not facts['errors'] and facts['documentsBefore']==facts['documentsAfter']==[]
        assert len(facts['calls'])==46
        assert all(c['ok'] and c['at'] and c['latencyMs']>=0 for c in facts['calls'])
        counts={method:sum(c['method']==method for c in facts['calls']) for method in
                ('initialize','tools/list','get_status','list_documents')}
        assert counts=={'initialize':8,'tools/list':8,'get_status':28,'list_documents':2}
        assert set(c['method'] for c in facts['calls'])==set(counts)
        assert len(facts['catalog'])==7
        assert facts['status']['protocol']==facts['status']['bridge']['protocol']==1
        assert facts['initialize']['protocolVersion']=='2025-11-25'
        check_stats(facts['connection'],[t['connectionMs'] for t in facts['trials'] if t['phase'].startswith('trial-')])
        check_stats(facts['statusHttpRoundTrip'],[c['latencyMs'] for c in facts['calls'] if c['phase']=='idle-probe' and c['method']=='get_status'])
        bridge=read('native-'+name+'-verified/bridge-timings.json')
        assert bridge['documentsBefore']==bridge['documentsAfter']==[]
        sidecar=read('native-'+name+'-verified/sidecar-timings.json')
        assert len(bridge['samples'])==30 and len(sidecar)==28
        for field,s in facts['bridgeTiming'].items(): check_stats(s,[r[field] for r in bridge['samples']])
        for field,s in facts['sidecarTiming'].items(): check_stats(s,[r[field] for r in sidecar])
        responsiveness=stats([r['dispatchWaitMs']+r['callbackMs'] for r in bridge['samples']])
        assert responsiveness['p95Ms']<50 and responsiveness['maxMs']<200
        results[name]={'calls':counts,'isolatedCallbackResponsiveness':responsiveness}
    info=candidate['status']
    assert info['release']==manifest['release'] and info['sidecarVersion']==manifest['projectVersion']
    assert candidate['initialize']['serverInfo']['version']==manifest['releaseVersion']
    assert info['interface']=='glyphs-mcp-sidecar' and info['interfaceVersion']==1
    assert info['jobKinds']==['width_delta','spacing','kerning_collision','start_nodes','slant']
    assert info['bridge']['host']=={'identifier':'com.GeorgSeifert.Glyphs4','version':'4.1','build':'4107'}
    for component in ('sidecar','bridge'):
        data=info if component=='sidecar' else info['bridge']
        assert data['release']==manifest['release']
        assert data['codeHash']==manifest[component]['codeHash']
        assert data['runtimeId']==manifest['releaseVersion']+'+'+data['codeHash'][7:19]
    assert all(read('preservation/preservation.json').values())
    old=REPO.parents[2]/'reports/v1-v2/01-connection-routing'
    for path,digest in read('baseline-report-checksums.json').items():
        assert hashlib.sha256((old/path).read_bytes()).hexdigest()==digest
    cases=read('routing-evaluation.json')['cases']
    assert len(cases)==9 and sum(c['result']=='fail' for c in cases)==1
    report=(ROOT/'report.md').read_text()
    for target in re.findall(r'\]\(([^)]+)\)',report):
        if '://' not in target:
            assert (ROOT/unquote(target)).exists(), target
    assert '387 Python tests passed' in report and '169 Swift tests passed' in report
    assert '** TEST SUCCEEDED **' in (ROOT/'validation-logs/discovery-identity-xcode-ownership-final.log').read_text()
    assert '387 passed, 1 skipped' in (ROOT/'validation-logs/discovery-identity-python-final.log').read_text()
    results.update(passed=True,baselineReportUnchanged=True,identityComplete=True,
                   routing='8 assessed passes; 1 preserved configuration failure; not a blinded LLM benchmark',
                   candidateInstalled=False,report02='paused')
    (ROOT/'validation.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__': validate()
