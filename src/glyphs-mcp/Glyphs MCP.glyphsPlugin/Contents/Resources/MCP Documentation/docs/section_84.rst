.. attribute:: userData
		A dictionary to store user data. Use a unique key and only use objects that can be stored in a property list (string, list, dict, numbers, NSData) otherwise the data will not be recoverable from the saved file.

		:type: dict

		.. code-block:: python
			# set value
			font.userData['rememberToMakeCoffee'] = True

			# delete value
			del font.userData['rememberToMakeCoffee']
