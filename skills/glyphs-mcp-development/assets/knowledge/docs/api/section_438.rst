.. attribute:: bezierPath
		The same path as an NSBezierPath object. Useful for drawing glyphs in plugins.

		:type: NSBezierPath

		.. code-block:: python
			# draw the path into the Edit view
			NSColor.redColor().set()
			layer.paths[0].bezierPath.fill()

	**Functions**

	.. function:: reverse()

		Reverses the path direction
