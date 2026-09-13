.. function:: scaleHeightToEmUnits

		Scale the image’s cropped height to a certain em unit value, retaining its aspect ratio.

		.. code-block:: python
			# position image’s origin at descender line
			layer.backgroundImage.position = NSPoint(0, font.masters[0].descender)

			# scale image to UPM value
			layer.backgroundImage.scaleHeightToEmUnits(font.upm)
