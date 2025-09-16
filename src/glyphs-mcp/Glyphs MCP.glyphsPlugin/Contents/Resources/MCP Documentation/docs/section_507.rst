.. attribute:: previewInstances
		Instances to show in the Preview area.

		Values are ``'live'`` for the preview of the current content of the Edit view, ``'all'`` for interpolations of all instances of the current glyph, or individual GSInstance objects.

		:type: string/GSInstance

		.. code-block:: python
			# Live preview of Edit view
			font.currentTab.previewInstances = 'live'

			# Text of Edit view shown in particular Instance interpolation (last defined instance)
			font.currentTab.previewInstances = font.instances[-1]

			# All instances of interpolation
			font.currentTab.previewInstances = 'all'
