.. attribute:: customParameters
		The custom parameters. List of :class:`GSCustomParameter` objects. You can access them by name or by index.

		:type: list, dict

		.. code-block:: python
			# access all parameters
			for parameter in font.instances[0].customParameters:
			    print(parameter)

			# set a parameter
			font.instances[0].customParameters['hheaLineGap'] = 10

			# add multiple parameters:
			parameter = GSCustomParameter("Name Table Entry", "1 1;"font name")
			font.customParameters.append(parameter)
			parameter = GSCustomParameter("Name Table Entry", "2 1;"style name")
			font.customParameters.append(parameter)

			# delete a parameter
			del font.instances[0].customParameters['hheaLineGap']
