.. attribute:: layerId
		The unique layer ID is used to access the layer in the :class:`glyphs <GSGlyph>` layer dictionary.

		For master layers this should be the id of the :class:`fontMaster <GSFontMaster>`.
		It could look like this: :samp:`FBCA074D-FCF3-427E-A700-7E318A949AE5`

		:type: str

		.. code-block:: python
			# see ID of active layer
			id = font.selectedLayers[0].layerId
			print(id)
			>> FBCA074D-FCF3-427E-A700-7E318A949AE5

			# access a layer by this ID
			layer = font.glyphs["a"].layers[id]
			layer = font.glyphs["a"].layers['FBCA074D-FCF3-427E-A700-7E318A949AE5']

			# for master layers, use ID of masters
			layer = font.glyphs["a"].layers[font.masters[0].id]
