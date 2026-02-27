.. attribute:: attributes
		path attributes like :samp:`fill`, :samp:`mask`, :samp:`strokeWidth`, :samp:`strokeHeight`, :samp:`strokeColor'`, :samp:`strokePos`

		.. code-block:: python

			# in B/W layers:
			path.attributes['fill'] = True
			path.attributes['mask'] = True
			path.attributes['strokeWidth'] = 100
			path.attributes['strokeHeight'] = 80

			# in color layers:
			path.attributes['strokeColor'] = NSColor.redColor()
			path.attributes['fillColor'] = NSColor.blueColor()
			path.attributes['strokePos'] = 1 # or 0, -1

		:type: dict
