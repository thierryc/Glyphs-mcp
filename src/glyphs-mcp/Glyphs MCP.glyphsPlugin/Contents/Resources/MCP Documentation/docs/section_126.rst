.. function:: setKerningForPair(fontMasterId, leftKey, rightKey, value [, direction=GSLTR])

		This sets the kerning for the two specified glyphs (leftKey or rightKey is the glyph name) or a kerning group key (@MMK_X_XX).

		:param fontMasterId: The id of the FontMaster
		:type fontMasterId: str
		:param leftKey: either a glyph name or a class name
		:type leftKey: str
		:param rightKey: either a glyph name or a class name
		:type rightKey: str
		:param value: kerning value
		:type value: float
		:param direction: optional writing direction (see Constants). Default is GSLTR.
		:type direction: str

		.. code-block:: python
			# set kerning for group T and group A for currently selected master
			# ('L' = left side of the pair and 'R' = left side of the pair)
			font.setKerningForPair(font.selectedFontMaster.id, '@MMK_L_T', '@MMK_R_A', -75)
