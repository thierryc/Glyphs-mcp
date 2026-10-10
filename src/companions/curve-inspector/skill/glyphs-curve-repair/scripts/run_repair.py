"""Thin per-target V2 callback; all repair math stays in the installed engine."""
from __future__ import annotations
import json


def run(layer, params, context):
    from curve_repair import ENGINE_VERSION, RepairError
    from curve_repair.native import NativeAdapter, glyph_state, digest
    if ENGINE_VERSION != params.get("engineVersion", "0.5.0"):
        raise RepairError("engine_version_mismatch", "Installed Curve Inspector and the skill differ.")
    operation = params.get("operation", "propose")
    if operation not in ("analyze", "propose", "repair"):
        raise RepairError("invalid_operation")
    target = context.get("target", context)
    glyph = layer.parent
    font = glyph.parent
    owner = glyph.layers[target["layer"]]
    if owner is None or str(glyph.name) != target["glyph"]:
        raise RepairError("stale")
    expected = params.get("expectedFingerprint")
    if expected and digest(glyph_state(font, glyph)) != expected:
        raise RepairError("stale", "Source differs from the reviewed preview.")
    adapter = NativeAdapter(job_context=True)
    if operation == "analyze":
        result = adapter.analyze(font, owner, all_joins=bool(params.get("allJoins", False)), surface=target["surface"],
                                 joins=tuple(tuple(j) for j in params["joins"]) if "joins" in params else None)
    else:
        proposal = adapter.propose(font, owner, surface=target["surface"],
            joins=tuple(tuple(item) for item in params["joins"]) if "joins" in params else None,
            all_joins=bool(params.get("allJoins", False)), all_layers=bool(params.get("allLayers", False)),
            method=params.get("method", "native-star"), tolerance_em=float(params.get("maxDeviationEm", .001)),
            tunni_balance=bool(params.get("tunniBalance", False)), region=params.get("region"))
        result = proposal.summary()
        if operation == "repair":
            result["application"] = adapter.apply(proposal, active_font=font)
    # Respect V2's bounded text channel; compact output never omits failures.
    coverage = result.get("coverage", {})
    if "locations" in coverage:
        result["coverage"] = {key: value for key, value in coverage.items() if key != "locations"}
    diagnostics = result.get("diagnostics", [])
    result["diagnosticCount"] = len(diagnostics)
    result["diagnostics"] = diagnostics[:5]
    result["diagnosticsTruncated"] = len(diagnostics) > 5
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__" and "layer" not in globals():
    raise SystemExit("Use this helper as a per-target Glyphs MCP python_script callback.")
