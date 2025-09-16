.. attribute:: rightKerningKey
		The key to be used with the kerning functions (:meth:`GSFont.kerningForPair()`, :meth:`GSFont.setKerningForPair()`:meth:`GSFont.removeKerningForPair()`).

		If the glyph has a :attr:`rightKerningGroup <GSGlyph.rightKerningGroup>` attribute, the internally used `@MMK_L_xx` notation will be returned (note that the L in there stands for the left side of the kerning pair for LTR fonts, which corresponds to the right kerning group of the glyph). If no group is given, the glyph’s name will be returned.

		See above for an example.

		:type: string

		.. versionadded:: 2.4
