.. attribute:: bounds
		Bounding box of the path, read-only

		:type: NSRect

		.. code-block:: python
			path = layer.paths[0] # first path

			# origin
			print(path.bounds.origin.x, path.bounds.origin.y)

			# size
			print(path.bounds.size.width, path.bounds.size.height)
