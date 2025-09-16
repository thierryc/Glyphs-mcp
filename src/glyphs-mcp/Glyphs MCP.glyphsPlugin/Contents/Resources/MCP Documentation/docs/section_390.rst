.. attribute:: userData
		A dictionary to store user data. Use a unique key and only use objects that can be stored in a property list (string, list, dict, numbers, NSData) otherwise the data will not be recoverable from the saved file.

		:type: dict

		.. code-block:: python
			# set value
			component.userData['rememberToMakeCoffee'] = True

			# delete value
			del component.userData['rememberToMakeCoffee']

		.. versionadded:: 2.5
