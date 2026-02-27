.. attribute:: layers
		Alternatively, you can set (and read) a list of :class:`GSLayer` objects. These can be any of the layers of a glyph.

		:type: list

		.. code-block:: python
			layers = []

			# display all layers of one glyph next to each other
			for layer in font.glyphs['a'].layers:
			    layers.append(layer)

			# append line break
			layers.append(GSControlLayer(10)) # 10 being the ASCII code of the new line character (\n)

			font.tabs[0].layers = layers
