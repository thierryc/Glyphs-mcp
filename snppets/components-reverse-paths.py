for s in font.selectedLayers:
    g = s.parent
    for l in g.layers:
        if not l.isSpecialLayer and not l.isMasterLayer:
            continue
        for i, c in enumerate(l.components):
            if i == 0:
                continue
            c.attributes['reversePaths'] = True
            c.attributes['mask'] = False

