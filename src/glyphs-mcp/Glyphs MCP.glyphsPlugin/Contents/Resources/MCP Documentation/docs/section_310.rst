.. attribute:: associatedMasterId
		The ID of the :class:`fontMaster <GSFontMaster>` this layer belongs to, in case this isn't a master layer. Every layer that isn't a master layer needs to be attached to one master layer.

		.. code-block:: python
			# add a new layer
			newLayer = GSLayer()
			newLayer.name = '{125, 100}' # (example for glyph-level intermediate master)

			# you may set the master ID that this layer will be associated with, otherwise the first master will be used
			newLayer.associatedMasterId = font.masters[-1].id # attach to last master
			font.glyphs['a'].layers.append(newLayer)

		:type: str
