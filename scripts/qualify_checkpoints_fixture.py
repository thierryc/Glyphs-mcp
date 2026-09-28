"""Serialize disposable real-font fixtures. Runs in a fresh glyphs-cli process."""
from pathlib import Path
import json
from GlyphsApp import GSFont
from Foundation import NSURL
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'build/beta8-milestone5/editor/Conversation.glyphspackage'
output=ROOT/'build/beta8-milestone6/editor'
loaded=GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(source)),None)
font=loaded[0] if isinstance(loaded,tuple) else loaded
assert font is not None
for suffix in ('glyphs','glyphspackage'):
    folder=output/suffix;folder.mkdir(parents=True,exist_ok=True)
    target=folder/('Checkpoint.'+suffix)
    assert not target.exists(), 'Preserve existing qualification evidence'
    font.familyName='Checkpoint qualification '+suffix
    font.save(str(target),makeCopy=True)
    (folder/'.glyphs-mcp.json').write_text(json.dumps({'schemaVersion':1,'gitCheckpoints':{'enabled':True}}))
    (folder/'unrelated.txt').write_text('original\n')
print('Created both disposable font formats')
