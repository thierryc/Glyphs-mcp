.. attribute:: id
		Used to identify :class:`Layers` in the Glyph

		see :attr:`GSGlyph.layers`

		:type: str

		.. code-block:: python
			# ID of first master
			print(font.masters[0].id)
			>> 3B85FBE0-2D2B-4203-8F3D-7112D42D745E

			# use this master to access the glyph’s corresponding layer
			print(glyph.layers[font.masters[0].id])
			>> <GSLayer "Light" (A)>
