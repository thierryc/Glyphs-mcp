.. function:: cutBetweenPoints(Point1, Point2)

		Cuts all paths that intersect the line from Point1 to Point2

		:param Point1: one point
		:param Point2: the other point

		.. code-block:: python
			# cut glyph in half horizontally at y=100
			layer.cutBetweenPoints(NSPoint(0, 100), NSPoint(layer.width, 100))
