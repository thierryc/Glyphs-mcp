"""Child of run_sidebar_count_experiment.py; never run in the working editor."""
import argparse
from contextlib import redirect_stderr
import faulthandler
import json
import os
from pathlib import Path
from queue import Empty
import sys
from threading import Event, Thread
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sidebar_count_experiment import CountGuard, VARIANTS, flag, validate_child_environment
from run_sidebar_count_experiment import write_json


def qualification_steps():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    validate_child_environment(output, os.environ, os.getpgrp())
    if output.exists():
        raise RuntimeError("Refusing to overwrite native evidence")
    evidence = dict(outcome="blocked", phase="imports", pid=os.getpid(), variant=args.variant,
                    workflows=[], cleanupErrors=[], checks=[], uiQualified=False)
    native_errors = None
    guard = None
    def record():
        write_json(output, evidence)
    def event(kind, **details):
        with (output.parent / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(event=kind, time=time.time(), **details))+"\n")
    record()
    try:
        import objc
        from AppKit import NSApplication, NSDocumentController, NSWindowDidBecomeKeyNotification
        from Foundation import NSNotificationCenter, NSRunLoop, NSDate, NSURL
        from GlyphsApp import Glyphs, GSFont, GSFontMaster, GSGlyph, GSPath, GSNode, GSComponent
        # The full editor replaces stderr with GlyphsErr (no fileno). The
        # qualification harness arms faulthandler at import time, so give it a
        # real, retained file instead of requiring a CLI-owned error stream.
        native_errors = (output.parent / "native-python.stderr.log").open("a", buffering=1)
        with redirect_stderr(native_errors):
            from native_script_harness import Harness

        if list(Glyphs.fonts):
            raise RuntimeError("Isolated probe unexpectedly contains existing fonts")

        evidence["host"] = dict(version=str(Glyphs.versionString), build=str(Glyphs.buildNumber),
                                appClass=str(NSApplication.sharedApplication().className()))
        evidence["phase"] = "fixture"
        record()
        h = Harness(count=1)
        # Build detached so setup cannot register Undo into the harness's
        # deliberately closed groups. Attach only the completed fixture.
        font = GSFont()
        font.familyName = "MCP Disposable Sidebar Count Experiment"
        font.masters = []
        for name in ("Regular", "Bold"):
            master = GSFontMaster(); master.name = name; font.masters.append(master)
        mids = [str(master.id) for master in font.masters]
        font.glyphs = []
        bases = ("a", "A", "alef-ar", "beh-ar", "uni4E00", "acutecomb", "one", "space", "period", "plus")
        names = [bases[i % len(bases)] + ".sidebar" + str(i).zfill(4) for i in range(1000)]
        def triangle(offset=0):
            path = GSPath(); path.closed = True
            for point in ((10+offset, 0), (60+offset, 700), (300+offset, 100)):
                path.nodes.append(GSNode(point))
            return path
        for index, name in enumerate(names):
            glyph = GSGlyph(name); font.glyphs.append(glyph)
            for mid in mids:
                layer = glyph.layers[mid]
                # Components depend on an untouched control, so changing a
                # target cannot silently change a control's resolved silhouette.
                if index and index % 10 == 0 and index != 900:
                    component = GSComponent(names[900]); component.automaticAlignment = False
                    layer.shapes = [component]
                else:
                    layer.shapes = [triangle()]
                layer.width = 500
        h.mid = mids[0]
        manager = h.doc.undoManager()
        manager.disableUndoRegistration()
        try:
            h.doc.setFont_(font)
        finally:
            manager.enableUndoRegistration()
        font.save(str(h.source), makeCopy=True)
        font.save(str(output.parent / "Disposable.glyphs"), makeCopy=True)
        h.clean()
        evidence["fixture"] = dict(path=str(output.parent / "Disposable.glyphs"), masters=mids,
                                   glyphs=len(font.glyphs), controls=200,
                                   categories=sorted({str(g.category) for g in font.glyphs}),
                                   scripts=sorted({str(g.script) for g in font.glyphs}))
        evidence["phase"] = "attach-font-view"
        record()

        def window_text(window):
            pieces = [str(window.title())]
            pending = [(window.contentView(), 0)]
            while pending and len(pieces) < 500:
                view, depth = pending.pop()
                if view is None or depth > 15:
                    continue
                getter = getattr(view, "stringValue", None)
                if callable(getter):
                    try: pieces.append(str(getter()))
                    except Exception: pass
                pending.extend((child, depth+1) for child in (view.subviews() or []))
            return "\n".join(pieces)
        def scan_alerts(_=None):
            for window in NSApplication.sharedApplication().windows():
                if window.isVisible():
                    text = window_text(window)
                    if "Invalid filter in sidebar" in text:
                        event("alert", windowClass=str(window.className()), text=text[:4000])
        # Observe only this process. Forward normal application behavior unchanged.
        observer = NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            NSWindowDidBecomeKeyNotification, None, None, scan_alerts)
        # A hand-built GSDocument can attach a window while leaving the sidebar
        # model uninitialized. Exercise the editor's normal document-read path.
        opened = NSDocumentController.sharedDocumentController().openDocumentWithContentsOfURL_display_error_(
            NSURL.fileURLWithPath_(str(h.source)), True, None)
        document, open_error = opened if isinstance(opened, tuple) else (opened, None)
        if document is None or open_error is not None:
            raise RuntimeError("Could not open disposable editor document: " + str(open_error))
        h.doc = document
        font = h.doc.font
        loaded_mids = [str(master.id) for master in font.masters]
        loaded_names = [str(g.name) for g in font.glyphs]
        evidence["editorOpen"] = dict(masters=loaded_mids, glyphs=len(loaded_names),
                                      glyphOrderChanged=loaded_names != names,
                                      missingNames=sorted(set(names)-set(loaded_names))[:20],
                                      extraNames=sorted(set(loaded_names)-set(names))[:20])
        if (len(loaded_mids) != len(mids) or set(loaded_mids) != set(mids)
                or len(loaded_names) != len(names) or set(loaded_names) != set(names)):
            raise RuntimeError("Editor document differs from the disposable fixture")
        h.clean()
        controller = h.doc.windowController()
        if controller is None:
            raise RuntimeError("Isolated GSDocument has no native window controller")
        controller.window().makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        # Return to the real application loop: the native sidebar installs its
        # background-built model on the main queue, which cannot reenter itself.
        yield .02
        font_view = font.fontView
        if font_view is None or font_view.view().window() is None or not font_view.view().window().isVisible():
            raise RuntimeError("No visible attached native Font View")
        sidebar = font_view.glyphsGroupViewController()
        outline = sidebar.myOutlineView()
        if outline is None or outline.window() is None:
            raise RuntimeError("Font View sidebar is not attached to a window")
        # Full-editor window creation attaches views before the sidebar finishes
        # populating its model. Allow that normal UI work to run, with a bound.
        deadline = time.monotonic() + 5
        while sidebar.glyphGroups() is None and time.monotonic() < deadline:
            scan_alerts()
            yield .02
        if sidebar.glyphGroups() is None:
            tree = sidebar.treeController()
            evidence["sidebarProbe"] = dict(
                sidebarClass=str(sidebar.className()),
                selectors=[name for name in dir(sidebar)
                           if any(word in name.lower() for word in ("group", "font", "tree", "content"))],
                outlineRows=int(outline.numberOfRows()),
                treeClass=str(tree.className()) if tree is not None else None,
                treeContent=repr(tree.content())[:5000] if tree is not None else None,
                arrangedObjects=repr(tree.arrangedObjects())[:5000] if tree is not None else None)
            raise RuntimeError("Attached sidebar did not populate its native group model")
        def items():
            pending = list(sidebar.glyphGroups()); result = []; seen = set()
            while pending:
                item = pending.pop(0); identity = objc.pyobjc_id(item)
                if identity in seen: continue
                seen.add(identity); result.append(item)
                pending.extend(list(item.subItems() or []))
            return result
        selected = lambda: list(sidebar.treeController().selectedObjects() or [])
        guard = CountGuard(items(), font, selected(), identity=objc.pyobjc_id)
        original_selection = [objc.pyobjc_id(item) for item in selected()]
        original_ui = flag(font, "isUpdateInterfaceEnabled")
        predicates = [(item, str(item.predicate())) for item in items() if item.predicate() is not None]
        # Let the actual native counters run before accepting this as a UI test.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(int(item.count()) >= 0 for item, _ in guard.rows):
            scan_alerts()
            yield .02
        if not any(int(item.count()) >= 0 for item, _ in guard.rows):
            raise RuntimeError("Attached sidebar counters never produced a native count")
        evidence.update(uiQualified=True, sidebar=dict(predicateItems=len(predicates),
                        eligibleItems=len(guard.rows), selectedItems=len(original_selection)), phase="qualified-ui")
        record(); event("ui-qualified")
        if args.preflight:
            evidence["outcome"] = "passed"
            h.service.close(); h.temp.cleanup()
            NSNotificationCenter.defaultCenter().removeObserver_(observer)
            record()
            return

        batching, suppress = VARIANTS[args.variant]
        target_names = names[:800]
        def capture():
            result = {}
            for glyph in font.glyphs:
                layers = {}
                for mid in mids:
                    layer = glyph.layers[mid]; shapes = []
                    for shape in layer.shapes:
                        if isinstance(shape, GSPath):
                            shapes.append(dict(kind="path", closed=bool(shape.closed),
                                nodes=[(float(n.position.x), float(n.position.y), str(n.type)) for n in shape.nodes]))
                        else:
                            shapes.append(dict(kind="component", name=str(shape.componentName),
                                transform=list(shape.transform), automatic=bool(shape.automaticAlignment)))
                    layers[mid] = dict(width=float(layer.width), shapes=shapes,
                                       anchors=[(a.name, float(a.position.x), float(a.position.y)) for a in layer.anchors],
                                       hints=len(layer.hints), userData=dict(layer.userData))
                result[str(glyph.name)] = dict(color=glyph.color, export=bool(glyph.export), layers=layers)
            return result
        before = capture()
        def settle(harness, label):
            # No run-loop pumping during mutations. The harness's main thread
            # continues its normal event loop while this worker waits.
            until = time.monotonic() + 2
            while time.monotonic() < until:
                harness.main(scan_alerts)
                time.sleep(.05)
            event("settled", label=label)
        def exercise(harness):
            if suppress: harness.main(guard.start)
            try:
                for workload in ("colors", "shapes", "addition"):
                    params = dict(names=target_names, masters=mids, base=names[900], batching=batching,
                                  additions=["_sidebar.add"+str(i).zfill(3) for i in range(16)])
                    source = workload_source(workload)
                    targets = [dict(glyph=n, layer=mid, surface="foreground") for n in target_names for mid in mids]
                    options = dict(source=source, entrypoint="script", params=params,
                                   targets=[] if workload == "addition" else targets)
                    write_json(output.parent / (workload+"-request.json"), options)
                    workflow = harness.start(options, "sidebar-"+args.variant+"-"+workload)
                    evidence["workflows"].append(dict(workload=workload, id=workflow["id"], jobId=workflow.get("jobId")))
                    record()
                    workflow = harness.wait(workflow, "waiting_run")
                    workflow = harness.wait(harness.choose(workflow, "run_script"), "applied")
                    harness.main(lambda: verify(workload, capture(), before, names, mids, params))
                    evidence["checks"].append(workload+": exact targets and controls verified")
                    harness.choose(workflow, "finish_script")
                    record()
                settle(harness, "after-refresh-before-restoration")
            finally:
                if suppress:
                    try: harness.main(guard.restore)
                    except BaseException as error:
                        evidence["cleanupErrors"].append(str(error)); record(); raise
            settle(harness, "after-restoration")
            def check_state():
                assert flag(font, "isUpdateInterfaceEnabled") == original_ui
                assert all(flag(item, "isSuppressingCount") == old for item, old in guard.rows)
                assert [objc.pyobjc_id(item) for item in selected()] == original_selection
                assert all(str(item.predicate()) == old for item, old in predicates)
                scan_alerts()
            harness.main(check_state)
            evidence["checks"].append("UI flags, predicates, selection and responsiveness restored")
            return dict(workloads=3)
        evidence["phase"] = "workloads"; record()
        if os.environ.get("MCP_ISOLATED_GUI_SETUP"):
            result = yield from editor_workflow_steps(h, exercise)
        else:
            result = h.run(exercise)
        evidence["execution"] = result
        evidence["outcome"] = "passed" if result.get("passed") else "failed"
        NSNotificationCenter.defaultCenter().removeObserver_(observer)
    except BaseException:
        evidence["error"] = traceback.format_exc()
        if evidence["phase"] != "attach-font-view": evidence["outcome"] = "failed"
    finally:
        if guard is not None and guard.active:
            try:
                guard.restore()
            except BaseException as error:
                evidence["cleanupErrors"].append(str(error))
                evidence["outcome"] = "failed"
        if native_errors is not None:
            faulthandler.cancel_dump_traceback_later()
            native_errors.close()
        record()


def editor_workflow_steps(harness, exercise):
    """Dispatch one bridge callback per real editor-loop turn, on its UI thread."""
    done = Event()
    result = {}
    def work():
        try:
            result["data"] = exercise(harness)
            result["passed"] = True
        except BaseException:
            result["error"] = traceback.format_exc()
        finally:
            harness.service.close()
            done.set()
    Thread(target=work, daemon=True).start()
    while not done.is_set():
        try:
            callback = harness.queue.get_nowait()
        except Empty:
            pass
        else:
            callback()
        yield .001
    harness.temp.cleanup()
    result["dispatcher"] = "One native callback per real editor-loop timer turn"
    return result


_active_probes = []


def main():
    steps = qualification_steps()
    if not os.environ.get("MCP_ISOLATED_GUI_SETUP"):
        for delay in steps:
            from Foundation import NSRunLoop, NSDate
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(delay))
        return
    from Foundation import NSTimer
    # Retain the generator across callbacks; never nest the main event loop.
    state = dict(steps=steps, timer=None)
    _active_probes.append(state)
    def advance(_=None):
        try:
            delay = next(steps)
        except StopIteration:
            _active_probes.remove(state)
        except BaseException:
            setup = json.loads(Path(os.environ["MCP_ISOLATED_GUI_SETUP"]).read_text())
            Path(setup["probe"], "loader-error.txt").write_text(traceback.format_exc())
            _active_probes.remove(state)
            steps.close()
        else:
            state["timer"] = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                max(.001, delay), False, advance)
    advance()


def workload_source(kind):
    preflight = '''from GlyphsApp import GSGlyph, GSPath, GSNode, GSComponent
from sidebar_count_experiment import interface_batch
owners = []
assert len(params['names']) == len(set(params['names']))
assert all(any(str(m.id) == mid for m in font.masters) for mid in params['masters'])
for name in params['names']:
    glyph = font.glyphs[name]
    assert glyph is not None, name
    layers = []
    for mid in params['masters']:
        layer = next((l for l in glyph.layers if str(l.layerId) == mid), None)
        assert layer is not None, (name, mid)
        layers.append(layer)
    owners.append((glyph, layers))
assert font.glyphs[params['base']] is not None
'''
    operations = {
        "colors": "for glyph, layers in owners:\n    glyph.color = 4",
        "shapes": '''for index, (glyph, layers) in enumerate(owners):
    for layer in layers:
        if index % 2:
            shape = GSComponent(params['base']); shape.automaticAlignment = False
        else:
            shape = GSPath(); shape.closed = True
            for point in ((20, 0), (70, 700), (310, 100)):
                shape.nodes.append(GSNode(point))
        layer.shapes = [shape]
        layer.width = 500''',
        "addition": '''for name in params['additions']:
    glyph = GSGlyph(name, autoName=False); glyph.export = False
    font.glyphs.append(glyph)
    for mid in params['masters']:
        layer = glyph.layers[mid]
        shape = GSComponent(params['base']); shape.automaticAlignment = False
        layer.shapes = [shape]; layer.width = 500''',
    }
    if kind == "addition":
        preflight += "assert len(params['additions']) == len(set(params['additions']))\nassert all(font.glyphs[n] is None for n in params['additions'])\n"
    return preflight + "with interface_batch(font, params['batching']):\n" + "\n".join("    "+line for line in operations[kind].splitlines()) + "\n"


def verify(kind, after, before, names, mids, params):
    additions = params["additions"] if kind == "addition" else []
    assert set(after) == set(names) | set(additions)
    for name in names[800:]:
        assert after[name] == before[name], ("control changed", name)
    for index, name in enumerate(names[:800]):
        expected = dict(before[name], color=4)
        assert after[name]["color"] == 4 and after[name]["export"] == expected["export"]
        if kind == "colors":
            assert after[name] == expected, name
        else:
            for mid in mids:
                layer = after[name]["layers"][mid]
                old = before[name]["layers"][mid]
                assert {k:v for k,v in layer.items() if k != "shapes"} == {k:v for k,v in old.items() if k != "shapes"}
                assert len(layer["shapes"]) == 1
                shape = layer["shapes"][0]
                if index % 2:
                    assert shape == dict(kind="component", name=params["base"], transform=[1,0,0,1,0,0], automatic=False)
                else:
                    assert shape["kind"] == "path" and shape["closed"]
                    assert shape["nodes"] == [(20,0,"line"),(70,700,"line"),(310,100,"line")]
    for name in additions:
        assert not after[name]["export"]
        for mid in mids:
            layer = after[name]["layers"][mid]
            assert layer["width"] == 500 and layer["shapes"] == [dict(kind="component", name=params["base"], transform=[1,0,0,1,0,0], automatic=False)]


if __name__ == "__main__":
    main()
