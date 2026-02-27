.. attribute:: components
		Collection of :class:`GSComponent` objects. This is only a helper proxy to iterate all components (without paths). To add/remove items, use :attr:`GSLayer.shapes`.

		:type: list

		.. code-block:: python
			for component in layer.components:
			    print(component)
