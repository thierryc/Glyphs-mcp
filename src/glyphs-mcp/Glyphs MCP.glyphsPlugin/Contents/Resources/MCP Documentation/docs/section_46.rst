.. attribute:: axes
		Collection of :class:`GSAxis`:

		.. code-block:: python
			for axis in font.axes:
			    print(axis)

			# to add a new axis
			axis = GSAxis()
			axis.name = "Some custom Axis"
			axis.axisTag = "SCAX"
			font.axes.append(axis)

			# to delete an axis
			del font.axes[0]

			font.axes.remove(someAxis)

		:type: list

		.. versionadded:: 2.5
		.. versionchanged:: 3
