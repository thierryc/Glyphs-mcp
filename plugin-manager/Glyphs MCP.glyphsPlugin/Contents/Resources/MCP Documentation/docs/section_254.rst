.. attribute:: tempData
		A dictionary to store data temporarily. Use a unique key. This will not be saved to file. If you need the data persistent, use feature.userData

		:type: dict

		.. code-block:: python
			# set value
			feature.tempData['rememberToMakeCoffee'] = True

			# delete value
			del feature.tempData['rememberToMakeCoffee']
