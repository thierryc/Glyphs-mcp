.. attribute:: anchors
		List of :class:`GSAnchor` objects.

		:type: list, dict

		.. code-block:: python
			# access all anchors:
			for a in layer.anchors:
			    print(a)

			# add a new anchor
			layer.anchors['top'] = GSAnchor()

			# delete anchor
			del layer.anchors['top']

			# copy anchors from another layer
			import copy
			layer.anchors = copy.copy(anotherlayer.anchors)
