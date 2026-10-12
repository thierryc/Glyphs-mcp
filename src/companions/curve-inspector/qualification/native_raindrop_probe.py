"""Independent native qualification; run only on an owned disposable fixture.

Loads the engine under a private package name, never reloads the live UI or
Reporter, and edits only detached fonts. Writes a qualification record, no font.
"""
import importlib.util
import json
from pathlib import Path
import sys
import traceback
import GlyphsApp as app

if font.familyName != "Curve Inspector Repair Fixture":
    raise RuntimeError("Owned fixture required")
previous_path = list(sys.path)
try:
    root = params["sourceRoot"]
    sys.path.insert(0, root)
    pkg = "curve_repair_raindrop_qualification"
    spec = importlib.util.spec_from_file_location(pkg, root + "/curve_repair/__init__.py",
                                                submodule_search_locations=[root + "/curve_repair"])
    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = module
    spec.loader.exec_module(module)
    native = __import__(pkg + ".native", fromlist=["NativeAdapter"])
    adapter = native.NativeAdapter(job_context=True)
    provenance = __import__(pkg + ".provenance", fromlist=["record"]).record(root)
    results = []
    source_model = tuple((str(l.layerId), tuple(tuple((n.position.x, n.position.y, str(n.type), int(n.connection)) for n in p.nodes) for p in l.paths)) for l in font.glyphs["test"].layers)

    for name in ("line-curve", "curve-line", "closed-line-curve", "closed-curve-line",
                 "short-line", "multi-axis-intermediate", "conditional", "adjacent"):
        trial = font.copy()
        glyph = trial.glyphs["test"]
        reverse = name in ("curve-line", "closed-curve-line")
        closed = name.startswith("closed")
        if name == "multi-axis-intermediate":
            axis = app.GSAxis(); axis.name = "Width"; axis.axisTag = "wdth"; axis.id = "a02"
            trial.axes.append(axis)
            for i, coordinates in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                if i < 2: master = trial.masters[i]
                else:
                    master = trial.masters[0].copy(); master.id = "MASTER" + str(i)
                    master.name = "Extra " + str(i); trial.masters.append(master)
                master.internalAxesValues = list(coordinates)
                if glyph.layers[master.id] is None:
                    layer = app.GSLayer(); layer.layerId = master.id; layer.associatedMasterId = master.id
                    glyph.layers.append(layer)
            trial.instances[0].internalAxesValues = [.5, .5]
            layer = glyph.layers[trial.masters[0].id].copy()
            layer.layerId = "INTERMEDIATE"; layer.attributes["coordinates"] = {str(trial.axes[0].axisId): .5, str(trial.axes[1].axisId): .5}
            glyph.layers.append(layer)
        if name == "conditional":
            for master in trial.masters:
                layer = glyph.layers[master.id].copy(); layer.layerId = "ALTERNATE-" + master.id
                layer.attributes["axisRules"] = {str(trial.axes[0].axisId): {"min": .5}}
                glyph.layers.append(layer)
        length = .2 if name == "short-line" else 20
        for layer in glyph.layers:
            path = app.GSPath()
            points = [((-length, 0), app.LINE), ((0, 0), app.LINE), ((4, 0), app.OFFCURVE),
                      ((10, 4), app.OFFCURVE), ((20, 10), app.CURVE)]
            if name == "adjacent":
                # Two raindrops shorten opposite ends of one shared straight line.
                points = [((-20, 10), app.LINE), ((-10, 4), app.OFFCURVE), ((-4, 0), app.OFFCURVE),
                          ((0, 0), app.CURVE), ((20, 0), app.LINE), ((24, 0), app.OFFCURVE),
                          ((30, 4), app.OFFCURVE), ((40, 10), app.CURVE)]
            for xy, kind in points: path.nodes.append(app.GSNode(xy, type=kind))
            path.closed = closed
            if reverse: path.reverse()
            joins = [i for i, n in enumerate(path.nodes) if (n.position.x, n.position.y) in ((0, 0), (20, 0))]
            for i in joins: path.nodes[i].connection = app.GSSMOOTH
            layer.shapes = [path]
        owner = glyph.layers[trial.masters[0].id]
        owner.selection = [owner.paths[0].nodes[i] for i in joins]
        before = native.glyph_state(trial, glyph)
        record = {"name": name, "selectedNodesOnly": joins, "grid": float(trial.gridLength)}
        try:
            proposal = adapter.propose(trial, owner, all_layers=True)
            record["sourceUnchangedByPreview"] = native.glyph_state(trial, glyph) == before
            record["summary"] = proposal.summary()
            record["application"] = adapter.apply(proposal, active_font=trial, active_owner=owner)
            record["repeat"] = adapter.propose(trial, owner, all_layers=True).report["status"]
        except Exception as exc:
            record.update(error=str(exc), code=getattr(exc, "code", None), traceback=traceback.format_exc())
            bp = owner.paths[0].bezierPath
            record["drawing"] = [(int(bp.elementAtIndex_associatedPoints_(i)[0]), [(float(p.x), float(p.y)) for p in bp.elementAtIndex_associatedPoints_(i)[1]]) for i in range(bp.elementCount())]
            record["sourceNodes"] = [(n.position.x, n.position.y, str(n.type), int(n.connection)) for n in owner.paths[0].nodes]
        results.append(record)
    unchanged = source_model == tuple((str(l.layerId), tuple(tuple((n.position.x, n.position.y, str(n.type), int(n.connection)) for n in p.nodes) for p in l.paths)) for l in font.glyphs["test"].layers)
    record = {"engineVersion": module.ENGINE_VERSION, "engineProvenance": provenance, "host": {"version": str(Glyphs.versionString), "build": str(Glyphs.buildNumber)},
              "sourceGeometryUnchanged": unchanged, "evidence": "independent detached adapter; installed UI is a separate gate", "cases": results}
    Path(params["recordPath"]).write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps([{k: r[k] for k in ("name", "application", "repeat", "error", "code") if k in r} for r in results]))
finally:
    sys.path[:] = previous_path
    for name in tuple(sys.modules):
        if name == "curve_repair_raindrop_qualification" or name.startswith("curve_repair_raindrop_qualification."):
            del sys.modules[name]
