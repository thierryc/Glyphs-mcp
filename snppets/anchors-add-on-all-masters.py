anchor_name = 'top'
for sl in font.selectedLayers:
    glyph = sl.parent
    # Try to use current layer's anchor position as reference
    ref_anchor = sl.anchors[anchor_name] if anchor_name in [a.name for a in sl.anchors] else None
    ref = ref_anchor.position if ref_anchor else None
    for m in font.masters:
        layer = glyph.layers[m.id]
        if ref is not None:
            pos = (ref.x, ref.y) if hasattr(ref, 'x') else tuple(ref)
        else:
            # Fallback: center x, top of bounds y
            try:
                b = layer.bounds
                x = layer.width/2
                y = b.origin.y + b.size.height
                pos = (x, y)
            except Exception:
                pos = (layer.width/2, 600)
        anchor = GSAnchor(anchor_name, pos)
        layer.anchors.append(anchor)

