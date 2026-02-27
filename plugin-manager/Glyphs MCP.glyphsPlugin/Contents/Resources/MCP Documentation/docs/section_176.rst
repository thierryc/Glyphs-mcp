.. attribute:: externalAxesValues
		List of floats specifying the positions for each axis for the user facing values

		:type: list

		.. code-block:: python
			# setting a value for a specific axis
			instance.externalAxesValues[2] = 12
			# or more precisely
			instance.externalAxesValues[axis.axisId] = 12
			# setting all values at once
			instance.externalAxesValues = [100, 12, 3.5]

		.. versionadded:: 3.2
