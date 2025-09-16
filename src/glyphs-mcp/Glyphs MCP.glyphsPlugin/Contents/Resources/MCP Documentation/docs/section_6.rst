.. attribute:: fonts
		Be aware that the order is defined by last used font. Append and extend generally don't insert at the end of the list.

		:type: list

		.. code-block:: python
			# access all open fonts
			for font in Glyphs.fonts:
			    print(font.familyName)

			# add a font
			font = GSFont()
			font.familyName = "My New Font"
			Glyphs.fonts.append(font)
