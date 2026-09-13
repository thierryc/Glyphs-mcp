"""Closed coordinate-patch contract and pure topology fingerprints."""

import hashlib
import json
import math


def topology_hash(paths, anchors, components):
    data=json.dumps([paths,anchors,components],ensure_ascii=False,separators=(',',':'))
    return 'sha256:'+hashlib.sha256(data.encode()).hexdigest()


def validate(value):
    from .models import ProtocolError,_text,_hash
    fields={'kind','glyph','layer','nodes','anchors','components','before','after','topologyHash'}
    def invalid():raise ProtocolError('invalid_request','invalid explicit coordinate patch')
    if set(value)!=fields:invalid()
    nodes,anchors,components=value['nodes'],value['anchors'],value['components']
    if not all(isinstance(v,list) for v in (nodes,anchors,components)):invalid()
    if not 1<=len(nodes)+len(anchors)+len(components)<=4096:invalid()
    def index(v):return isinstance(v,int) and not isinstance(v,bool) and 0<=v<4096
    if any(not isinstance(n,list) or len(n)!=2 or not all(index(i) for i in n) for n in nodes):invalid()
    if any(not isinstance(n,str) or not n or len(n)>255 for n in anchors) or any(not index(i) for i in components):invalid()
    if len({tuple(n) for n in nodes})!=len(nodes) or len(set(anchors))!=len(anchors) or len(set(components))!=len(components):invalid()
    lengths=[2]*(len(nodes)+len(anchors))+[6]*len(components)
    for key in ('before','after'):
        vectors=value[key]
        if not isinstance(vectors,list) or len(vectors)!=len(lengths):invalid()
        if any(not isinstance(v,list) or len(v)!=size or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v,size in zip(vectors,lengths)):invalid()
    if value['before']==value['after']:invalid()
    return {**value,'glyph':_text(value['glyph'],'glyph'),'layer':_text(value['layer'],'layer'),
            'topologyHash':_hash(value['topologyHash'],'topologyHash')}
