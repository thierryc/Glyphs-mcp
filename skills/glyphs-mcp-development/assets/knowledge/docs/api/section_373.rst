**Functions**

	.. function:: copy()

		Returns a full copy of the layer

	.. function:: decomposeComponents()

		Decomposes all components of the layer at once.

	.. function:: decomposeCorners()

		Decomposes all corners of the layer at once.

		.. versionadded:: 2.4

	.. function:: compareString()

		Returns a string representing the outline structure of the glyph, for compatibility comparison.

		:return: The comparison string

		:rtype: str

		.. code-block:: python

			print(layer.compareString())
			>> oocoocoocoocooc_oocoocoocloocoocoocoocoocoocoocoocooc_

	.. function:: connectAllOpenPaths()

		Closes all open paths when end points are further than 1 unit away from each other.


	.. function:: copyDecomposedLayer()

		Returns a copy of the layer with all components decomposed.

		:return: A new layer object

		:rtype: :class:`GSLayer`

	.. function:: syncMetrics()

		Take over LSB and RSB from linked glyph.

		.. code-block:: python
			# sync metrics of all layers of this glyph
			for layer in glyph.layers:
			    layer.syncMetrics()

	.. function:: correctPathDirection()

		Corrects the path direction.
