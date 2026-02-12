# Glyphs Font Factory — AGENTS.md

This repository is a scaffold to create a new font **from scratch** in Glyphs using the **Glyphs MCP server**.

## Hard Rules (non-negotiable)

1. Use the Glyphs MCP server for all font creation/modification.
   - Prefer `mcp__glyphs-mcp-server__execute_code` for bulk generation.
2. Do **not** edit `.glyphs` / `.glyphspackage` files directly.
   - No patching, no parsing, no rewriting the source file on disk.
   - The only valid way to create/update a `.glyphs` source is:
     - Build the font in memory via GlyphsApp (`GSFont`, `GSFontMaster`, `GSGlyph`, etc.)
     - Save via `font.save(path=...)` inside Glyphs.app
3. Store sources in `sources/` and exports in `exports/`.

## Trigger Phrase

If the user says “create a new variable font” (or similar), follow this file verbatim.

## Interactive Setup Interview (ask before running any code)

Use `fontfactory.defaults.json` as defaults. Ask and record answers:

1. `FAMILY_NAME`
2. `OUTPUT_GLYPHS_PATH`
   - Default: `sources/<FAMILY_NAME>.glyphs`
   - Use an absolute path in the final `CONFIG` (do not rely on the Glyphs process working directory).
3. Spacing
   - Proportional or monospace?
   - If monospace: `MONO_WIDTH` (default 600)
4. Metrics (accept defaults or override)
   - `UPM` (default 1000)
   - `ASCENDER` (default 800)
   - `CAP_HEIGHT` (default 700)
   - `X_HEIGHT` (default 500)
   - `DESCENDER` (default -200)
5. Axis count (**must be the first VF decision**)
   - Ask: “How many axes: 1 or 2?”
6. If `AXES=1`
   - Axis tag (default `wght`)
   - Packaging: “1 VF (roman only) or 2 VFs (roman + italic as separate files)?”
     - If 2 VFs: you will run the generator twice with different master lists + output paths.
7. If `AXES=2`
   - Choose:
     - `wght + ital` (recommended; ital is discrete 0/1)
     - `wght + slnt` (ok for oblique-compatible designs; slnt continuous)
     - `wght + wdth` (warning: requires extra width masters; do not proceed unless user explicitly accepts placeholder masters)
8. Masters and coordinates
   - Provide a master list and axis coordinates per master.
   - Defaults (if unsure): use `axis_presets.two_axes_wght_ital`.
9. Glyph coverage preset
   - Default: `latinext_essentials`
10. Feature preset
   - Default: `minimal`
11. Confirmation gate
   - Print a config summary.
   - Require an explicit “yes” to proceed.

After the interview, write a run snapshot JSON to:
- `fontfactory-runs/<timestamp>-<FAMILY_NAME>.json`

This file is allowed to be written normally. Only `.glyphs` sources are “MCP-only writes”.

## Generator (run via `mcp__glyphs-mcp-server__execute_code`)

Paste this into an MCP `execute_code` call. Before running, fill `CONFIG` from the interview.

```python
import os
import json
import time
import unicodedata

import GlyphsApp
from GlyphsApp import Glyphs, GSAnchor, GSAxis, GSComponent, GSFeature, GSFont, GSFontMaster, GSGlyph


# Fill this dict from the interview before running.
CONFIG = {
    "family_name": "MyFamily",
    # IMPORTANT: set an absolute path (do not rely on the Glyphs process working directory).
    "output_path": "/ABS/PATH/TO/THIS_REPO/sources/MyFamily.glyphs",
    "metrics": {
        "upm": 1000,
        "ascender": 800,
        "capHeight": 700,
        "xHeight": 500,
        "descender": -200,
    },
    "spacing": {
        "isMonospace": False,
        "monoWidth": 600,
        "defaultWidth": 600,
    },
    # Axes order matters: master.axes[index] maps to axes[index].
    "axes": [
        {"tag": "wght", "name": "Weight"},
        {"tag": "ital", "name": "Italic"},
    ],
    # One dict per master.
    # axis coords must include all axis tags in CONFIG["axes"].
    "masters": [
        {"name": "Light", "italicAngle": 0, "axes": {"wght": 300, "ital": 0}},
        {"name": "Heavy", "italicAngle": 0, "axes": {"wght": 900, "ital": 0}},
        {"name": "Light Italic", "italicAngle": -10, "axes": {"wght": 300, "ital": 1}},
        {"name": "Heavy Italic", "italicAngle": -10, "axes": {"wght": 900, "ital": 1}},
    ],
    "glyphset": {
        "unicodeRanges": ["0020-007E", "00A0-00FF", "0100-017F", "0180-024F", "1E00-1EFF"],
        "includeUnicode": [
            "00AD",
            "2010",
            "2013",
            "2014",
            "2018-201F",
            "2020",
            "2021",
            "2022",
            "2026",
            "2030",
            "2039",
            "203A",
            "2044",
            "20AC",
            "20BF",
            "20BD",
            "20BA",
            "2212",
        ],
        # Nonspacing combining marks (encoded). Keep these exportable by default.
        "combiningMarksUnicode": [
            "0300",
            "0301",
            "0302",
            "0303",
            "0304",
            "0306",
            "0307",
            "0308",
            "030A",
            "030B",
            "030C",
            "0323",
            "0327",
            "0328",
            "0309",
            "0311",
            "031B",
        ],
    },
    "features": {
        "automatic": ["mark", "mkmk", "kern"],
        "stubs": [],
    },
    "colors": {
        "roots_color_1": ["n", "o", "t", "H", "O", "i", "l", "a", "e", "p", "d", "zero", "one", "acutecomb", "gravecomb"],
        "derived_color_2": [],
        "fallback_color": 3,
    },
}


def die(msg):
    raise RuntimeError(msg)


def uhex(cp):
    return ("%04X" % cp) if cp <= 0xFFFF else ("%06X" % cp)


def parse_hex_token(tok):
    tok = tok.strip().upper()
    if not tok:
        return []
    if "-" in tok:
        a, b = tok.split("-", 1)
        lo = int(a, 16)
        hi = int(b, 16)
        if hi < lo:
            die("Bad range: %s" % tok)
        return list(range(lo, hi + 1))
    return [int(tok, 16)]


def expand_specs(specs):
    cps = []
    for s in specs:
        cps.extend(parse_hex_token(s))
    # unique, stable order
    seen = set()
    out = []
    for cp in cps:
        if cp in seen:
            continue
        seen.add(cp)
        out.append(cp)
    return out


def glyph_name_for_unicode(font, u):
    info = GlyphsApp._glyphInfoForUnicode(Glyphs, u, font)
    return info.name if info and getattr(info, "name", None) else ("uni" + u)


def ensure_glyph_by_unicode(font, cp):
    u = uhex(cp)
    name = glyph_name_for_unicode(font, u)
    g = font.glyphs[name]
    if not g:
        g = GSGlyph(name)
        font.glyphs.append(g)
    g.unicode = u
    g.export = True
    return g


def ensure_glyph_by_name(font, name, export=True):
    g = font.glyphs[name]
    if not g:
        g = GSGlyph(name)
        font.glyphs.append(g)
    g.export = bool(export)
    return g


def layer_for(glyph, master_id):
    return glyph.layers[master_id]


def set_layer_width_all_masters(glyph, masters, width):
    for m in masters:
        layer_for(glyph, m.id).width = float(width)


def ensure_anchor(layer, name, x, y):
    # Glyphs anchors collection behaves like a dict in most builds.
    try:
        existing = layer.anchors[name]
    except Exception:
        existing = None
        for a in list(layer.anchors):
            if getattr(a, "name", None) == name:
                existing = a
                break
    if existing:
        existing.position = (float(x), float(y))
        return existing
    a = GSAnchor(name, (float(x), float(y)))
    layer.anchors.append(a)
    return a


def default_width():
    sp = CONFIG.get("spacing", {})
    if sp.get("isMonospace"):
        return float(sp.get("monoWidth", 600))
    return float(sp.get("defaultWidth", 600))


def base_anchor_y_for_cp(cp):
    ch = chr(cp)
    cat = unicodedata.category(ch)
    m = CONFIG["metrics"]
    if cat.startswith("L"):
        # crude uppercase test: Unicode upper differs
        if ch == ch.upper() and ch != ch.lower():
            return float(m["capHeight"])
        return float(m["xHeight"])
    return float(m["xHeight"])


def ensure_base_anchors(font, glyph, cp, masters):
    # Add default top/bottom anchors for letters (placeholders until outlines exist).
    ch = chr(cp)
    if not unicodedata.category(ch).startswith("L"):
        return
    for m in masters:
        layer = layer_for(glyph, m.id)
        w = layer.width or default_width()
        cx = w * 0.5
        top_y = base_anchor_y_for_cp(cp)
        ensure_anchor(layer, "top", cx, top_y)
        ensure_anchor(layer, "bottom", cx, 0)
        # Optional anchors used by some marks.
        ensure_anchor(layer, "ogonek", w * 0.9, 0)
        ensure_anchor(layer, "horn", w * 0.75, top_y)


def mark_attach_kind(mark_cp):
    # Decide anchor family for this combining mark.
    # Special cases first.
    if mark_cp == 0x0328:  # ogonekcomb
        return ("ogonek", "_ogonek")
    if mark_cp == 0x031B:  # horncomb
        return ("horn", "_horn")
    ccc = unicodedata.combining(chr(mark_cp))
    # Most below marks: ccc < 230 (and nonzero)
    if ccc and ccc < 230:
        return ("bottom", "_bottom")
    return ("top", "_top")


def ensure_mark_anchors(font, mark_glyph, mark_cp, masters):
    # Marks are nonspacing by default in this scaffold.
    for m in masters:
        layer = layer_for(mark_glyph, m.id)
        layer.width = 0
        # Default underscore anchors at origin; stacking anchors separated by 200 units.
        base_name, undersc = mark_attach_kind(mark_cp)
        if undersc == "_top":
            ensure_anchor(layer, "_top", 0, 0)
            ensure_anchor(layer, "top", 0, 200)
        elif undersc == "_bottom":
            ensure_anchor(layer, "_bottom", 0, 0)
            ensure_anchor(layer, "bottom", 0, -200)
        elif undersc == "_ogonek":
            ensure_anchor(layer, "_ogonek", 0, 0)
            ensure_anchor(layer, "ogonek", 0, -200)
        elif undersc == "_horn":
            ensure_anchor(layer, "_horn", 0, 0)
            ensure_anchor(layer, "horn", 0, 200)


def clear_layer_shapes(layer):
    # Clears paths + components reliably in Glyphs 3.
    if hasattr(layer, "shapes"):
        layer.shapes = []
    else:
        for c in list(layer.components):
            try:
                layer.components.remove(c)
            except Exception:
                pass
        for p in list(layer.paths):
            try:
                layer.paths.remove(p)
            except Exception:
                pass


def anchor_pos(layer, name):
    try:
        a = layer.anchors[name]
        return a.position if a else None
    except Exception:
        for it in list(layer.anchors):
            if getattr(it, "name", None) == name:
                return it.position
    return None


def add_component(layer, name, automatic, dx, dy):
    c = GSComponent(name)
    c.automaticAlignment = bool(automatic)
    c.position = (float(dx), float(dy))
    layer.components.append(c)
    return c


def dotless_base_name(base_cp, mark_cps):
    # If base is i/j and it has any combining mark, prefer dotlessi/dotlessj.
    # This is a sane default for Latin fonts.
    if base_cp == ord("i") and mark_cps:
        return "dotlessi", 0x0131
    if base_cp == ord("j") and mark_cps:
        return "dotlessj", 0x0237
    return None, None


def compose_from_nfd(font, target_glyph, target_cp, masters, combining_set):
    ch = chr(target_cp)
    nfd = unicodedata.normalize("NFD", ch)
    if not nfd or len(nfd) == 1:
        return False
    base_cp = ord(nfd[0])
    mark_cps = [ord(c) for c in nfd[1:] if ord(c) in combining_set]
    if not mark_cps:
        return False

    # ensure base glyph exists
    special_name, special_cp = dotless_base_name(base_cp, mark_cps)
    if special_name:
        base_g = ensure_glyph_by_unicode(font, special_cp)
    else:
        base_g = ensure_glyph_by_unicode(font, base_cp)

    # ensure marks exist
    mark_glyphs = []
    for mcp in mark_cps:
        mg = ensure_glyph_by_unicode(font, mcp)
        mark_glyphs.append((mcp, mg))

    # compose per master
    for m in masters:
        layer = layer_for(target_glyph, m.id)
        clear_layer_shapes(layer)
        layer.width = layer_for(base_g, m.id).width or default_width()

        add_component(layer, base_g.name, False, 0, 0)

        # attach one above-chain and one below-chain; ogonek/horn attach to base.
        last_above = None
        last_below = None
        for mcp, mg in mark_glyphs:
            base_name, undersc = mark_attach_kind(mcp)
            mark_layer = layer_for(mg, m.id)

            if undersc in ("_ogonek", "_horn"):
                base_layer_for_attach = layer_for(base_g, m.id)
                base_anchor_name = base_name
            else:
                # Split above vs below chains.
                if undersc == "_top":
                    base_layer_for_attach = layer_for(last_above, m.id) if last_above else layer_for(base_g, m.id)
                    base_anchor_name = "top" if not last_above else "top"
                else:
                    base_layer_for_attach = layer_for(last_below, m.id) if last_below else layer_for(base_g, m.id)
                    base_anchor_name = "bottom" if not last_below else "bottom"

            base_anchor = anchor_pos(base_layer_for_attach, base_anchor_name) if base_layer_for_attach else None
            mark_anchor = anchor_pos(mark_layer, undersc)

            if base_anchor is not None and mark_anchor is not None:
                dx = base_anchor.x - mark_anchor.x
                dy = base_anchor.y - mark_anchor.y
                add_component(layer, mg.name, True, dx, dy)
            else:
                add_component(layer, mg.name, False, 0, 0)

            # update chains only for top/bottom marks
            if undersc == "_top":
                last_above = mg
            elif undersc == "_bottom":
                last_below = mg

    return True


def ensure_feature(font, tag, automatic=True, code=None):
    # Replace-or-create by name.
    for f in list(font.features):
        if getattr(f, "name", None) == tag:
            f.automatic = bool(automatic)
            if code is not None and not automatic:
                f.code = code
            return f
    feat = GSFeature(tag)
    feat.automatic = bool(automatic)
    if code is not None and not automatic:
        feat.code = code
    font.features.append(feat)
    return feat


def is_composite_only(glyph, masters):
    for m in masters:
        layer = layer_for(glyph, m.id)
        if len(layer.paths) != 0:
            return False
        if len(layer.components) == 0:
            return False
    return True


def apply_colors(font, masters):
    colors = CONFIG.get("colors", {})
    roots = set(colors.get("roots_color_1", []))
    derived2 = set(colors.get("derived_color_2", []))
    fallback = int(colors.get("fallback_color", 3))

    if not derived2:
        # Auto-fill color 2 with Basic Latin + Latin-1 as "next to draw".
        for g in list(font.glyphs):
            if not getattr(g, "unicode", None):
                continue
            try:
                cp = int(str(g.unicode), 16)
            except Exception:
                continue
            if (0x0020 <= cp <= 0x007E) or (0x00A0 <= cp <= 0x00FF):
                derived2.add(g.name)

    for g in list(font.glyphs):
        if is_composite_only(g, masters):
            g.color = -1
            continue
        if g.name in roots:
            g.color = 1
        elif g.name in derived2:
            g.color = 2
        else:
            g.color = fallback


def main():
    out_path = str(CONFIG["output_path"]).strip()
    if not os.path.isabs(out_path):
        die('CONFIG["output_path"] must be an absolute path. Got: %r' % out_path)
    out_dir = os.path.dirname(out_path)
    if not os.path.isdir(out_dir):
        die("Output directory does not exist: %s" % out_dir)

    font = GSFont()
    font.familyName = CONFIG["family_name"]

    # Metrics
    m = CONFIG["metrics"]
    font.upm = int(m["upm"])

    # Spacing
    sp = CONFIG.get("spacing", {})
    font.isFixedPitch = 1 if sp.get("isMonospace") else 0

    # Axes
    # Clear any axes (new font starts empty, but keep this robust).
    try:
        while len(font.axes):
            font.axes.remove(font.axes[0])
    except Exception:
        pass

    axes = CONFIG["axes"]
    axis_tags = []
    for ax in axes:
        a = GSAxis()
        a.axisTag = ax["tag"]
        a.name = ax["name"]
        font.axes.append(a)
        axis_tags.append(ax["tag"])

    # Masters
    master_defs = CONFIG["masters"]
    if not master_defs:
        die("No masters defined.")

    # Reuse the default master for the first definition.
    masters = list(font.masters)
    if not masters:
        die("GSFont has no default master; unexpected.")
    # Remove any extra default masters (should be 1).
    while len(font.masters) > 1:
        font.masters.remove(font.masters[-1])

    def apply_master_def(master, d):
        master.name = d["name"]
        master.italicAngle = float(d.get("italicAngle", 0))
        master.ascender = float(m["ascender"])
        master.descender = float(m["descender"])
        master.xHeight = float(m["xHeight"])
        master.capHeight = float(m["capHeight"])
        # axis coords
        coords = d.get("axes", {})
        for i, tag in enumerate(axis_tags):
            if tag not in coords:
                die("Master %s missing axis coord for %s" % (d["name"], tag))
            master.axes[i] = float(coords[tag])

    apply_master_def(font.masters[0], master_defs[0])
    for d in master_defs[1:]:
        mm = GSFontMaster()
        apply_master_def(mm, d)
        font.masters.append(mm)

    masters = list(font.masters)

    # Basic required glyphs
    ensure_glyph_by_name(font, ".notdef", export=True)
    ensure_glyph_by_name(font, ".null", export=True)
    ensure_glyph_by_name(font, "nonmarkingreturn", export=True)

    # Glyph coverage
    gs = CONFIG["glyphset"]
    base_cps = []
    for r in gs.get("unicodeRanges", []):
        base_cps.extend(expand_specs([r]))
    include_cps = expand_specs(gs.get("includeUnicode", []))
    combining_cps = expand_specs(gs.get("combiningMarksUnicode", []))
    combining_set = set(combining_cps)

    target_cps = []
    for cp in base_cps + include_cps + combining_cps:
        if cp not in target_cps:
            target_cps.append(cp)

    # Create glyphs and set placeholder widths
    w = default_width()
    for cp in target_cps:
        g = ensure_glyph_by_unicode(font, cp)
        if cp in combining_set:
            # Mark glyphs: width 0, anchors created below
            for mm in masters:
                layer_for(g, mm.id).width = 0
        else:
            set_layer_width_all_masters(g, masters, w)

    # Marks: anchors + width=0
    for cp in combining_cps:
        mg = ensure_glyph_by_unicode(font, cp)
        ensure_mark_anchors(font, mg, cp, masters)

    # Bases: anchors
    for cp in target_cps:
        if cp in combining_set:
            continue
        g = ensure_glyph_by_unicode(font, cp)
        ensure_base_anchors(font, g, cp, masters)

    # Compose decomposable glyphs
    composed = 0
    for cp in target_cps:
        if cp in combining_set:
            continue
        g = ensure_glyph_by_unicode(font, cp)
        if compose_from_nfd(font, g, cp, masters, combining_set):
            composed += 1

    # Features
    feats = CONFIG.get("features", {})
    for tag in feats.get("automatic", []):
        ensure_feature(font, tag, automatic=True)
    for tag in feats.get("stubs", []):
        # keep stubs non-automatic with empty code so it is visible and editable.
        ensure_feature(font, tag, automatic=False, code="")

    # Colors (do not color composites)
    apply_colors(font, masters)

    # Save + open
    font.save(path=out_path)
    try:
        # Make it visible in UI.
        Glyphs.fonts.append(font)
        Glyphs.font = font
    except Exception:
        pass

    print("Saved:", out_path)
    print("Masters:", [m.name for m in masters])
    print("Axes:", axis_tags)
    print("Glyphs:", len(list(font.glyphs)))
    print("ComposedByNFD:", composed)


main()
```

## Post-drawing Rebuild (run after you draw roots; `mcp__glyphs-mcp-server__execute_code`)

This script re-centers anchors from real outline bounds and rebuilds decomposable composites idempotently.
It expects the generated font to be the active font in Glyphs.

```python
import unicodedata

import GlyphsApp
from GlyphsApp import Glyphs, GSComponent


def layer_signature_is_composite_only(layer):
    return len(layer.paths) == 0 and len(layer.components) > 0


def clear_layer_shapes(layer):
    if hasattr(layer, "shapes"):
        layer.shapes = []
    else:
        for c in list(layer.components):
            try:
                layer.components.remove(c)
            except Exception:
                pass
        for p in list(layer.paths):
            try:
                layer.paths.remove(p)
            except Exception:
                pass


def ensure_anchor(layer, name, x, y):
    try:
        a = layer.anchors[name]
        if a:
            a.position = (float(x), float(y))
            return a
    except Exception:
        pass
    a = GlyphsApp.GSAnchor(name, (float(x), float(y)))
    layer.anchors.append(a)
    return a


def anchor_pos(layer, name):
    try:
        a = layer.anchors[name]
        return a.position if a else None
    except Exception:
        for it in list(layer.anchors):
            if getattr(it, "name", None) == name:
                return it.position
    return None


def mark_attach_kind(mark_cp):
    if mark_cp == 0x0328:
        return ("ogonek", "_ogonek")
    if mark_cp == 0x031B:
        return ("horn", "_horn")
    ccc = unicodedata.combining(chr(mark_cp))
    if ccc and ccc < 230:
        return ("bottom", "_bottom")
    return ("top", "_top")


def add_component(layer, name, automatic, dx, dy):
    c = GSComponent(name)
    c.automaticAlignment = bool(automatic)
    c.position = (float(dx), float(dy))
    layer.components.append(c)
    return c


def dotless_base_name(base_cp, mark_cps):
    if base_cp == ord("i") and mark_cps:
        return "dotlessi"
    if base_cp == ord("j") and mark_cps:
        return "dotlessj"
    return None


font = Glyphs.font
if not font:
    raise RuntimeError("No font open.")

masters = list(font.masters)

# Build combining mark set present in font (encoded Mn in U+0300..U+036F).
combining_set = set()
unicode_to_glyph = {}
for g in font.glyphs:
    if not g.unicode:
        continue
    cp = int(str(g.unicode), 16)
    unicode_to_glyph[cp] = g
    if 0x0300 <= cp <= 0x036F:
        combining_set.add(cp)

# 0) Recenter mark anchors (underscore anchors x=center bounds, y=0; stacking anchors y=bounds top/bottom).
for g in font.glyphs:
    if not g.unicode or not g.export:
        continue
    cp = int(str(g.unicode), 16)
    if cp not in combining_set:
        continue
    for m in masters:
        layer = g.layers[m.id]
        if len(layer.paths) == 0:
            continue
        b = layer.bounds
        cx = b.origin.x + b.size.width * 0.5
        base_name, undersc = mark_attach_kind(cp)
        if undersc == "_top":
            ensure_anchor(layer, "_top", cx, 0)
            ensure_anchor(layer, "top", cx, b.origin.y + b.size.height)
        elif undersc == "_bottom":
            ensure_anchor(layer, "_bottom", cx, 0)
            ensure_anchor(layer, "bottom", cx, b.origin.y)
        elif undersc == "_ogonek":
            ensure_anchor(layer, "_ogonek", cx, 0)
            ensure_anchor(layer, "ogonek", cx, b.origin.y)
        elif undersc == "_horn":
            ensure_anchor(layer, "_horn", cx, 0)
            ensure_anchor(layer, "horn", cx, b.origin.y + b.size.height)

# 1) Recenter anchors on drawn base glyphs from bounds (keeps y at metrics).
for g in font.glyphs:
    if not g.unicode or not g.export:
        continue
    cp = int(str(g.unicode), 16)
    ch = chr(cp)
    if not unicodedata.category(ch).startswith("L"):
        continue

    for m in masters:
        layer = g.layers[m.id]
        if len(layer.paths) == 0:
            continue
        b = layer.bounds
        cx = b.origin.x + b.size.width * 0.5
        top_y = m.capHeight if (ch == ch.upper() and ch != ch.lower()) else m.xHeight
        ensure_anchor(layer, "top", cx, top_y)
        ensure_anchor(layer, "bottom", cx, 0)
        ensure_anchor(layer, "ogonek", layer.width * 0.9, 0)
        ensure_anchor(layer, "horn", layer.width * 0.75, top_y)

# 2) Rebuild decomposable composites.
for g in font.glyphs:
    if not g.unicode or not g.export:
        continue
    cp = int(str(g.unicode), 16)
    if cp in combining_set:
        continue
    ch = chr(cp)
    nfd = unicodedata.normalize("NFD", ch)
    if not nfd or len(nfd) == 1:
        continue
    base_cp = ord(nfd[0])
    mark_cps = [ord(c) for c in nfd[1:] if ord(c) in combining_set]
    if not mark_cps:
        continue

    base_name_override = dotless_base_name(base_cp, mark_cps)
    if base_name_override and font.glyphs[base_name_override]:
        base_g = font.glyphs[base_name_override]
    else:
        base_g = unicode_to_glyph.get(base_cp)
    if not base_g:
        continue

    mark_glyphs = []
    for mcp in mark_cps:
        mg = unicode_to_glyph.get(mcp)
        if mg:
            mark_glyphs.append((mcp, mg))

    for m in masters:
        layer = g.layers[m.id]
        clear_layer_shapes(layer)
        layer.width = base_g.layers[m.id].width
        add_component(layer, base_g.name, False, 0, 0)

        last_above = None
        last_below = None
        for mcp, mg in mark_glyphs:
            base_name, undersc = mark_attach_kind(mcp)
            mark_layer = mg.layers[m.id]
            if undersc in ("_ogonek", "_horn"):
                base_layer_for_attach = base_g.layers[m.id]
                base_anchor_name = base_name
            else:
                if undersc == "_top":
                    base_layer_for_attach = (last_above.layers[m.id] if last_above else base_g.layers[m.id])
                    base_anchor_name = "top"
                else:
                    base_layer_for_attach = (last_below.layers[m.id] if last_below else base_g.layers[m.id])
                    base_anchor_name = "bottom"

            base_anchor = anchor_pos(base_layer_for_attach, base_anchor_name)
            mark_anchor = anchor_pos(mark_layer, undersc)
            if base_anchor and mark_anchor:
                dx = base_anchor.x - mark_anchor.x
                dy = base_anchor.y - mark_anchor.y
                add_component(layer, mg.name, True, dx, dy)
            else:
                add_component(layer, mg.name, False, 0, 0)

            if undersc == "_top":
                last_above = mg
            elif undersc == "_bottom":
                last_below = mg

print("Rebuild done.")
```

## QA (short; `mcp__glyphs-mcp-server__execute_code`)

```python
import unicodedata
from GlyphsApp import Glyphs

font = Glyphs.font
if not font:
    raise RuntimeError("No font open.")

masters = list(font.masters)

def is_composite_only(g):
    for m in masters:
        layer = g.layers[m.id]
        if len(layer.paths) != 0:
            return False
        if len(layer.components) == 0:
            return False
    return True

bad_colored_composites = []
roots_to_draw = []
mark_width_errors = []
missing_anchor_bases = []

for g in font.glyphs:
    if not getattr(g, "export", True):
        continue
    # composites should be uncolored
    if is_composite_only(g) and getattr(g, "color", -1) != -1:
        bad_colored_composites.append(g.name)
    # report empty roots
    if not is_composite_only(g):
        empty_all = True
        for m in masters:
            layer = g.layers[m.id]
            if len(layer.paths) > 0:
                empty_all = False
                break
        if empty_all and g.unicode:
            roots_to_draw.append(g.name)
    # check combining marks widths
    if g.unicode:
        cp = int(str(g.unicode), 16)
        if 0x0300 <= cp <= 0x036F:
            for m in masters:
                if g.layers[m.id].width != 0:
                    mark_width_errors.append((g.name, m.name, g.layers[m.id].width))
                    break
    # base anchor sanity for letters
    if g.unicode:
        cp = int(str(g.unicode), 16)
        ch = chr(cp)
        if unicodedata.category(ch).startswith("L"):
            for m in masters:
                layer = g.layers[m.id]
                if not layer.anchors or not (layer.anchors["top"] and layer.anchors["bottom"]):
                    missing_anchor_bases.append((g.name, m.name))
                    break

print("Family:", font.familyName)
print("Masters:", [m.name for m in masters])
print("Axes:", [(a.axisTag, a.name) for a in getattr(font, \"axes\", [])])
print("Exported glyphs:", len([gg for gg in font.glyphs if getattr(gg, \"export\", True)]))
print("Bad colored composites:", len(bad_colored_composites))
if bad_colored_composites:
    print("  sample:", bad_colored_composites[:20])
print("Combining mark width errors:", len(mark_width_errors))
if mark_width_errors:
    print("  sample:", mark_width_errors[:10])
print("Missing base anchors:", len(missing_anchor_bases))
if missing_anchor_bases:
    print("  sample:", missing_anchor_bases[:10])
print("Roots to draw (encoded, empty):", len(roots_to_draw))
print("  sample:", roots_to_draw[:40])
```
