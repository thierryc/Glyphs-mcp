"""Bounded language-pair proofs with native stored/effective evidence.

One volatile Unicode map covers only the fixed dataset alphabet, at most 512
entries, and retains no native glyph objects. Building it advances at most 256
glyphs per read. Other documents or changed generation/dirty/count invalidate
it. This is neither a font-wide kerning inventory nor a persisted history index.
"""
import base64
import json
import math
import uuid
from glyphs_mcp_protocol import kerning_dataset as dataset
from glyphs_mcp_protocol.kerning_edits import DIRECTIONS, SIDES, GROUPS, read_stored
from glyphs_mcp_protocol.reads import KERNING_SCAN_LIMIT, KERNING_PAGE_LIMIT
from .core import BridgeError
from .context import value


def error(message,code='invalid_request'): return BridgeError(code,message)


def cursor(data):
    return 'kp1.'+base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode()


def decode(raw):
    try:
        if not isinstance(raw,str) or not raw.startswith('kp1.') or len(raw)>8192: raise ValueError()
        data=json.loads(base64.b64decode(raw[4:],altchars=b'-_',validate=True))
        if (not isinstance(data,dict) or set(data)!={'map','scope','phase','offset'}
                or data['phase'] not in ('mapping','pairs') or type(data['offset']) is not int or data['offset']<0): raise ValueError()
        return data
    except (ValueError,TypeError,RecursionError) as exc:
        raise error('Use the unmodified nextCursor from the previous proof page') from exc


def glyph_record(glyph):
    name,identity,code=value(glyph,'name'),value(glyph,'id'),value(glyph,'unicode')
    if not isinstance(name,str) or not 1<=len(name)<=255 or identity is None:
        raise error('Native Unicode mapping identity unavailable','unsupported_read')
    return [str(identity),name,str(code) if code else None]


def mapping(adapter,font,document,c):
    state=[document,adapter._generation(font),adapter._dirty(font),len(font.glyphs)]
    cached=getattr(adapter,'_kerning_proof_map',None)
    if cached and cached['state']==state and cached['index']:
        if glyph_record(font.glyphs[cached['index']-1])!=cached['boundary']: cached=None
    if not cached or cached['state']!=state:
        if c: raise error('Proof document or mapping changed; restart without a cursor','stale_kerning_cursor')
        cached=dict(state=state,id=uuid.uuid4().hex,index=0,chars={},boundary=None)
        adapter._kerning_proof_map=cached
    if c and c['map']!=cached['id']:
        raise error('Proof mapping expired; restart without a cursor','stale_kerning_cursor')
    return cached


def map_page(font,cache,offset):
    total=cache['state'][3]
    if offset>cache['index'] or offset>total: raise error('Invalid proof mapping offset')
    end=min(total,offset+KERNING_SCAN_LIMIT)
    scanned=0
    for i in range(cache['index'],end):
        record=glyph_record(font.glyphs[i]);cache['boundary']=record
        identity,name,code=record; character=None
        try:
            if code and len(code)<=6: character=chr(int(code,16))
        except ValueError: pass
        if character in dataset.alphabet():
            old=cache['chars'].get(character)
            if old is None: cache['chars'][character]=dict(id=identity,name=name,ambiguous=False)
            elif old['id']!=identity: old['ambiguous']=True
        cache['index']=i+1;scanned+=1
    return end,scanned


def coverage(font,master,direction,left,right):
    groups=[]
    for glyph,prefix in zip((left,right),SIDES[direction]):
        name=value(glyph,GROUPS[prefix]+'KerningGroup')
        groups.append(prefix+str(name) if name else None)
    ln,rn=str(left.name),str(right.name)
    def exact(l,r):
        if l is None or r is None: return None
        stored=read_stored(font,master,l,r,direction)
        if stored is not None and (type(stored) not in (int,float) or not math.isfinite(stored)):
            raise error('Stored kerning value unavailable','unsupported_read')
        return stored
    result=dict(glyphPair=exact(ln,rn),glyphGroup=exact(ln,groups[1]),groupGlyph=exact(groups[0],rn),
                groupPair=exact(*groups),leftGroup=groups[0],rightGroup=groups[1],
                effective=dict(status='unknown',value=None))
    # Indexed native accessor avoids materializing missing master layers.
    get_left=getattr(left,'layerForId_',None);get_right=getattr(right,'layerForId_',None)
    if callable(get_left) and callable(get_right):
        ll,rr=get_left(master),get_right(master)
    else:  # Plain test hosts only; native Glyphs uses layerForId_.
        ll,rr=(left.layers.get(master),right.layers.get(master)) if isinstance(left.layers,dict) and isinstance(right.layers,dict) else (None,None)
    if ll is not None and rr is not None:
        try:
            effective=ll.nextKerningForLayer_direction_(rr,DIRECTIONS[direction])
            if isinstance(effective,(int,float)) and math.isfinite(effective):
                missing = effective == float(2**63-1)  # Native NSNotFound on supported 64-bit Glyphs.
                ambiguous = missing and any(result[k] == effective for k in ('glyphPair','glyphGroup','groupGlyph','groupPair'))
                result['effective']=dict(status='unknown' if ambiguous else 'none' if missing else 'native',
                                         value=None if missing else effective)
        except Exception: pass  # Exact storage remains useful; never infer precedence.
    return result


def read(adapter,font,document,entities,fields):
    if len(entities)!=1 or fields!=['pairs']: raise error('A kerning_proof page is the sole selector with fields [pairs]')
    request=entities[0]
    if set(request)-{'kind','master','direction','languages','limit','cursor'}: raise error('Unexpected kerning_proof fields')
    languages=request.get('languages');direction=request.get('direction');master=request.get('master')
    if (not isinstance(languages,list) or not languages or any(not isinstance(l,str) or l not in dataset.languages() for l in languages)
            or len(languages)!=len(set(languages))): raise error('Choose unique supported language tags: '+', '.join(dataset.languages()))
    if not isinstance(direction,str) or direction not in DIRECTIONS: raise error('Choose explicit LTR, RTL or vertical direction')
    if not isinstance(master,str) or not master: raise error('Choose an exact master ID')
    adapter._entity(font,'master',{'id':master})
    limit=request.get('limit',KERNING_PAGE_LIMIT)
    if type(limit) is not int or not 1<=limit<=KERNING_PAGE_LIMIT: raise error('Proof limit must be 1-100')
    scope=[document,master,direction,sorted(languages),limit]
    c=decode(request['cursor']) if 'cursor' in request else None
    if c and c['scope']!=scope: raise error('Proof scope changed; restart without a cursor','stale_kerning_cursor')
    cache=mapping(adapter,font,document,c)
    result=dict(items=[],returned=0,complete=False,nextCursor=None,scannedGlyphs=0,scannedCandidates=0,
                skippedMissing=0,skippedAmbiguous=0,skippedExamples=[],supportedLanguages=dataset.languages(),
                provenance=dataset.provenance(),claim='Pairs to inspect. Existing coverage is not a spacing judgement. Primary Unicode mapping only; ambiguous mappings are skipped. Proof strings are unshaped character pairs.')
    if (c and c['phase']=='mapping') or (not c and cache['index']<cache['state'][3]):
        end,scanned=map_page(font,cache,c['offset'] if c else cache['index'])
        result.update(phase='mapping',scannedGlyphs=scanned,mappedGlyphs=cache['index'],totalGlyphs=cache['state'][3],
                      nextCursor=cursor(dict(map=cache['id'],scope=scope,phase='pairs' if end==cache['state'][3] else 'mapping',offset=0 if end==cache['state'][3] else end)))
    else:
        rows=dataset.candidates(languages); offset=c['offset'] if c else 0
        if cache['index']!=cache['state'][3] or offset>len(rows): raise error('Proof mapping is incomplete or cursor invalid')
        result['phase']='pairs'
        while offset<len(rows) and result['scannedCandidates']<KERNING_SCAN_LIMIT and len(result['items'])<limit:
            pair,tags=rows[offset];offset+=1;result['scannedCandidates']+=1
            mapped=[cache['chars'].get(char) for char in pair]
            reason='ambiguous' if any(m and m['ambiguous'] for m in mapped) else 'missing' if not all(mapped) else None
            if reason:
                result['skippedAmbiguous' if reason=='ambiguous' else 'skippedMissing']+=1
                if len(result['skippedExamples'])<10: result['skippedExamples'].append(dict(characters=pair,reason=reason))
                continue
            glyphs=[font.glyphs[m['name']] for m in mapped]
            if any(g is None or str(g.id)!=m['id'] for g,m in zip(glyphs,mapped)):
                raise error('Proof glyph binding changed; restart','stale_kerning_cursor')
            result['items'].append(dict(characters=pair,left=mapped[0]['name'],right=mapped[1]['name'],languages=tags,
                                        proof=pair,coverage=coverage(font,master,direction,*glyphs)))
        result.update(returned=len(result['items']),totalCandidates=len(rows),complete=offset==len(rows),
                      nextCursor=None if offset==len(rows) else cursor(dict(map=cache['id'],scope=scope,phase='pairs',offset=offset)))
    return [dict(entity=dict(request),values=result)]
