.. function:: ligatureComponents(String, [font=None])

		If defined as a ligature in the glyph database, this function returns a list of glyph names that this ligature could be composed of.

		:param string: glyph name
		:param font: if you add a font, and the font has a local glyph info, it will be used instead of the global info data.
		:rtype: list

		.. code-block:: python
			print(Glyphs.ligatureComponents('allah-ar'))

			>> (
			    "alef-ar",
			    "lam-ar.init",
			    "lam-ar.medi",
			    "heh-ar.fina"
			)
