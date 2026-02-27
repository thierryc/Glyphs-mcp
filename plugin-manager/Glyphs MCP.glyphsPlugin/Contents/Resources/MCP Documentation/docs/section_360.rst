.. function:: intersectionsBetweenPoints(Point1, Point2, components=False)

		Return all intersection points between a measurement line and the paths in the layer. This is basically identical to the measurement tool in the UI.

		Normally, the first returned point is the starting point, the last returned point is the end point. Thus, the second point is the first intersection, the second last point is the last intersection.

		:param Point1: one point
		:param Point2: the other point
		:param components: if components should be measured. Default: False
		:param ignoreLocked: ignore locked or unfocused paths. Default: False

		.. code-block:: python
			# show all intersections with glyph at y=100
			intersections = layer.intersectionsBetweenPoints((-1000, 100), (layer.width+1000, 100))
			print(intersections)

			# left sidebearing at measurement line
			print(intersections[1].x)

			# right sidebearing at measurement line
			print(layer.width - intersections[-2].x)
