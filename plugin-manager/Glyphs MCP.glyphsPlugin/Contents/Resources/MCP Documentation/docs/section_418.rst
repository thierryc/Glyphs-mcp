.. function:: applyTransform

		Apply a transformation matrix to the component.

		.. code-block:: python
			component = layer.components[0]

			component.applyTransform((
			    0.5, # x scale factor
			    0.0, # x skew factor
			    0.0, # y skew factor
			    0.5, # y scale factor
			    0.0, # x position
			    0.0  # y position
			))

	.. function:: copy()

		Returns a full copy of the component
