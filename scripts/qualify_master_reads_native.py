"""Plugin-free native master read gate on source-only disposable objects."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ("protocol", "bridge"):
    sys.path.insert(0, str(ROOT / "src" / name))
from GlyphsApp import Glyphs, GSFont, GSFontMaster
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError

OUT = Path(os.environ["R04_NATIVE_OUT"])
BASE = Path(os.environ["R04_BASELINE"])
expected = json.loads((BASE / "expected.json").read_text())["scopes"]
fonts = [GSFont(expected[name]["baseline"]) for name in ("core", "batch")]
unsaved = GSFont()
unsaved.masters = []
for index in range(3):
    master = GSFontMaster()
    master.id = f"opaque-native-{index}"
    master.name = "Regular"
    unsaved.masters.append(master)
fonts.append(unsaved)
adapter = GlyphsAdapter(Glyphs)
adapter._fonts = lambda: fonts
core = BridgeCore(adapter, lambda callback: callback())
checks = []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    assert condition, name


def read(doc, entities, fields=("id", "name")):
    return core.read_entities(doc, entities, list(fields))


def error(doc, entities, code):
    try:
        read(doc, entities)
    except BridgeError as exc:
        check(f"reject {entities}: {code}", exc.code == code)
    else:
        check(f"must reject {entities}", False)


try:
    docs = core.list_documents()
    values = {}
    for index, scope in enumerate(("core", "batch")):
        doc = docs[index]["id"]
        selector = {"kind": "masters", "limit": 100}
        rows = []
        while True:
            page = read(doc, [selector])[0]["values"]
            rows.extend(page["items"])
            if page["complete"]:
                break
            check("incomplete page has cursor", page["nextCursor"] is not None)
            selector["cursor"] = page["nextCursor"]
        check(scope + " native names and IDs exact", rows == expected[scope]["masters"])
        values[scope] = rows
        check(scope + " disk unchanged", hashlib.sha256(Path(expected[scope]["baseline"]).read_bytes()).hexdigest() == expected[scope]["sha256"])
    doc = docs[2]["id"]
    check("unsaved path absent", docs[2]["path"] is None)
    page = read(doc, [{"kind": "masters"}])[0]["values"]
    check("opaque IDs and duplicate names enumerate", page["items"] == [{"id": f"opaque-native-{i}", "name": "Regular"} for i in range(3)])
    for selector in ({"kind": "master"}, {"kind": "master", "id": ""}):
        error(doc, [selector], "invalid_request")
    for identity in ("Regular", "missing"):
        error(doc, [{"kind": "master", "id": "opaque-native-0"}, {"kind": "master", "id": identity}], "target_not_found")
    exact = read(doc, [{"kind": "master", "id": "opaque-native-1"}, {"kind": "master", "id": "opaque-native-0"}])
    check("opaque exact selectors resolve duplicate names", [r["values"]["id"] for r in exact] == ["opaque-native-1", "opaque-native-0"])
    first = read(docs[1]["id"], [{"kind": "masters"}])[0]["values"]
    cursor = first["nextCursor"]
    extra = GSFontMaster(); extra.id = "added-native"; fonts[1].masters.append(extra)
    error(docs[1]["id"], [{"kind": "masters", "cursor": cursor}], "stale_master_cursor")
    fonts[1].masters.remove(extra)
    prior = fonts[1].masters[99].id
    fonts[1].masters[99].id = "changed-boundary"
    error(docs[1]["id"], [{"kind": "masters", "cursor": cursor}], "stale_master_cursor")
    fonts[1].masters[99].id = prior
    check("restored boundary resumes", read(docs[1]["id"], [{"kind": "masters", "cursor": cursor}])[0]["values"]["complete"])
    check("read target unrelated core unchanged", read(docs[0]["id"], [{"kind": "masters"}])[0]["values"]["items"] == expected["core"]["masters"])
finally:
    OUT.write_text(json.dumps({"checks": checks, "passed": bool(checks) and all(c["passed"] for c in checks),
                              "host": {"version": str(Glyphs.versionString), "build": str(Glyphs.buildNumber)},
                              "scope": "native source-only objects; UI lifecycle qualified separately"}, indent=2) + "\n")
print(json.dumps({"passed": True, "checks": len(checks)}))
