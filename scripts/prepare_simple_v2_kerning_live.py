"""Seed/restore explicit collisions through the bridge on the authorized copy."""

import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'build/simple-v2/sidecar'),str(ROOT/'scripts')]
from glyphs_mcp_protocol import load_or_create_token
from glyphs_mcp_sidecar.bridge_client import BridgeClient
from glyphs_mcp_sidecar.source import source_hash
from qualify_simple_v2_live import _poll,_assert_responsive


def main():
    config=json.loads((ROOT/'build/lean-benefits-current.json').read_text())
    source=Path(config['source']);assert source.is_relative_to('/private/tmp')
    assert source_hash(Path(config['original']))==config['originalHash']
    bridge=BridgeClient('http://127.0.0.1:9681',load_or_create_token(),timeout=10)
    docs=bridge.documents();assert len(docs)==1 and docs[0]['path']==str(source),docs
    document=docs[0];path=ROOT/'build/kerning-live-fixture.json'
    restore='--restore' in sys.argv
    if restore:
        record=json.loads(path.read_text());patch=record['patch']
        assert patch['documentId']==document['id']
        bridge.discard(patch['jobId'])
    else:
        assert not document['dirty'],document
        # Obtain all master identities from the verified external preflight.
        preflight=json.loads((Path(config['root'])/'spacing-preflight/report.json').read_text())
        masters=list(dict.fromkeys(r['layer'] for r in preflight['layers']))
        selectors=[dict(kind='kerning',master=mid,direction='LTR',left='A',right='V') for mid in masters]
        baseline=bridge.read_entities(document['id'],selectors,['value'])
        changes=[dict(s,before=v['values']['value'],after=-2000.125) for s,v in zip(selectors,baseline)]
        patch=dict(version=1,jobId='collision-fixture-'+uuid4().hex,documentId=document['id'],
            sourcePath=str(source),sourceHash=source_hash(source),generation=document['generation'],
            changes=changes,summary='Disposable collision acceptance fixture')
        record={'patch':patch,'sourceHashBeforeFixture':source_hash(source)}
        path.write_text(json.dumps(record,indent=2)+'\n')
        bridge.apply(patch)
    state,measurement=_poll(lambda:bridge.operation(patch['jobId']),bridge.status,
        terminal={'applied','discarded','failed','cancelled'},timeout=30,interval=.05,settle_seconds=2)
    assert state['status']==('discarded' if restore else 'applied'),state
    selectors=[{k:c[k] for k in ('kind','master','direction','left','right')} for c in patch['changes']]
    actual=bridge.read_entities(document['id'],selectors,['value'])
    assert [v['values']['value'] for v in actual]==[c['before' if restore else 'after'] for c in patch['changes']]
    _assert_responsive(measurement)
    record['restored' if restore else 'seeded']=True
    record['restoreResponse' if restore else 'seedResponse']=measurement
    path.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'phase':'restore' if restore else 'seed','pairs':len(selectors),'response':measurement}))


if __name__=='__main__':main()
