"""External pair-specific correction using native effective kerning resolution."""

import math
import json

from . import collision
from .spacing import exact_copy, lookup
from .worker import WorkerError


def prepare(font, request):
    options = collision.validate_options(request.get("options", {}))
    masters = [m for m in font.masters if not options["masters"] or str(m.id) in options["masters"]]
    missing = sorted(set(options["masters"]) - {str(m.id) for m in masters})
    if missing:
        raise WorkerError("Kerning masters missing from saved source: " + json.dumps(missing, ensure_ascii=False)
                          + ". Keep the document ID; correct the exact master IDs and prepare a new job.")
    if not masters:
        raise ValueError("no kerning masters selected")
    missing = sorted({name for pair in options["pairs"] for name in pair if lookup(font.glyphs, name) is None})
    if missing:
        raise WorkerError("Kerning glyphs missing from saved source: " + json.dumps(missing, ensure_ascii=False)
                          + ". Keep the document ID; correct the pair names and prepare a new job. No document rediscovery is needed.")
    changes, rows = [], []
    for left_name, right_name in options["pairs"]:
        left, right = lookup(font.glyphs, left_name), lookup(font.glyphs, right_name)
        for master in masters:
            mid = str(master.id)
            row = {"left": left_name, "right": right_name, "master": mid, "direction": "LTR"}
            try:
                ll, rl = lookup(left.layers, mid), lookup(right.layers, mid)
                if ll is None or rl is None:
                    raise ValueError("selected master layer is unavailable")
                # Native resolution owns group/exception precedence.
                native = float(ll.nextKerningForLayer_direction_(rl, 0))
                effective = 0.0 if native > 1e12 else native
                if not math.isfinite(effective):
                    raise ValueError("native effective kerning is not finite")
                measured = collision.measure(exact_copy(ll), exact_copy(rl), effective,
                    target_gap=options["targetGap"], dense_step=options["denseStep"])
                if measured is None:
                    raise ValueError("no usable shared outline samples")
                before = font.kerningForPair(mid, left_name, right_name, direction=0)
                row.update(measurement=measured, effectiveBefore=effective, storedBefore=before,
                           groupKeys=[str(left.rightKerningKey), str(right.leftKerningKey)])
                delta = max(0.0, options["targetGap"] - measured["minGap"])
                row.update(status="suggested" if delta > 1e-9 else "unchanged", delta=delta)
                if delta > 1e-9:
                    after = effective + delta
                    # A measured pair becomes an exact exception. Changing a
                    # shared class from one representative would affect untested pairs.
                    change = {"kind": "kerning", "master": mid, "direction": "LTR",
                              "left": left_name, "right": right_name, "before": before, "after": after}
                    font.setKerningForPair(mid, left_name, right_name, after, direction=0)
                    resolved = float(ll.nextKerningForLayer_direction_(rl, 0))
                    if abs(resolved - after) > 1e-8:
                        raise ValueError("native kerning did not resolve to the proposed exception")
                    row["after"] = after
                    changes.append(change)
            except (ValueError, AttributeError) as error:
                row.update(status="unavailable", reason=str(error))
            finally:
                # The detached font must stay at its baseline between pairs.
                if row.get("delta", 0) > 1e-9:
                    if row["storedBefore"] is None:
                        font.removeKerningForPair(mid, left_name, right_name, direction=0)
                    else:
                        font.setKerningForPair(mid, left_name, right_name, row["storedBefore"], direction=0)
            rows.append(row)
    return changes, {"kind": "kerning_collision", "pairs": rows, "claim": collision.CLAIM}
