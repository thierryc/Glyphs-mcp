.. attribute:: name
		a optional name

		:type: str

	.. attribute:: selected
		Selection state of guide in UI.

		:type: bool

		.. code-block:: python
			# select guide
			layer.guides[0].selected = True

			# print(selection state)
			print(layer.guides[0].selected)
