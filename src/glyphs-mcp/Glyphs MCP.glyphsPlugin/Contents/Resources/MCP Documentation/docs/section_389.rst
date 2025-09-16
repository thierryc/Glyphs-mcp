.. attribute:: bezierPath
		The component as an NSBezierPath object. Useful for drawing glyphs in plugins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.components[0].bezierPath.fill()
