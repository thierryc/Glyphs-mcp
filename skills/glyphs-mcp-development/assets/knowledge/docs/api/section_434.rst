.. attribute:: bezierPath
		Returns the closed paths of the component as bezier path, already transformed. Useful for drawing glyphs in plugins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.components[0].bezierPath.fill()
