.. attribute:: userData
		A dictionary to store user data. Use a unique key, and only use objects that can be stored in a property list (bool, string, list, dict, numbers, NSData), otherwise the data will not be recoverable from the saved file.

		:type: dict

		.. code-block:: python
			# set value
			font.masters[0].userData['rememberToMakeTea'] = True

			# delete value
			del font.masters[0].userData['rememberToMakeTea']
