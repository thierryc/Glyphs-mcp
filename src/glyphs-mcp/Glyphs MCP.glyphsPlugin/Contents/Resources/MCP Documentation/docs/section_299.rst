.. attribute:: smartComponentAxes
		A list of :class:`GSSmartComponentAxis` objects.

		These are the axis definitions for the interpolations that take place within the Smart Components. Corresponds to the ‘Properties’ tab of the glyph’s ‘Show Smart Glyph Settings’ dialog.

		Also see https://glyphsapp.com/tutorials/smart-components for reference.

		:type: list

		.. code-block:: python
			# Adding two interpolation axes to the glyph

			axis1 = GSSmartComponentAxis()
			axis1.name = 'crotchDepth'
			axis1.topValue = 0
			axis1.bottomValue = -100
			g.smartComponentAxes.append(axis1)

			axis2 = GSSmartComponentAxis()
			axis2.name = 'shoulderWidth'
			axis2.topValue = 100
			axis2.bottomValue = 0
			g.smartComponentAxes.append(axis2)

			# Deleting one axis
			del g.smartComponentAxes[1]
