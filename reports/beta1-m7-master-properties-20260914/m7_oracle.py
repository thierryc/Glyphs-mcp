"""Independent native verification; never fills public tool results."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent/'beta1-h6-kerning-discovery-20260914'))
import h6_oracle as base
METRICS = ('ascender','capHeight','xHeight','descender','italicAngle')
FIELDS = ('id','name',*METRICS,'axes')
def rows(font):
    return [dict(id=m.id, name=m.name,
        **{key:getattr(m,'default'+key[0].upper()+key[1:])() for key in METRICS},
        axes=dict(items=[dict(axisId=a.axisId,tag=a.axisTag,name=a.name,index=i,
                      internalValue=m.internalAxesValues[a.axisId],externalValue=m.externalAxesValues[a.axisId])
                      for i,a in enumerate(font.axes)], total=len(font.axes),returned=len(font.axes),complete=True))
            for m in font.masters]
def snapshot(font):
    data=base.snapshot(font)
    data['masterProperties']=rows(font)
    data['fontMetadata']={'family':font.familyName,'userData':dict(font.userData),
        'customParameters':[(p.name,str(p.value)) for p in font.customParameters],
        'axes':[dict(object=base.base.native_id(a),id=a.axisId,name=a.name,tag=a.axisTag) for a in font.axes],
        'metrics':None if font.metrics.values() is None else
                  [(m.id,str(m.name),str(m.type),str(m.filter)) for m in font.metrics]}
    data['masterMetadata']=[dict(object=base.base.native_id(m),userData=dict(m.userData),
        customParameters=[(p.name,str(p.value)) for p in m.customParameters],
        metricStores=str(m.metrics.values())) for m in font.masters]
    return data
digest=base.digest
