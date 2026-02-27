.. attribute:: crop
		Crop rectangle. This is relative to the image size in pixels, not the font’s em units (just in case the image is scaled to something other than 100%).

		:type: :class:`NSRect`

		.. code-block:: python
			# change cropping
			layer.backgroundImage.crop = NSRect(NSPoint(0, 0), NSPoint(1200, 1200))
