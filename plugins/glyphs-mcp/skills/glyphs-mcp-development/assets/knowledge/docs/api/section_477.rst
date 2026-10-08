.. attribute:: userData
		A dictionary to store user data. Use a unique key and only use objects that can be stored in a property list (string, list, dict, numbers, NSData) otherwise the data will not be recoverable from the saved file.

		:type: dict

		.. code-block:: python
			# set value
			node.userData['rememberToMakeCoffee'] = True

			# delete value
			del node.userData['rememberToMakeCoffee']

		.. versionadded:: 2.4.1

	**Functions**

	.. function:: copy()

		Returns a full copy of the node

	.. function:: makeNodeFirst()

		Turn this node into the start point of the path.

	.. function:: toggleConnection()

		Toggle between sharp and smooth connections.
