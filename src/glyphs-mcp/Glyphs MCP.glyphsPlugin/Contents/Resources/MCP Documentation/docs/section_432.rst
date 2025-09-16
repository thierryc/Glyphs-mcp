.. attribute:: bounds
		Bounding box of the segment as NSRect. Read-only.

		:type: NSRect

		.. code-block:: python
			bounds = segment.bounds
			# origin
			print(bounds.origin.x, bounds.origin.y)

			# size
			print(bounds.size.width, bounds.size.height)
