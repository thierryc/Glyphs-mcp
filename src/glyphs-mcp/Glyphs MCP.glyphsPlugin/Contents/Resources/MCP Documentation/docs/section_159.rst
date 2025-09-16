.. attribute:: customParameters
		The custom parameters. List of :class:`GSCustomParameter` objects. You can access them by name or by index.

		:type: list, dict

		.. code-block:: python
			# access all parameters
			for parameter in font.masters[0].customParameters:
			    print(parameter)

			# set a parameter
			font.masters[0].customParameters['underlinePosition'] = -135

			# add multiple parameters:
			parameter = GSCustomParameter("CJK Guide", 10)
			font.customParameters.append(parameter)
			parameter = GSCustomParameter("CJK Guide", 20)
			font.customParameters.append(parameter)

			# delete a parameter
			del font.masters[0].customParameters['underlinePosition']

	**Functions**

	.. function:: copy()

		Returns a full copy of the master
