.. attribute:: instances
		Collection of :class:`GSInstance` objects.

		.. code-block:: python
			for instance in font.instances:
			    print(instance)

			# to add a new instance
			instance = GSInstance()
			instance.name = "Some Instance"
			font.instances.append(instance)

			# to delete an instances
			del font.instances[0]

			font.instances.remove(someInstance)

		:type: list
