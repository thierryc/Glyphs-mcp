.. attribute:: backgroundImage
		The background image. It will be scaled so that 1 em unit equals 1 of the image’s pixels.

		:type: :class:`GSBackgroundImage`

		.. code-block:: python
			# set background image
			layer.backgroundImage = GSBackgroundImage('/path/to/file.jpg')

			# remove background image
			layer.backgroundImage = None
