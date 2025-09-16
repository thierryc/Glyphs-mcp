.. attribute:: completeBezierPath
		The layer as an NSBezierPath object including paths from components. Useful for drawing glyphs in plug-ins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.completeBezierPath.fill()
