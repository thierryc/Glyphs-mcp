.. attribute:: bounds
		Bounding box of the component, read-only

		:type: NSRect

		.. code-block:: python
			component = layer.components[0] # first component

			# origin
			print(component.bounds.origin.x, component.bounds.origin.y)

			# size
			print(component.bounds.size.width, component.bounds.size.height)
