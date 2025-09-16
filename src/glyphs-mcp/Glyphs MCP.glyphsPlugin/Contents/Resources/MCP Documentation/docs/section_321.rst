.. attribute:: paths
		List of :class:`GSPath` objects. This is only a helper proxy to iterate all paths (without components). To add/remove items, use :attr:`GSLayer.shapes`.

		:type: list

		.. code-block:: python
			# access all paths
			for path in layer.paths:
			    print(path)
