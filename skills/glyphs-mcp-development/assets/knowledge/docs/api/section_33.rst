.. function:: glyphInfoForName(name, [font=None])

		Generates :class:`GSGlyphInfo` object for a given glyph name.

		:param name: Glyph name
		:param font: if you add a font, and the font has a local glyph info, it will be used instead of the global info data.
		:return: :class:`GSGlyphInfo`
