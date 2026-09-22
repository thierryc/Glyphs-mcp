"""Prepare explicit reference metadata edits on a disposable saved source."""
from glyphs_mcp_protocol import dimensions as contract


def prepare(font, request):
    options = contract.validate_options(request.get("options"))
    root = font.userData[contract.STORAGE_KEY]
    changes, rows = [], []
    for target in options["changes"]:
        identity, key, value = target["master"], target["key"], target["value"]
        try:
            master = font.masters[identity]
        except (KeyError, IndexError, TypeError):
            master = None
        if master is None or str(master.id) != identity:
            contract.fail("Dimensions master is unavailable: " + identity, "target_not_found")
        _, _, containers = contract.containers(root, identity)
        before = contract.read_state(root, identity, key)
        after = {"present": value is not None, "value": value}
        unchanged = (not before["present"] and value is None or before["present"]
                     and value is not None and contract.same_number(before["value"], value))
        status = "no-op" if unchanged else "clear" if value is None else "overwrite" if before["present"] else "fill"
        row = {"master": identity, "masterName": str(master.name), **contract.CATALOG[key],
               "before": before, "after": before if unchanged else after, "status": status}
        rows.append(row)
        if not unchanged:
            changes.append(contract.validate_change({"kind": "dimension", "master": identity, "key": key,
                            "before": before, "after": after, "containersBefore": containers}))
    return changes, {"kind": "dimensions_edit", "targets": rows, "targetCount": len(rows),
                     "changedCount": len(changes), "noChangeCount": len(rows) - len(changes),
                     "requiredOverwrites": contract.approval_entries(changes),
                     "claim": "Reference notes only. Blank fills need no approval; existing-value changes require exact conversational approval. Application never saves."}
