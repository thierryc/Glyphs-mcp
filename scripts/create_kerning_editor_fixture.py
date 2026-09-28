"""Create new disposable editor fixtures; never overwrite an existing font."""
import json
from pathlib import Path
import sys
from native_script_harness import Harness,GSFontMaster
ROOT=Path(__file__).resolve().parents[1]
suffix=[a for a in sys.argv[1:] if a!='--'][0]
target=ROOT/'build/beta8-milestone8/editor'/suffix/('Kerning.'+suffix)
assert not target.exists(),target
target.parent.mkdir(parents=True,exist_ok=True)
h=Harness(count=3,suffix=suffix,single_master=True)
font=h.doc.font
h.doc.undoManager().beginUndoGrouping()
font.familyName='M8 Kerning qualification '+suffix
font.masters[0].name='Regular'
other=GSFontMaster();other.name='Control';font.masters.append(other)
for g,name,char in zip(font.glyphs,('A','V','n'),('A','V','n')):
    g.beginUndo();g.name=name;g.unicode=f'{ord(char):04X}'
    for side in ('left','right','top','bottom'):setattr(g,side+'KerningGroup',side+'_'+name)
    g.layers[h.mid].shapes=[s.copy() for s in g.layers[h.mid].background.shapes]
    g.endUndo()
for direction in (0,2,4):
    font.setKerningForPair(h.mid,'A','V',-10.125,direction=direction)
    font.setKerningForPair(other.id,'A','V',-31.125,direction=direction)
h.doc.undoManager().endUndoGrouping()
font.save(str(target),makeCopy=True)
target.with_name('fixture.json').write_text(json.dumps(dict(path=str(target),master=h.mid,otherMaster=str(other.id),familyName=font.familyName),indent=2)+'\n')
print(str(target))
