.. attribute:: shapes
		List of :class:`GSShape` objects. That are most likely :class:`GSPath` or :class:`GSComponent`

		:type: list

		.. code-block:: python
			# access all shapes
			for shape in layer.shapes:
			    print(shape)

			# delete shape
			del layer.shapes[0]

			# copy shapes from another layer
			import copy
			layer.shapes = copy.copy(anotherlayer.shapes)
