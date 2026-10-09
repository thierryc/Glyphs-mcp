.. function:: removeKerningForPair(fontMasterId, leftKey, rightKey, direction=GSLTR)

		Removes the kerning for the two specified glyphs (LeftKey or RightKey is the glyph name) or a kerning group key (@MMK_X_XX).

		:param FontMasterId: The id of the FontMaster
		:type FontMasterId: str
		:param leftKey: either a glyph name or a class name
		:type leftKey: str
		:param rightKey: either a glyph name or a class name
		:type rightKey: str
		:param direction: optional writing direction (see Constants; 'GSLTR' (0) or 'GSVertical'). Default is GSLTR. (added in 2.6.6)
		:type direction: int

		.. code-block:: python
			# remove kerning for group T and group A for all masters
			# ('L' = left side of the pair and 'R' = left side of the pair)
			for master in font.masters:
			    font.removeKerningForPair(master.id, '@MMK_L_T', '@MMK_R_A')
