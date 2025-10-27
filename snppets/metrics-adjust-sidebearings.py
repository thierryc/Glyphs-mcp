delta = 10  # change to desired value, negative to tighten
for sl in font.selectedLayers:
    sl.LSB = sl.LSB + delta
    sl.RSB = sl.RSB + delta

