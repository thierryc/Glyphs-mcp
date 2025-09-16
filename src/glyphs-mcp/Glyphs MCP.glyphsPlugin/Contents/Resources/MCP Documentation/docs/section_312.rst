.. attribute:: attributes
		layer attributes like :samp:`axisRules`, :samp:`coordinates`, :samp:`colorPalette`, :samp:`sbixSize`, :samp:`color`, :samp:`svg`

		.. code-block:: python

			axis = font.axes[0]
			layer.attributes["axisRules"] = {axis.axisId: {'min': 100}}
			layer.attributes["coordinates"] = {axis.axisId: 99}
			layer.attributes["colorPalette"] = 2  # This makes the layer a CPAL layer for color index 2

		:type: dict
