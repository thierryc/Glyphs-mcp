.. attribute:: numbers
		The numbers. A list of :class:`GSMetric` objects. For each number, there is a metricsValue in the masters, linked by the `id`.

		:type: list, dict

		.. code-block:: python
			print(font.numbers[0].name)

			# add a number
			number = GSMetric()
			number.horizontal = False # or True
			number.name = "Some Name"
			font.numbers.append(number)
			master.numbers[number.name] = 123
