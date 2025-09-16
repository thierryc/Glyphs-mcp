.. attribute:: guides
		List of :class:`GSGuide` objects.

		:type: list

		.. code-block:: python
			# access all guides
			for guide in layer.guides:
			    print(guide)

			# add guide
			newGuide = GSGuide()
			newGuide.position = NSPoint(100, 100)
			newGuide.angle = -10.0
			layer.guides.append(newGuide)

			# delete guide
			del layer.guides[0]

			# copy guides from another layer
			import copy
			layer.guides = copy.copy(anotherlayer.guides)
