.. attribute:: openBezierPath
		Returns the open paths of the component as bezier path, already transformed. Useful for drawing glyphs in plugins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.components[0].openBezierPath.stroke()
