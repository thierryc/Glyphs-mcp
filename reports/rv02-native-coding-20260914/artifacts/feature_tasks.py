"""Native feature artifacts; never treated as an MCP feature tool."""
from GlyphsApp import GSFeature

def value(obj,name):
 v=getattr(obj,name)
 return v() if callable(v) else v

def review(font):
 return dict(features=[dict(name=f.name,code=f.code,automatic=bool(value(f,'automatic')),disabled=bool(value(f,'disabled'))) for f in font.features],classes=[dict(name=c.name,code=c.code) for c in font.classes],prefixes=[dict(name=p.name,code=p.code) for p in font.featurePrefixes])

def create_ss20(font,invalid=False):
 if font.features['ss20'] is not None:raise ValueError('Existing ss20 preserved; choose another tag')
 for name in ('g','g.ss01'):
  if font.glyphs[name] is None:raise ValueError('Missing glyph: '+name)
 f=GSFeature('ss20','sub g by '+('rv01.missing' if invalid else 'g.ss01')+';')
 f.automatic=False
 font.features.append(f)
 return f
