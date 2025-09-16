.. attribute:: scale
		Scale factor of image.

		A scale factor of 1.0 (100%) means that 1 font unit is equal to 1 point.

		Set the scale factor for x and y scale simultaneously with an integer or a float value. For separate scale factors, please use a tuple.

		:type: tuple, NSPoint

		.. code-block:: python
			# change scale
			layer.backgroundImage.scale = 1.2 # changes x and y to 120%
			layer.backgroundImage.scale = (1.1, 1.2) # changes x to 110% and y to 120%
