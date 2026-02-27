.. attribute:: glyphs
		Collection of :class:`GSGlyph` objects. Returns a list, but you may also call glyphs using index or glyph name or character as key.

		:type: list, dict

		.. code-block:: python
			# Access all glyphs
			for glyph in font.glyphs:
			    print(glyph)
			>> <GSGlyph "A" with 4 layers>
			>> <GSGlyph "B" with 4 layers>
			>> <GSGlyph "C" with 4 layers>
			...

			# Access one glyph
			print(font.glyphs['A'])
			>> <GSGlyph "A" with 4 layers>

			# Access a glyph by character (new in v2.4.1)
			print(font.glyphs['Ư'])
			>> <GSGlyph "Uhorn" with 4 layers>

			# Access a glyph by unicode (new in v2.4.1)
			print(font.glyphs['01AF'])
			>> <GSGlyph "Uhorn" with 4 layers>

			# Access a glyph by index
			print(font.glyphs[145])
			>> <GSGlyph "Uhorn" with 4 layers>

			# Add a glyph
			font.glyphs.append(GSGlyph('adieresis'))

			# Duplicate a glyph under a different name
			newGlyph = font.glyphs['A'].copy()
			newGlyph.name = 'A.alt'
			font.glyphs.append(newGlyph)

			# Delete a glyph
			del font.glyphs['A.alt']
