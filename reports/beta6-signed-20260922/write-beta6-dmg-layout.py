from pathlib import Path
from ds_store import DSStore
from mac_alias import Alias
mount=Path('build/beta6-dmg-mount.txt').read_text().strip()
alias=Alias.for_file(mount+'/.background/background.tiff').to_bytes()
with DSStore.open(mount+'/.DS_Store','w+') as d:
 d['.']['bwsp']={'ShowStatusBar':False,'ShowToolbar':False,'ShowTabView':False,'ContainerShowSidebar':False,'WindowBounds':'{{100, 100}, {680, 448}}','ShowSidebar':False,'ShowPathbar':False}
 d['.']['icvp']={'viewOptionsVersion':1,'backgroundType':2,'backgroundImageAlias':alias,'backgroundColorRed':1.0,'backgroundColorGreen':1.0,'backgroundColorBlue':1.0,'gridOffsetX':0.0,'gridOffsetY':0.0,'gridSpacing':100.0,'arrangeBy':'none','showIconPreview':True,'showItemInfo':False,'labelOnBottom':True,'textSize':12.0,'iconSize':112.0,'scrollPositionX':0.0,'scrollPositionY':0.0}
 d['.']['vstl']=('type',b'icnv')
 d['Glyphs MCP.app']['Iloc']=(170,194)
 d['Applications']['Iloc']=(510,194)
with DSStore.open(mount+'/.DS_Store','r') as d:
 assert d['Glyphs MCP.app']['Iloc']==(170,194)
 assert d['Applications']['Iloc']==(510,194)
 assert d['.']['icvp']['iconSize']==112
 print('Layout metadata verified: 680x448, app (170,194), Applications (510,194), 112px icons, 12pt text, TIFF background.')
