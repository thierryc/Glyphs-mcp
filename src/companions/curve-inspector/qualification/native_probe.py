"""Run as a V2 whole-script job on the disposable named fixture only.

This proves adapter behavior independently of installed Reporter/UI code.
It never imports or reloads the live Reporter and never saves the fixture.
"""
import json
import sys
import traceback
import importlib

if font.familyName != "Curve Inspector Repair Fixture":
    raise RuntimeError("Native qualification requires the owned disposable fixture.")

source_root = params["sourceRoot"]
previous_path = list(sys.path)
sys.path.insert(0, source_root)
try:
    import GlyphsApp as app
    # Independent helper iteration only; never reload the live Reporter/UI.
    for name in ("curve_repair.coverage", "curve_repair.supertool", "curve_repair.outline", "curve_repair.native"):
        importlib.reload(importlib.import_module(name))
    from curve_repair.native import NativeAdapter, glyph_state, position, precision
    from curve_repair import ENGINE_VERSION
    adapter = NativeAdapter(job_context=True)
    glyph = font.glyphs["test"]
    owner = glyph.layers[font.masters[0].id]
    results = {"engineVersion": ENGINE_VERSION,
               "hostVersion": str(Glyphs.versionString), "hostBuild": str(Glyphs.buildNumber),
               "constants": {"sharp": app.GSSHARP, "smooth": app.GSSMOOTH, "star": app.GSSUPERSMOOTH},
               "masters": [str(m.id) for m in font.masters],
               "axes": [list(m.internalAxesValues) for m in font.masters],
               "nodes": [{"type": str(n.type), "connection": int(n.connection), "position": position(n)} for n in owner.paths[0].nodes]}
    primitive = owner.paths[0].primitiveRepresentation()
    results["primitiveType"] = type(primitive).__name__
    state = glyph_state(font, glyph)
    for method in ("native-star", "supertool-handles"):
        try:
            proposal = adapter.propose(font, owner, joins=((0, 3),), all_layers=True, method=method)
            summary = proposal.summary()
            results[method] = {key: summary[key] for key in (
                "status", "editCount", "storedCoordinatesPreserved", "maxMeasuredDeviationEm", "maxEffectiveJoinMovementEm")}
            results[method]["coverage"] = proposal.report["coverage"]
            if params.get("verifyApplication"):
                results[method]["application"] = adapter.apply(proposal, active_font=font, active_owner=owner)
                # Reset only this fixture's invocation-owned edits; verify exact
                # restoration independently of the V2 whole-font offer.
                identifiers = sorted({edit.layer_id for edit in proposal.edits})
                for identifier in identifiers:
                    layer = glyph.layers[identifier]
                    with precision(layer, method == "supertool-handles"):
                        for edit in proposal.edits:
                            if edit.layer_id != identifier: continue
                            node = layer.paths[edit.path].nodes[edit.node]
                            if edit.before_position != edit.after_position: node.position = edit.before_position
                            if edit.before_connection != edit.after_connection: node.setConnection_(edit.before_connection)
                if glyph_state(font, glyph) != state: raise RuntimeError("Fixture reset failed")
                results[method]["fixtureResetVerified"] = True
        except Exception as exc:
            results[method] = {"error": str(exc), "type": type(exc).__name__, "traceback": traceback.format_exc()}
    results["sourceGeometryUnchanged"] = glyph_state(font, glyph) == state
    print(json.dumps(results, sort_keys=True))
finally:
    sys.path[:] = previous_path
