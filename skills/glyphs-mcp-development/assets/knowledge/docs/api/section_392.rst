.. attribute:: tempData
		A dictionary to store data temporarily. Use a unique key. This will not be saved to file. If you need the data persistent, use layer.userData

		:type: dict

		.. code-block:: python
			# set value
			layer.tempData['rememberToMakeCoffee'] = True

			# delete value
			del layer.tempData['rememberToMakeCoffee']
