.. attribute:: kerning
		Kerning for LTR writing
		A multi-level dictionary. The first level’s key is the :attr:`GSFontMaster.id` (each master has its own kerning), the second level’s key is the :attr:`GSGlyph.id` or class id (@MMK_L_XX) of the first glyph, the third level’s key is a glyph id or class id (@MMK_R_XX) for the second glyph. The values are the actual kerning values.

		To set a value, it is better to use the method :meth:`GSFont.setKerningForPair()`. This ensures a better data integrity (and is faster).

		:type: dict
