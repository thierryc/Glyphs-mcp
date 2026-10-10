"""Direct panel: one Apply, no preview lifecycle, callbacks cannot mutate."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/companions/curve-inspector"))
from curve_repair.native import identity
from curve_repair.actions import default_limit, validate_limit

PATH = Path(__file__).resolve().parents[3] / "src/companions/curve-inspector/glyphs_curve_inspector/controller.py"

class Control:
    def __init__(self, state=0): self.enabled=True; self.value=state; self.hidden=False; self.text=""
    def selectedSegment(self): return self.value
    def setSelectedSegment_(self,v): self.value=v
    def stringValue(self): return self.text
    def state(self): return self.value
    def setState_(self, v): self.value=v
    def setEnabled_(self, v): self.enabled=v
    def setHidden_(self, v): self.hidden=v
    def setStringValue_(self, v): self.text=v
    def setToolTip_(self, v): self.tooltip=v

def controller():
    tree=ast.parse(PATH.read_text())
    cls=next(n for n in tree.body if isinstance(n, ast.ClassDef))
    queue=[]; removed=[]; calls=[]
    font=SimpleNamespace(upm=1000); host=SimpleNamespace(font=font, removeCallback=lambda f: removed.append(f))
    scope=SimpleNamespace(font=font,glyphs=(object(),),description="o · selected outlines",layer=None,background=False,selection=())
    def steps(*a, **kw):
        calls.append(kw)
        result=SimpleNamespace(changed=1,skipped=[],message=lambda: "1 repaired",details=lambda: "Undo available")
        yield result
        return result
    env=dict(NSObject=object,objc=SimpleNamespace(python_method=lambda f:f),Glyphs=host,
             AppHelper=SimpleNamespace(callAfter=lambda f:queue.append(f)),identity=identity,
             resolve_scope=lambda *a, **kw:scope,visible_layer=None,apply_steps=steps,native_app=None,default_limit=default_limit,validate_limit=validate_limit,value=lambda o,k,d=None:getattr(o,k,d))
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(PATH),"exec"),env)
    c=env['RepairController'](); c._scope_key=None;c._limit_font=None;c._closed=c._scheduled=False; c._task=c._font=None
    c.mode=Control();c.all_masters=Control();c.limit=Control();c.limit.text='1'
    def number(s):
        try:return float(s)
        except ValueError:return None
    c.number_formatter=SimpleNamespace(numberFromString_=number,stringFromNumber_=lambda n:str(n))
    c.apply_button=Control();c.status=Control(); c.reporter=SimpleNamespace(attached_=lambda _:None,_repair_window=c)
    return SimpleNamespace(c=c,queue=queue,calls=calls,host=host,removed=removed)

def test_native_selector_arity():
    for cls in (n for n in ast.parse(PATH.read_text()).body if isinstance(n,ast.ClassDef)):
        for m in (n for n in cls.body if isinstance(n,ast.FunctionDef)):
            if any(isinstance(d,ast.Attribute) and d.attr=='python_method' for d in m.decorator_list): continue
            assert m.name.count('_')==len(m.args.args)-1,m.name

def test_panel_has_no_preview_scope_popup_or_drawers():
    text=PATH.read_text()
    assert 'Preview' not in text and 'preview_' not in text and 'NSPopUpButton' not in text
    assert 'Details' not in text and 'Settings' not in text
    assert '280, 146' in text and 'layout_method' not in text
    assert 'NSSegmentedControl' in text and 'self.tunni' not in text
    assert 'setHidden_' not in text and 'Max change' in text

def test_apply_has_default_node_mode_and_visible_limit():
    r=controller();r.c.check_source()
    assert r.c.apply_button.enabled and not r.calls
    r.c.mode.setSelectedSegment_(1)
    r.c.changed_(None)
    r.c.apply_(None)
    assert not r.c.apply_button.enabled and not r.calls
    while r.queue:r.queue.pop(0)()
    assert r.calls==[dict(method='default-node',all_masters=False,max_change_units=1)]
    assert r.c.apply_button.enabled and r.c.status.text=='1 repaired' and 'Undo' in r.c.status.tooltip

def test_document_switch_before_callback_never_applies():
    r=controller();r.c.apply_(None);r.host.font=object()
    r.queue.pop(0)()
    assert not r.calls and r.c._task is None and 'document changed' in r.c.status.text

def test_overlay_refresh_callback_is_read_only():
    r=controller();r.c.queueCheck_(None);r.queue.pop(0)()
    assert not r.calls and 'selected outlines' in r.c.status.text

def test_close_cancels_pending_work():
    r=controller();r.c.apply_(None);r.c.windowWillClose_(None)
    while r.queue:r.queue.pop(0)()
    assert not r.calls and len(r.removed)==1 and r.c.reporter._repair_window is None


def test_unchanged_canvas_notifications_preserve_last_apply_result():
    r=controller();r.c.check_source();r.c.apply_(None)
    while r.queue:r.queue.pop(0)()
    text=r.c.status.text
    r.c.queueCheck_(None)
    while r.queue:r.queue.pop(0)()
    assert r.c.status.text==text and text=='1 repaired'
    r.c.all_masters.setState_(1);r.c.changed_(None)
    assert 'All masters' in r.c.status.text


import pytest
@pytest.mark.parametrize('text',['','0','-1','NaN','Infinity','abc'])
def test_invalid_limit_disables_apply_and_does_not_execute(text):
    r=controller();r.c.check_source();r.c.limit.text=text;r.c.controlTextDidChange_(None)
    assert not r.c.apply_button.enabled and not r.calls and 'Max change' in r.c.status.text

def test_limit_resets_on_document_change_using_upm():
    r=controller();r.c.check_source();assert float(r.c.limit.text)==1
    r.c.limit.text='3';r.c.controlTextDidChange_(None)
    scope=r.c.check_source.__globals__['resolve_scope'](None,None)
    new_font=SimpleNamespace(upm=2048)
    scope.font=new_font;r.host.font=new_font;r.c.check_source()
    assert float(r.c.limit.text)==2.048 and r.c.apply_button.enabled
