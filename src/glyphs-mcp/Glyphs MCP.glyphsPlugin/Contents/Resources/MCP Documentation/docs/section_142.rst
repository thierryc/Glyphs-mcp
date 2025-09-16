.. attribute:: internalAxesValues
		List of floats specifying the positions for each axis

		:type: list

		.. code-block:: python
			# setting a value for a specific axis
			master.internalAxesValues[2] = 12
			# or more precisely
			master.internalAxesValues[axis.axisId] = 12
			# setting all values at once
			master.internalAxesValues = [100, 12, 3.5]

		.. versionadded:: 3.2
