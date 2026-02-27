.. attribute:: hints
		List of :class:`GSHint` objects.

		:type: list

		.. code-block:: python
			# access all hints
			for hint in layer.hints:
			    print(hint)

			# add a new hint
			newHint = GSHint()
			# change behaviour of hint here, like its attachment nodes
			layer.hints.append(newHint)

			# delete hint
			del layer.hints[0]

			# copy hints from another layer
			import copy
			layer.hints = copy.copy(anotherlayer.hints)
			# remember to reconnect the hints’ nodes with the new layer’s nodes
