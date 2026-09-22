"""Isolated Glyphs 4 coordinator/save/Undo qualification on a disposable font.

Run: glyphs run --app '/Applications/Glyphs 4.app' --plugins '' scripts/qualify_edit_workflow_native.py
This does not install components, relaunch the user's editor, or touch open fonts.
"""
import json
import os
from pathlib import Path
from queue import Queue, Empty
import sys
from threading import Event, Thread
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'/part) for part in ('protocol','bridge','sidecar')]
from AppKit import NSApplication
from Foundation import NSURL, NSRunLoop, NSDate
import objc
from GlyphsApp import Glyphs, GSFont, GSFontMaster, GSGlyph, GSLayer
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_sidecar.service import SidecarService
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.worker import GlyphsCliWorker
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_sidecar.source import source_hash

OUT = ROOT/'build/edit-workflow-native'
APPLY_ONLY = os.environ.get('GLYPHS_MCP_QUALIFY_APPLY_ONLY') == '1'
OUT.mkdir(parents=True,exist_ok=True)
source = OUT/('disposable-'+str(time.time_ns())+'.glyphs')
checks=[]; tasks=Queue(); finished=Event(); outcome={}
def check(label, result):
    checks.append({'name':label,'passed':bool(result)})
    assert result,label

def main_call(callback):
    done=Event(); result={}
    def invoke():
        try: result['value']=callback()
        except BaseException as exc: result['error']=exc
        finally: done.set()
    tasks.put(invoke)
    if not done.wait(20): raise TimeoutError('Native qualification dispatcher')
    if 'error' in result: raise result['error']
    return result.get('value')

NSApplication.sharedApplication()
font=GSFont();font.familyName='MCP Conversation Disposable';font.masters.append(GSFontMaster());font.glyphs.append(GSGlyph('A'))
layer=GSLayer();layer.layerId=font.masters[0].id;layer.associatedMasterId=layer.layerId
font.glyphs['A'].layers.append(layer);layer.width=600
native_document=objc.lookUpClass('GSDocument').alloc().init();native_document.setFont_(font)
font.save(str(source),makeCopy=True);native_document.setFileURL_(NSURL.fileURLWithPath_(str(source)))
native_document.setFileType_('com.schriftgestaltung.glyphs')
manager=native_document.undoManager()
while manager.groupingLevel():manager.endUndoGrouping()
manager.removeAllActions();native_document.updateChangeCount_(2)
layer.width=610;native_document.updateChangeCount_(0)
if APPLY_ONLY:
    font.save(str(source),makeCopy=True);native_document.updateChangeCount_(2)
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.1))
    while manager.groupingLevel():manager.endUndoGrouping()
    manager.removeAllActions();native_document.updateChangeCount_(2)
glyph_history=font.glyphs['A'].undoManager()
while glyph_history.groupingLevel():glyph_history.endUndoGrouping()
glyph_history.setGroupsByEvent_(False);glyph_history.removeAllActions()
if APPLY_ONLY:native_document.updateChangeCount_(2)
adapter=GlyphsAdapter(Glyphs);adapter._fonts=lambda:[font]
native_save=adapter.save_document
def traced_save(*args, **kwargs):
    try:return native_save(*args, **kwargs)
    except Exception as exc:
        outcome['nativeException']=repr(exc.__cause__)
        raise
adapter.save_document=traced_save
core=BridgeCore(adapter, tasks.put)
identity=core.list_documents()[0]['id']

class Bridge:
    def call(self, callback):
        try:return main_call(callback)
        except BridgeError as exc:raise BridgeClientError(exc.code,exc.message,exc.details)
    def status(self):return self.call(core.status)
    def documents(self):return self.call(core.list_documents)
    def apply(self, patch):return self.call(lambda:core.begin_apply(patch))
    def operation(self, job):return self.call(lambda:core.operation(job))
    def discard(self, job):return self.call(lambda:core.discard(job))
    def save(self, request):return self.call(lambda:core.begin_save(request))
    def save_operation(self, identity):return self.call(lambda:core.save_operation(identity))
    def accept(self, job, request):return self.call(lambda:core.begin_accept(job,request))
    def complete_accept(self, job, **kwargs):return self.call(lambda:core.complete_accept(job,**kwargs))

service=SidecarService(Bridge(),jobs=JobStore(OUT/('jobs-'+str(time.time_ns()))),
 worker=GlyphsCliWorker(executable='/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs',app='/Applications/Glyphs 4.app'))
def choose(value,name):
    action=next(a for a in value['actions'] if a['action']==name)
    return service.edit_workflows.respond(value['id'],value['revision'],action['token'])
def wait(value,state):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        value=service.edit_workflows.get(value['id'])
        if value['state']==state:return value
        if value['state'] in {'failed','uncertain','outdated'}:raise AssertionError(value)
        time.sleep(.05)
    raise TimeoutError(value)

def run():
    try:
        value=service.edit_workflows.start(identity,kind='width_delta',delta=8,glyphs=['A'],idempotency_key='native-edit')
        outcome['initialState']=value
        check('native prerequisite state',value['state']=='preparing' if APPLY_ONLY else value['state']=='waiting_save')
        if not APPLY_ONLY:
            initial=value;value=choose(value,'save_continue');choose(initial,'save_continue')
        value=wait(value,'applied')
        check('real worker and native application',main_call(lambda:float(layer.width))==618)
        check('prerequisite saved original work only',main_call(lambda:float(_load_font(source).glyphs['A'].layers[0].width))==610)
        saved_hash=source_hash(source)
        check('result remains dirty',main_call(lambda:bool(native_document.isDocumentEdited())))
        main_call(glyph_history.undo);check('native glyph Undo restores prerequisite value',main_call(lambda:float(layer.width))==610)
        main_call(glyph_history.redo);check('native glyph Redo restores result',main_call(lambda:float(layer.width))==618)
        value=wait(choose(value,'discard'),'discarded')
        check('guarded discard restores exact width',main_call(lambda:float(layer.width))==610)
        check('discard did not save',source_hash(source)==saved_hash)
        if APPLY_ONLY:
            main_call(lambda:font.save(str(source),makeCopy=True));main_call(lambda:native_document.updateChangeCount_(2))
        else:service.save_document(identity)
        value=service.edit_workflows.start(identity,kind='width_delta',delta=8,glyphs=['A'],mode='preview',idempotency_key='native-preview')
        value=wait(value,'ready');check('preview leaves native font unchanged',main_call(lambda:float(layer.width))==610)
        value=wait(choose(value,'apply'),'applied')
        if not APPLY_ONLY:
            value=wait(choose(value,'save_result'),'saved')
            check('separate final save verified',value['receipt']['verification']=='native_and_source_hash')
            check('saved result reopens with new width',main_call(lambda:float(_load_font(source).glyphs['A'].layers[0].width))==618)
        outcome['passed']=True
    except BaseException:
        outcome['error']=traceback.format_exc()
    finally:
        service.close();finished.set()

Thread(target=run,daemon=True).start()
while not finished.is_set():
    try:tasks.get(timeout=.005)()
    except Empty:pass
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.001))
outcome.update(checks=checks,host={'version':str(Glyphs.versionString),'build':str(Glyphs.buildNumber)},scope='isolated native helper, not installed client qualification', nativeSaveIncluded=not APPLY_ONLY)
(OUT/('apply-only-result.json' if APPLY_ONLY else 'result.json')).write_text(json.dumps(outcome,indent=2)+'\n')
print(json.dumps(outcome),flush=True)
if not outcome.get('passed'):raise RuntimeError(outcome.get('error'))
