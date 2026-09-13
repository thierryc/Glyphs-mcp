.. attribute:: active

		:type: bool

		.. versionadded:: 2.5

	**Functions**

	.. function:: update()

		Calls the automatic feature code generator for this feature.
		You can use this to update all OpenType features before export.

		.. code-block:: python
			# first update all features
			for feature in font.features:
			    if feature.automatic:
			        feature.update()

			# then export fonts
			for instance in font.instances:
			    if instance.active:
			        instance.generate()
