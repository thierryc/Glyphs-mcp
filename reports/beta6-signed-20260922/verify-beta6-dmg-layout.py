import sys,json
from ds_store import DSStore
with DSStore.open(sys.argv[1]+'/.DS_Store','r') as d:
 assert d['Glyphs MCP.app']['Iloc']==(170,194)
 assert d['Applications']['Iloc']==(510,194)
 assert d['.']['icvp']['iconSize']==112
 assert d['.']['icvp']['backgroundType']==2
 assert d['.']['bwsp']['WindowBounds']=='{{100, 100}, {680, 448}}'
 print(json.dumps({'imageLayout':'verified','app':[170,194],'applications':[510,194],'iconSize':112,'background':'TIFF','windowSize':[680,448]}))
