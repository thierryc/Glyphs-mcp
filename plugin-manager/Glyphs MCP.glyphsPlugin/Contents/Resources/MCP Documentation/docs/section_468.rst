.. attribute:: tempData
		A dictionary to store data temporarily. Use a unique key. This will not be saved to file. (If you need the data persistent, use hint.settings() (not documented, yet))

		:type: dict

		.. code-block:: python
			# set value
			hint.tempData['rememberToMakeCoffee'] = True

			# delete value
			del hint.tempData['rememberToMakeCoffee']
