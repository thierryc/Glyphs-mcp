.. function:: applyTransform(transform)

		Apply a transformation matrix to the layer.

		.. code-block:: python
			layer.applyTransform([
			    0.5, # x scale factor
			    0.0, # x skew factor
			    0.0, # y skew factor
			    0.5, # y scale factor
			    0.0, # x position
			    0.0  # y position
			])

			from Foundation import NSAffineTransform, NSMidX, NSMidY
			bounds = Layer.bounds
			transform = NSAffineTransform.new()
			transform.translateXBy_yBy_(NSMidX(bounds), NSMidY(bounds))
			transform.rotateByDegrees_(-30)
			transform.translateXBy_yBy_(-NSMidX(bounds), -NSMidY(bounds))
			Layer.applyTransform(transform)

		:param transform: a list of 6 numbers, a NSAffineTransform or a NSAffineTransformStruct
