.. attribute:: bounds
		Bounding box of whole glyph as NSRect. Read-only.

		:type: NSRect

		.. code-block:: python
			# origin
			print(layer.bounds.origin.x, layer.bounds.origin.y)

			# size
			print(layer.bounds.size.width, layer.bounds.size.height)
