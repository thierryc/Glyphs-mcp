.. attribute:: axes

		Collection of :class:`GSAxis`:

		.. code-block:: python
			for axis in font.axes:
			    print(axis)

			# to add a new axis
			axis = GSAxis()
			axis.name = "Some custom Axis"
			axis.axisTag = "SCAX"
			glyph.axes.append(axis)

			# to delete an axis
			del glyph.axes[0]

						glyph.axes.remove(someAxis)

		:type: list

		.. versionadded:: 4
