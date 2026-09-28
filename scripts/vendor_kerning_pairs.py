#!/usr/bin/env python3
"""Reproduce pinned MIT pair facts; no article text, word corpus or font values."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = 'b7a0e29ed81a8edee7b4b6cb1935ebf7d29ca611'
LANGUAGES = ('cs','da','de','en','es','et','fi','fr','hr','hu','it','lt','lv','nl','no','pl','pt','ro','se','sk','sl','sq','sv','tr')
ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT/'src/protocol/glyphs_mcp_protocol/data/kerning-pairs'
BASE = 'https://raw.githubusercontent.com/andre-fuchs/kerning-pairs/'+REVISION+'/'


def generate(source):
    def read(path):
        item=source/path
        if not item.exists():
            item.parent.mkdir(parents=True,exist_ok=True)
            item.write_bytes(urllib.request.urlopen(BASE+path,timeout=60).read())
        return item.read_bytes()
    inputs, pairs = [], {}
    for language in LANGUAGES:
        path=f'count/by_language/{language}/common_kerning_pairs.json'
        data=read(path); rows=json.loads(data)
        normalized=[]; seen=set()
        for pair,_score in rows:
            if not isinstance(pair,str) or len(pair)!=2 or any(ord(c)<32 for c in pair):
                raise ValueError('Unexpected upstream pair: '+repr(pair))
            if pair not in seen: normalized.append(pair); seen.add(pair)
        pairs[language]=normalized
        inputs.append(dict(language=language,source=BASE+path,sha256=hashlib.sha256(data).hexdigest(),rows=len(rows),pairs=len(normalized)))
    serialized=(json.dumps(pairs,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
    license_text=read('LICENSE.md'); readme=read('readme.md')
    meta=dict(source='https://github.com/andre-fuchs/kerning-pairs',revision=REVISION,license='MIT',
              copyright='Copyright (c) 2019 André Fuchs',
              languageTags='Upstream count/by_language directory codes and pinned readme language table. se is labelled Sami upstream; no broader coverage claim.',
              normalization='Retain two-character pair order within each language, deduplicate within that language, discard upstream scores. No case expansion, Unicode normalization, alternate glyph guessing, or kerning values.',
              limitations='Corpus-derived Basic Latin through Latin Extended A and quotes. Candidate pairs for inspection, not exhaustive language or shaping coverage.',
              recipe='scripts/vendor_kerning_pairs.py',inputs=inputs,
              licenseSource=BASE+'LICENSE.md',licenseSha256=hashlib.sha256(license_text).hexdigest(),
              descriptionSource=BASE+'readme.md',descriptionSha256=hashlib.sha256(readme).hexdigest(),
              normalizedSha256=hashlib.sha256(serialized).hexdigest())
    return {'pairs.json':serialized,'LICENSE.md':license_text,'provenance.json':(json.dumps(meta,ensure_ascii=False,indent=2)+'\n').encode()}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=ROOT/'build/beta8-milestone8/research/upstream')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    outputs=generate(args.source_dir)
    for name,data in outputs.items():
        target=DESTINATION/name
        if args.check:
            if target.read_bytes()!=data: raise SystemExit('Not reproducible: '+str(target))
        else:
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print(f'{len(LANGUAGES)} languages; {len(outputs["pairs.json"])} normalized bytes; reproducible={args.check}')
