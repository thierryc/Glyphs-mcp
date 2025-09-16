.. attribute:: segments
		A list of segments as NSPoint objects. Two objects represent a line, four represent a curve. Start point of the segment is included.

		:type: list

		.. code-block:: python
			# access all segments
			for path in layer.paths:
			    for segment in path.segments:
			        print(segment)
