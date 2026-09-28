"""Read-only native proof qualification and cold-map/page latency evidence."""
import json
from pathlib import Path
import resource
import sys
import time
from native_script_harness import Harness
from glyphs_mcp_protocol import kerning_dataset as dataset
from glyphs_mcp_sidecar.source import source_hash

suffix,density,output=[a for a in sys.argv[1:] if a!='--']
chars=sorted(dataset.alphabet() if density=='dense' else set(' AVToabcdefghijklmnopqrstuvwxyz'))
h=Harness(count=len(chars),suffix=suffix,single_master=True)


def exercise(h):
    def setup():
        font=h.doc.font
        for glyph,char in zip(font.glyphs,chars):
            glyph.beginUndo();glyph.unicode=f'{ord(char):04X}';glyph.endUndo()
        font.save(str(h.source),makeCopy=True);h.clean()
    h.main(setup)
    before=source_hash(h.source)
    document=h.service.list_documents()[0]['id']
    original=h.main(lambda:h.adapter.document_state(document))
    evidence=[]
    for languages in (['en'],['fr','de'],dataset.languages()):
        h.main(lambda:setattr(h.adapter,'_kerning_proof_map',None))
        request=dict(kind='kerning_proof',master=h.mid,direction='LTR',languages=languages,limit=100)
        pages=[];items=[];start=time.perf_counter()
        while True:
            began=time.perf_counter()
            # Exercise the real core read entry, not a direct implementation call.
            response=h.main(lambda:h.core.read_entities(document,[request],['pairs']))
            latency=time.perf_counter()-began
            result=response[0]['values'];items.extend(result['items'])
            assert result['scannedGlyphs']<=256 and result['scannedCandidates']<=256 and len(result['items'])<=100
            pages.append(dict(seconds=latency,bytes=len(json.dumps(response,ensure_ascii=False).encode()),phase=result['phase'],
                              scannedGlyphs=result['scannedGlyphs'],scannedCandidates=result['scannedCandidates'],returned=result['returned']))
            if result['complete']:break
            request={**request,'cursor':result['nextCursor']}
        expected=[pair for pair,tags in dataset.candidates(languages) if all(c in chars for c in pair)]
        assert [item['characters'] for item in items]==expected
        assert len(set(expected))==len(items)
        assert all(item['coverage']['glyphPair'] is None for item in items)
        assert all(item['coverage']['effective']['status']=='none' for item in items),items[:1]
        assert h.main(lambda:h.adapter.document_state(document))==original
        evidence.append(dict(languages=languages,seconds=time.perf_counter()-start,pairs=len(items),pages=pages,
                             longestReadSeconds=max(p['seconds'] for p in pages),maxResponseBytes=max(p['bytes'] for p in pages)))
    assert source_hash(h.source)==before
    return dict(format=suffix,density=density,glyphs=len(chars),evidence=evidence,peakRSSBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                savedSourceUnchanged=True,liveStateUnchanged=True,saveCallsDuringProofs=0)


result=h.run(exercise)
result['methodology']='Fresh native process per format/density/repetition; three language filters each start with a cold bounded Unicode map. Read timings include harness main-thread dispatch and response, exclude CLI startup, HTTP/model latency and rendering. Every page has <=256 glyph or candidate scans and <=100 returned pairs. No shaping, collisions or value suggestions.'
Path(output).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='error'}),flush=True)
if not result.get('passed'):raise RuntimeError(result.get('error'))
