.. attribute:: name
		The name of the anchor

		:type: str

	.. attribute:: selected
		Selection state of anchor in UI.

		.. code-block:: python
			# select anchor
			layer.anchors[0].selected = True

			# log selection state
			print(layer.anchors[0].selected)

		:type: bool

	.. attribute:: orientation
		If the position of the anchor is relative to the LSB (0), center (2) or RSB (1).

		:type: int
