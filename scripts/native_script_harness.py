"""Disposable native documents and real sidecar/chat orchestration for qualification."""
import json
from pathlib import Path
from queue import Queue, Empty
import sys
import tempfile
import shutil
from threading import Event, Thread
import time
import traceback
import faulthandler
faulthandler.dump_traceback_later(45)
ROOT=Path(__file__).resolve().parents[1]
for part in ('protocol','bridge','sidecar'):sys.path.insert(0,str(ROOT/'src'/part))
import objc
from AppKit import NSApplication
from Foundation import NSURL, NSRunLoop, NSDate
from GlyphsApp import Glyphs, GSFont, GSFontMaster, GSGlyph, GSPath, GSNode
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge import saved_script
from glyphs_mcp_sidecar.bridge_client import BridgeClientError
from glyphs_mcp_sidecar.service import SidecarService
from glyphs_mcp_sidecar.jobs import JobStore
from glyphs_mcp_sidecar.worker import GlyphsCliWorker


class Harness:
    def __init__(self,count=1,contours=1,suffix='glyphs',single_master=False,batch_fixture=False,fixture=None):
        NSApplication.sharedApplication()
        self.temp=tempfile.TemporaryDirectory(prefix='glyphs-native-workflow-')
        self.source=Path(self.temp.name).resolve()/('Probe.'+suffix)
        if fixture:
            fixture=Path(fixture)
            if fixture.is_dir(): shutil.copytree(fixture,self.source)
            else: shutil.copy2(fixture,self.source)
            loaded=GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(self.source)),None)
            font=loaded[0] if isinstance(loaded,tuple) else loaded
            assert font is not None and len(font.glyphs)==count
        else:
            font=GSFont();font.grid=1;font.familyName='Native workflow probe'
            if single_master: font.masters = []
            font.masters.append(GSFontMaster())
            mid=str(font.masters[0].id)
            if batch_fixture: font.glyphs = [GSGlyph('probe'+str(i)) for i in range(count)]
            for i in range(count):
                if batch_fixture: glyph=font.glyphs['probe'+str(i)]
                else:
                    glyph=GSGlyph('probe'+str(i));font.glyphs.append(glyph)
                layer=glyph.layers[mid];layer.width=500
                for j in range(contours):
                    path=GSPath();path.closed=True
                    for point in ((10.25+j,0),(55.5+j,700.25),(300.25+j,100.5)):path.nodes.append(GSNode(point))
                    layer.background.shapes.append(path)
        self.mid=str(font.masters[0].id)
        self.doc=objc.lookUpClass('GSDocument').alloc().init();self.doc.setFont_(font)
        if not fixture: font.save(str(self.source),makeCopy=True)
        self.doc.setFileURL_(NSURL.fileURLWithPath_(str(self.source)))
        self.doc.setFileType_('com.glyphsapp.glyphspackage' if suffix=='glyphspackage' else 'com.schriftgestaltung.glyphs')
        self.clean()
        self.queue=Queue();self.max_chunk=0;self.chunks=0;self.native_seconds=0
        self.adapter=GlyphsAdapter(Glyphs);self.adapter._fonts=lambda:[self.doc.font]
        # Standalone GSDocument omits Cocoa dataOfType:error:. Qualify actual
        # font serialization here; do not represent this as editor NSDocument saving.
        def fixture_save(identity,target,mode):
            self.doc.font.save(target,makeCopy=True)
            self.doc.setFileURL_(NSURL.fileURLWithPath_(target));self.doc.updateChangeCount_(2)
            return dict(writeAttempted=True,nativeSaveSucceeded=True,nativeError=None,
                        **{k:v for k,v in self.adapter._document_state(self.doc.font).items() if k in ('path','dirty','generation')})
        self.adapter.save_document=fixture_save
        self.core=BridgeCore(self.adapter,self.schedule)
        harness=self
        class Bridge:
            def call(self,callback):
                try:return harness.main(callback)
                except BridgeError as e:raise BridgeClientError(e.code,e.message,e.details)
            def status(self):return self.call(harness.core.status)
            def documents(self):return self.call(harness.core.list_documents)
            def apply(self,p,**kw):return self.call(lambda:harness.core.begin_apply(p,**kw))
            def prepare_typed(self,r):
                from glyphs_mcp_bridge import typed_preparation
                return self.call(lambda:typed_preparation.begin(harness.core,r,BridgeError))
            def prepared_typed(self,j):
                from glyphs_mcp_bridge import typed_preparation
                return self.call(lambda:typed_preparation.result(harness.core,j,BridgeError))
            def finish_edit(self,j):return self.call(lambda:harness.core.finish_edit(j))
            def operation(self,j):return self.call(lambda:harness.core.operation(j))
            def discard(self,j):return self.call(lambda:harness.core.discard(j))
            def run_script(self,r):return self.call(lambda:harness.core.begin_script(r))
            def review_script(self,r):return self.call(lambda:saved_script.review(harness.core,r,BridgeError))
            def reviewed_script(self,j):return self.call(lambda:saved_script.review_result(harness.core,j,BridgeError))
            def restore_saved_script(self,r):return self.call(lambda:saved_script.restore(harness.core,r,BridgeError))
            def finish_script(self,j):return self.call(lambda:harness.core.finish_script(j))
            def save(self,r):return self.call(lambda:harness.core.begin_save(r))
            def save_operation(self,j):return self.call(lambda:harness.core.save_operation(j))
            def accept(self,j,r):return self.call(lambda:harness.core.begin_accept(j,r))
            def complete_accept(self,j,**kw):return self.call(lambda:harness.core.complete_accept(j,**kw))
        self.service=SidecarService(Bridge(),jobs=JobStore(Path(self.temp.name)/'jobs'),worker=GlyphsCliWorker(
            executable='/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs',app='/Applications/Glyphs 4.app'))

    def clean(self):
        font=self.doc.font
        for manager in [self.doc.undoManager()]+[g.undoManager() for g in font.glyphs]:
            while manager.groupingLevel():manager.endUndoGrouping()
            manager.setGroupsByEvent_(False);manager.removeAllActions()
        self.doc.updateChangeCount_(2)

    def main(self,callback):
        done=Event();result={}
        def call():
            try:result['value']=callback()
            except BaseException as e:
                traceback.print_exc();result['error']=e
            finally:done.set()
        self.queue.put(call)
        if not done.wait(120):raise TimeoutError('native dispatcher')
        if 'error' in result:raise result['error']
        return result.get('value')

    def schedule(self,callback):
        def measured():
            start=time.perf_counter()
            callback()
            seconds=time.perf_counter()-start
            self.max_chunk=max(self.max_chunk,seconds);self.chunks+=1;self.native_seconds+=seconds
        self.queue.put(measured)

    def choose(self,value,name):
        a=next(a for a in value['actions'] if a['action']==name)
        return self.service.edit_workflows.respond(value['id'],value['revision'],a['token'])

    def wait(self,value,*states):
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            value=self.service.edit_workflows.get(value['id'])
            if value['state'] in states:return value
            expected_cleanup = value.get('poll') and bool({'failed','cancelled'} & set(states))
            if (value.get('error') and not expected_cleanup) or value['state'] in {'failed','uncertain','outdated','interrupted'}:raise AssertionError(value)
            time.sleep(.01)
        raise TimeoutError(value)

    def start(self,options,key):
        identity=self.service.list_documents()[0]['id']
        return self.service.edit_workflows.start(identity,kind='python_script',options=options,idempotency_key=key,mode='preview')

    def run(self,callback):
        done=Event();result={}
        def work():
            try:result['data']=callback(self);result['passed']=True
            except BaseException:result['error']=traceback.format_exc()
            finally:self.service.close();done.set()
        Thread(target=work,daemon=True).start()
        while not done.is_set():
            try:
                with objc.autorelease_pool():self.queue.get(timeout=.001)()
            except Empty:pass
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.001))
        self.temp.cleanup()
        faulthandler.cancel_dump_traceback_later()
        result['host']=dict(version=str(Glyphs.versionString),build=str(Glyphs.buildNumber))
        result['saveAdapter']='Native GSFont writer for standalone fixture; editor NSDocument save not exercised'
        return result
