# encoding: utf-8

###########################################################################################################
#
#
# General Plugin
#
# Read the docs:
# https://github.com/schriftgestalt/GlyphsSDK/tree/master/Python%20Templates/General%20Plugin
#
#
###########################################################################################################

import json, os, sys, traceback
from pathlib import Path
import objc
from Foundation import NSBundle, NSHomeDirectory, NSTimer, NSRunLoop, NSRunLoopCommonModes
from AppKit import NSApplication, NSModalPanelRunLoopMode
from GlyphsApp import Glyphs, GSGlyphsInfo
from GlyphsApp.plugins import GeneralPlugin
from PyObjCTools import AppHelper
class MCPSidebarIsolationProbe(GeneralPlugin):
 @objc.python_method
 def settings(self):self.name="Sidebar Isolation Probe"
 @objc.python_method
 def start(self):
  config=os.environ.get("MCP_ISOLATED_GUI_SETUP")
  if not config:return
  meta=json.loads(Path(config).read_text())
  if NSBundle.mainBundle().bundleIdentifier()!=meta["identifier"]:return
  if Path(str(NSHomeDirectory())).resolve()!=Path(meta["home"]).resolve():return
  self.meta=meta
  Path(meta["probe"],"loader.json").write_text(json.dumps({"pid":os.getpid(),"bundle":str(NSBundle.mainBundle().bundlePath()),"identifier":str(NSBundle.mainBundle().bundleIdentifier()),"home":str(NSHomeDirectory()),"support":str(GSGlyphsInfo.applicationSupportPath()),"fontCount":len(Glyphs.fonts)},indent=2))
  self.observationTimer=NSTimer.timerWithTimeInterval_repeats_block_(0.5,True,lambda _:self.observeStartup())
  NSRunLoop.mainRunLoop().addTimer_forMode_(self.observationTimer,NSRunLoopCommonModes)
  NSRunLoop.mainRunLoop().addTimer_forMode_(self.observationTimer,NSModalPanelRunLoopMode)
  AppHelper.callLater(2,self.runProbe)
 @objc.python_method
 def observeStartup(self):
  result=[]
  for w in NSApplication.sharedApplication().windows():
   if not w.isVisible():continue
   row={"title":str(w.title()),"class":str(w.className()),"texts":[]};pending=[w.contentView()]
   while pending and len(row["texts"])<200:
    view=pending.pop()
    if view is None:continue
    for field in ("stringValue","title"):
     method=getattr(view,field,None)
     if callable(method):
      try:
       text=str(method())
       if text:row["texts"].append(text[:2000])
      except Exception:pass
    pending.extend(list(view.subviews() or []))
   result.append(row)
  Path(self.meta["probe"],"startup-windows.json").write_text(json.dumps(result,indent=2))
 @objc.python_method
 def runProbe(self):
  old=list(sys.argv)
  try:
   sys.path.insert(0,"/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/scripts")
   sys.argv=["probe","--output",str(Path(self.meta["probe"],"result.json")),"--variant","baseline","--preflight"]
   from qualify_sidebar_counts_native import main
   main()
  except BaseException:
   Path(self.meta["probe"],"loader-error.txt").write_text(traceback.format_exc())
  finally:sys.argv=old
 @objc.python_method
 def __file__(self):return __file__
