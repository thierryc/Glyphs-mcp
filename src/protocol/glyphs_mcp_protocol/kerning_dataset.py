"""Pinned candidate facts, never proposed numeric kerning values."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent/'data'/'kerning-pairs'


@lru_cache(maxsize=1)
def contents():
    raw=(ROOT/'pairs.json').read_bytes()
    provenance=json.loads((ROOT/'provenance.json').read_text())
    if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=provenance['normalizedSha256']:
        raise ValueError('Bundled kerning pair provenance mismatch')
    rows=json.loads(raw)
    return rows, provenance


def languages(): return sorted(contents()[0])


@lru_cache(maxsize=1)
def alphabet():
    chars=frozenset(c for pairs in contents()[0].values() for pair in pairs for c in pair)
    if len(chars)>512: raise ValueError('Bundled kerning alphabet exceeds its validated bound')
    return chars


def candidates(languages):
    rows, _=contents(); found={}
    for language in sorted(languages):
        for rank,pair in enumerate(rows[language]):
            old=found.setdefault(pair,[rank,[]]);old[0]=min(old[0],rank);old[1].append(language)
    return [(pair,value[1]) for pair,value in sorted(found.items(),key=lambda item:(item[1][0],item[0]))]


def provenance():
    _, value=contents()
    return {key:value[key] for key in ('source','revision','license','normalizedSha256','limitations')}
