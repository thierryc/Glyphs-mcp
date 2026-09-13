.. attribute:: colorObject
		NSColor object of layer color, useful for drawing in plugins.

		:type: NSColor

		.. code-block:: python
			# use layer color to draw the outline
			layer.colorObject.set()

			# Get RGB (and alpha) values (as float numbers 0..1, multiply with 256 if necessary)
			R, G, B, A = layer.colorObject.colorUsingColorSpace_(NSColorSpace.genericRGBColorSpace()).getRed_green_blue_alpha_(None, None, None, None)

			print(R, G, B)
			>> 0.617805719376 0.958198726177 0.309286683798

			print(round(R * 256), int(G * 256), int(B * 256))
			>> 158 245 245

			# Draw layer
			layer.bezierPath.fill()

			# set the layer color.
			layer.colorObject = NSColor.colorWithDeviceRed_green_blue_alpha_(247.0 / 255.0, 74.0 / 255.0, 62.9 / 255.0, 1)
