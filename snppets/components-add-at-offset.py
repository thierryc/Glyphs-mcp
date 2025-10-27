component_name = 'acute'
ox, oy = 0, 120
for sl in font.selectedLayers:
    c = GSComponent(component_name)
    c.position = (ox, oy)
    sl.components.append(c)

