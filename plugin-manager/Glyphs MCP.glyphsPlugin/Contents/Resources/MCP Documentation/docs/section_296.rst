.. attribute:: selected
		Return True if the Glyph is selected in the Font View.
		This is different to the property font.selectedLayers which returns the selection from the active tab.

		:type: bool

		.. code-block:: python
			# access all selected glyphs in the Font View
			for glyph in font.glyphs:
			    if glyph.selected:
			        print(glyph)
