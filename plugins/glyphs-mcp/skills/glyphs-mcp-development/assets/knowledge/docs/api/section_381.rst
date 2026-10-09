.. attribute:: openBezierPath
		All open paths of the layer as an NSBezierPath object. Useful for drawing glyphs as outlines in plug-ins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.openBezierPath.stroke()
