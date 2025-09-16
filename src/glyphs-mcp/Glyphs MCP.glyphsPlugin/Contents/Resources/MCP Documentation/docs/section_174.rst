.. attribute:: axes
		List of floats specifying the positions for each axis

		:type: list

		.. code-block:: python
			# setting a value for a specific axis
			instance.axes[2] = 12
			# setting all values at once
			instance.axes = [100, 12, 3.5] # make sure that the count of numbers matches the count of axes

		.. versionadded:: 2.5.2
		.. deprecated:: 3.2
