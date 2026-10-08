.. attribute:: completeOpenBezierPath
		All open paths of the layer as an NSBezierPath object including paths from components. Useful for drawing glyphs as outlines in plugins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.completeOpenBezierPath.stroke()
