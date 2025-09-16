.. attribute:: transform
		Transformation matrix of the component.
		If Glyphs 3, this is computed from the scale, rotation and position.

		:type: NSAffineTransformStruct

		.. code-block:: python
			component.transform = ((
			    0.5, # x scale factor
			    0.0, # x skew factor
			    0.0, # y skew factor
			    0.5, # y scale factor
			    0.0, # x position
			    0.0  # y position
			))
