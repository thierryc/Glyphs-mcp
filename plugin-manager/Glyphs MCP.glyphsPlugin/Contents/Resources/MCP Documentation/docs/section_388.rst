.. attribute:: smartComponentValues
		Dictionary of interpolations values of the Smart Component. Key are the axis.id, values are between the top and the bottom value of the corresponding :class:`GSSmartComponentAxis` objects. Corresponds to the values of the ‘Smart Component Settings’ dialog. Returns None if the component is not a Smart Component.

		For newly setup smart glyphs, the axis.id is a random string. After saving and re-opening the file, the name and id is the same. As long as you don't change the name. So it is saver to always go through the smart glyphs > axis > id (as explained in the code sample below.

		Also see https://glyphsapp.com/tutorials/smart-components for reference.

		:type: dict, int

		.. code-block:: python

			component = glyph.layers[0].shapes[1]
			widthAxis = component.component.smartComponentAxes['Width']  # get the width axis from the smart glyph
			components.smartComponentValues[widthAxis.id] = 45

			# Check whether a component is a smart component
			for component in layer.components:
			    if component.smartComponentValues is not None:
			        # do stuff
