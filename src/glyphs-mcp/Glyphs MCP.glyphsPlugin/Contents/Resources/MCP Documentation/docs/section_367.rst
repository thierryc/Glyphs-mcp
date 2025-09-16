.. attribute:: position
		The position of the anchor

		:type: NSPoint

		.. code-block:: python
			# read position
			print(layer.anchors['top'].position.x, layer.anchors['top'].position.y)

			# set position
			layer.anchors['top'].position = NSPoint(175, 575)

			# increase vertical position by 50 units
			layer.anchors['top'].position = NSPoint(layer.anchors['top'].position.x, layer.anchors['top'].position.y + 50)
