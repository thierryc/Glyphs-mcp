.. attribute:: smartComponentValues
		Dictionary of interpolation values of the Smart Component. Keys are the ``axisId`` of the :class:`GSAxis` objects in the smart glyph’s :attr:`GSGlyph.axes` (or the font’s :attr:`GSFont.axes`). Corresponds to the values of the ‘Smart Component Settings’ dialog. Returns None if the component is not a Smart Component.

		For newly setup smart glyphs, the axis.axisId is a random string. After saving and re-opening the file, the name and axisId stay the same, as long as you don't change the name. So it is safer to always go through the smart glyph > axis > axisId (as explained in the code sample below).

		Also see https://glyphsapp.com/learn/smart-components for reference.

		:type: dict, int

		.. code-block:: python

			component = glyph.layers[0].shapes[1]
			widthAxis = component.component.axes[0]  # get the width axis from the smart glyph
			component.smartComponentValues[widthAxis.axisId] = 45

			# Check whether a component is a smart component
			for component in layer.components:
			    if component.smartComponentValues is not None:
			        # do stuff
