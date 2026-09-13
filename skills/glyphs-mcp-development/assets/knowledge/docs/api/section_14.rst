.. attribute:: colorDefaults
		Access to default settings cast to a color.

		:type: NSColor

		.. code-block:: python
			color = Glyphs.colorDefaults["GSColorCanvas"]
			color.set()
			NSBezierPath.fillRect_(rect)
