from GlyphsApp import GSFont
from pathlib import Path
f=GSFont(str(Path(__file__).parent/'MasterPropertiesTest.glyphs')).copy()
print('BEFORE',f.filepath, f.parent, dict(f.tempData))
del f.tempData['filePath']
print('AFTER',f.filepath, f.parent, dict(f.tempData))
assert f.filepath is None
assert len(f.masters)==3
print('M7 UNSAVED COPY',f.filepath,len(f.masters))
