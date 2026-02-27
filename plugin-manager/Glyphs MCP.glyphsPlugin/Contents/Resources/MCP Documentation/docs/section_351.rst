.. attribute:: smartComponentPoleMapping
		Maps this layer to the poles on the interpolation axes of the Smart Glyph. The dictionary keys are the names of the :class:`GSSmartComponentAxis` objects. The values are 1 for bottom pole and 2 for top pole. Corresponds to the 'Layers' tab of the glyph’s ‘Show Smart Glyph Settings’ dialog.

		Also see https://glyphsapp.com/tutorials/smart-components for reference.

		:type: dict, int

		.. code-block:: python
			# Map layers to top and bottom poles:
			crotchDepthAxis = glyph.smartComponentAxes['crotchDepth']
			shoulderWidthAxis = glyph.smartComponentAxes['shoulderWidth']

			for layer in glyph.layers:

			    # Regular layer
			    if layer.name == 'Regular':
			        layer.smartComponentPoleMapping[crotchDepthAxis.id] = 2
			        layer.smartComponentPoleMapping[shoulderWidthAxis.id] = 2

			    # NarrowShoulder layer
			    elif layer.name == 'NarrowShoulder':
			        layer.smartComponentPoleMapping[crotchDepthAxis.id] = 2
			        layer.smartComponentPoleMapping[shoulderWidthAxis.id] = 1

			    # LowCrotch layer
			    elif layer.name == 'LowCrotch':
			        layer.smartComponentPoleMapping[crotchDepthAxis.id] = 1
			        layer.smartComponentPoleMapping[shoulderWidthAxis.id] = 2


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

		:rtype: string

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
