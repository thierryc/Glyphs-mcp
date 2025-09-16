.. attribute:: layers
		The layers of the glyph, collection of :class:`GSLayer` objects. You can access them either by index or by layer ID, which can be a :attr:`GSFontMaster.id`.
		The layer IDs are usually a unique string chosen by Glyphs.app and not set manually. They may look like this: 3B85FBE0-2D2B-4203-8F3D-7112D42D745E

		:type: list, dict

		.. code-block:: python
			# get active layer
			layer = font.selectedLayers[0]

			# get glyph of this layer
			glyph = layer.parent

			# access all layers of this glyph
			for layer in glyph.layers:
			    print(layer.name)

			# access layer of currently selected master of active glyph ...
			# (also use this to access a specific layer of glyphs selected in the Font View)
			layer = glyph.layers[font.selectedFontMaster.id]

			# directly access 'Bold' layer of active glyph
			for master in font.masters:
			    if master.name == 'Bold':
			        id = master.id
			        break
			layer = glyph.layers[id]

			# add a new layer
			newLayer = GSLayer()
			newLayer.name = '{125, 100}' # (example for glyph-level intermediate master)
			# you may set the master ID that this layer will be associated with, otherwise the first master will be used
			newLayer.associatedMasterId = font.masters[-1].id # attach to last master
			font.glyphs['a'].layers.append(newLayer)

			# duplicate a layer under a different name
			newLayer = font.glyphs['a'].layers[0].copy()
			newLayer.name = 'Copy of layer'
			# FYI, this will still be the old layer ID (in case of duplicating) at this point
			print(newLayer.layerId)
			font.glyphs['a'].layers.append(newLayer)
			# FYI, the layer will have been assigned a new layer ID by now, after having been appended
			print(newLayer.layerId)

			# replace the second master layer with another layer
			newLayer = GSLayer()
			newLayer.layerId = font.masters[1].id # Make sure to sync the master layer ID
			font.glyphs['a'].layers[font.masters[1].id] = newLayer

			# delete last layer of glyph
			# (Also works for master layers. They will be emptied)
			del font.glyphs['a'].layers[-1]

			# delete currently active layer
			del font.glyphs['a'].layers[font.selectedLayers[0].layerId]
