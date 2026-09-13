.. function:: kerningForPair(fontMasterId, leftKey, rightKey [, direction=LTR])

		This returns the kerning value for the two specified glyphs (leftKey or rightKey is the glyph name) or a kerning group key (@MMK_X_XX).

		:param fontMasterId: The id of the FontMaster
		:type fontMasterId: str
		:param leftKey: either a glyph name or a class name
		:type leftKey: str
		:param rightKey: either a glyph name or a class name
		:type rightKey: str
		:param direction: optional writing direction (see Constants; 'LTR' (0) or 'RTLTTB'). Default is LTR.
		:type direction: int
		:return: The kerning value
		:rtype: float

		.. code-block:: python
			# print(kerning between w and e for currently selected master)
			font.kerningForPair(font.selectedFontMaster.id, 'w', 'e')
			>> -15.0

			# print(kerning between group T and group A for currently selected master)
			# ('L' = left side of the pair and 'R' = left side of the pair)
			font.kerningForPair(font.selectedFontMaster.id, '@MMK_L_T', '@MMK_R_A')
			>> -75.0

			# in the same font, kerning between T and A would be zero, because they use group kerning instead.
			font.kerningForPair(font.selectedFontMaster.id, 'T', 'A')
			>> None
